# Audio pipeline

> V1 update (29 October 2026): see [current workflow](V1_USER_GUIDE.md), [access/consent/retention](V1_ACCESS_AND_LIFECYCLE.md) and [current verification report](V1_IMPLEMENTATION_REPORT.md). Earlier test counts and operator-attestation instructions below describe the original MVP; participant confirmation and review now govern capture and sharing.


## Capture

The browser only requests `getUserMedia` after consent attestation and an explicit Start button. It detects supported MediaRecorder types (WebM/Opus, MP4, Ogg), records chunks locally, supports pause/resume, shows recording state/time, stops at the configured duration limit, cancels/releases tracks and offers preview. Permission and recorder failures are shown. Source adapters yield bytes and MIME metadata; none calls AI from the browser.

Browser limitations apply: background suspension, interrupted phone calls, locked-screen capture and uninterrupted recording are not promised. Selecting the system microphone is available immediately; named alternatives become available after the browser grants permission and enumerates devices. Mobile Safari may choose MP4. Only Chrome's simulated microphone was exercised automatically.

## Ingestion and integrity

A consent-attested versioned session is created using an idempotency key. Chunked/raw uploads enforce content type, chunk SHA256, sequence uniqueness and total encoded bytes. Completion validates sequence coverage and whole-file hash, creates controlled file metadata and queues a durable job. Source code never builds storage paths from a supplied filename; UUID conversation directories isolate stored media.

Metadata: server session/conversation UUID, authenticated organization, optional device, source type, language, creation/ingestion time, byte count, hash, MIME, measured duration, sample rate, job stages/attempt/error/retryability. An optional timezone-aware `captured_at` is stored separately as a device-reported capture time; retention always uses server time. Device clocks are not required.

## Normalization

PyAV decodes the actual stream, resamples to 16 kHz, mono, signed 16-bit PCM WAV, and counts decoded samples. Client MIME/duration are hints, never trusted validation. No audio stream, corruption, fewer than 0.1 seconds, silence/very low energy and duration overflow yield explicit failures. Frame-by-frame normalization bounds output duration and avoids loading the entire decoded recording into memory. The input format must be supported by the installed PyAV/FFmpeg build.

The tested pin is PyAV 16.0.1 with faster-whisper 1.2.1. PyAV 19 removed an argument used by that faster-whisper release; the real test caught it. Do not independently upgrade PyAV without re-running real transcription.

## Speech

`TranscriptionProvider.transcribe(Path, language)` returns text, timestamped segments, detected language, provider and model. faster-whisper uses a local model path, CPU int8, VAD, English by default and no automatic downloads. A missing model/dependency is retryable after setup; silence/corruption requires a new recording. The tiny model is suitable for smoke tests, not a quality guarantee. English-only models cannot transcribe Hindi; install a multilingual model and configure language before testing Hindi.

A saved transcript is committed before any extraction request. Disabling audio retention deletes original and normalized files once that commit succeeds. AI retries then reuse the transcript. Failed speech retains its input until manual deletion or expiry so setup/model issues can be fixed.

## Extraction and persistence

`ExtractionProvider.extract(TranscriptionResult, industry, configured_categories)` returns a Pydantic `Extraction`. The local Ollama adapter sends a JSON schema in `format`, a low-temperature prompt and untrusted transcript data. An explicitly selected compatible endpoint can use `response_format.json_schema`. No provider is silently substituted.

Categories cover feedback, preferences, complaints, requests, experience/operational problems, intent/opportunities, price, competitors and unresolved questions. Industry topics come from a configurable business profile. Additional categories can be configured in Settings. Every insight specifies stated/inferred, estimated confidence, uncertainty and evidence. Exact quotes must occur in the saved transcript; the LLM adapter ignores model-proposed segment numbers and attaches a timestamp only when an exact quote matches one unique source segment. Custom provider indices must still pass strict validation. Timestamp bounds are derived from the verified segment, never invented by the model. Cross-segment quotes can omit a segment index and therefore have no claimed timestamp.

Suggested actions refer to a valid insight index, then become reviewable tasks with no invented owner or due date. Extraction/insights/evidence/tasks commit atomically. No valid AI result means failed/pending status, no fabricated summary and no fake business metric. Schema and quote checks cannot guarantee semantic correctness; managers must verify important conclusions.

## Installed Mac configuration

Ollama/Qwen3 4B runs locally with thinking disabled, seed 42 and an 8,192-token context. Model-generated segment numbers are ignored: unique exact source matches determine timestamps; ambiguous or cross-segment matches have no claimed timestamp. The runtime is configured for one loaded model and one request at a time, with idle unloading after one minute. Small-model category and recommendation quality remains a human-review responsibility.
