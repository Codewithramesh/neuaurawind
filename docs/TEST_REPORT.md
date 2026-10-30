# Actual test report — installed Mac configuration

Windows portability update (30 October): [compatibility report](WINDOWS_COMPATIBILITY_REPORT.md) records 84 passing backend tests, 18 frontend tests, actual Mac launcher/model regression, and the remaining native Windows acceptance checks.

> V1 update (29 October 2026): see [current workflow](V1_USER_GUIDE.md), [access/consent/retention](V1_ACCESS_AND_LIFECYCLE.md) and [current verification report](V1_IMPLEMENTATION_REPORT.md). Earlier test counts and operator-attestation instructions below describe the original MVP; participant confirmation and review now govern capture and sharing.


Updated **27 October 2026**, Asia/Kolkata. Apple Silicon Mac, macOS 26.5.2, 8 GB memory; Python 3.12.0, Node 22.23.3. The local AI setup is now installed and the real audio-to-intelligence pipeline has passed. Physical MacBook/phone microphone acceptance remains **NOT VERIFIED**.

## Final configuration

- faster-whisper 1.2.1, local tiny.en weights (~75 MB), CPU int8; PyAV 16.0.1.
- Ollama 0.40.11 installed with Homebrew; local **Qwen3 4B**, Q4_K_M, approximately 2.5 GB on disk.
- AI thinking disabled; seed 42; 8,192-token context. One loaded model and one concurrent request. Desktop launcher unloads an idle model after one minute and disables Ollama cloud features.
- Both app and model server bind loopback only. Personal workspace has not been seeded with test conversations or a default account. Verification uses isolated databases and synthetic speech.

## Results

| Check | Status | Observed result |
|---|---|---|
| Backend unit/integration/security/contract suite | PASS | **47 passed**, 14.82 seconds; **93%** statement coverage |
| Frontend unit/component suite | PASS | **9 passed**, Vitest 5.0.5 |
| Production build | PASS | Strict TypeScript + Vite 7.3.7; JS 280.18 kB / gzip 86.66 kB |
| Earlier Chrome browser baseline | PASS, earlier run | **2 passed** with simulated microphone and explicit TEST DOUBLE AI providers; not proof of current real AI browser behavior |
| New browser interaction test | NOT VERIFIED | The browser permission gate declined the isolated localhost test origin; no alternate browser route was used |
| Real restaurant pipeline | PASS | Browser-source and device-source WAV → genuine Whisper → genuine Qwen3 → validated insights/evidence → saved records → task approval through API |
| Real retail pipeline | PASS | Both source types completed; size inquiry produced a `product_request`; suggested tasks approved through API |
| Real HTTP wearable simulator | PASS | Actual CLI uploaded encoded chunks; full analysis completed with exit **0** |
| Real process restart persistence | PASS | Simulator transcript/results survived an actual backend shutdown/restart |
| Device revocation | PASS | Revoked credential rejected with HTTP **401** |
| Desktop service manager stop/start | PASS | Both services stopped; both restarted; selected model reported installed; live idle expiry measured at 60 seconds |
| Desktop shortcut files | PASS, file checks | Executable, shell syntax valid, correct project paths, project symlink and VS Code workspace verified; Finder double-click flow not automated |
| Python dependency check / migrations | PASS | No broken requirements; schema at `7965ef7f839d (head)` |
| Physical MacBook microphone and OS permission | NOT VERIFIED | No ambient microphone capture was performed |
| Physical phone / wearable hardware | NOT VERIFIED | No attached physical devices |
| Personal account creation | USER STEP | User chooses their own email/password; no default or generated production password |

## Genuine test audio and outcomes

The restaurant fixture is macOS Samantha synthetic speech, **6.661 seconds**, transcribed as:

> The coffee was excellent. We waited 20 minutes for our order. Please check how long it takes to serve drinks.

For both source types, the final model produced positive-feedback and complaint signals, exact source quotations and follow-up actions. The isolated overview reported **2 conversations, 2 succeeded, 0 failed**. Suggested actions were approved using the authenticated task API.

The retail fixture is **7.506 seconds**, describing a shirt's fabric/fit and asking for an extra-large size. Both source types completed with a product-request signal and source evidence. Suggested actions were approved using the API. Again, the isolated overview reported **2 conversations, 2 succeeded, 0 failed**.

The live simulator used 12,000-byte chunks against a separate real HTTP backend, genuine speech and genuine AI. It returned **0**, preserved data across a process restart, and rejected its credential after revocation. No mock fallback was configured in these runs.

All stored evidence quotations were checked against the actual saved transcripts. Timestamp attachment uses a unique exact source-segment match, not numbers guessed by the LLM.

## Quality limits

These are functional smoke tests, not a representative accuracy benchmark. Qwen3 4B can combine signals, omit a separate compliment, or assign a service inquiry to a broad product-request category. Confidence is an uncalibrated model estimate. **Category/sentiment counts and recommendations require manager review against evidence.** No noisy-room, long-recording, multi-speaker, Hindi or calibrated business-quality evaluation is claimed.

Current end-to-end browser verification was blocked by its permission gate. The earlier two browser tests covered recording controls, transport, evidence display, task approval, responsive navigation and simulated device registration with deliberate test providers. The current frontend build/component tests pass; physical microphone and current real-AI UI behavior remain unverified.

## Issues found and repaired

1. PyAV 19 removed an argument used by faster-whisper 1.2.1. Pinning PyAV 16.0.1 restored genuine transcription.
2. A real model attached a valid quote to the wrong segment. The LLM adapter now grounds timestamps from unique exact transcript matches and still rejects fabricated quotes. Regression tests cover ambiguous quotes, fabricated text and invalid indices from custom providers.
3. The trial Qwen2.5 3B model misclassified a size inquiry as a preference. Qwen3 4B passed the restaurant praise and retail product-request smoke checks. The unused 3B model was removed. This improves these cases; it does not guarantee taxonomy accuracy on every conversation.
4. Earlier Node test-tool audit findings were repaired by upgrading Vitest. The later source-only changes did not add dependencies.

## Reproduce

```bash
./scripts/test.sh
.venv/bin/python scripts/verify_real.py local-data/verification/authorized-test.wav --require-complete --review-task
.venv/bin/python scripts/verify_real.py local-data/verification/retail-test.wav --industry retail --require-complete --review-task
.venv/bin/python scripts/verify_simulator.py local-data/verification/authorized-test.wav --require-complete
.venv/bin/python scripts/desktop.py status
```

Raw local evidence is under ignored `local-data/verification/`: backend-tests.txt, real-transcription.json, real-pipeline.json, real-retail-pipeline.json, real-simulator.json, extraction-quality JSON, installed-paths.json and the earlier screenshots. Test audio/report files can contain supplied transcript content; keep them private and delete them when no longer needed.
