# V1 — Computer and phone usage

Windows users: complete [Windows setup](WINDOWS_SETUP.md) and start with **Start NEUAURA.cmd**. The workflow below is shared; the Mac startup command/path describes the existing installation.

Project: `/Users/mukkararamesh/Documents/ChatGPT/neuaurab2b`

Start using **Desktop → NEUAURA B2B → Start NEUAURA.command**, or:

```bash
cd /Users/mukkararamesh/Documents/ChatGPT/neuaurab2b
.venv/bin/python scripts/desktop.py start
```

Open http://localhost:8000 on the Mac. Existing account credentials remain valid. Use Settings to add stores and provision manager/staff accounts. Select the intended store in the top bar. Each account belongs to one organization; its assigned role/stores determine access.

## Consent-controlled capture

1. Select **New conversation**. Confirm organization/store, enter title and a specific purpose.
2. List every participant reference separated by commas, including staff/operator if speaking. Use references such as “Guest 1, Staff 1”; names are unnecessary.
3. Explicitly select **Computer / browser microphone**, **Phone microphone**, **Uploaded authorized test audio**, or **Simulated wearable audio transfer**. The last source needs a registered simulated device assigned to the store.
4. Click **Prepare session**. No microphone is requested yet.
5. Hand the phone/Mac to each participant using **Participant review**, or let them open their private confirmation link on an authorized device. Each participant reads the explanation and makes their own decision. Confirmations are not identity verification; the operator must ensure the roster is complete. A participant who declines prevents capture.
6. Recheck the roster, consent, source and visible indicator; select the conditions checkbox and **Validate consent and prepare capture**.
7. For a microphone source, click **Start recording** and allow the OS/browser microphone permission. Keep the app in the foreground. Pause immediately when needed; recheck the conditions checkbox before Resume. Stop the recording before upload.
8. For an authorized import, click **Finalize authorized audio**, then choose a real file. For a simulator, simulate start/pause/resume/stop as needed, then choose real audio. These controls do not connect to physical hardware or generate fake audio.
9. Preview the finalized microphone audio and select **Analyze conversation**. Import/simulator audio can also be previewed. If transfer fails, keep the page open and retry: the same upload/chunks are reused. A reload cannot recover audio that existed only in browser memory.
10. The session opens in processing/review. Decoding, transcription and AI analysis happen after the session. Errors expose retry guidance; successful transcripts persist across an extraction retry.

A new participant or changed consent requires a fresh confirmation round. Stop/withdraw controls restrict results and remove audio. Participants may withdraw using their link or tell the operator to stop. Downloaded exports cannot be recalled.

## Review, approval and follow-up

1. Open a `Needs review` conversation from history. Read the transcript and summary; verify quotes and available timestamps.
2. Correct inaccurate findings, category, fact/inference, recommendation, uncertainty, priority rationale and proposed measure. Reject unsupported findings. Model confidence is not a measured probability of correctness.
3. If the transcript is wrong, use **Correct transcript and summary**. Corrections invalidate existing finding approvals/timestamps. Use **Re-analyze saved transcript** to generate new candidates from the correction; no new recording is made.
4. A manager/admin checks each finding's sharing checkbox and approves or rejects it. Once all findings are reviewed, select **Approve session for sharing**.
5. Only then do approved findings enter the shared dashboard and business-insights view. Theme counts use distinct sessions; one complaint does not establish a recurring/systemic issue.
6. Approve/edit/dismiss suggested tasks. Assign an active member authorized for that store. A due date is operator-set by default. A reviewer may mark a spoken commitment only with its exact transcript quote; review the meaning/date yourself. AI never silently establishes the deadline. Assigned staff may complete an approved task.
7. Use **Export approved records (JSON)** in Business insights. CSV is also available to authorized reviewers through `/api/v1/exports?format=csv` with the session's normal authenticated API context/store header. Raw transcripts/audio and unapproved findings are not exported.

Staff can capture/read their own raw sessions and see approved store intelligence; store managers can review raw sessions in their assigned stores; owners/admins manage organization access and policy.

## Phone connection

A phone cannot reach the Mac's `localhost`; an ordinary LAN HTTP address does not provide the trusted context required by browser microphone capture. Follow [PHONE_TESTING.md](PHONE_TESTING.md) for a private trusted HTTPS route (Tailscale Serve) and secure cookies/host allowlist. No public tunnel or external paid service was introduced.

The private phone route, physical phone microphone, background/lock behavior and actual Mac microphone remain acceptance tests on your hardware. Tailscale account/phone setup is not completed automatically. Keep the phone awake in the foreground and test a permission denial, interruption, withdrawal and a successful short recording before a pilot. When HTTPS cookies are enabled, use HTTPS for the entire session; do not mix the loopback HTTP sign-in with phone HTTPS.

## Recovery and deletion

Reopen New conversation and choose **Recover prepared session** to recover its metadata. No microphone activates automatically. After connection loss, return to the foreground, reconnect, revalidate consent and explicitly continue. If audio is unavailable, cancel the unfinished session and create another.

History supports search, lifecycle/processing filters and date filters. Dashboard dates and selected store scope its counts. Date filters/count buckets use UTC session-creation dates; they do not assume an uploaded file’s claimed capture date. Deleting an authorized conversation removes local audio, transcript, findings, tasks and participant/review records. Minimal audit metadata and private backups are separate; see [access and lifecycle](V1_ACCESS_AND_LIFECYCLE.md).
