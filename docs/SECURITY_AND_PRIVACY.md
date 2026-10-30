# Security and privacy

> V1 update (29 October 2026): see [current workflow](V1_USER_GUIDE.md), [access/consent/retention](V1_ACCESS_AND_LIFECYCLE.md) and [current verification report](V1_IMPLEMENTATION_REPORT.md). Earlier test counts and operator-attestation instructions below describe the original MVP; participant confirmation and review now govern capture and sharing.


## Implemented controls

- Loopback binding by default. Authentication required for all business records. A first-run setup token is generated in the private local data folder (POSIX mode 600 on macOS; inherited private NTFS ACL on Windows) and deleted after bootstrap. No public self-provisioning endpoint or default password.
- PBKDF2-SHA256 passwords with independent random salts and 600,000 iterations; constant-time comparisons. Auth sessions use random tokens, SHA256 storage, 12-hour expiry, HttpOnly and SameSite=Strict cookies. CSRF token required on cookie-authenticated mutations; unsafe cross-origin requests are rejected.
- TrustedHost allowlist reduces DNS rebinding. Allowed hosts must be configured for a private HTTPS phone URL. CSP, no-sniff, same-origin referrer policy, frame denial, no-store API responses and a self-only microphone permission policy are set.
- Organization ownership derives from authentication. Tenant filters apply to conversations, insights, tasks, devices, aggregates, audio and audit reads. Devices are additionally restricted to their own upload sessions. Cross-tenant record access returns 404.
- Per-device random credentials are shown once and stored only as hashes. Authorization/revocation is checked on every device call; registry reads exclude hashes/secrets. Only admins provision/revoke. A device cannot authorize another device or use dashboard routes.
- Login/bootstrap limits, device request limits and session-creation limits use sliding windows. These are local to one process; deployment-wide distributed rate limits/quotas are not implemented.
- Chunk and whole-file checksums, idempotency, upload limits, supported MIME checks, actual decoding, bounded decoded duration, silence detection and exact evidence verification.
- Audio outside the database in private server-generated UUID paths. `.env`, database, models and audio are ignored by Git. No client filename controls storage location. API returns controlled audio only after tenant authentication and only if retention is enabled.
- Local speech recognition with local-only model loading. Loopback Ollama by default. Remote transcript processing requires explicit configuration and HTTPS; redirects/environment proxy inference are disabled. No silent cloud fallbacks.
- No HTML rendering of transcripts/AI output; React escapes displayed text. Transcript instructions are explicitly untrusted data in the extraction prompt. Schema and evidence checks do not prove semantic correctness.

## Consent and recording

The user must explicitly attest appropriate authorization before capture/upload. The microphone starts only through a user action and shows visible recording state. The attestation actor, server time and notice version are stored. This attestation does not establish every participant's consent or legal compliance. The business must determine the applicable requirements and tell all participants what is captured, why, who can access it, and how to request deletion. Do not use covert recording.

Default notice: "Record only conversations you are authorized to capture and process. Inform all participants as required. Recordings may contain personal information. Insights are AI interpretations with possible errors. A manager should verify supporting evidence before acting."

No speaker biometrics, face capture, GPS, emotion diagnosis or identity profiling is implemented. Prefer brief test recordings without sensitive personal information.

## Retention and deletion

Default conversation retention is 30 days (`NEUAURA_RETENTION_DAYS`). Hourly worker cleanup runs on startup and deletes expired conversations and their dependent records/files. Open uploads older than 24 hours are removed. If the service/worker is stopped, cleanup resumes on startup. Audio retention defaults off. During queued/failed speech recognition, input audio is temporarily retained for retry. After a transcript is committed, original and normalized audio are removed even if AI extraction later fails.

If audio retention is enabled, playback remains authenticated and files expire with the conversation. Manual deletion cascades transcripts, segments, insights, evidence, tasks, audio metadata, consent and job/session rows, removes media directories, and leaves a minimal audit entry (actor, target UUID, action, time). Database deletion does not guarantee secure physical erasure from SQLite free pages, SSD snapshots or independent backups; no secure-erase claim is made. Backup retention needs an operator-defined policy. Audit events contain no conversation text and currently have no separate expiration policy.

## Scope and remaining production work

This is a single-machine MVP, not a certified or penetration-tested production system. First-run UI provisions one workspace/admin. Multi-user invites, role administration, SSO/MFA, password reset, credential rotation, account deletion, encryption at rest/key management, shared quotas, multi-worker claims/leases, malware sandboxing, formal security review and regulatory validation are not implemented. PostgreSQL and physical hardware are not verified.

Use FileVault (macOS) or BitLocker/device encryption (Windows), with access-controlled backups. Do not expose the development server or Vite publicly. For phone testing, use private Tailscale Serve with tailnet access control, trusted HTTPS, Secure cookies and configured allowed hosts. Read [phone setup](PHONE_TESTING.md). Public production deployment needs its own reviewed identity, TLS, rate-limit, retention and operations configuration.

Windows open-file locks: playback permission is revoked when consent is withdrawn. Physical removal of files held open by a decoder/browser may be delayed; durable cleanup markers survive restart, and the independent watchdog retries every two seconds. Pending cleanup blocks new upload writes for that session. When audio retention is disabled, original audio, normalized audio and uploaded chunks are removed after transcription. See [Windows setup](WINDOWS_SETUP.md).
