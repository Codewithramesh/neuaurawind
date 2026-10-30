import logging
import threading
from datetime import datetime, timedelta, timezone
from sqlalchemy import delete, select
from .models import (AudioFile, AuditEvent, Conversation, Evidence, Insight, Organization, ParticipantConsent,
                     ProcessingJob, Task, Transcript, now)
from .audio import normalize_audio
from .providers import ProcessingError, TranscriptionResult
from .governance import consent_valid, policy_for
from .cleanup import delete_uploads, retry_deletions

logger = logging.getLogger(__name__)


class Pipeline:
    """Durable single worker. Model calls never hold locks that block withdrawal/deletion."""
    def __init__(self, settings, factory, transcriber, extractor, locks):
        self.settings, self.factory = settings, factory
        self.transcriber, self.extractor = transcriber, extractor
        self.stop_event, self.wake = threading.Event(), threading.Event()
        self.thread, self.locks, self.lease_thread = None, locks, None

    def start(self):
        self.stop_event.clear()
        with self.factory() as db:
            for job in db.scalars(select(ProcessingJob).where(ProcessingJob.status == "processing")):
                conversation = db.get(Conversation, job.conversation_id)
                if consent_valid(db, conversation):
                    job.status, conversation.status, conversation.session_state = "queued", "queued", "processing"
                else:
                    job.status, conversation.status, conversation.session_state = "cancelled", "restricted", "interrupted"
            # The browser cannot prove capture continued after page/server loss.
            for conversation in db.scalars(select(Conversation).where(Conversation.session_state.in_({"recording", "paused"}))):
                conversation.session_state, conversation.capture_conditions_confirmed = "interrupted", False
                db.add(AuditEvent(org_id=conversation.org_id, actor="recovery", action="capture.interrupted", target_id=conversation.id))
            db.commit()
        self.thread = threading.Thread(target=self.run, name="neuaura-pipeline", daemon=True)
        self.thread.start()
        self.lease_thread = threading.Thread(target=self.monitor_capture, name="neuaura-capture-lease", daemon=True)
        self.lease_thread.start()

    def stop(self):
        self.stop_event.set(); self.wake.set()
        if self.thread: self.thread.join(timeout=5)
        if self.lease_thread: self.lease_thread.join(timeout=3)

    def run(self):
        last_retention = 0
        import time
        while not self.stop_event.is_set():
            try:
                if time.monotonic() - last_retention > 3600:
                    self.retention(); last_retention = time.monotonic()
                with self.factory() as db:
                    job = db.scalar(select(ProcessingJob).where(ProcessingJob.status == "queued").order_by(ProcessingJob.updated_at).limit(1))
                    cid = job.conversation_id if job else None
                if cid: self.process(cid)
                else: self.wake.wait(2); self.wake.clear()
            except Exception as exc:
                logger.error("Worker loop failed (%s); persisted work remains recoverable", type(exc).__name__)
                self.wake.wait(2); self.wake.clear()

    def current(self, db, cid, version):
        conversation = db.get(Conversation, cid)
        job = db.scalar(select(ProcessingJob).where(ProcessingJob.conversation_id == cid))
        if not conversation or not job or job.status != "processing" or conversation.session_state != "processing" or conversation.consent_version != version or not consent_valid(db, conversation):
            return None, None
        return conversation, job

    def process(self, cid):
        # Claim, perform external work, and commit only after checking consent again.
        with self.locks[cid], self.factory() as db:
            conversation = db.get(Conversation, cid)
            job = db.scalar(select(ProcessingJob).where(ProcessingJob.conversation_id == cid))
            if not conversation or not job or job.status != "queued": return
            if not consent_valid(db, conversation) or conversation.session_state != "processing":
                job.status, conversation.status = "cancelled", "restricted"
                job.error_code, job.error_message = "CONSENT_REQUIRED", "Revalidate participant consent before processing."
                db.commit(); return
            version, language = conversation.consent_version, conversation.language
            job.status, conversation.status = "processing", "processing"
            job.attempts += 1; job.error_code = job.error_message = None; job.updated_at = now()
            transcript = db.get(Transcript, cid)
            result = TranscriptionResult(transcript.text, transcript.segments, transcript.language, transcript.provider, transcript.model) if transcript else None
            job.stage = "extract" if result else "normalize"
            db.commit()
        try:
            if result is None:
                folder = self.settings.data_dir / "uploads" / cid
                normalized = folder / "normalized.wav"
                duration = normalize_audio(folder / "original", normalized, self.settings.max_duration_seconds)
                with self.locks[cid], self.factory() as db:
                    conversation, job = self.current(db, cid, version)
                    if not conversation: return
                    audio = db.scalar(select(AudioFile).where(AudioFile.conversation_id == cid))
                    audio.normalized_path, audio.codec = str(normalized), "pcm_s16le"
                    conversation.duration, job.stage = duration, "transcribe"
                    db.commit()
                result = self.transcriber.transcribe(normalized, language)
                if not result.text.strip() or not result.segments:
                    raise ProcessingError("NO_SPEECH", "No intelligible speech was detected.", False)
                if any(not s.get("text", "").strip() or s.get("start", -1) < 0 or s.get("end", -1) < s.get("start", 0) or s.get("end", 0) > duration + 1 for s in result.segments):
                    raise ProcessingError("TRANSCRIPT_INVALID", "Speech provider returned invalid segments.", False)
                with self.locks[cid], self.factory() as db:
                    conversation, job = self.current(db, cid, version)
                    if not conversation: return
                    db.add(Transcript(conversation_id=cid, text=result.text, segments=result.segments,
                        provider=result.provider, model=result.model, language=result.language))
                    if not self.settings.retain_audio:
                        delete_uploads(self.settings.data_dir, cid)
                        audio = db.scalar(select(AudioFile).where(AudioFile.conversation_id == cid))
                        audio.original_path = audio.normalized_path = None
                    job.stage = "extract"; db.commit()
            with self.locks[cid], self.factory() as db:
                conversation, job = self.current(db, cid, version)
                if not conversation: return
                org = db.get(Organization, conversation.org_id)
                industry, categories = org.industry, org.categories
            extraction = self.extractor.extract(result, industry, categories)
            from .providers import validate_evidence
            from .schemas import Extraction
            extraction = validate_evidence(Extraction.model_validate(extraction), result, categories)
            with self.locks[cid], self.factory() as db:
                conversation, job = self.current(db, cid, version)
                if not conversation: return
                conversation.summary, conversation.topics, conversation.entities = extraction.summary, extraction.topics, extraction.entities
                findings = []
                for item in extraction.insights:
                    finding = Insight(conversation_id=cid, **item.model_dump(exclude={"evidence"}))
                    db.add(finding); db.flush(); findings.append(finding)
                    for evidence in item.evidence:
                        segment = result.segments[evidence.segment_index] if evidence.segment_index is not None else {}
                        db.add(Evidence(insight_id=finding.id, quote=evidence.quote, start=segment.get("start"), end=segment.get("end")))
                for action in extraction.actions:
                    db.add(Task(org_id=conversation.org_id, conversation_id=cid, insight_id=findings[action.insight_index].id,
                        title=findings[action.insight_index].title[:180], description=action.description, priority=action.priority))
                job.status, job.stage, conversation.status = "succeeded", "complete", "complete"
                conversation.session_state, conversation.review_status, conversation.state_updated_at = "needs_review", "unreviewed", now()
                job.retryable, job.updated_at = False, now()
                db.add(AuditEvent(org_id=conversation.org_id, actor="pipeline", action="processing.needs_review", target_id=cid,
                    details={"speech_model":result.model,"extraction_model":self.settings.llm_model}))
                db.commit()
        except Exception as exc:
            with self.locks[cid], self.factory() as db:
                conversation, job = self.current(db, cid, version)
                if not conversation: return
                error = exc if isinstance(exc, ProcessingError) else ProcessingError("PROCESSING_FAILED", "Processing failed. Check local service configuration, then retry.")
                if not isinstance(exc, ProcessingError): logger.error("Processing failure %s (%s)", cid, type(exc).__name__)
                job.status, conversation.status, conversation.session_state = "failed", "failed", "failed"
                job.error_code, job.error_message, job.retryable, job.updated_at = error.code, str(error), error.retryable, now()
                db.commit()

    def delete_conversation(self, db, conversation, actor):
        cid = conversation.id
        with self.locks[cid]:
            db.add(AuditEvent(org_id=conversation.org_id, actor=actor, action="conversation.deleted", target_id=cid))
            db.execute(delete(Conversation).where(Conversation.id == cid)); db.commit()
            delete_uploads(self.settings.data_dir, cid)

    def monitor_capture(self):
        while not self.stop_event.wait(2):
            try:
                self.expire_captures()
                retry_deletions(self.settings.data_dir, self.locks)
            except Exception as exc: logger.error("Capture lease check failed (%s)", type(exc).__name__)

    def expire_captures(self):
        cutoff = (datetime.now(timezone.utc) - timedelta(seconds=20)).isoformat()
        with self.factory() as db:
            ids = list(db.scalars(select(Conversation.id).where(Conversation.session_state.in_({"recording", "paused"}), Conversation.state_updated_at < cutoff)))
        for cid in ids:
            with self.locks[cid], self.factory() as db:
                conversation = db.get(Conversation, cid)
                if conversation and conversation.session_state in {"recording", "paused"} and conversation.state_updated_at < cutoff:
                    conversation.session_state, conversation.capture_conditions_confirmed = "interrupted", False
                    db.add(AuditEvent(org_id=conversation.org_id, actor="capture_lease", action="capture.interrupted", target_id=cid))
                    db.commit()

    def retention(self):
        now_utc = datetime.now(timezone.utc)
        with self.factory() as db:
            identifiers = list(db.scalars(select(Conversation.id)))
        for cid in identifiers:
            with self.locks[cid], self.factory() as db:
                conversation = db.get(Conversation, cid)
                if not conversation: continue
                org = db.get(Organization, conversation.org_id)
                policy = policy_for(self.settings, org)
                age = (now_utc - datetime.fromisoformat(conversation.created_at)).total_seconds()
                if age > max(policy['transcript_days'], policy['derived_days'], policy['consent_days']) * 86400 or (conversation.status == 'awaiting_audio' and age > 86400):
                    self.delete_conversation(db, conversation, "retention"); continue
                if age > policy['raw_audio_hours'] * 3600:
                    delete_uploads(self.settings.data_dir, cid)
                    audio = db.scalar(select(AudioFile).where(AudioFile.conversation_id == cid))
                    if audio: audio.original_path = audio.normalized_path = None
                if age > policy['transcript_days'] * 86400:
                    db.execute(delete(Transcript).where(Transcript.conversation_id == cid))
                    # Exact excerpts are transcript content too; expire them with their source.
                    for finding in db.scalars(select(Insight).where(Insight.conversation_id == cid)):
                        db.execute(delete(Evidence).where(Evidence.insight_id == finding.id))
                        finding.evidence_status, finding.review_status = "source_expired", "restricted"
                    conversation.session_state = "needs_review"
                if age > policy['derived_days'] * 86400:
                    db.execute(delete(Task).where(Task.conversation_id == cid))
                    db.execute(delete(Insight).where(Insight.conversation_id == cid))
                    conversation.summary, conversation.topics, conversation.entities = None, [], []
                    conversation.session_state = "needs_review"
                if age > policy['consent_days'] * 86400:
                    db.execute(delete(ParticipantConsent).where(ParticipantConsent.conversation_id == cid))
                    conversation.review_status, conversation.session_state = "restricted", "needs_review"
                if age > min(policy['transcript_days'], policy['derived_days'], policy['consent_days']) * 86400:
                    job = db.scalar(select(ProcessingJob).where(ProcessingJob.conversation_id == cid))
                    if job and job.status in {"queued", "processing"}:
                        job.status, job.error_code, job.retryable = "cancelled", "RETENTION_EXPIRED", False
                        job.error_message = "Required source or consent records expired under the organization policy."
                        conversation.status, conversation.review_status = "restricted", "restricted"
                db.commit()
