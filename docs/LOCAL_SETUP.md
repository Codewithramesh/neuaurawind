> For the installed Mac, use the Desktop **NEUAURA B2B** shortcuts. Ollama and qwen3:4b have now been installed, with weights in this project under `models/ollama/`. See [START HERE](START_HERE.md). The instructions below also describe a fresh installation.

For Windows x64, use [Windows setup](WINDOWS_SETUP.md) and the `.cmd` launchers. The Mac-specific paths below describe the existing Mac installation.

> V1 update (29 October 2026): see [current workflow](V1_USER_GUIDE.md), [access/consent/retention](V1_ACCESS_AND_LIFECYCLE.md) and [current verification report](V1_IMPLEMENTATION_REPORT.md). Earlier test counts and operator-attestation instructions below describe the original MVP; participant confirmation and review now govern capture and sharing.


# Local setup on macOS

## Prerequisites and verified runtime

Tested: Apple Silicon arm64, macOS 26.5.2, Python 3.12.0, Node 22.23.3, npm 10.9.9. Use Python 3.12 and Node 22.12 or later. Python 3.14 was available but was not selected for ML-wheel compatibility. No CUDA, GPU-specific packages, paid hosting or production domain are needed. CPU int8 is the supported tested speech mode.

```bash
cd /Users/mukkararamesh/Documents/ChatGPT/neuaurab2b
./scripts/setup.sh
.venv/bin/python scripts/download_model.py
./scripts/start.sh
```

Setup creates `.venv`, installs exact Python dependency pins, copies safe configuration if absent, runs the initial Alembic migration, runs `npm ci` and builds the frontend. Downloads require internet. The model command separately downloads tiny.en (~75 MB); there is no automatic download at runtime. Models live outside source control under `models/`.

First run: read `cat local-data/setup-token` after startup. Open `http://localhost:8000`, enter the token, business name, industry, email and a password of at least 12 characters. Then sign in. The token is deleted on successful setup. Never send this token or your passwords in screenshots/chat/logs. There is no default account.

## Local AI

1. Install native [Ollama](https://ollama.com/download).
2. Run `ollama serve` in another terminal, or launch its native app if it already serves the API.
3. Run `ollama pull qwen3:4b`. This model is roughly 2.5 GB; allow several GB disk/RAM and CPU processing time. The project does not download it automatically. A larger capable model can improve structured evidence extraction at greater resource cost.
4. Default `.env`: provider `ollama`, base `http://127.0.0.1:11434`, model `qwen3:4b`. Restart NEUAURA after configuration changes.
5. Check Settings → Intelligence engines. Speech model readiness means model files exist; Ollama readiness checks the installed model listing. Neither indicator guarantees transcript/extraction quality.

The [Ollama structured-output API](https://docs.ollama.com/capabilities/structured-outputs) accepts a JSON schema in `format`; NEUAURA validates the returned JSON and exact evidence again. An unavailable model yields `AI_UNAVAILABLE`, not mock output.

### Optional compatible remote provider

Only configure this if you deliberately authorize transcripts to leave the Mac. Audio itself remains local in this implementation. Put secrets in `.env`, never source control:

```dotenv
NEUAURA_EXTRACTION_PROVIDER=openai_compatible
NEUAURA_LLM_BASE_URL=https://YOUR_PROVIDER_HOST/v1
NEUAURA_LLM_MODEL=YOUR_SUPPORTED_MODEL
NEUAURA_LLM_API_KEY=YOUR_PRIVATE_KEY
NEUAURA_ALLOW_CLOUD=true
```

The endpoint must support `/chat/completions` and JSON-schema structured output. No vendor-specific compatibility or live cloud account has been verified. No automatic fallback exists. Non-loopback HTTP endpoints are rejected. Private-LAN inference also requires explicit remote opt-in and HTTPS.

## Speech model and language

Tiny English is installed in this workspace and real transcription was tested. A model install can be repeated safely. To use a different supported small model:

```bash
.venv/bin/python scripts/download_model.py --model base.en
# Set NEUAURA_WHISPER_MODEL_PATH=models/faster-whisper-base.en in .env, then restart.
```

Multilingual `tiny`/`base` can be downloaded explicitly. Set `NEUAURA_LANGUAGE=hi` with a multilingual model for Hindi experiments; Hindi is NOT VERIFIED. English-only `.en` models cannot support Hindi. There is no speaker diarization, translation, identity recognition or calibrated sentiment/confidence scoring.

## Development, migration, checks, shutdown

```bash
./scripts/dev.sh
# Browser: http://localhost:5173, API upstream: localhost:8000
# The Vite proxy preserves same-origin cookies and CSRF checks.
.venv/bin/python -m alembic -c backend/alembic.ini current
.venv/bin/python -m alembic -c backend/alembic.ini upgrade head
./scripts/status.sh
./scripts/test.sh
(cd frontend && npm run e2e)
```

Both servers bind loopback. Ctrl+C in `start.sh` or `./scripts/stop.sh` stops the single service; Ctrl+C in `dev.sh` stops both. The dev launcher reports if either process exits. A built dashboard is served by the backend, so production-style local use needs only port 8000. Do not run more than one worker/process. `--reload` is intentionally not used around the persistent job worker.

New migrations: edit models, then `.venv/bin/python -m alembic -c backend/alembic.ini revision --autogenerate -m 'Describe the change'`; review the generated migration before `upgrade head`.

## Persistence and recovery

Default database: `local-data/neuaura.sqlite3`, plus WAL/SHM. Media: `local-data/uploads/UUID/`. Restarting keeps sessions, conversations, transcripts and tasks. Interrupted jobs are requeued at startup. SQLite backups should use a consistent database backup while stopped or SQLite's backup API, with access controls equivalent to live data. Never copy just the DB while ignoring an active WAL.

A missing speech model leaves a retryable failed job with setup instructions. Install it and choose Retry. If AI fails after speech, its transcript remains available; retry reuses it. Non-retryable corrupted/silent/duration failures require a new recording. Retry is capped at five attempts. Logs contain processing errors and identifiers, not transcripts, prompts or credentials.

PyAV is pinned to 16.0.1 because 19.0.2 broke faster-whisper 1.2.1's `metadata_errors` argument. Keep lockfiles together and run `scripts/verify_real.py` after changing audio dependencies.
