# NEUAURA B2B V1 — repository audit

Audit date: 29 October 2026 (Asia/Kolkata). Baseline: commit `9cb33df`, existing FastAPI/SQLAlchemy/Alembic/SQLite and React/TypeScript/Vite application. Work was performed in the existing repository, on `codex/v1-consent-lifecycle`.

| Area | Baseline finding | V1 implementation |
|---|---|---|
| Authentication | Real password hashing, hashed cookie sessions, CSRF, setup-token bootstrap, sign-out, rate limiting | Preserved; initial store onboarding, owner role, active-member check, permission changes invalidate sessions |
| Organization isolation | Real `org_id` checks; administrator role used for provisioning | Preserved and extended with store assignments and owner/admin/manager/staff permissions |
| Store model | Missing | Stores, memberships, scoped UI selector, store-bound sessions/devices and assignment validation |
| Participant consent | Operator attestation only, stored when upload was created | Independent participant confirmation links, versioned decisions, purpose/retention notice, withdrawal and restriction |
| Capture lifecycle | Browser-only recording states; backend primarily tracked processing | Backend-enforced session state machine, expected-state/version checks, duplicate-capture protection and interruption recovery |
| Browser capture | Real MediaRecorder, pause/resume, preview, chunk integrity; physical microphone unverified | Preparation before microphone permission, source labeling, explicit revalidation, stop on observed network/background/consent interruption |
| Ingestion | Real authenticated, resumable, checksum-protected chunk API | Preserved; participant consent and finalized session now required; device cannot manufacture consent |
| Speech | Actual local faster-whisper with installed English weights | Preserved; validate nonempty text/segments and duration boundaries |
| AI | Actual Ollama/Qwen3 4B, strict schema, exact quotations and server-derived timestamps | More business categories and optional impact/action/measurement/rationale fields, explicit uncalibrated-score labeling |
| Worker | Persistent jobs, retries, transcript reuse, startup recovery | Model calls no longer block withdrawal/deletion locks; recheck consent/version before writes; reanalysis of corrected transcripts |
| Human review | Suggested tasks could be edited/approved; findings were shared immediately | Finding correction/rejection/approval/restriction, transcript correction, session approval, review history, sharing check |
| Dashboard | Real data, but unreviewed findings contributed | Approved findings from approved sessions only, review queue, distinct-session themes, store and date filtering |
| Tasks | Suggested/approved/completed/dismissed, free-text owner | Member ID assignment, store validation, task title, operator-set deadline basis, review prerequisites and staff completion permission |
| Exports | Missing | Reviewer-authorized JSON/CSV of approved records; CSV formula neutralization; export audit event |
| Retention | Default audio deletion after transcript, whole-conversation expiration | Organization policy for pending/raw audio, transcripts, derived records and consent; source expiry restricts findings |
| Devices | Real per-device credentials, heartbeat, errors, revocation and CLI simulator | Typed provider boundary, operator-prepared sessions, explicit simulated controls, unknown physical indicators and transport rejected |
| Deployment | Local Mac launcher, production SPA, private HTTPS phone instructions | Same local architecture; no paid service, public exposure or automatic cloud fallback added |
| Test doubles | Providers in `tests/` and isolated browser-test server; production uses real providers | Still test-only; new UI/API tests explicitly identify doubles; genuine AI tests use generated speech in isolated databases |

Existing `.env`, model files, dependency installations and user records were preserved. A private SQLite backup was made before migration; the migration was first exercised on a database copy and checked for row-count, credential and foreign-key preservation. Existing operator attestations are not converted into participant consent. Existing findings are unreviewed and require revalidation/review to enter shared intelligence.

Physical microphone/phone tests and physical wearable integration were not established by the audit. Earlier browser test results belong to the previous build; they do not establish V1 browser or phone acceptance.
