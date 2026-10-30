# NEUAURA B2B V1

Complete Windows and macOS source: [Codewithramesh/neuaurawind](https://github.com/Codewithramesh/neuaurawind). On Windows, download the source ZIP from **Code → Download ZIP**, then follow [Windows setup](docs/WINDOWS_SETUP.md).

**V1 workflow upgrade (29 October 2026):** store-scoped roles, individual participant confirmations, backend session transitions, withdrawal, finding/session approval, reviewed-only dashboards, member-assigned tasks and approved exports. Start with [V1 usage](docs/V1_USER_GUIDE.md), [audit](docs/V1_AUDIT.md), [access/lifecycle](docs/V1_ACCESS_AND_LIFECYCLE.md) and [implementation/verification report](docs/V1_IMPLEMENTATION_REPORT.md). Existing account credentials are preserved; previous operator attestations are not treated as participant consent.

A local-first conversation-intelligence MVP for authorized business conversations, built from an empty directory. React + TypeScript + Vite, FastAPI, SQLAlchemy, Alembic, SQLite, local faster-whisper, and configurable structured LLM extraction.

**Implemented and exercised:** authenticated workspace, explicit microphone capture, file uploads, persistent jobs, real local transcription, evidence validation, dashboard aggregation, task review, tenant isolation, per-device credentials, resumable authenticated uploads, simulator, retention and deletion.

**Local AI is installed on the existing Mac:** Ollama + Qwen3 4B, plus local faster-whisper. Genuine restaurant and retail audio workflows, task review, and the device simulator have been exercised. **Physical MacBook/phone microphone acceptance is NOT VERIFIED**; earlier browser tests used a simulated microphone. No customer conversations or invented business statistics are seeded into your workspace. See [actual test results](docs/TEST_REPORT.md).

## Windows setup

Use native Windows x64 with Python 3.12, Node 22.12+, the Visual C++ x64 runtime and Ollama. Follow [Windows setup and usage](docs/WINDOWS_SETUP.md), then double-click **Setup NEUAURA.cmd**, **Download models.cmd**, and **Start NEUAURA.cmd**. Windows creates its own environment and workspace; do not copy a Mac `.venv`. Native Windows execution/microphone acceptance remains to be completed on a Windows PC.

## Start on this Mac

Open **Desktop → NEUAURA B2B → Start NEUAURA.command**. It starts the app and local AI, then opens **http://localhost:8000**. Use **Stop NEUAURA.command** to stop both. **Project files** opens the source folder; **NEUAURA.code-workspace** opens it in VS Code.

First use: double-click **Copy setup token.command**, paste into the browser's Setup token field, enter your business details, and choose your own email/password. The token is deleted after successful setup. There is no default admin account.

Equivalent commands:

```bash
cd /Users/mukkararamesh/Documents/ChatGPT/neuaurab2b
.venv/bin/python scripts/desktop.py start
.venv/bin/python scripts/desktop.py status
.venv/bin/python scripts/desktop.py stop
```

Read [START HERE](docs/START_HERE.md) for exact file locations and beginner directions. The backend-only `./scripts/start.sh` remains available for development; it expects the AI service to be running separately.

For a fresh machine: use Python 3.12 and Node 22.12+; run `./scripts/setup.sh`, then `.venv/bin/python scripts/download_model.py` (tiny English speech model, approximately 75 MB). Install Ollama and pull the configured model explicitly. All Python and Node dependencies are locked. Installation requires internet; speech and the configured local AI run locally.

## Configure AI extraction

Install the native [Ollama](https://ollama.com/download) app/CLI separately. NEUAURA does not install or download a large language model automatically. The default `qwen3:4b` download is roughly 2.5 GB; allow several GB of disk space and RAM, and expect CPU inference to take time.

```bash
cp .env.example .env  # only if .env does not already exist
chmod 600 .env
ollama serve         # separate terminal; omit if the Ollama app already serves it
ollama pull qwen3:4b
./scripts/start.sh
```

Settings shows the configured engines. The default transcript endpoint is loopback only. Remote endpoints require explicit `NEUAURA_ALLOW_CLOUD=true` and HTTPS; no automatic cloud fallback exists. See [setup](docs/LOCAL_SETUP.md) for an optional compatible API endpoint and model changes.

## Test with your computer microphone

1. Open `http://localhost:8000`, create the workspace, and sign in.
2. Configure Ollama as above for full extraction. Without it, speech transcripts still persist and the job displays an actionable failure.
3. Click **New conversation**, confirm store/source, enter a purpose and every participant reference, then **Prepare session**.
4. Each participant reads their notice and confirms only for themselves using **Participant review** or their private link. An operator attestation does not grant consent.
5. Recheck consent/roster/source/visible indicator, validate capture conditions, then explicitly **Start recording**. Allow the browser microphone permission.
6. Stop, preview and **Analyze conversation**. Interruption/withdrawal stops capture and requires revalidation; reload does not preserve in-memory audio.
7. A store manager/admin verifies findings, corrects/rejects them and approves the session. Only approved records enter shared intelligence. Review/assign suggested tasks separately. [Detailed V1 directions](docs/V1_USER_GUIDE.md).

Enable browser microphone permission and the OS microphone privacy setting (macOS System Settings or Windows Settings). Physical microphone permission cannot be verified by automated headless tests.

## Simulated wearable

In **Devices → Register device**, create an explicitly simulated device. Save its one-time credential in a private file (mode `600`) outside source control. Do not put credentials into firmware source or command-line arguments.

Prepare an operator-owned **Simulated wearable audio transfer** session in the app, obtain participant confirmations and finalize it. Then use its upload session ID:

```bash
.venv/bin/python device-simulator/submit.py /absolute/path/conversation.wav \
  --device-id YOUR_REGISTERED_DEVICE_ID \
  --credential-file /absolute/path/private-device-credential \
  --session-id OPERATOR_PREPARED_UPLOAD_SESSION_ID
```

Device credentials cannot create participant consent. The simulator submits real audio to the prepared session with chunk/whole-file checksums. Exit `0` means post-session processing succeeded and needs review; `2` means failed, `3` means still pending. Reuse the same prepared upload ID and file to resume. [Current device API](docs/DEVICE_API_SPEC.md).

A physical wearable provisions a distinct revocable credential, creates a session, submits encoded audio/chunks over HTTPS, completes the checksum handshake, and polls status. The ingestion boundary normalizes audio into mono 16 kHz PCM; speech, extraction, persistence, tasks and dashboard are exactly the same downstream components. [Hardware integration](docs/HARDWARE_INTEGRATION.md).

## Commands

```bash
./scripts/dev.sh                           # FastAPI :8000 + Vite :5173; Ctrl+C stops both
./scripts/status.sh                        # report running services
.venv/bin/python -m alembic -c backend/alembic.ini upgrade head
./scripts/test.sh                          # backend + frontend tests + production build
cd frontend && npm run e2e                 # Chrome, simulated mic, isolated TEST DOUBLE AI
# From repository root, only with generated speech/no human participants and real providers:
.venv/bin/python scripts/verify_real.py /absolute/path/generated-speech.wav --synthetic-fixture --require-complete
```

Stop the running server with **Ctrl+C** in its terminal or `./scripts/stop.sh` from this directory. Only one backend process/worker is supported. Local API docs: `/docs`; OpenAPI: `/openapi.json`; exported contract: `shared/api-contracts/openapi.json`.

## Documentation

- [Architecture](docs/ARCHITECTURE.md) · [Audio pipeline](docs/AUDIO_PIPELINE.md)
- [Local setup](docs/LOCAL_SETUP.md) · [Secure phone testing](docs/PHONE_TESTING.md)
- [Device API](docs/DEVICE_API_SPEC.md) · [Hardware integration](docs/HARDWARE_INTEGRATION.md)
- [Security & privacy](docs/SECURITY_AND_PRIVACY.md) · [Actual tests](docs/TEST_REPORT.md)
- [Limitations](docs/LIMITATIONS.md)
