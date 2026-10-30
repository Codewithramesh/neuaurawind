# NEUAURA on Windows

Native Windows x64 support was added on 30 October 2026. No WSL, Git Bash, Docker, Homebrew or macOS files are needed to run it. The same backend, dashboard, consent/review workflow, local transcription, local AI and device simulator are used on both systems.

**Verification status:** application regressions and actual launcher start/stop/restart are tested on macOS. Windows branches and Windows dependency wheel availability are checked here; a native Windows run, microphone recording, desktop shortcuts and NTFS permissions still need execution on a Windows PC. The included `compatibility.yml` workflow runs native macOS/Windows checks when this version is pushed to GitHub; the report records the checks completed before publication. Check the repository’s Actions tab for subsequent native CI results. Physical wearable controls remain unimplemented on either OS.

See the [implementation and verification report](WINDOWS_COMPATIBILITY_REPORT.md) for exact coverage.

## Install once

Use Windows 11 x64, or Windows 10 22H2 x64 where its support policy permits. Windows ARM64 and 32-bit Windows/Python are outside this build's supported target. Keep several GB free for dependencies/models; the default AI download is about 2.5 GB. Eight GB RAM can run the small models with limited headroom; CPU inference can take time.

Install these official prerequisites, then reopen terminals/VS Code so PATH updates take effect:

1. [Python 3.12 for Windows](https://www.python.org/downloads/windows/): select the **64-bit** installer, include the Python launcher (`py`), and enable the PATH option. `py -3.12 --version` should work. This project currently targets Python 3.12.
2. [Node.js](https://nodejs.org/en/download): Node **22.12 or newer**, with npm. The verified Mac runtime uses Node 22; the CI uses Node 22 on both platforms.
3. [Microsoft Visual C++ v14 x64 runtime](https://aka.ms/vc14/vc_redist.x64.exe), required by the speech engine. This installer may ask for administrator approval. [Microsoft requirements](https://learn.microsoft.com/en-us/cpp/windows/latest-supported-vc-redist?view=msvc-170), [CTranslate2 requirements](https://opennmt.net/CTranslate2/installation.html).
4. [Ollama for Windows](https://ollama.com/download/windows). Its native application usually runs the local API in the background on port 11434. See the [official Windows guide](https://docs.ollama.com/windows).
5. Optional: [VS Code](https://code.visualstudio.com/) with Microsoft's Python extension. Git is only needed if you clone/push instead of transferring a source ZIP.

Get the complete source from [Codewithramesh/neuaurawind](https://github.com/Codewithramesh/neuaurawind) using **Code → Download ZIP**, or clone it from a terminal with Git installed:

```powershell
git clone https://github.com/Codewithramesh/neuaurawind.git
cd neuaurawind
```

Put this updated source folder somewhere writable and private, for example:

```text
C:\Users\YOUR_NAME\Projects\NeuauraB2B
```

The source includes `backend`, `frontend`, `scripts`, `models/README.md`, and `Setup NEUAURA.cmd`. Copying a `.venv` from a Mac will not work. Do not transfer Mac `.venv`, `frontend/node_modules`, `frontend/dist`, `.env`, `models/ollama`, or `local-data` as part of a fresh install. Windows creates its own environment, config, model store and workspace. Keep live business data out of shared folders, network drives and OneDrive; SQLite and local permissions need a private local NTFS folder. If your Desktop is redirected to OneDrive, only shortcuts are placed there; keep the project/data elsewhere.

Double-click **Setup NEUAURA.cmd**. It creates `.venv\Scripts\python.exe`, installs pinned dependencies, creates `.env` only when absent, builds the dashboard, runs migrations, and installs shortcuts in **Desktop → NEUAURA B2B**. It preserves existing configuration/accounts/data. It refuses to overwrite an unrelated shortcuts folder or reuse a Mac virtual environment.

Then double-click **Download models.cmd**. This is an explicit internet download: it installs the tiny English speech model (about 75 MB), starts the local services, and pulls the configured Ollama model (`qwen3:4b` by default). Keep the window open until it finishes. Downloads are never triggered during a recording or processing job.

If a shortcut cannot be installed because of a desktop policy, run `scripts\setup.cmd --no-shortcuts`; the root `.cmd` launchers still work. No PowerShell execution-policy change is required: the app uses inline Windows PowerShell commands for native ACLs/shortcuts.

## Every day

1. Double-click **Start NEUAURA.cmd** in the project, or **Start NEUAURA** in the Desktop shortcuts folder. Open [NEUAURA](http://localhost:8000). The app stays on this computer's loopback interface.
2. On a new workspace only, run **Copy setup token.cmd** (or its Desktop shortcut), paste into the browser's Setup token field, and choose your business details/email/password. There is no default account. An existing workspace keeps its login.
3. Use **New session** → select the store and **Computer / browser microphone** → list participants/purpose → have every participant personally confirm → prepare the source → explicitly start recording → stop and finalize → wait for processing → review the transcript/findings → approve findings/session before they appear in shared views. [Full workflow](V1_USER_GUIDE.md).
4. Double-click **Stop NEUAURA.cmd** when finished. Saved records persist. It requests graceful server shutdown and stops only an Ollama process this launcher started and can still identify. An already-running native Ollama tray application is reused and left running; quit it from its tray icon if desired.

For a recording, use a current Chrome or Edge browser and allow the microphone for `localhost:8000`. Also enable **Settings → Privacy & security → Microphone → Microphone access**, and permission for desktop apps. Keep the page visible and computer awake. File upload accepts supported WAV/WebM/MP4/M4A/MP3/FLAC/Ogg formats. The OS/browser may interrupt recording on sleep or lock; native background recording is not implemented. Phone use needs trusted private HTTPS; the phone's `localhost` points at the phone. [Phone setup](PHONE_TESTING.md).

## Commands and VS Code

Open the project folder or `NEUAURA.code-workspace` in VS Code. **Terminal → New Terminal** opens PowerShell; **Terminal → Run Task** offers start, stop and tests. The tasks select the Windows Python automatically. If VS Code already remembers a different interpreter, use **Python: Select Interpreter** and select `.venv\Scripts\python.exe`.

From PowerShell in the project folder:

```powershell
.\scripts\setup.cmd                 # initial install/update; does not reset data
.\scripts\download-models.cmd       # explicit model download
.\scripts\start.cmd
.\scripts\status.cmd
.\scripts\stop.cmd
.\scripts\test.cmd                  # backend, frontend and production build
.\scripts\dev.cmd                   # separate Vite developer UI; stop normal app first
```

Virtual environment activation is optional. For individual Python tools:

```powershell
.\.venv\Scripts\python.exe scripts\download_model.py
.\.venv\Scripts\python.exe -m alembic -c backend\alembic.ini current
.\.venv\Scripts\python.exe scripts\install_desktop_shortcuts.py
```

The simulator also runs with that interpreter; replace the POSIX command prefix in [device instructions](DEVICE_API_SPEC.md) with `.\.venv\Scripts\python.exe`. Use Windows paths for audio/credential files. Keep credentials private; `chmod` is a macOS/Linux command. The simulator transfers a real file and is explicitly simulated hardware.

## File locations

Paths below are relative to the folder where you placed the project:

| Item | Windows location |
|---|---|
| Source and launchers | Your `NeuauraB2B` project folder |
| Python environment | `.venv\Scripts\python.exe` |
| Configuration | `.env` (never commit) |
| Workspace database | `local-data\neuaura.sqlite3` and WAL/SHM files |
| Audio, when retained | `local-data\uploads\SESSION_ID\` |
| Service logs | `local-data\logs\server.log`, `ollama.log` |
| Process state/shutdown controls | `local-data\server-process.json`, `server-stop.json`, `ollama-process.json` |
| Locked-file deletion retry markers | `local-data\cleanup-pending\` |
| First-use token | `local-data\setup-token`, deleted after workspace creation |
| Speech model | `models\faster-whisper-tiny.en\` |
| Ollama models | Native Ollama store, normally `%USERPROFILE%\.ollama\models`; an explicit `OLLAMA_MODELS` override wins |
| Desktop shortcuts | Windows' actual Desktop location → `NEUAURA B2B` (including redirected Desktops) |

`NEUAURA_DATA_DIR` and `NEUAURA_WHISPER_MODEL_PATH` in `.env` can change these paths; relative paths resolve from the project root. For absolute Windows paths in `.env`, use forward slashes such as `C:/Users/YOUR_NAME/PrivateData/NEUAURA`. Leave `NEUAURA_DATABASE_URL` blank for the automatically constructed SQLite URL. Logs/process files follow the configured data folder. Startup protects that folder using an NTFS ACL for the current user and SYSTEM; a permission failure stops startup with an error. Use filesystem access controls on `.env`, external credentials and backups as well.

Do not copy a live SQLite database by itself: stop the app and take a consistent backup, including any uncheckpointed WAL. Moving existing Mac business data, retained audio paths and accounts to another machine needs a deliberate backup/restore operation; the fresh Windows setup does not do that migration automatically.

## Troubleshooting and acceptance

- **`py` or Node not found:** install the prerequisites and reopen the terminal/app. Python must be 3.12 x64. A copied `.venv` must be removed/renamed and recreated; preserve `.env`/`local-data`.
- **DLL load error:** install the official Visual C++ x64 runtime, restart the terminal and run setup again. No system FFmpeg command is needed; the pinned PyAV wheel supplies decoding libraries.
- **Ollama unavailable/model missing:** open Ollama, then run Download models. `ollama list` and Settings show the installed model. An already-running Ollama server controls its own model store and environment; project settings do not reconfigure that existing process. Remote/cloud inference remains disabled unless explicitly configured.
- **Data folder permission error:** use a private local NTFS folder you own. The app needs Windows PowerShell and permission to set its data ACL. Do not solve this by publishing data or opening the service to the network.
- **Port 8000 busy:** stop the previous app with its own launcher/terminal first. This launcher will not kill unrelated services or silently move the app. A server answering an occupied port is reused without claiming ownership; verify it is the intended NEUAURA instance.
- **Stop pending:** an active HTTP request may delay graceful shutdown. Let it finish, close playback and run Stop again. Windows open-file locks can delay physical audio deletion; access is revoked immediately and deletion is retried by the independent watchdog every two seconds and after restart. Keep the app running to finish cleanup. The default non-retention path also removes upload chunks.
- **Microphone denied:** check browser/site permissions and Windows microphone privacy settings, then refresh and prepare the source again. Do not approve recording silently.

On the first Windows PC, run `scripts\test.cmd`, then test a short, consented microphone recording through genuine transcription/AI output and reviewer approval. Test file upload, permission denial, withdrawal, restart persistence and Stop. This is the remaining physical Windows acceptance check; CI uses isolated test data and provider doubles for application regression, not a real microphone or downloaded LLM.
