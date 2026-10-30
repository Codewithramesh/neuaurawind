# Local model storage

Model weights are ignored by Git. The application only opens explicitly installed local model files; it never downloads them during a recording/job.

```bash
.venv/bin/python scripts/download_model.py                # tiny.en ≈75 MB
.venv/bin/python scripts/download_model.py --model base.en # ≈145 MB
```

Set `NEUAURA_WHISPER_MODEL_PATH` to the corresponding directory if not using tiny.en. `.en` models are English-only. `tiny` and `base` are multilingual but Hindi has not been verified.

The tested runtime uses faster-whisper 1.2.1, CTranslate2 4.8.4, PyAV 16.0.1, CPU int8 on macOS arm64. Missing model files produce `MODEL_MISSING` and a retryable failure. Native whisper.cpp is a documented future alternative, not an implemented adapter.

The installed Qwen3 4B LLM weights live in `models/ollama/` because the Desktop launcher sets `OLLAMA_MODELS` to that directory. Ollama itself is installed by Homebrew at `/opt/homebrew/bin/ollama`. The selected model is roughly 2.5 GB. Future model changes/downloads remain explicit; the launcher never downloads replacements automatically. See `docs/LOCAL_SETUP.md`.

Windows: run **Download models.cmd** from the project, or `.\.venv\Scripts\python.exe scripts\download_model.py`. A fresh native Ollama installation uses its own model store (`%USERPROFILE%\.ollama\models` by default). The launcher preserves an existing project model store on Mac but does not relocate a running native Ollama service. See [Windows setup](../docs/WINDOWS_SETUP.md). Windows speech-engine execution still requires a native acceptance run.
