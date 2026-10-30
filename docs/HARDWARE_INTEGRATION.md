# Connecting the future wearable

The core application accepts normalized audio from browser/phone microphone, authorized imported audio, or an operator-associated device upload. Hardware transport is isolated from transcription, evidence validation, review and business intelligence.

Implemented software boundaries: typed `DeviceProvider`/`CaptureCapabilities`, store-bound identity, per-device credentials and revocation, HTTP heartbeat/error/status, consent-controlled session association, validated session transitions, resumable chunks, SHA256 integrity, one durable post-session job, and an explicitly labeled simulator. The real provider intentionally rejects remote capture controls because no physical transport/indicator contract is implemented. No fake health/battery/physical connection is displayed.

## Required next steps, in order

1. Obtain hardware specifications: codec/container, sample rate/channels, maximum recording duration/size, onboard storage, clock accuracy, power behavior, whether recordings can be paused, battery reporting and OS/firmware control surfaces.
2. Select Bluetooth, Wi-Fi, USB or another transport with the hardware team. No final radio/protocol is assumed by this repository. For BLE, determine whether a native phone bridge is needed; a web page is not assumed to support background wearable audio reception.
3. Specify provisioning of a distinct device credential, secure storage, rotation and revocation. Associate a real device with an authorized store and operator-owned session without giving the device consent authority.
4. Implement actual connect/disconnect, transport acknowledgements, start/pause/resume/stop where supported, and a visible/audible physical recording indicator. Validate actual stop behavior, including withdrawal, disconnect, backgrounding, battery loss and server/phone loss. If any required indicator/control cannot be guaranteed, capture must remain unavailable.
5. Define short-lived control/capture leases appropriate to actual hardware. The present browser/simulator lease is a software mechanism, not a physical failsafe. Confirm how an offline device stops and how it communicates recording status to participants.
6. Connect the adapter's encoded audio to the existing authenticated upload session. Preserve chunk order/checksums, timestamps supplied by a trusted basis, replay/idempotency behavior and consent/session version checks. Never upload unauthorized buffered audio after consent withdrawal.
7. Run hardware-in-the-loop tests: permissions and participant workflow, indicator visibility, start/pause/resume/stop, withdrawal during capture and transfer, corrupted/missing/duplicate chunks, reconnect/resume, revocation, low battery, clock drift and recovery after power loss.
8. Verify actual transcript/evidence/task quality on authorized restaurant/retail recordings in realistic noise, language and duration conditions. Capture acceptance evidence and firmware/phone/OS/browser versions before claiming integration complete.

Physical transport, firmware, recording indicators, real battery telemetry, background native capture and hardware-in-the-loop results are **NOT TESTED/NOT IMPLEMENTED**. Post-session analysis can be tested now with genuine files and installed local engines without manufacturing those capabilities. Live transcription/streaming analysis and CRM actions remain outside this release.
