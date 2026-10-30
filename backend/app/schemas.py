import re
from datetime import date, datetime
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Login(StrictModel):
    email: str = Field(min_length=3, max_length=254)
    password: str = Field(min_length=1, max_length=256)


class Bootstrap(Login):
    name: str = Field(min_length=1, max_length=120)
    industry: Literal["restaurant", "retail", "hospitality", "service"] = "restaurant"
    store_name: str = Field(default="Main store", min_length=1, max_length=120)

    @field_validator("password")
    @classmethod
    def strong_password(cls, value):
        if len(value) < 12:
            raise ValueError("Use at least 12 characters")
        return value


class SessionCreate(StrictModel):
    title: str = Field(min_length=1, max_length=160)
    source_type: Literal["browser", "phone_microphone", "upload", "device"] = "browser"
    consent_attested: Literal[True] | None = None  # Legacy metadata; never grants participant consent.
    store_id: str | None = None
    device_id: str | None = None
    purpose: str = Field(min_length=3, max_length=500)
    participant_refs: list[str] = Field(min_length=1, max_length=20)
    language: str = Field(default="en", pattern=r"^[a-z]{2}$")
    captured_at: datetime | None = None

    @field_validator("participant_refs")
    @classmethod
    def participants(cls, values):
        cleaned = [v.strip() for v in values]
        if any(not v or len(v) > 80 for v in cleaned) or len(set(cleaned)) != len(cleaned):
            raise ValueError("Use distinct participant references, 1–80 characters each; names are unnecessary")
        return cleaned

    @field_validator("captured_at")
    @classmethod
    def aware_capture_time(cls, value):
        if value is not None and value.tzinfo is None:
            raise ValueError("Capture timestamps must include a UTC offset")
        return value


class CompleteUpload(StrictModel):
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    total_chunks: int = Field(ge=1, le=1000)


class DeviceRegister(StrictModel):
    name: str = Field(min_length=1, max_length=100)
    device_type: str = Field(default="wearable", min_length=1, max_length=50)
    model: str = Field(min_length=1, max_length=100)
    simulated: bool = False
    firmware: str | None = Field(default=None, max_length=80)
    store_id: str | None = None


class Heartbeat(StrictModel):
    battery: float | None = Field(default=None, ge=0, le=100)
    firmware: str | None = Field(default=None, max_length=80)
    health: dict[str, str | int | float | bool] = Field(default_factory=dict, max_length=20)


class TaskUpdate(StrictModel):
    description: str | None = Field(default=None, min_length=1, max_length=2000)
    status: Literal["approved", "dismissed", "completed", "suggested"] | None = None
    priority: Literal["low", "medium", "high"] | None = None
    due_date: date | None = None
    title: str | None = Field(default=None, min_length=3, max_length=180)
    owner_id: str | None = None
    deadline_basis: Literal["not_established", "operator_set", "reviewer_confirmed_commitment"] | None = None
    deadline_quote: str | None = Field(default=None, max_length=3000)


class StoreCreate(StrictModel):
    name: str = Field(min_length=1, max_length=120)


class MemberCreate(Login):
    role: Literal["admin", "manager", "staff"] = "staff"
    store_ids: list[str] = Field(default_factory=list, max_length=100)

    @field_validator("password")
    @classmethod
    def strong_password(cls, value):
        if len(value) < 12:
            raise ValueError("Use at least 12 characters")
        return value


class MemberUpdate(StrictModel):
    role: Literal["admin", "manager", "staff"]
    store_ids: list[str] = Field(default_factory=list, max_length=100)
    active: bool = True


class ParticipantDecision(StrictModel):
    decision: Literal["grant", "withdraw", "decline"]
    informed: Literal[True]


class Transition(StrictModel):
    action: Literal["ready", "start", "pause", "resume", "interrupt", "stop", "cancel"]
    expected_state: str
    consent_version: int = Field(ge=1)
    conditions_confirmed: bool = False


class CaptureHeartbeat(StrictModel):
    consent_version: int = Field(ge=1)
    state: Literal["recording", "paused"]


class ParticipantList(StrictModel):
    participant_refs: list[str] = Field(min_length=1, max_length=20)
    _participants = field_validator("participant_refs")(SessionCreate.participants.__func__)


class FindingReview(StrictModel):
    review_status: Literal["corrected", "approved", "rejected", "restricted"]
    sharing_checked: bool = False
    title: str | None = Field(default=None, min_length=3, max_length=180)
    description: str | None = Field(default=None, min_length=3, max_length=2000)
    category: str | None = Field(default=None, min_length=2, max_length=80)
    topic: str | None = Field(default=None, min_length=2, max_length=120)
    basis: Literal["stated", "inferred"] | None = None
    sentiment: Literal["positive", "negative", "neutral"] | None = None
    uncertainty: str | None = Field(default=None, max_length=1000)
    impact: str | None = Field(default=None, max_length=2000)
    recommendation: str | None = Field(default=None, max_length=2000)
    success_metric: str | None = Field(default=None, max_length=1000)
    priority_rationale: str | None = Field(default=None, max_length=1000)


class TranscriptCorrection(StrictModel):
    text: str = Field(min_length=3, max_length=100000)
    summary: str | None = Field(default=None, min_length=3, max_length=3000)


class RetentionPolicy(StrictModel):
    raw_audio_hours: int = Field(default=24, ge=0, le=720)
    transcript_days: int = Field(default=30, ge=1, le=3650)
    derived_days: int = Field(default=30, ge=1, le=3650)
    consent_days: int = Field(default=30, ge=1, le=3650)


class ProfileUpdate(StrictModel):
    name: str = Field(min_length=1, max_length=120)
    industry: Literal["restaurant", "retail", "hospitality", "service"]
    categories: list[str] = Field(default_factory=list, max_length=30)

    @field_validator("categories")
    @classmethod
    def valid_categories(cls, values):
        if any(not re.fullmatch(r"[a-z][a-z0-9_]{1,59}", x) for x in values):
            raise ValueError("Categories must be lowercase snake_case")
        return list(dict.fromkeys(values))


class EvidenceInput(StrictModel):
    quote: str = Field(min_length=3, max_length=3000)
    segment_index: int | None = Field(default=None, ge=0)


class InsightInput(StrictModel):
    category: str = Field(min_length=2, max_length=80)
    topic: str = Field(min_length=2, max_length=120)
    title: str = Field(min_length=3, max_length=180)
    description: str = Field(min_length=3, max_length=2000)
    sentiment: Literal["positive", "negative", "neutral"]
    basis: Literal["stated", "inferred"]
    confidence: float = Field(ge=0, le=1)
    uncertainty: str = Field(max_length=1000)
    evidence: list[EvidenceInput] = Field(min_length=1, max_length=10)
    impact: str | None = Field(default=None, max_length=2000)
    recommendation: str | None = Field(default=None, max_length=2000)
    success_metric: str | None = Field(default=None, max_length=1000)
    priority_rationale: str | None = Field(default=None, max_length=1000)


class ActionInput(StrictModel):
    insight_index: int = Field(ge=0)
    description: str = Field(min_length=3, max_length=2000)
    priority: Literal["low", "medium", "high"]


class Extraction(StrictModel):
    summary: str = Field(min_length=3, max_length=3000)
    topics: list[str] = Field(max_length=30)
    entities: list[str] = Field(max_length=30)
    insights: list[InsightInput] = Field(max_length=50)
    actions: list[ActionInput] = Field(max_length=30)

    @model_validator(mode="after")
    def linked_actions(self):
        if any(a.insight_index >= len(self.insights) for a in self.actions):
            raise ValueError("Action references a missing insight")
        return self


class DeviceResponse(BaseModel):
    id: str
    org_id: str
    name: str
    device_type: str
    model: str
    firmware: str | None
    status: str
    simulated: bool
    last_seen: str | None
    battery: float | None
    health: dict
    created_at: str
    connection: str
    store_id: str | None
    capabilities: dict


class DeviceProvisioned(DeviceResponse):
    credential: str


class SessionResponse(BaseModel):
    id: str
    org_id: str
    conversation_id: str
    device_id: str | None
    idempotency_key: str
    request_hash: str
    status: str
    chunks: dict
    mime: str | None
    error: str | None
    created_at: str
    session_state: str | None = None
    consent_version: int | None = None
    participant_links: list[dict] = Field(default_factory=list)


class ChunkResponse(BaseModel):
    sequence: int
    sha256: str
    duplicate: bool


class CompletionResponse(BaseModel):
    conversation_id: str
    status: str
    duplicate: bool


class StatusJob(BaseModel):
    id: str
    conversation_id: str
    status: str
    stage: str
    attempts: int
    error_code: str | None
    error_message: str | None
    retryable: bool
    updated_at: str


class SessionStatusResponse(BaseModel):
    session_state: str
    consent_version: int
    consent_valid: bool
    session_id: str
    conversation_id: str
    upload_status: str
    received_chunks: list[int]
    id: str
    org_id: str
    device_id: str | None
    title: str
    source_type: str
    language: str
    status: str
    duration: float | None
    summary: str | None
    topics: list[str]
    entities: list[str]
    created_at: str
    ingested_at: str | None
    captured_at: str | None
    job: StatusJob | None
