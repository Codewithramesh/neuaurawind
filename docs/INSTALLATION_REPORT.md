# Installation completed on this Mac

> V1 update (29 October 2026): see [current workflow](V1_USER_GUIDE.md), [access/consent/retention](V1_ACCESS_AND_LIFECYCLE.md) and [current verification report](V1_IMPLEMENTATION_REPORT.md). Earlier test counts and operator-attestation instructions below describe the original MVP; participant confirmation and review now govern capture and sharing.


27 October 2026. The new B2B source remains at:

**`/Users/mukkararamesh/Documents/ChatGPT/neuaurab2b`**

## What was done

- Confirmed the existing Python environment, Node, VS Code, local database and speech weights.
- Installed **Ollama 0.40.11** through Homebrew, including its required dependencies. The project still uses its existing Python 3.12 virtual environment; Homebrew's Python dependency does not replace that interpreter.
- Downloaded and tested local LLMs. Selected **Qwen3 4B** after the smaller trial model misclassified a product-size request; removed the unused trial model. Final AI weights occupy about **2.3 GiB**, plus **75 MiB** for Whisper.
- Configured local-only inference, no thinking, an 8,192-token context, one active model/request and a one-minute idle unload timeout for this 8 GB machine.
- Fixed source-evidence timestamp grounding and added regression tests. Ran 47 backend tests, 9 frontend tests, production build, real restaurant/retail audio tests, real task approvals and the live simulator/restart/revocation workflow.
- Added one-click service controls, private setup-token copying, a Finder link to the source and a VS Code workspace/tasks file. Tested service stop/start and verified the shortcut files.
- Copied the existing first-run setup token to the clipboard without exposing its value in chat. The Desktop helper can copy it again.
- Left NEUAURA and its local model server running at `http://localhost:8000` and loopback port 11434.

## Easy access

Open **Finder → Desktop → NEUAURA B2B**:

- **Start NEUAURA.command** starts the app and AI and opens the browser.
- **Stop NEUAURA.command** stops the services managed by this project.
- **Copy setup token.command** copies the private first-run token. Paste it into the browser, then choose your own email/password.
- **Project files** opens the real source directory.
- **NEUAURA.code-workspace** opens the project in VS Code.

No login-startup agent or public tunnel was installed. Use Start after restarting the Mac.

## File locations

| Files | Absolute location |
|---|---|
| Project/source | `/Users/mukkararamesh/Documents/ChatGPT/neuaurab2b` |
| Desktop controls | `/Users/mukkararamesh/Desktop/NEUAURA B2B` |
| Saved database | Project `local-data/neuaura.sqlite3` |
| Private setup token | Project `local-data/setup-token` (deleted after account creation) |
| Settings | Project `.env` |
| Whisper weights | Project `models/faster-whisper-tiny.en` |
| Ollama/Qwen weights | Project `models/ollama` |
| Ollama executable | `/opt/homebrew/bin/ollama` |
| Logs | Project `local-data/logs` |
| Full test results | Project `docs/TEST_REPORT.md` and `local-data/verification` |
| Beginner instructions | Project `docs/START_HERE.md` |

## Remaining user actions and access limits

Create the personal workspace by pasting the setup token and choosing an email/password. No production password/default account was chosen for you. Then grant the actual browser/macOS microphone permission when you deliberately start recording.

Direct Codex control of VS Code was not enabled. Browser access to the separate test origin was declined, so the real audio/AI checks used local APIs and isolated databases. No alternate browser path was used to work around that decline. Physical MacBook/phone microphones and the latest real-AI browser interaction remain NOT VERIFIED.

## Older Desktop project

An older, unrelated project already existed at `Desktop/Neuaura`. I initially placed the B2B shortcuts there and overwrote its Mac launcher. The new shortcuts were moved into the dedicated **NEUAURA B2B** folder. The older launcher was recreated to launch its own `server.mjs` on port 4173, matching its existing Windows launcher's behavior. The previous untracked launcher bytes were unavailable, so byte-for-byte restoration is not claimed. No older application code/data was imported into this B2B project.

References: [Homebrew Ollama formula](https://formulae.brew.sh/formula/ollama), [official Qwen3 4B model](https://ollama.com/library/qwen3:4b), [Ollama thinking controls](https://docs.ollama.com/capabilities/thinking).
