# NEUAURA V1 device boundary — consent-controlled HTTP transfer

Current software schema: 1.1.0. The actual request/response definitions are exported in `shared/api-contracts/openapi.json`; local interactive docs are at `/docs`. This is the software HTTP transfer boundary, **not a chosen physical wearable radio/transport protocol**.

## Identity and capabilities

An organization owner/admin registers a device with `POST /api/v1/devices/register`: `name`, `model`, `device_type`, `simulated`, `store_id`, optional `firmware`. `store_id` must be authorized; it may be inferred only if exactly one store is available. A unique bearer credential is returned once and only its hash is stored. Keep it in a private mode-600 file or device secret storage, never source control or command-line arguments.

`GET /devices/{device_id}` reports only actual stored/observed values. Connection is `not_seen`, `recently_seen` (HTTP activity within 120 seconds), `offline`, or `revoked`; it is not a claim of a BLE/Wi-Fi connection. Battery remains null until explicitly reported. Simulated identity is always labeled. Provider capabilities are typed in `backend/app/device_provider.py`; real hardware has transfer capability only and unknown/unverified controls/indicator/battery reporting. Simulated controls change software session state and do not manufacture audio or telemetry.

Heartbeat: `POST /devices/{id}/heartbeat`, optional reported `battery` 0–100, `firmware`, bounded `health` metadata. Error: `POST /devices/{id}/errors`, `code` and `message` up to 500 characters; no conversation content. Revocation: owner/admin `POST /devices/{id}/revoke`. Each credential is restricted to its organization/device's sessions. No transcript/audio playback endpoint accepts device credentials.

## Operator preparation is mandatory

A bearer device **cannot create participant consent**. The old attestation-only create flow is rejected with `OPERATOR_PREPARATION_REQUIRED`. Existing clients must be updated; `--consent-attested` is no longer the simulator's authorization mechanism.

1. Authorized signed-in operator calls `POST /api/v1/sessions` with `Idempotency-Key` (8–128 safe characters):

   ```json
   {
     "title": "Authorized simulated retail test",
     "source_type": "device",
     "device_id": "REGISTERED_DEVICE_ID",
     "store_id": "AUTHORIZED_STORE_ID",
     "purpose": "Review product availability feedback",
     "participant_refs": ["Guest 1", "Staff 1"],
     "language": "en"
   }
   ```

2. Each participant reads and confirms their own versioned notice using the private token returned in `participant_links`. `GET/POST /api/v1/participant-consent` use `X-Consent-Token`; grant/withdraw/decline requires explicit `informed:true`. Do not automate these decisions for actual human participants.
3. Operator validates capture conditions and performs the allowed transitions through `/conversations/{conversation_id}/transition`, with `action`, `expected_state`, `consent_version`, `conditions_confirmed` where needed. Simulated software controls can start/pause/resume/stop. Actual wearable control/indicator integration returns 501 rather than claiming success.
4. A finalized simulated session enters `finalizing`. The device receives its **upload session ID** through an authorized provisioning/association step (the current app displays it for simulation). The physical mechanism for sending that association is unresolved until hardware is specified.

Browser/phone/import source sessions use the same downstream ingestion and worker. `phone_microphone` is an explicit source label; a browser cannot silently receive wearable audio.

## Transfer protocol

- Device sends `Authorization: Bearer …` using its own credential over HTTPS outside loopback.
- `POST /sessions/{upload_id}/audio?sequence=N`: raw chunk bytes, supported audio Content-Type, `X-Chunk-SHA256` lowercase hex. Sequences 0–999; complete coverage required at finalization. Retries of identical chunks are idempotent; changed bytes at an accepted sequence conflict. Total size is bounded by workspace settings.
- `POST /sessions/{upload_id}/complete`:
  ```json
  {"sha256":"LOWERCASE_SHA256_OF_THE_CONCATENATED_AUDIO", "total_chunks":3}
  ```
- All current participants must still consent, capture conditions must be validated and capture must be finalized. Checksum acceptance persists original audio and one durable processing job. It does not claim transcription success. Decoding/duration/model failures are reported by the job.
- `GET /sessions/{upload_id}/status`: upload status, received sequences, session state, consent-valid flag and processing metadata. No full transcript or participant confirmation tokens are returned.
- Original/normalized audio is temporary by default; raw-audio retention also applies to failed/pending work. No recording is accepted after withdrawal/revocation/cancellation.

Processing statuses: queued/processing/complete/failed/restricted. Review lifecycle: `needs_review` after actual successful analysis; `approved` only after human finding/session review. Exports require human approval.

## Simulator

```bash
.venv/bin/python device-simulator/submit.py /absolute/path/authorized.wav \
  --device-id DEVICE_ID \
  --credential-file /absolute/path/private-device-credential \
  --session-id OPERATOR_PREPARED_UPLOAD_ID
```

Only `simulated=true` identities are accepted. Reuse the same upload ID/file/chunk size after transfer failure. Exit 0 means actual processing completed (results still require review); 2 failed; 3 pending. The simulator does not capture a microphone, create consent, generate speech, invent battery levels or connect a physical wearable.

For generated-speech-only integration checks, `scripts/verify_real.py` and `scripts/verify_simulator.py` require `--synthetic-fixture`. Their test consent actions are explicitly labeled and are not evidence of consent by any real participant. No test-provider fallback is loaded in production.
