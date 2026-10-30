import hashlib
import hmac
import os
import re
import secrets
import threading
from collections import Counter, defaultdict
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import urlparse
from fastapi import Depends, FastAPI, Header, HTTPException, Query, Request, Response
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from starlette.middleware.trustedhost import TrustedHostMiddleware
from .config import ROOT, Settings
from .db import database
from .models import (AudioFile, AuditEvent, AuthSession, Consent, Conversation, Device, Evidence, Insight,
                     Organization, ProcessingJob, Task, Transcript, UploadSession, User, Store, StoreMembership, ParticipantConsent, ReviewEvent, now, uid)
from .providers import FasterWhisperProvider, LLMExtractionProvider
from .pipeline import Pipeline
from .schemas import Bootstrap, CompleteUpload, DeviceRegister, Heartbeat, Login, ProfileUpdate, SessionCreate, TaskUpdate
from .schemas import DeviceResponse, DeviceProvisioned, SessionResponse, ChunkResponse, CompletionResponse, SessionStatusResponse
from .security import RateLimiter, digest, new_session, password_hash, verify_password
from .audio import AUDIO_TYPES, file_sha
from .device_provider import SimulatedDeviceProvider, TransferOnlyProvider
from dataclasses import asdict
from .governance import (ADMIN_ROLES, scope, stores_for, raw_allowed, raw_filter, consent_valid, require_consent, create_participants, policy_for)


def fail(status, code, message):
    raise HTTPException(status, detail={"code": code, "message": message})


def record(row, exclude=()):
    return {c.name: getattr(row, c.name) for c in row.__table__.columns if c.name not in exclude}


def create_app(settings=None, *, transcriber=None, extractor=None):
    settings = settings or Settings()
    engine, factory = database(settings)
    locks = defaultdict(threading.RLock)
    limiter = RateLimiter()
    pipeline = Pipeline(settings, factory, transcriber or FasterWhisperProvider(settings),
                        extractor or LLMExtractionProvider(settings), locks)

    @asynccontextmanager
    async def lifespan(app):
        os.umask(0o077)
        # database() already protects the directory, including a Windows NTFS ACL.
        with factory() as db:
            empty = db.scalar(select(func.count()).select_from(User)) == 0
        token_file = settings.data_dir / "setup-token"
        if empty and not token_file.exists():
            fd = os.open(token_file, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            with os.fdopen(fd, "w") as f:
                f.write(secrets.token_urlsafe(32))
        if settings.worker_enabled:
            pipeline.start()
        yield
        pipeline.stop()
        engine.dispose()

    app = FastAPI(title="NEUAURA API", version="1.1.0", lifespan=lifespan)
    app.state.settings, app.state.engine, app.state.factory, app.state.pipeline = settings, engine, factory, pipeline
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=settings.allowed_hosts)

    @app.middleware("http")
    async def protect(request: Request, call_next):
        if request.url.path.startswith("/api/") and request.method not in {"GET", "HEAD", "OPTIONS"}:
            origin = request.headers.get("origin")
            if origin and urlparse(origin).netloc != request.headers.get("host"):
                return JSONResponse({"detail": {"code": "ORIGIN_REJECTED", "message": "Use the same origin for the application and API."}}, status_code=403)
            length = request.headers.get("content-length")
            if length:
                try:
                    if int(length) > settings.max_upload_mb * 1024 * 1024:
                        return JSONResponse({"detail": {"code": "UPLOAD_LIMIT", "message": "Request exceeds the upload limit."}}, status_code=413)
                except ValueError:
                    return JSONResponse({"detail": {"code": "INVALID_LENGTH", "message": "Invalid Content-Length"}}, status_code=400)
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "same-origin"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Permissions-Policy"] = "microphone=(self), camera=()"
        response.headers["Content-Security-Policy"] = "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; media-src 'self' blob:; connect-src 'self' ws: wss:; frame-ancestors 'none'; base-uri 'self'; form-action 'self'"
        if request.url.path.startswith("/api/"):
            response.headers["Cache-Control"] = "no-store"
        return response

    def db_session():
        with factory() as db:
            yield db

    def user_auth(request: Request, db=Depends(db_session)):
        token = request.cookies.get("neuaura_session", "")
        session = db.get(AuthSession, digest(token)) if token else None
        if not session or session.expires_at <= now():
            fail(401, "AUTH_REQUIRED", "Sign in to your workspace.")
        if request.method not in {"GET", "HEAD", "OPTIONS"}:
            if not hmac.compare_digest(request.headers.get("x-csrf-token", ""), session.csrf):
                fail(403, "CSRF_REJECTED", "Session verification failed. Refresh and try again.")
        user = db.get(User, session.user_id)
        if not user or not user.active:
            fail(401, "AUTH_REQUIRED", "Session is no longer valid.")
        return user

    def admin_auth(user=Depends(user_auth)):
        if user.role not in ADMIN_ROLES:
            fail(403, "ADMIN_REQUIRED", "A workspace administrator must perform this action.")
        return user

    def principal(request: Request, db=Depends(db_session)):
        authorization = request.headers.get("authorization", "")
        if authorization:
            if not authorization.startswith("Bearer "):
                fail(401, "DEVICE_AUTH_REQUIRED", "Use a per-device bearer credential.")
            device = db.scalar(select(Device).where(Device.credential_hash == digest(authorization[7:])))
            if not device or device.status != "authorized":
                fail(401, "DEVICE_REVOKED_OR_INVALID", "Device credential is invalid or revoked.")
            limiter.check("device:" + device.id, 120)
            device.last_seen = now()
            db.commit()
            return device
        return user_auth(request, db)

    def owned(db, model, identifier, actor):
        row = db.get(model, identifier)
        if not row or row.org_id != actor.org_id:
            fail(404, "NOT_FOUND", "Record not found.")
        if isinstance(actor, Device):
            target_device = row.id if isinstance(row, Device) else row.device_id
            if target_device != actor.id:
                fail(404, "NOT_FOUND", "Record not found.")
        if isinstance(actor, User):
            if isinstance(row, Conversation) and not raw_allowed(db, actor, row):
                fail(404, "NOT_FOUND", "Record not found.")
            if isinstance(row, UploadSession):
                conversation = db.get(Conversation, row.conversation_id)
                if not raw_allowed(db, actor, conversation):
                    fail(404, "NOT_FOUND", "Record not found.")
            if isinstance(row, Device) and row.store_id not in scope(db, actor):
                fail(404, "NOT_FOUND", "Record not found.")
            if isinstance(row, Task):
                conversation = db.get(Conversation, row.conversation_id)
                if conversation.store_id not in scope(db, actor):
                    fail(404, "NOT_FOUND", "Record not found.")
        return row

    def audit(db, actor, action, target):
        db.add(AuditEvent(org_id=actor.org_id, actor=actor.id, action=action, target_id=target))

    def device_json(device):
        data = record(device, {"credential_hash"})
        data["capabilities"] = asdict((SimulatedDeviceProvider() if device.simulated else TransferOnlyProvider()).capabilities)
        if device.status == "revoked":
            data["connection"] = "revoked"
        elif not device.last_seen:
            data["connection"] = "not_seen"
        else:
            elapsed = datetime.now(timezone.utc) - datetime.fromisoformat(device.last_seen)
            data["connection"] = "recently_seen" if elapsed.total_seconds() < 120 else "offline"
        return data

    def conversation_json(db, conversation, detail=False):
        data = record(conversation)
        job = db.scalar(select(ProcessingJob).where(ProcessingJob.conversation_id == conversation.id))
        data["job"] = record(job) if job else None
        data["consent_valid"] = consent_valid(db, conversation)
        session = db.scalar(select(UploadSession).where(UploadSession.conversation_id == conversation.id))
        data["upload_session_id"] = session.id if session else None
        if not data["consent_valid"]:
            data["summary"], data["topics"], data["entities"] = None, [], []
        if detail:
            transcript = db.get(Transcript, conversation.id)
            data["transcript"] = record(transcript) if transcript else None
            data["insights"] = [insight_json(db, i) for i in db.scalars(select(Insight).where(Insight.conversation_id == conversation.id, Insight.review_status != "superseded"))]
            data["tasks"] = [record(t) for t in db.scalars(select(Task).where(Task.conversation_id == conversation.id, Task.status != "superseded"))]
            audio = db.scalar(select(AudioFile).where(AudioFile.conversation_id == conversation.id))
            data["audio_retained"] = bool(audio and audio.original_path and Path(audio.original_path).is_file() and settings.retain_audio)
            consent = db.scalar(select(Consent).where(Consent.conversation_id == conversation.id))
            data["consent"] = record(consent) if consent else None
            data["participants"] = [record(p, {"token_hash"}) for p in db.scalars(select(ParticipantConsent).where(ParticipantConsent.conversation_id == conversation.id, ParticipantConsent.version == conversation.consent_version))]
            data["review_history"] = [record(e) for e in db.scalars(select(ReviewEvent).where(ReviewEvent.conversation_id == conversation.id).order_by(ReviewEvent.created_at))]
            if not data["consent_valid"]:
                data.update(transcript=None, insights=[], tasks=[], audio_retained=False)
        return data

    def insight_json(db, insight):
        data = record(insight)
        conversation = db.get(Conversation, insight.conversation_id)
        data.update(org_id=conversation.org_id, store_id=conversation.store_id)
        data["evidence"] = [record(e) for e in db.scalars(select(Evidence).where(Evidence.insight_id == insight.id))]
        return data

    @app.get("/api/v1/health", tags=["System"])
    def health(db=Depends(db_session)):
        return {"status": "ok", "version": "1.1.0", "bootstrap_required": db.scalar(select(func.count()).select_from(User)) == 0}

    @app.post("/api/v1/bootstrap", status_code=201, tags=["Authentication"])
    def bootstrap(body: Bootstrap, request: Request, x_setup_token: str = Header(default=""), db=Depends(db_session)):
        limiter.check("bootstrap:" + request.client.host, 5, 300)
        with locks["bootstrap"]:
            if db.scalar(select(func.count()).select_from(User)):
                fail(409, "ALREADY_CONFIGURED", "A workspace already exists. Sign in.")
            path = settings.data_dir / "setup-token"
            if not path.exists() or not hmac.compare_digest(x_setup_token, path.read_text().strip()):
                fail(403, "SETUP_TOKEN_REQUIRED", "Enter the setup token from the configured data folder on this computer.")
            org = Organization(name=body.name, industry=body.industry)
            db.add(org)
            db.flush()
            user = User(org_id=org.id, email=body.email.lower().strip(), password_hash=password_hash(body.password), role="owner")
            db.add(user)
            db.flush()
            store = Store(org_id=org.id, name=body.store_name)
            db.add(store)
            db.flush()
            db.add(StoreMembership(user_id=user.id, store_id=store.id))
            audit(db, user, "workspace.created", org.id)
            db.commit()
            path.unlink(missing_ok=True)
            return {"id": org.id, "message": "Workspace created. Sign in."}

    @app.post("/api/v1/auth/login", tags=["Authentication"])
    def login(body: Login, request: Request, response: Response, db=Depends(db_session)):
        limiter.check("login:" + request.client.host, 10, 300)
        user = db.scalar(select(User).where(User.email == body.email.lower().strip()))
        # Perform the same expensive operation for unknown accounts to reduce timing leakage.
        dummy = "pbkdf2_sha256$600000$00000000000000000000000000000000$" + "0" * 64
        valid = verify_password(body.password, user.password_hash if user else dummy)
        if not user or not user.active or not valid:
            fail(401, "INVALID_LOGIN", "Email or password is incorrect.")
        old = request.cookies.get("neuaura_session")
        if old:
            previous = db.get(AuthSession, digest(old))
            if previous:
                db.delete(previous)
        token, csrf = new_session(db, user.id, settings.session_hours)
        response.set_cookie("neuaura_session", token, httponly=True, secure=settings.secure_cookies,
                            samesite="strict", max_age=settings.session_hours * 3600)
        audit(db, user, "auth.login", user.id)
        db.commit()
        return {"csrf": csrf}

    @app.get("/api/v1/auth/me", tags=["Authentication"])
    def me(request: Request, user=Depends(user_auth), db=Depends(db_session)):
        session = db.get(AuthSession, digest(request.cookies["neuaura_session"]))
        return {"user": record(user, {"password_hash"}), "organization": record(db.get(Organization, user.org_id)), "csrf": session.csrf, "stores": [record(s) for s in stores_for(db, user)]}

    @app.post("/api/v1/auth/logout", status_code=204, tags=["Authentication"])
    def logout(request: Request, response: Response, user=Depends(user_auth), db=Depends(db_session)):
        db.delete(db.get(AuthSession, digest(request.cookies["neuaura_session"])))
        db.commit()
        response.delete_cookie("neuaura_session")

    @app.get("/api/v1/settings", tags=["Workspace"])
    def get_settings(user=Depends(user_auth), db=Depends(db_session)):
        ready = False
        try:
            import httpx
            if settings.extraction_provider == "ollama":
                response = httpx.get(settings.llm_base_url.rstrip("/") + "/api/tags", timeout=2, trust_env=False, follow_redirects=False)
                ready = response.is_success and any(m.get("name") == settings.llm_model for m in response.json().get("models", []))
        except Exception:
            pass
        from .providers import CATEGORIES, PROFILES
        return {"organization": record(db.get(Organization, user.org_id)), "retain_audio": settings.retain_audio,
                "retention_days": settings.retention_days, "max_upload_mb": settings.max_upload_mb,
                "max_duration_seconds": settings.max_duration_seconds, "language": settings.language,
                "transcription": {"provider": "faster-whisper", "model": settings.whisper_model_path.name,
                                  "ready": (settings.whisper_model_path / "model.bin").is_file()},
                "extraction": {"provider": settings.extraction_provider, "model": settings.llm_model,
                               "ready": ready, "cloud_enabled": settings.allow_cloud},
                "categories": CATEGORIES, "profiles": PROFILES, "stores": [record(s) for s in stores_for(db, user)], "role": user.role, "retention_policy": policy_for(settings, db.get(Organization, user.org_id))}

    @app.patch("/api/v1/settings/profile", tags=["Workspace"])
    def profile(body: ProfileUpdate, user=Depends(admin_auth), db=Depends(db_session)):
        org = db.get(Organization, user.org_id)
        for k, v in body.model_dump().items():
            setattr(org, k, v)
        audit(db, user, "profile.updated", org.id)
        db.commit()
        return record(org)

    def create_session(body, key, actor, db):
        if not key or not re.fullmatch(r"[A-Za-z0-9_.:-]{8,128}", key):
            fail(422, "IDEMPOTENCY_KEY_REQUIRED", "Use an 8–128 character Idempotency-Key header.")
        if isinstance(actor, Device):
            fail(403, "OPERATOR_PREPARATION_REQUIRED", "An authorized operator must prepare the session and obtain participant consent in the app. Use that session's upload ID.")
        allowed = scope(db, actor, body.store_id)
        store_id = body.store_id or (allowed[0] if len(allowed) == 1 else None)
        if not store_id:
            fail(422, "STORE_REQUIRED", "Select an authorized store.")
        device = owned(db, Device, body.device_id, actor) if body.device_id else None
        if body.source_type == "device" and (not device or device.store_id != store_id or device.status != "authorized"):
            fail(422, "DEVICE_REQUIRED", "Select an authorized device assigned to this store.")
        if body.source_type != "device" and device:
            fail(422, "SOURCE_MISMATCH", "A device may only be assigned to a device source.")
        request_hash = digest(body.model_dump_json() + actor.id)
        with locks["session:" + actor.org_id]:
            previous = db.scalar(select(UploadSession).where(UploadSession.org_id == actor.org_id, UploadSession.idempotency_key == key))
            if previous:
                if previous.request_hash != request_hash:
                    fail(409, "IDEMPOTENCY_CONFLICT", "This key was already used with different session data.")
                return record(previous)
            conversation = Conversation(org_id=actor.org_id, device_id=device.id if device else None,
                title=body.title, source_type=body.source_type, language=body.language, store_id=store_id,
                created_by=actor.id, purpose=body.purpose,
                captured_at=body.captured_at.astimezone(timezone.utc).isoformat() if body.captured_at else None)
            db.add(conversation)
            db.flush()
            session = UploadSession(org_id=actor.org_id, conversation_id=conversation.id, device_id=conversation.device_id,
                                    idempotency_key=key, request_hash=request_hash)
            db.add(session)
            db.add(Consent(conversation_id=conversation.id, attested=bool(body.consent_attested), actor=actor.id))
            links = create_participants(db, conversation, body.participant_refs)
            audit(db, actor, "session.created", conversation.id)
            db.commit()
            return {**record(session), "session_state": conversation.session_state, "consent_version": conversation.consent_version, "participant_links": links}

    @app.post("/api/v1/sessions", status_code=201, response_model=SessionResponse, tags=["Audio ingestion"])
    def session_create(body: SessionCreate, idempotency_key: str = Header(default=""), actor=Depends(principal), db=Depends(db_session)):
        limiter.check("session-create:" + actor.id, 30)
        return create_session(body, idempotency_key, actor, db)

    @app.post("/api/v1/devices/{device_id}/sessions", status_code=201, response_model=SessionResponse, tags=["Devices"])
    def device_session(device_id: str, body: SessionCreate, idempotency_key: str = Header(default=""), actor=Depends(principal), db=Depends(db_session)):
        if not isinstance(actor, Device) or actor.id != device_id:
            fail(403, "DEVICE_AUTH_REQUIRED", "Use this device's own credential.")
        return create_session(body, idempotency_key, actor, db)

    @app.post("/api/v1/sessions/{session_id}/audio", response_model=ChunkResponse, tags=["Audio ingestion"])
    async def upload(session_id: str, request: Request, sequence: int = Query(default=0, ge=0, le=999),
                     x_chunk_sha256: str = Header(default=""), actor=Depends(principal), db=Depends(db_session)):
        session = owned(db, UploadSession, session_id, actor)
        conversation = db.get(Conversation, session.conversation_id)
        require_consent(db, conversation)
        if conversation.session_state not in {"finalizing", "processing", "needs_review", "approved"}:
            fail(409, "NOT_FINALIZED", "Stop capture or validate the imported source before transferring audio.")
        if not re.fullmatch(r"[a-f0-9]{64}", x_chunk_sha256):
            fail(422, "CHUNK_CHECKSUM_REQUIRED", "Provide X-Chunk-SHA256 for each audio body.")
        mime = request.headers.get("content-type", "").split(";")[0].lower()
        if mime not in AUDIO_TYPES:
            fail(415, "UNSUPPORTED_MEDIA", "Unsupported audio content type.")
        maximum = settings.max_upload_mb * 1024 * 1024
        payload = bytearray()
        async for block in request.stream():
            payload.extend(block)
            if len(payload) > maximum:
                fail(413, "UPLOAD_LIMIT", "Upload exceeds the configured size limit.")
        if not payload:
            fail(422, "EMPTY_UPLOAD", "Audio body is empty.")
        checksum = hashlib.sha256(payload).hexdigest()
        if not hmac.compare_digest(checksum, x_chunk_sha256):
            fail(422, "CHUNK_CHECKSUM_MISMATCH", "Chunk integrity check failed. Retry this chunk.")
        with locks[session.conversation_id]:
            db.refresh(session)
            db.refresh(conversation)
            require_consent(db, conversation)
            chunks = dict(session.chunks)
            old = chunks.get(str(sequence))
            if old:
                if old["sha256"] != checksum:
                    fail(409, "CHUNK_CONFLICT", "This sequence number already has different content.")
                return {"sequence": sequence, "sha256": checksum, "duplicate": True}
            if session.status != "open":
                fail(409, "SESSION_COMPLETED", "This session is already complete.")
            if sum(x["bytes"] for x in chunks.values()) + len(payload) > maximum:
                fail(413, "UPLOAD_LIMIT", "Combined chunks exceed the upload limit.")
            if session.mime and session.mime != mime:
                fail(409, "FORMAT_MISMATCH", "All chunks must use the same content type.")
            folder = settings.data_dir / "uploads" / session.conversation_id
            from .cleanup import pending_file
            if pending_file(settings.data_dir, session.conversation_id).exists():
                fail(409, "AUDIO_CLEANUP_PENDING", "Close audio playback and wait for pending file cleanup before uploading again.")
            folder.mkdir(parents=True, exist_ok=True, mode=0o700)
            path = folder / f"chunk-{sequence}"
            tmp = folder / f"chunk-{sequence}.tmp"
            tmp.write_bytes(payload)
            os.replace(tmp, path)
            chunks[str(sequence)] = {"sha256": checksum, "bytes": len(payload)}
            session.chunks, session.mime = chunks, mime
            db.commit()
        return {"sequence": sequence, "sha256": checksum, "duplicate": False}

    @app.post("/api/v1/sessions/{session_id}/complete", response_model=CompletionResponse, tags=["Audio ingestion"])
    def complete(session_id: str, body: CompleteUpload, actor=Depends(principal), db=Depends(db_session)):
        session = owned(db, UploadSession, session_id, actor)
        with locks[session.conversation_id]:
            db.refresh(session)
            conversation = db.get(Conversation, session.conversation_id)
            require_consent(db, conversation)
            if session.status == "complete":
                audio = db.scalar(select(AudioFile).where(AudioFile.conversation_id == session.conversation_id))
                if audio.sha256 != body.sha256 or len(session.chunks) != body.total_chunks:
                    fail(409, "COMPLETION_CONFLICT", "Completion metadata differs from the accepted audio.")
                return {"conversation_id": session.conversation_id, "status": "accepted", "duplicate": True}
            if conversation.session_state != "finalizing" or not conversation.capture_conditions_confirmed:
                fail(409, "NOT_FINALIZED", "Capture must be stopped and finalized before processing.")
            if set(session.chunks) != {str(i) for i in range(body.total_chunks)}:
                fail(409, "MISSING_CHUNKS", "Upload every chunk from sequence 0 through total_chunks - 1.")
            folder = settings.data_dir / "uploads" / session.conversation_id
            from .cleanup import pending_file
            if pending_file(settings.data_dir, session.conversation_id).exists():
                fail(409, "AUDIO_CLEANUP_PENDING", "Close audio playback and wait for pending file cleanup before finalizing again.")
            assembled = folder / "assembling"
            try:
                with assembled.open("wb") as out:
                    for i in range(body.total_chunks):
                        chunk = folder / f"chunk-{i}"
                        if not chunk.exists() or file_sha(chunk) != session.chunks[str(i)]["sha256"]:
                            fail(409, "CHUNK_DAMAGED", "Stored chunk is missing or corrupt. Cancel and submit a new session.")
                        out.write(chunk.read_bytes())
                if file_sha(assembled) != body.sha256:
                    fail(422, "CHECKSUM_MISMATCH", "Whole-file SHA256 did not match. Check chunk order and retry completion.")
                os.replace(assembled, folder / "original")
                conversation = db.get(Conversation, session.conversation_id)
                audio = AudioFile(conversation_id=conversation.id, sha256=body.sha256,
                    bytes=sum(x["bytes"] for x in session.chunks.values()), mime=session.mime, original_path=str(folder / "original"))
                db.add(audio)
                db.add(ProcessingJob(conversation_id=conversation.id))
                conversation.status, conversation.ingested_at, session.status = "queued", now(), "complete"
                conversation.session_state, conversation.state_updated_at = "processing", now()
                audit(db, actor, "audio.accepted", conversation.id)
                db.commit()
                for chunk in folder.glob("chunk-*"):
                    chunk.unlink(missing_ok=True)
                pipeline.wake.set()
                return {"conversation_id": conversation.id, "status": "accepted", "duplicate": False}
            finally:
                assembled.unlink(missing_ok=True)

    @app.get("/api/v1/sessions/{session_id}/status", response_model=SessionStatusResponse, tags=["Audio ingestion"])
    def session_status(session_id: str, actor=Depends(principal), db=Depends(db_session)):
        session = owned(db, UploadSession, session_id, actor)
        conversation = db.get(Conversation, session.conversation_id)
        return {"session_id": session.id, "conversation_id": conversation.id, "upload_status": session.status,
                "received_chunks": sorted(int(x) for x in session.chunks), **conversation_json(db, conversation)}

    @app.delete("/api/v1/sessions/{session_id}", status_code=204, tags=["Audio ingestion"])
    def cancel_session(session_id: str, actor=Depends(principal), db=Depends(db_session)):
        session = owned(db, UploadSession, session_id, actor)
        if session.status != "open":
            fail(409, "SESSION_COMPLETED", "Delete the conversation to remove an accepted upload.")
        pipeline.delete_conversation(db, db.get(Conversation, session.conversation_id), actor.id)

    @app.get("/api/v1/conversations", tags=["Conversations"])
    def conversations(request: Request, q: str = Query(default="", max_length=200), status: str | None = None,
                      date_from: str | None = Query(default=None, pattern=r"^\d{4}-\d{2}-\d{2}$"),
                      date_to: str | None = Query(default=None, pattern=r"^\d{4}-\d{2}-\d{2}$"),
                      limit: int = Query(default=100, ge=1, le=200), offset: int = Query(default=0, ge=0),
                      user=Depends(user_auth), db=Depends(db_session)):
        query = select(Conversation).where(Conversation.org_id == user.org_id, Conversation.store_id.in_(scope(db, user, request.headers.get("x-store-id"))), raw_filter(user))
        if q:
            query = query.outerjoin(Transcript).where(Conversation.review_status != "restricted").where(Conversation.title.icontains(q, autoescape=True) |
                    Conversation.summary.icontains(q, autoescape=True) | Transcript.text.icontains(q, autoescape=True))
        if status:
            query = query.where(Conversation.session_state == status) if status in {"draft", "awaiting_consent", "ready", "recording", "paused", "interrupted", "finalizing", "needs_review", "approved", "cancelled"} else query.where(Conversation.status == status)
        if date_from:
            query = query.where(Conversation.created_at >= date_from)
        if date_to:
            query = query.where(Conversation.created_at <= date_to + "T23:59:59.999999+00:00")
        rows = db.scalars(query.order_by(Conversation.created_at.desc()).offset(offset).limit(limit))
        return [conversation_json(db, c) for c in rows]

    @app.get("/api/v1/conversations/{cid}", tags=["Conversations"])
    def conversation_detail(cid: str, user=Depends(user_auth), db=Depends(db_session)):
        return conversation_json(db, owned(db, Conversation, cid, user), True)

    @app.get("/api/v1/conversations/{cid}/audio", tags=["Conversations"])
    def audio_playback(cid: str, user=Depends(user_auth), db=Depends(db_session)):
        conversation = owned(db, Conversation, cid, user)
        require_consent(db, conversation)
        audio = db.scalar(select(AudioFile).where(AudioFile.conversation_id == cid))
        if not settings.retain_audio or not audio or not audio.original_path or not Path(audio.original_path).is_file():
            fail(404, "AUDIO_NOT_RETAINED", "Audio is not retained under the current privacy policy.")
        return FileResponse(audio.original_path, media_type=audio.mime)

    @app.delete("/api/v1/conversations/{cid}", status_code=204, tags=["Conversations"])
    def conversation_delete(cid: str, user=Depends(user_auth), db=Depends(db_session)):
        conversation = owned(db, Conversation, cid, user)
        pipeline.delete_conversation(db, conversation, user.id)

    @app.post("/api/v1/conversations/{cid}/retry", tags=["Conversations"])
    def retry(cid: str, user=Depends(user_auth), db=Depends(db_session)):
        conversation = owned(db, Conversation, cid, user)
        require_consent(db, conversation)
        with locks[cid]:
            job = db.scalar(select(ProcessingJob).where(ProcessingJob.conversation_id == cid))
            if not job or job.status != "failed" or not job.retryable:
                fail(409, "NOT_RETRYABLE", "Only retryable failed jobs can be retried.")
            if job.attempts >= 5:
                fail(409, "RETRY_LIMIT", "Five attempts reached. Inspect configuration and submit a new recording.")
            job.status, job.updated_at = "queued", now()
            db.get(Conversation, cid).status = "queued"
            conversation.session_state = "processing"
            audit(db, user, "processing.retried", cid)
            db.commit()
            pipeline.wake.set()
            return {"status": "queued"}

    def approved_query(db, user, request):
        return select(Insight).join(Conversation).where(Conversation.org_id == user.org_id,
            Conversation.store_id.in_(scope(db, user, request.headers.get("x-store-id"))),
            Insight.review_status == "approved", Conversation.session_state == "approved")

    @app.get("/api/v1/insights", tags=["Intelligence"])
    def insights(request: Request, category: str | None = None, user=Depends(user_auth), db=Depends(db_session)):
        query = approved_query(db, user, request)
        if category:
            query = query.where(Insight.category == category)
        return [insight_json(db, x) for x in db.scalars(query.order_by(Insight.created_at.desc()).limit(1000))
                if consent_valid(db, db.get(Conversation, x.conversation_id))]

    @app.get("/api/v1/overview", tags=["Intelligence"])
    def overview(request: Request, date_from: str | None = Query(default=None, pattern=r"^\d{4}-\d{2}-\d{2}$"),
                 date_to: str | None = Query(default=None, pattern=r"^\d{4}-\d{2}-\d{2}$"), user=Depends(user_auth), db=Depends(db_session)):
        store_ids = scope(db, user, request.headers.get("x-store-id"))
        rows = list(db.scalars(select(Conversation).where(Conversation.org_id == user.org_id,
            Conversation.store_id.in_(store_ids), raw_filter(user))))
        findings = [i for i in db.scalars(approved_query(db, user, request)) if consent_valid(db, db.get(Conversation, i.conversation_id))]
        tasks = list(db.scalars(select(Task).join(Conversation).where(Task.org_id == user.org_id,
            Conversation.store_id.in_(store_ids), Conversation.session_state == "approved", Task.status.in_({"approved", "completed"}))))
        def in_range(conversation):
            day = conversation.created_at[:10]
            return (not date_from or day >= date_from) and (not date_to or day <= date_to)
        rows = [row for row in rows if in_range(row)]
        findings = [finding for finding in findings if in_range(db.get(Conversation, finding.conversation_id))]
        tasks = [task for task in tasks if in_range(db.get(Conversation, task.conversation_id))]
        statuses = Counter(x.status for x in rows)
        sentiments = Counter(x.sentiment for x in findings)
        complaints = Counter(topic for _, topic in {(x.conversation_id, x.topic) for x in findings if x.category in {"complaint", "experience_problem", "operational_bottleneck", "negative_feedback"}})
        requests = Counter(topic for _, topic in {(x.conversation_id, x.topic) for x in findings if x.category in {"product_request", "service_request", "customer_need", "availability"}})
        by_date = Counter(x.created_at[:10] for x in rows)
        insight_dates = Counter((x.created_at[:10], x.sentiment) for x in findings)
        dates = [(datetime.now(timezone.utc) - timedelta(days=i)).date().isoformat() for i in range(13, -1, -1)]
        return {"total_conversations": len(rows), "succeeded": statuses["complete"], "failed": statuses["failed"],
            "awaiting_review": sum(x.session_state == "needs_review" for x in rows),
            "approved_findings": len(findings), "sample_note": "Findings reflect approved records from selected stores. Theme counts use distinct sessions; session totals follow your raw-data permissions. One session does not establish a trend.",
            "processing": statuses["processing"] + statuses["queued"], "positive": sentiments["positive"], "negative": sentiments["negative"],
            "open_tasks": sum(t.status == "approved" for t in tasks),
            "complaints": [{"topic": k, "count": v} for k, v in complaints.most_common(6)],
            "requests": [{"topic": k, "count": v} for k, v in requests.most_common(6)],
            "recent_insights": [insight_json(db, x) for x in sorted(findings, key=lambda x: x.created_at, reverse=True)[:5]],
            "trend": [{"date": d, "conversations": by_date[d], "positive": insight_dates[(d, "positive")], "negative": insight_dates[(d, "negative")]} for d in dates]}

    @app.get("/api/v1/tasks", tags=["Tasks"])
    def tasks(request: Request, user=Depends(user_auth), db=Depends(db_session)):
        query = select(Task).join(Conversation).where(Task.org_id == user.org_id,
            Conversation.store_id.in_(scope(db, user, request.headers.get("x-store-id"))))
        if user.role not in ADMIN_ROLES | {"manager"}:
            query = query.where((Conversation.created_by == user.id) | ((Task.owner_id == user.id) & Task.status.in_({"approved", "completed"}) & (Conversation.session_state == "approved")))
        return [record(t) for t in db.scalars(query.order_by(Task.created_at.desc()).limit(1000))
                if consent_valid(db, db.get(Conversation, t.conversation_id))]

    @app.patch("/api/v1/tasks/{task_id}", tags=["Tasks"])
    def task_update(task_id: str, body: TaskUpdate, user=Depends(user_auth), db=Depends(db_session)):
        task = owned(db, Task, task_id, user)
        conversation = db.get(Conversation, task.conversation_id)
        require_consent(db, conversation)
        values = body.model_dump(exclude_unset=True, mode="json")
        if user.role not in ADMIN_ROLES | {"manager"}:
            if task.owner_id != user.id or set(values) != {"status"} or values["status"] != "completed" or task.status != "approved":
                fail(403, "REVIEWER_REQUIRED", "Only reviewers can approve or edit tasks. Assigned staff may complete approved tasks.")
        if values.get("status") in {"approved", "completed"}:
            finding = db.get(Insight, task.insight_id)
            if conversation.session_state != "approved" or finding.review_status != "approved":
                fail(409, "REVIEW_REQUIRED", "Approve the source finding and session before approving a task.")
        if "owner_id" in values and values["owner_id"]:
            assigned = db.get(User, values["owner_id"])
            if not assigned or not assigned.active or assigned.org_id != user.org_id or conversation.store_id not in scope(db, assigned):
                fail(422, "INVALID_ASSIGNEE", "Assign an active member authorized for this store.")
            values["owner"] = assigned.email
        if "due_date" in values:
            values["deadline_basis"] = "operator_set" if values["due_date"] else "not_established"
            if body.deadline_basis == "reviewer_confirmed_commitment" and values["due_date"]:
                transcript = db.get(Transcript, conversation.id)
                if not body.deadline_quote or not transcript or body.deadline_quote not in transcript.text:
                    fail(422, "COMMITMENT_EVIDENCE_REQUIRED", "Provide an exact transcript quote supporting the reviewer-confirmed commitment.")
                values["deadline_basis"] = "reviewer_confirmed_commitment"
            else:
                values["deadline_quote"] = None
        elif "deadline_basis" in values or "deadline_quote" in values:
            fail(422, "DUE_DATE_REQUIRED", "Set the due date and its basis together.")
        if "owner_id" in values and not values["owner_id"]:
            values["owner"] = None
        if any(values.get(k, "unchanged") is None for k in {"description", "priority", "status", "title", "deadline_basis"}):
            fail(422, "NULL_FIELD", "Description, priority and status cannot be null.")
        for key, value in values.items():
            setattr(task, key, value)
        db.add(ReviewEvent(conversation_id=conversation.id, target_id=task.id, actor=user.id, action="task.updated", fields=list(values)))
        audit(db, user, "task.updated", task.id)
        db.commit()
        return record(task)

    @app.post("/api/v1/devices/register", status_code=201, response_model=DeviceProvisioned, tags=["Devices"])
    def register(body: DeviceRegister, user=Depends(admin_auth), db=Depends(db_session)):
        token = "neu_dev_" + secrets.token_urlsafe(32)
        values = body.model_dump()
        ids = scope(db, user, body.store_id)
        values["store_id"] = body.store_id or (ids[0] if len(ids) == 1 else None)
        if not values["store_id"]:
            fail(422, "STORE_REQUIRED", "Select a store for this device.")
        device = Device(org_id=user.org_id, credential_hash=digest(token), **values)
        db.add(device)
        db.flush()
        audit(db, user, "device.provisioned", device.id)
        db.commit()
        return {**device_json(device), "credential": token}

    @app.get("/api/v1/devices", response_model=list[DeviceResponse], tags=["Devices"])
    def devices(request: Request, user=Depends(user_auth), db=Depends(db_session)):
        return [device_json(x) for x in db.scalars(select(Device).where(Device.org_id == user.org_id, Device.store_id.in_(scope(db, user, request.headers.get("x-store-id")))).order_by(Device.created_at.desc()))]

    @app.get("/api/v1/devices/{device_id}", response_model=DeviceResponse, tags=["Devices"])
    def device_detail(device_id: str, actor=Depends(principal), db=Depends(db_session)):
        return device_json(owned(db, Device, device_id, actor))

    @app.post("/api/v1/devices/{device_id}/revoke", tags=["Devices"])
    def revoke(device_id: str, user=Depends(admin_auth), db=Depends(db_session)):
        device = owned(db, Device, device_id, user)
        device.status = "revoked"
        for conversation in db.scalars(select(Conversation).where(Conversation.device_id == device.id, Conversation.session_state.in_({"ready", "recording", "paused"}))):
            with locks[conversation.id]:
                conversation.session_state, conversation.capture_conditions_confirmed = "interrupted", False
                audit(db, user, "device.capture_interrupted", conversation.id)
        audit(db, user, "device.revoked", device.id)
        db.commit()
        return device_json(device)

    @app.post("/api/v1/devices/{device_id}/heartbeat", response_model=DeviceResponse, tags=["Devices"])
    def heartbeat(device_id: str, body: Heartbeat, actor=Depends(principal), db=Depends(db_session)):
        if not isinstance(actor, Device) or actor.id != device_id:
            fail(403, "DEVICE_AUTH_REQUIRED", "Use this device's own credential.")
        for key, value in body.model_dump(exclude_unset=True).items():
            setattr(actor, key, value)
        actor.last_seen = now()
        db.commit()
        return device_json(actor)

    @app.post("/api/v1/devices/{device_id}/errors", status_code=202, tags=["Devices"])
    def device_error(device_id: str, body: dict[str, str], actor=Depends(principal), db=Depends(db_session)):
        if not isinstance(actor, Device) or actor.id != device_id:
            fail(403, "DEVICE_AUTH_REQUIRED", "Use this device's own credential.")
        if set(body) != {"code", "message"} or any(len(v) > 500 for v in body.values()):
            fail(422, "INVALID_ERROR", "Send code and message, each up to 500 characters. Do not include conversation content.")
        actor.health = {**actor.health, "last_error": body}
        audit(db, actor, "device.error", actor.id)
        db.commit()
        return {"accepted": True}

    @app.get("/api/v1/audit", tags=["Workspace"])
    def audits(user=Depends(admin_auth), db=Depends(db_session)):
        return [record(x) for x in db.scalars(select(AuditEvent).where(AuditEvent.org_id == user.org_id).order_by(AuditEvent.created_at.desc()).limit(100))]

    from .v1_routes import install_v1_routes
    install_v1_routes(app, settings=settings, factory=factory, locks=locks, pipeline=pipeline,
        db_session=db_session, user_auth=user_auth, admin_auth=admin_auth, principal=principal,
        owned=owned, audit=audit, record=record, conversation_json=conversation_json, insight_json=insight_json, limiter=limiter)

    dist = ROOT / "frontend/dist"
    if dist.is_dir():
        app.mount("/assets", StaticFiles(directory=dist / "assets"), name="assets")

        @app.get("/{path:path}", include_in_schema=False)
        def frontend(path: str):
            if path.startswith("api/"):
                fail(404, "NOT_FOUND", "API route not found.")
            return FileResponse(dist / "index.html")
    return app


app = create_app()
