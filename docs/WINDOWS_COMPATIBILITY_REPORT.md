# Windows compatibility report — 30 October 2026

The source now supports native Windows x64 and retains macOS support. This report separates implementation from actual execution evidence. [Windows installation and daily use](WINDOWS_SETUP.md).

## Changes

- Added root double-click Setup, Download models, Start, Stop and Copy setup token `.cmd` launchers, plus Windows setup/status/test/dev commands.
- Replaced Bash-dependent service startup with a shared Python launcher and server runner. Platform-specific virtual-environment paths, npm entry points, browser opening, clipboard, Desktop location and process flags are handled explicitly.
- Replaced unconditional Unix `fcntl` locking with cross-platform `filelock`. Process ownership uses checkout identity, creation time and command checks; reused PIDs and unrelated services are left alone.
- Added a private, instance-specific local shutdown request so the API can finish gracefully on Windows. A second server cannot acquire the same data-folder lock. macOS legacy process records are recognized during upgrade.
- Excluded `uvloop` on Windows, retained compatible speech/audio pins, and added pinned `psutil` for portable process identification.
- Built SQLite URLs using SQLAlchemy's URL API. Data/model paths remain relative to the project unless explicitly configured; logs and service state follow the configured data folder.
- Protected Windows data folders with native user/SYSTEM NTFS ACLs. Shortcuts use native Windows shell links and the actual Desktop location, without administrator-only symlinks. Desktop command windows keep errors visible.
- Added durable audio-deletion retries for Windows sharing violations. Withdrawal immediately revokes playback paths, pending cleanup blocks new upload writes, and an independent watchdog retries physical removal even while model work is running. Markers survive restart. Non-retained audio removes its upload folder after transcription.
- Removed Mac-only labels from the shared UI and made VS Code tasks, interpreter configuration and Playwright's Python path portable.
- Added native Windows/macOS GitHub Actions checks using a checkout path containing spaces, including Windows-only ACL, sharing-lock and shortcut tests.

## Executed on this macOS arm64 computer

| Check | Result |
|---|---|
| Backend regression suite | **84 passed**, two native Windows tests skipped |
| Frontend component/audio tests | **18 passed** |
| TypeScript and production dashboard build | Passed |
| Real subprocess startup, duplicate start, wrong-instance shutdown rejection, stop and restart | Passed, including data paths with spaces and Tamil characters |
| Detached desktop launcher, idempotent start and stop | Passed in an isolated workspace |
| PID reuse / other-checkout / unrelated-process protection | Passed |
| Simulated Windows file-sharing error, durable retry, access revocation and cleanup | Passed; the native sharing-lock test remains Windows-only |
| PyPI package metadata for CPython 3.12 Windows x64 | All **52** applicable pinned requirements have compatible wheels; this is not an installation/runtime test |
| npm lockfile Windows native build packages | Windows x64 esbuild and Rollup MSVC entries present |
| Genuine local faster-whisper + Ollama, generated restaurant speech | Browser upload and simulated wearable transfer both completed; real transcripts/findings produced and suggested tasks approved through the API |
| Updated real Mac installation | Restarted using shared launcher; health, dashboard and compiled asset returned HTTP 200 |
| Existing local workspace | All table row counts and account IDs/emails/roles/password hashes preserved; private pre-update SQLite backup saved |
| Dependency consistency, Python compilation, whitespace check | Passed |

Local evidence is in `local-data/verification/windows-port-regressions.txt`, `windows-wheel-check.json`, `windows-port-real-models.txt`, `v1-real-pipeline.json` and `windows-port-runtime.json`. These private runtime files are excluded from source distributions and Git. Generated-speech/provider-double checks do not prove physical microphone quality or human consent.

## Not executed here

There is no Windows host attached to this task. Windows setup/CMD execution, native NTFS/PowerShell behavior, Windows shell shortcuts, Windows speech inference and a real Windows microphone therefore remain **unverified on hardware**. Two tests specifically cover native Windows ACL/sharing locks and shortcuts; they skip on macOS and are enabled on Windows. The CI workflow is included. At completion of the local portability work it had not run; subsequent automated results are available in the [repository’s Actions tab](https://github.com/Codewithramesh/neuaurawind/actions). Browser E2E was not executed in this change.

A Windows acceptance pass should run `scripts\test.cmd`, complete a consented short microphone session through real transcription/AI/reviewer approval, test file import/denied permissions/withdrawal, restart to verify persistence, and use Stop. Keep the page in the foreground. Physical wearable controls and native background recording are not implemented on either OS.

## Distribution and existing data

The source ZIP in `local-data/releases/NEUAURA-B2B-Windows-2026-10-30.zip` contains the current source, tests and setup instructions. It excludes `.env`, credentials, recordings, databases/backups, installed dependencies and model weights. Windows installs its own environment and downloads its own model files explicitly. Existing Mac data is preserved in place; moving a live Mac workspace to Windows is a separate deliberate backup/restore operation. The complete source is published to [Codewithramesh/neuaurawind](https://github.com/Codewithramesh/neuaurawind).
