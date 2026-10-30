"""Shared consent, state and access invariants. No capture or model mocks live here."""
from datetime import datetime, timedelta, timezone
from sqlalchemy import select, or_
from fastapi import HTTPException
from .models import Conversation, ParticipantConsent, Store, StoreMembership, User, AuditEvent, now

ADMIN_ROLES = {"owner", "admin"}
NOTICE_VERSION = "v1-2026-10-29"
NOTICE = (
    "This session records your conversation, transcribes it, and uses AI to suggest business findings and follow-ups. "
    "AI may be wrong. The operator and authorized store managers can review the recording and transcript; "
    "approved findings may be shared with authorized members of this store. No automatic external sharing or CRM action occurs. "
    "Audio retention and record retention are shown below. You can decline or withdraw using this link or tell the operator to stop. "
    "Withdrawal stops processing and restricts results; the operator can delete the session. Already downloaded exports cannot be recalled. "
    "Confirm only for yourself. This workflow does not verify your identity or prove that everyone present is listed."
)
ACTIVE = {"recording", "paused"}
TRANSITIONS = {
    "ready": ({"awaiting_consent", "draft", "interrupted"}, "ready"),
    "start": ({"ready"}, "recording"),
    "pause": ({"recording"}, "paused"),
    "resume": ({"paused"}, "recording"),
    "interrupt": ({"recording", "paused", "ready"}, "interrupted"),
    "stop": ({"recording", "paused", "ready"}, "finalizing"),
    "cancel": ({"draft", "awaiting_consent", "ready", "recording", "paused", "interrupted", "finalizing", "failed"}, "cancelled"),
}


def reject(code, message, status=409):
    raise HTTPException(status, detail={"code": code, "message": message})


def stores_for(db, user):
    query = select(Store).where(Store.org_id == user.org_id)
    if user.role not in ADMIN_ROLES:
        query = query.join(StoreMembership, StoreMembership.store_id == Store.id).where(StoreMembership.user_id == user.id)
    return list(db.scalars(query.order_by(Store.name)))


def scope(db, user, store_id=None):
    ids = [s.id for s in stores_for(db, user)]
    if store_id:
        if store_id not in ids:
            reject("STORE_NOT_FOUND", "Store not found or access is not assigned.", 404)
        return [store_id]
    return ids


def raw_allowed(db, user, conversation):
    return (conversation.org_id == user.org_id and conversation.store_id in scope(db, user)
            and (user.role in ADMIN_ROLES | {"manager"} or conversation.created_by == user.id))


def raw_filter(user):
    return True if user.role in ADMIN_ROLES | {"manager"} else Conversation.created_by == user.id


def consent_valid(db, conversation):
    participants = list(db.scalars(select(ParticipantConsent).where(ParticipantConsent.conversation_id == conversation.id,
        ParticipantConsent.version == conversation.consent_version)))
    return bool(participants) and all(p.status == "granted" and p.version == conversation.consent_version for p in participants)


def require_consent(db, conversation):
    if not consent_valid(db, conversation):
        reject("CONSENT_REQUIRED", "Every listed participant must confirm this session's current notice before capture or processing.")
    if conversation.session_state in {"cancelled", "deleted", "deletion_pending"}:
        reject("SESSION_CLOSED", "This session is closed.")


def transition(db, conversation, body, actor):
    if conversation.session_state != body.expected_state or conversation.consent_version != body.consent_version:
        reject("STATE_CONFLICT", "Session changed. Refresh its state before trying again.")
    origins, destination = TRANSITIONS[body.action]
    if conversation.session_state not in origins:
        reject("INVALID_TRANSITION", f"Cannot {body.action} a session in {conversation.session_state}.")
    if body.action in {"ready", "start", "resume", "stop"}:
        require_consent(db, conversation)
    if body.action in {"ready", "resume"}:
        if not body.conditions_confirmed:
            reject("CAPTURE_CONDITIONS_REQUIRED", "Revalidate the participant roster, source availability and visible recording indicator.")
        conversation.capture_conditions_confirmed = True
    if body.action == "start" and not conversation.capture_conditions_confirmed:
        reject("CAPTURE_CONDITIONS_REQUIRED", "Prepare the source and recording indicator first.")
    if body.action in {"start", "resume"}:
        duplicate = db.scalar(select(Conversation).where(Conversation.id != conversation.id,
            Conversation.org_id == conversation.org_id, Conversation.session_state.in_(ACTIVE),
            or_(Conversation.created_by == conversation.created_by,
                Conversation.device_id == conversation.device_id if conversation.device_id else False)))
        if duplicate:
            reject("CAPTURE_ALREADY_ACTIVE", "Stop or interrupt the other active capture before starting another.")
    if body.action in {"interrupt", "cancel"}:
        conversation.capture_conditions_confirmed = False
    conversation.session_state, conversation.state_updated_at = destination, now()
    db.add(AuditEvent(org_id=conversation.org_id, actor=actor.id, action="session." + body.action,
                      target_id=conversation.id, details={"state": destination, "consent_version": conversation.consent_version}))


def policy_for(settings, org):
    return {"raw_audio_hours": 24, "transcript_days": settings.retention_days,
            "derived_days": settings.retention_days, "consent_days": settings.retention_days, **(org.retention_policy or {})}


def create_participants(db, conversation, references):
    import secrets
    from .security import digest
    links = []
    for reference in references:
        token = secrets.token_urlsafe(32)
        row = ParticipantConsent(conversation_id=conversation.id, participant_ref=reference, token_hash=digest(token),
            token_expires_at=(datetime.now(timezone.utc) + timedelta(hours=24)).isoformat(), version=conversation.consent_version)
        db.add(row)
        db.flush()
        links.append({"id": row.id, "participant_ref": reference, "token": token})
    return links
