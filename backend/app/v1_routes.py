"""Consent-controlled session management, membership, review and approved exports."""
import csv
import io
from datetime import datetime, timedelta, timezone
from fastapi import Depends, Header, Request, Response
from sqlalchemy import delete, select
from sqlalchemy.exc import IntegrityError
from .models import (AudioFile, AuditEvent, AuthSession, Conversation, Device, Evidence, Insight, Organization,
    ParticipantConsent, ProcessingJob, ReviewEvent, Store, StoreMembership, Task, Transcript, UploadSession, User, now)
from .schemas import (CaptureHeartbeat, FindingReview, MemberCreate, MemberUpdate, ParticipantDecision, ParticipantList,
    RetentionPolicy, StoreCreate, TranscriptCorrection, Transition)
from .governance import (ADMIN_ROLES, NOTICE, NOTICE_VERSION, consent_valid, create_participants,
    policy_for, raw_allowed, reject, require_consent, scope, stores_for, transition)
from .security import digest, password_hash


def install_v1_routes(app, *, settings, factory, locks, pipeline, db_session, user_auth, admin_auth,
                      principal, owned, audit, record, conversation_json, insight_json, limiter):
    def reviewer(user=Depends(user_auth)):
        if user.role not in ADMIN_ROLES | {"manager"}:
            reject("REVIEWER_REQUIRED", "An administrator or assigned store manager must review this record.", 403)
        return user

    def member_json(db, user):
        return {**record(user, {"password_hash"}), "store_ids": scope(db, user)}

    @app.get("/api/v1/stores", tags=["Membership"])
    def stores(user=Depends(user_auth), db=Depends(db_session)):
        return [record(s) for s in stores_for(db, user)]

    @app.post("/api/v1/stores", status_code=201, tags=["Membership"])
    def add_store(body: StoreCreate, user=Depends(admin_auth), db=Depends(db_session)):
        row = Store(org_id=user.org_id, name=body.name.strip())
        db.add(row); db.flush(); audit(db, user, "store.created", row.id); db.commit()
        return record(row)

    @app.get("/api/v1/members", tags=["Membership"])
    def members(user=Depends(user_auth), db=Depends(db_session)):
        ids = scope(db, user)
        rows = db.scalars(select(User).where(User.org_id == user.org_id))
        return [member_json(db, u) for u in rows if user.role in ADMIN_ROLES or bool(set(ids) & set(scope(db, u)))]

    def validate_stores(db, actor, ids):
        if len(set(ids)) != len(ids) or not set(ids).issubset(scope(db, actor)):
            reject("INVALID_STORES", "Choose stores belonging to this organization.", 422)

    @app.post("/api/v1/members", status_code=201, tags=["Membership"])
    def add_member(body: MemberCreate, user=Depends(admin_auth), db=Depends(db_session)):
        validate_stores(db, user, body.store_ids)
        if body.role != "admin" and not body.store_ids:
            reject("STORE_REQUIRED", "Assign at least one store to managers and staff.", 422)
        row = User(org_id=user.org_id, email=body.email.lower().strip(), password_hash=password_hash(body.password), role=body.role)
        db.add(row)
        try:
            db.flush()
        except IntegrityError:
            db.rollback(); reject("ACCOUNT_UNAVAILABLE", "This email is unavailable.", 409)
        for sid in body.store_ids:
            db.add(StoreMembership(user_id=row.id, store_id=sid))
        audit(db, user, "member.created", row.id); db.commit()
        return member_json(db, row)

    @app.patch("/api/v1/members/{member_id}", tags=["Membership"])
    def edit_member(member_id: str, body: MemberUpdate, user=Depends(admin_auth), db=Depends(db_session)):
        row = owned(db, User, member_id, user)
        validate_stores(db, user, body.store_ids)
        if row.id == user.id or row.role == "owner":
            reject("PROTECTED_ADMIN", "Use another administrator for account changes; the owner cannot be demoted here.")
        if body.role != "admin" and body.active and not body.store_ids:
            reject("STORE_REQUIRED", "Assign at least one store.", 422)
        row.role, row.active = body.role, body.active
        db.execute(delete(StoreMembership).where(StoreMembership.user_id == row.id))
        for sid in body.store_ids:
            db.add(StoreMembership(user_id=row.id, store_id=sid))
        db.execute(delete(AuthSession).where(AuthSession.user_id == row.id))
        audit(db, user, "member.permissions_changed", row.id); db.commit()
        return member_json(db, row)

    def by_token(db, token):
        if not token or len(token) > 200:
            reject("CONSENT_LINK_INVALID", "Consent link is invalid.", 404)
        row = db.scalar(select(ParticipantConsent).where(ParticipantConsent.token_hash == digest(token)))
        if not row or (row.status == "pending" and row.token_expires_at < now()):
            reject("CONSENT_LINK_EXPIRED", "Consent link is invalid or expired. Ask the operator for a new link.", 410)
        return row, db.get(Conversation, row.conversation_id)

    @app.get("/api/v1/participant-consent", tags=["Participant consent"])
    def notice(x_consent_token: str = Header(default=""), db=Depends(db_session)):
        participant, conversation = by_token(db, x_consent_token)
        org = db.get(Organization, conversation.org_id)
        return {"organization": org.name, "store": db.get(Store, conversation.store_id).name,
            "purpose": conversation.purpose, "source": conversation.source_type, "notice": NOTICE,
            "notice_version": NOTICE_VERSION, "retention": policy_for(settings, org),
            "audio_retained": settings.retain_audio, "participant_ref": participant.participant_ref,
            "status": participant.status, "session_state": conversation.session_state,
            "processing_location": "explicitly configured cloud service" if settings.allow_cloud else "local computer"}

    def restrict(db, conversation, actor):
        conversation.session_state = "interrupted" if conversation.session_state in {"ready", "recording", "paused", "finalizing", "awaiting_consent"} else "needs_review"
        conversation.review_status = "restricted"
        conversation.capture_conditions_confirmed = False
        conversation.state_updated_at = now()
        job = db.scalar(select(ProcessingJob).where(ProcessingJob.conversation_id == conversation.id))
        if job:
            job.status, job.error_code, job.error_message, job.retryable = "cancelled", "CONSENT_WITHDRAWN", "Consent is no longer valid. Results are restricted.", False
            conversation.status = "restricted"
        for finding in db.scalars(select(Insight).where(Insight.conversation_id == conversation.id)):
            finding.review_status = "restricted"
        for task in db.scalars(select(Task).where(Task.conversation_id == conversation.id)):
            task.status = "dismissed"
        db.add(AuditEvent(org_id=conversation.org_id, actor=actor, action="consent.withdrawn", target_id=conversation.id))
        # Revoke playback immediately; Windows may defer removal of open files.
        from .cleanup import delete_uploads
        audio = db.scalar(select(AudioFile).where(AudioFile.conversation_id == conversation.id))
        if audio: audio.original_path = audio.normalized_path = None
        delete_uploads(settings.data_dir, conversation.id)

    @app.post("/api/v1/participant-consent", tags=["Participant consent"])
    def decide(body: ParticipantDecision, request: Request, x_consent_token: str = Header(default=""), db=Depends(db_session)):
        limiter.check("consent:" + request.client.host, 100)
        participant, conversation = by_token(db, x_consent_token)
        with locks[conversation.id]:
            db.refresh(participant); db.refresh(conversation)
            if body.decision == "grant":
                if participant.status in {"withdrawn", "declined"} or conversation.session_state in {"cancelled", "deleted"}:
                    reject("REVALIDATION_REQUIRED", "Ask the operator to prepare a new consent round.")
                participant.status, participant.granted_at = "granted", now()
                audit(db, type("Participant", (), {"id":"participant:" + participant.id,"org_id":conversation.org_id})(), "consent.granted", conversation.id)
            else:
                participant.status = "withdrawn" if body.decision == "withdraw" else "declined"
                participant.withdrawn_at = now()
                restrict(db, conversation, "participant:" + participant.id)
            db.commit()
            return {"status": participant.status, "session_state": conversation.session_state, "consent_valid": consent_valid(db, conversation)}

    @app.post("/api/v1/conversations/{cid}/participants", tags=["Participant consent"])
    def participants(cid: str, body: ParticipantList, user=Depends(user_auth), db=Depends(db_session)):
        conversation = owned(db, Conversation, cid, user)
        with locks[cid]:
            db.refresh(conversation)
            if conversation.session_state in {"recording", "paused", "processing", "approved", "cancelled", "deleted"}:
                reject("STOP_FIRST", "Stop capture or restrict the reviewed session before changing participants.")
            for prior in db.scalars(select(ParticipantConsent).where(ParticipantConsent.conversation_id == cid)):
                prior.status, prior.token_hash = "superseded", None
            conversation.consent_version += 1
            conversation.capture_conditions_confirmed = False
            if conversation.status == "awaiting_audio":
                conversation.session_state = "awaiting_consent"
            links = create_participants(db, conversation, body.participant_refs)
            audit(db, user, "consent.revalidation_requested", cid); db.commit()
            return {"participant_links": links, "consent_version": conversation.consent_version}

    @app.post("/api/v1/conversations/{cid}/withdraw-consent", tags=["Participant consent"])
    def withdraw(cid: str, user=Depends(user_auth), db=Depends(db_session)):
        conversation = owned(db, Conversation, cid, user)
        with locks[cid]:
            for participant in db.scalars(select(ParticipantConsent).where(ParticipantConsent.conversation_id == cid)):
                participant.status, participant.withdrawn_at = "withdrawn", now()
            restrict(db, conversation, user.id); db.commit()
        return {"status": "restricted", "message": "Capture must stop. Results are restricted; downloaded exports cannot be recalled."}

    @app.post("/api/v1/conversations/{cid}/transition", tags=["Session lifecycle"])
    def session_transition(cid: str, body: Transition, actor=Depends(principal), db=Depends(db_session)):
        conversation = owned(db, Conversation, cid, actor)
        from .device_provider import SimulatedDeviceProvider, TransferOnlyProvider
        if conversation.source_type == "device":
            device = db.get(Device, conversation.device_id)
            if device.status != "authorized": reject("DEVICE_REVOKED", "Select an authorized capture source.")
            provider = SimulatedDeviceProvider() if device.simulated else TransferOnlyProvider()
            if body.action not in {"cancel", "interrupt"}:
                try: provider.validate_command(body.action)
                except NotImplementedError:
                    reject("UNVERIFIED_DEVICE_CONTROLS", "Physical transport and recording indicators are not integrated. Use an explicitly simulated device for software tests.", 501)
        with locks["capture:" + actor.org_id], locks[cid]:
            db.refresh(conversation)
            transition(db, conversation, body, actor)
            if body.action == "cancel":
                job = db.scalar(select(ProcessingJob).where(ProcessingJob.conversation_id == cid))
                if job: job.status = "cancelled"
                upload = db.scalar(select(UploadSession).where(UploadSession.conversation_id == cid))
                if upload: upload.status = "cancelled"
                from .cleanup import delete_uploads
                delete_uploads(settings.data_dir, cid)
            db.commit()
            return conversation_json(db, conversation)

    @app.post("/api/v1/conversations/{cid}/capture-heartbeat", tags=["Session lifecycle"])
    def capture_heartbeat(cid: str, body: CaptureHeartbeat, actor=Depends(principal), db=Depends(db_session)):
        conversation = owned(db, Conversation, cid, actor)
        with locks[cid]:
            db.refresh(conversation); require_consent(db, conversation)
            if body.consent_version != conversation.consent_version or body.state != conversation.session_state:
                reject("STATE_CONFLICT", "Capture state changed; refresh before reporting activity.")
            conversation.state_updated_at = now(); db.commit()
            return {"session_state":conversation.session_state,"lease_seconds":20}

    @app.patch("/api/v1/insights/{finding_id}/review", tags=["Review"])
    def review_finding(finding_id: str, body: FindingReview, user=Depends(reviewer), db=Depends(db_session)):
        finding = db.get(Insight, finding_id)
        if not finding:
            reject("NOT_FOUND", "Finding not found.", 404)
        conversation = owned(db, Conversation, finding.conversation_id, user)
        with locks[conversation.id]:
            require_consent(db, conversation)
            if conversation.status != "complete":
                reject("RESULT_REQUIRED", "Only successfully processed findings can be reviewed.")
            if body.review_status == "approved" and not body.sharing_checked:
                reject("SHARING_REVIEW_REQUIRED", "Check the finding and evidence for accuracy and identifying information before sharing.")
            values = body.model_dump(exclude_unset=True, exclude={"sharing_checked"})
            if any(value is None for key, value in values.items() if key in {"title", "description", "category", "topic", "basis", "sentiment", "uncertainty"}):
                reject("NULL_FIELD", "Required finding fields cannot be null.", 422)
            from .providers import CATEGORIES
            if values.get("category", finding.category) not in CATEGORIES + db.get(Organization, user.org_id).categories:
                reject("INVALID_CATEGORY", "Choose a configured category.", 422)
            transcript = db.get(Transcript, conversation.id)
            evidence = list(db.scalars(select(Evidence).where(Evidence.insight_id == finding.id)))
            if body.review_status == "approved" and (not transcript or not evidence or any(e.quote not in transcript.text for e in evidence)):
                reject("EVIDENCE_INVALID", "Correct the transcript and reprocess evidence before approval.")
            for key, value in values.items(): setattr(finding, key, value)
            for task in db.scalars(select(Task).where(Task.insight_id == finding.id)):
                task.status = "dismissed" if body.review_status in {"rejected", "restricted"} else "suggested"
            finding.reviewed_by, finding.reviewed_at = user.id, now()
            conversation.session_state, conversation.review_status = "needs_review", "corrected" if len(values) > 1 else "unreviewed"
            db.add(ReviewEvent(conversation_id=conversation.id, target_id=finding.id, actor=user.id,
                action="finding." + body.review_status, fields=list(values)))
            audit(db, user, "finding." + body.review_status, finding.id); db.commit()
            return insight_json(db, finding)

    @app.post("/api/v1/conversations/{cid}/approve", tags=["Review"])
    def approve(cid: str, user=Depends(reviewer), db=Depends(db_session)):
        conversation = owned(db, Conversation, cid, user)
        with locks[cid]:
            require_consent(db, conversation)
            findings = list(db.scalars(select(Insight).where(Insight.conversation_id == cid, Insight.review_status != "superseded")))
            if conversation.status != "complete" or not db.get(Transcript, cid):
                reject("RESULT_REQUIRED", "A successful transcript and analysis are required.")
            if any(i.review_status not in {"approved", "rejected"} for i in findings):
                reject("REVIEW_INCOMPLETE", "Approve or reject every finding before sharing the session.")
            conversation.review_status, conversation.session_state = "approved", "approved"
            db.add(ReviewEvent(conversation_id=cid, target_id=cid, actor=user.id, action="session.approved"))
            audit(db, user, "session.approved", cid); db.commit()
            return conversation_json(db, conversation)

    @app.patch("/api/v1/conversations/{cid}/transcript", tags=["Review"])
    def correct_transcript(cid: str, body: TranscriptCorrection, user=Depends(reviewer), db=Depends(db_session)):
        conversation = owned(db, Conversation, cid, user)
        with locks[cid]:
            require_consent(db, conversation)
            transcript = db.get(Transcript, cid)
            if not transcript or conversation.status != "complete": reject("RESULT_REQUIRED", "No completed transcript exists.")
            transcript.text, transcript.segments = body.text, []  # Corrected text has no invented word timings.
            transcript.provider = "human_corrected"
            if body.summary is not None: conversation.summary = body.summary
            conversation.session_state, conversation.review_status = "needs_review", "corrected"
            for finding in db.scalars(select(Insight).where(Insight.conversation_id == cid)):
                finding.review_status = "restricted"
                for evidence in db.scalars(select(Evidence).where(Evidence.insight_id == finding.id)):
                    evidence.start = evidence.end = None
                    if evidence.quote not in body.text: finding.evidence_status = "invalid_after_correction"
            for task in db.scalars(select(Task).where(Task.conversation_id == cid)): task.status = "suggested"
            db.add(ReviewEvent(conversation_id=cid, target_id=cid, actor=user.id, action="transcript.corrected", fields=["text", "summary"]))
            audit(db, user, "transcript.corrected", cid); db.commit()
            return conversation_json(db, conversation, True)

    @app.post("/api/v1/conversations/{cid}/reanalyze", tags=["Review"])
    def reanalyze(cid: str, user=Depends(reviewer), db=Depends(db_session)):
        conversation = owned(db, Conversation, cid, user)
        with locks[cid]:
            require_consent(db, conversation)
            job = db.scalar(select(ProcessingJob).where(ProcessingJob.conversation_id == cid))
            if not job or job.status not in {"succeeded", "failed"} or not db.get(Transcript, cid):
                reject("RESULT_REQUIRED", "A saved transcript and an idle processing job are required.")
            if job.attempts >= 5: reject("RETRY_LIMIT", "Five processing attempts reached. Inspect the provider configuration.")
            for finding in db.scalars(select(Insight).where(Insight.conversation_id == cid)):
                finding.review_status = "superseded"
            for task in db.scalars(select(Task).where(Task.conversation_id == cid)): task.status = "superseded"
            conversation.session_state, conversation.status, conversation.review_status = "processing", "queued", "unreviewed"
            job.status, job.stage, job.updated_at = "queued", "extract", now()
            db.add(ReviewEvent(conversation_id=cid, target_id=cid, actor=user.id, action="analysis.requeued"))
            audit(db, user, "analysis.requeued", cid); db.commit(); pipeline.wake.set()
            return conversation_json(db, conversation)

    @app.get("/api/v1/exports", tags=["Exports"])
    def export(request: Request, format: str = "json", user=Depends(reviewer), db=Depends(db_session)):
        if format not in {"json", "csv"}: reject("EXPORT_FORMAT", "Use json or csv.", 422)
        query = select(Insight).join(Conversation).where(Conversation.org_id == user.org_id,
            Conversation.store_id.in_(scope(db, user, request.headers.get("x-store-id"))),
            Conversation.session_state == "approved", Insight.review_status == "approved")
        rows = []
        for finding in db.scalars(query):
            conversation = db.get(Conversation, finding.conversation_id)
            if not consent_valid(db, conversation): continue
            row = insight_json(db, finding)
            row.update(organization_id=user.org_id, store_id=conversation.store_id)
            row["tasks"] = [record(t) for t in db.scalars(select(Task).where(Task.insight_id == finding.id, Task.status.in_({"approved", "completed"})))]
            rows.append(row)
        audit(db, user, "approved_records.exported", user.org_id); db.commit()
        if format == "json": return {"records":rows, "exported_at":now(), "warning":"Downloaded exports cannot be recalled after withdrawal or deletion."}
        buffer = io.StringIO()
        fields = ["id", "conversation_id", "store_id", "category", "description", "basis", "uncertainty", "recommendation", "success_metric"]
        writer = csv.DictWriter(buffer, fieldnames=fields, extrasaction="ignore"); writer.writeheader()
        for row in rows:
            safe = {k: ("'" + str(row.get(k)) if str(row.get(k) or "").lstrip().startswith(("=", "+", "-", "@", "\t", "\r")) else row.get(k)) for k in fields}
            writer.writerow(safe)
        return Response(buffer.getvalue(), media_type="text/csv", headers={"Content-Disposition":'attachment; filename="neuaura-approved.csv"'})

    @app.patch("/api/v1/settings/retention", tags=["Workspace"])
    def retention(body: RetentionPolicy, user=Depends(admin_auth), db=Depends(db_session)):
        org = db.get(Organization, user.org_id); org.retention_policy = body.model_dump()
        audit(db, user, "retention.policy_updated", org.id); db.commit()
        return policy_for(settings, org)
