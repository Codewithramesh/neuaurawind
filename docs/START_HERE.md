# Use NEUAURA on this Mac

For Windows x64, use [Windows setup](WINDOWS_SETUP.md) and the `.cmd` launchers. The Mac-specific paths below describe the existing Mac installation.

> V1 update (29 October 2026): see [current workflow](V1_USER_GUIDE.md), [access/consent/retention](V1_ACCESS_AND_LIFECYCLE.md) and [current verification report](V1_IMPLEMENTATION_REPORT.md). Earlier test counts and operator-attestation instructions below describe the original MVP; participant confirmation and review now govern capture and sharing.


The **new B2B project** is stored at:

`/Users/mukkararamesh/Documents/ChatGPT/neuaurab2b`

Your Desktop contains a separate **NEUAURA B2B** shortcuts folder:

`/Users/mukkararamesh/Desktop/NEUAURA B2B`

An older, separate project exists at Desktop/Neuaura. The new B2B project does not import its source or use its data. Use the new **NEUAURA B2B** shortcuts for this application.

## Start and stop without finding Terminal

1. In Finder, click **Desktop**, then open **NEUAURA B2B**.
2. Double-click **Start NEUAURA.command**. It starts the local AI service and NEUAURA, then opens `http://localhost:8000`.
3. Leave the services running while you use the app. Closing the browser does not stop them.
4. When finished, double-click **Stop NEUAURA.command**. It stops NEUAURA and the Ollama process started by this project's launcher. Saved data remains.

These launchers do not enable a login/background service on your Mac. Run Start again after restarting the laptop. A Terminal window appears when a .command file is launched; it tells you when it is safe to close the window. Model inference on this 8 GB Mac may take time, especially the first recording after startup.

## First-time account setup

The installer deliberately does not choose your password or create a default account.

1. Start NEUAURA.
2. Double-click **Copy setup token.command** in the Desktop shortcuts folder. It copies the private token without printing it.
3. In the browser, click the **Setup token** field and press **Command+V**.
4. Enter your business name, industry, email, and a password of at least 12 characters.
5. Click **Create workspace**, then sign in.

The setup token is deleted after successful account creation. Later you only need to sign in. Keep your password private.

## Record and review

Click **New conversation**, enter a title, attest that participants have given the required permission, then click **Start recording** and allow your browser's microphone prompt. Speak a short English test, stop, preview and choose **Analyze conversation**. The panel updates automatically. Review the saved transcript, exact evidence, AI insights and suggested tasks. Approve tasks only after checking the evidence.

You can choose **Upload a file** to analyze existing authorized audio. Default limits: 50 MB and ten minutes. Audio is removed after successful transcription by default; transcripts and intelligence persist in the database. Physical microphone behavior still needs the user's real permission/manual test.

## Find the project in Finder or VS Code

Double-click **Project files** in the Desktop shortcuts folder. That opens the actual project folder.

Double-click **NEUAURA.code-workspace** to open it in VS Code. In VS Code, **Terminal → Run Task** offers start, stop and automated tests. The configured Python interpreter is this project's `.venv/bin/python`.

Finder can also open any path with **Command+Shift+G**; paste the full project path above.

## Exact locations

| Item | Location |
|---|---|
| Source code | Project `frontend/`, `backend/`, `shared/`, `device-simulator/` |
| SQLite database | Project `local-data/neuaura.sqlite3` |
| Audio while processing | Project `local-data/uploads/` |
| Whisper English speech model | Project `models/faster-whisper-tiny.en/` |
| Ollama model weights | Project `models/ollama/` |
| Installed Ollama executable | `/opt/homebrew/bin/ollama` (Homebrew-managed) |
| Python environment | Project `.venv/` |
| Node frontend packages | Project `frontend/node_modules/` |
| Configuration | Project `.env` (private; do not share) |
| Background service logs | Project `local-data/logs/` |
| Test results | Project `docs/TEST_REPORT.md` and `local-data/verification/` |
| Desktop shortcuts | `/Users/mukkararamesh/Desktop/NEUAURA B2B/` |

To recreate these shortcuts later, run `.venv/bin/python scripts/install_desktop_shortcuts.py` from the project. The installer refuses to merge into an unrelated existing Desktop folder.

## Equivalent commands

From the project directory:

```bash
.venv/bin/python scripts/desktop.py start
.venv/bin/python scripts/desktop.py status
.venv/bin/python scripts/desktop.py stop
```

Ollama was installed through the official Homebrew registry. Its server is bound to `127.0.0.1:11434`, cloud features are disabled by the project launcher, and model files are stored inside this project. A server already running under another launcher is reused; this project's Stop only stops an Ollama process it started and still recognizes.
