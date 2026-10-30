# V1 access, consent and session contracts

## Organization and store access

Each account belongs to one organization. The app displays that authenticated organization and allows selecting assigned stores. Switching organization requires signing in to a separately provisioned account; this is not a multi-organization account-switching SaaS control plane. Bootstrap provisions the initial organization, owner and first store. Existing administrators retain their role. Administrators provision additional members with a privately shared initial password; there is no email invitation service or CRM.

| Operation | Owner/admin | Manager | Staff | Device bearer |
|---|---|---|---|---|
| Create stores, provision users, change retention, view organization audit, provision/revoke devices | Organization | Denied | Denied | Denied |
| Prepare capture | Authorized store | Assigned store | Assigned store | Denied |
| Raw session/transcript/audio/participant evidence | Organization | Assigned stores | Sessions created by self | No raw transcript/audio download; own session progress only |
| Shared findings | Approved sessions in authorized stores | Approved sessions in assigned stores | Approved sessions in assigned stores | Denied |
| Correct/approve findings and sessions; export | Organization | Assigned stores | Denied | Denied |
| Assign/approve/edit tasks | Organization | Assigned stores | Denied | Denied |
| Complete approved task | Authorized reviewer | Assigned-store reviewer | Assigned to self, with approved source | Denied |
| Upload chunks/status | Authorized session | Assigned-store session | Own session | Only session bound to that credential's device |
| Delete or withdraw | Authorized raw session | Assigned-store raw session | Own raw session | Upload cancellation only; no consent decisions |

Cross-organization and unauthorized-store objects return 404. Mutation dependencies enforce permissions, not only hidden buttons. Disabling/reassigning a member invalidates their sessions. A user cannot demote/disable their own administrator account through the membership editor, or demote the owner.

## Participant confirmation

1. Operator chooses authenticated organization/store, source, purpose and every participant reference. Names are not required.
2. `POST /api/v1/sessions` creates `awaiting_consent` and returns a private token for each participant once. `consent_attested` is accepted as legacy operator metadata only.
3. Each participant reads their notice and explicitly selects their decision. Links use the browser fragment `/#consent/TOKEN`; API requests carry `X-Consent-Token`, keeping tokens out of request URLs/access logs. Do not share these capability links publicly.
4. Confirmation notices disclose recording, transcription, local/explicitly configured cloud AI, business use, raw/reviewed access, retention, withdrawal and external-export limits. Grant links expire after 24 hours while pending. Granted links remain usable for withdrawal until the consent record expires/is deleted.
5. Stored evidence: session link, pseudonymous participant reference, notice/version, status, grant/withdrawal time and token hash. No identity verification, speaker identification or proof of a complete real-world roster is claimed. Handing a link to a participant is a workflow aid, not authentication of that person's legal identity.
6. Every current-round participant must grant; the operator separately validates roster, source and recording indicator. Neither login acceptance nor a checked operator box grants participant consent.
7. A changed roster invalidates the consent round; earlier confirmations remain as superseded evidence until retention/deletion. Old capability links are revoked.

The software implements a policy workflow, not a legal determination that recording is permitted in a jurisdiction. The pilot organization must establish its approved purposes, participant process and retention rules.

## Backend session states

Processing `status` remains separate for compatibility (`awaiting_audio`, `queued`, `processing`, `complete`, `failed`, `restricted`). `session_state` is authoritative for capture and review.

```text
awaiting_consent --all grants + conditions--> ready
ready --start--> recording --pause--> paused
paused --consent + explicit conditions/resume--> recording
recording/paused --stop--> finalizing
ready --stop (authorized imported/partial audio)--> finalizing
finalizing --integrity acceptance, unique job--> processing
processing --valid output--> needs_review
needs_review --each finding approved/rejected + session approval--> approved
processing --failure--> failed --eligible retry--> processing
ready/recording/paused --interruption--> interrupted
interrupted --consent and conditions revalidated--> ready
eligible unfinished states --cancel--> cancelled
```

Transitions require `expected_state` and `consent_version`; stale or invalid operations fail with 409. One operator/device cannot have duplicate active captures. Audio completion requires current consent, validated capture conditions and finalizing state. Chunks/whole-file checksums, contiguous sequences and a unique processing-job constraint prevent partial/double ingestion. Decoding/duration validation occurs in the durable worker: corrupted audio becomes failed, never successful.

The browser stops actual MediaRecorder capture before awaiting stop/pause network calls where applicable. It interrupts on an observed offline/background/device-error event or failed consent polling. Cross-device withdrawal is observed through approximately two-second polling while the page is running; network/browser suspension prevents a guaranteed remote physical stop. App-owned active microphone tracks are released when capture is cancelled or unmounted. The app never starts the microphone on login or restores it automatically after reload.

Active captures report a five-second heartbeat. An independent backend watchdog expires an unconfirmed recording/paused session after approximately 20 seconds and requires revalidation, even if an AI job is running. This backend lease cannot force a suspended/offline physical microphone to stop. Only session metadata/ID is recoverable after reload. Audio stays in browser memory until upload and is not promised to survive suspension/reload. After interruptions, the user may revalidate and finalize an available partial recording or prepare another capture. Physical recording indicators remain unverified.

Withdrawal immediately invalidates processing on the backend, restricts results and deletes local session audio. Operator capture stops locally when they withdraw; participant-link withdrawal reaches the operator through polling. Worker calls run outside mutation locks, then validate consent/version/job existence again before committing. Deletion cascades session records and removes temporary/original/normalized audio, so pending model work cannot recreate the deleted record.

## Review and evidence

Every genuine result becomes `needs_review`. Findings have unreviewed/corrected/approved/rejected/restricted states. Only reviewers can approve sharing, after checking accuracy and identifying information. Every current finding must be approved or rejected before the session enters `approved`. Shared APIs and exports require both finding and session approval plus current consent. Suggested tasks remain non-executable and require approved source records before approval/completion. Assignment uses an active store-authorized member ID, not an arbitrary owner label. Due dates are operator-set unless a reviewer explicitly marks a spoken commitment and supplies an exact supporting transcript quotation; the reviewer remains responsible for interpreting its meaning and date. The model never generates an authoritative task deadline.

Evidence quotes must be exact contiguous transcript text. Only the server associates a unique segment match with a timestamp. Fact/inference is explicit. Confidence is the model's own uncalibrated estimate (`uncalibrated_model_estimate`), not an accuracy measurement. Impact, recommendation, priority rationale and success metric may be null when unsupported; no revenue or deadline is synthesized.

Transcript corrections clear timestamps, restrict findings and reset tasks. `POST /conversations/{id}/reanalyze` archives old findings/tasks as superseded and reuses the corrected transcript without another microphone/STT call. Approval must be repeated. Review events retain actor, target, action, field names and time without copying entire transcript versions into an audit log.

## Retention and deletion

Defaults: pending/raw audio up to 24 hours, transcripts 30 days, derived records 30 days, consent evidence 30 days. With `NEUAURA_RETAIN_AUDIO=false`, audio is removed earlier immediately after transcription. Organization settings can bound these periods independently; the worker sweeps at startup and about hourly while running, so expiration is not an exact wall-clock erase guarantee. The full session is deleted after the longest configured period, and abandoned unsubmitted sessions expire after 24 hours.

When a transcript expires, its quotations expire too and dependent findings become restricted. Consent expiry blocks sharing/processing. Derived-record expiry removes summaries/findings/tasks. API deletion is synchronous for local records/files and coordinated with the worker. Cancelled-session metadata remains until expiry/deletion. Minimal deletion/export/audit event IDs remain for administrators. No application-level database encryption is claimed; enable an approved encrypted disk/backup policy and use HTTPS outside loopback. FileVault status is unverified.

The private pre-migration backup under `local-data/backups/`, operator-managed backups and already downloaded exports are separate copies. Automatic erasure/recall of these is not implemented. External AI remains disabled by default; if deliberately enabled, that provider's retention/deletion terms require a separate approved policy.
