"""A simulated wearable using only documented v1 HTTP contracts. No fake AI or telemetry."""
import argparse
import hashlib
import json
import mimetypes
import os
import time
from pathlib import Path
from uuid import uuid4
import httpx

parser = argparse.ArgumentParser(description="Submit authorized real audio through NEUAURA's device API")
parser.add_argument("audio", type=Path)
parser.add_argument("--url", default="http://127.0.0.1:8000")
parser.add_argument("--device-id", required=True)
parser.add_argument("--session-id", required=True, help="Upload session ID prepared and consented by an operator in the app")
parser.add_argument("--credential-file", type=Path, help="Private file containing the per-device credential (POSIX chmod 600 or restricted Windows ACL); or NEUAURA_DEVICE_TOKEN")
parser.add_argument("--chunk-bytes", type=int, default=4*1024*1024)
parser.add_argument("--idempotency-key", default=None, help="Reuse this key to resume the same session")
parser.add_argument("--title", default="Simulated wearable test")
parser.add_argument("--language", default="en")

parser.add_argument("--timeout", type=int, default=300)
args = parser.parse_args()
if args.chunk_bytes < 1 or args.chunk_bytes > 50*1024*1024:
    parser.error("--chunk-bytes must be between 1 byte and 50 MB")
token = args.credential_file.read_text().strip() if args.credential_file else os.environ.get("NEUAURA_DEVICE_TOKEN", "")
if not token:
    parser.error("Provide --credential-file or NEUAURA_DEVICE_TOKEN. Do not put credentials into command-line arguments.")
from urllib.parse import urlparse
parsed = urlparse(args.url)
if parsed.scheme != "https" and parsed.hostname not in {"127.0.0.1", "localhost", "::1"}:
    parser.error("Device connections outside loopback require HTTPS")
key = args.idempotency_key or str(uuid4())
base = args.url.rstrip("/") + "/api/v1"
print(f"SIMULATED DEVICE · idempotency key: {key}", flush=True)
with httpx.Client(base_url=base, headers={"Authorization": "Bearer " + token}, timeout=120, trust_env=False) as client:
    def request(method, path, **kw):
        for attempt in range(3):
            try:
                response = client.request(method, path, **kw)
                if response.status_code >= 500 and attempt < 2:
                    time.sleep(2**attempt)
                    continue
                response.raise_for_status()
                return response.json()
            except httpx.TransportError:
                if attempt == 2:
                    raise
                time.sleep(2**attempt)
    device = request("GET", f"/devices/{args.device_id}")
    if not device["simulated"]:
        parser.error("This client only operates on explicitly simulated devices. Register one with simulated=true.")
    session = {"id":args.session_id}
    prepared = request("GET", f"/sessions/{args.session_id}/status")
    if prepared["device_id"] != args.device_id or not prepared["consent_valid"] or prepared["session_state"] not in {"finalizing", "processing", "needs_review", "approved"}:
        parser.error("An operator must obtain participant confirmations, validate conditions and finalize this device session in the app first.")
    hasher, count = hashlib.sha256(), 0
    mime = mimetypes.guess_type(args.audio)[0] or "application/octet-stream"
    with args.audio.open("rb") as audio:
        while chunk := audio.read(args.chunk_bytes):
            hasher.update(chunk)
            request("POST", f"/sessions/{session['id']}/audio?sequence={count}", content=chunk,
                headers={"Content-Type":mime,"X-Chunk-SHA256":hashlib.sha256(chunk).hexdigest()})
            count += 1
    result = request("POST", f"/sessions/{session['id']}/complete", json={"sha256":hasher.hexdigest(),"total_chunks":count})
    print(json.dumps(result, indent=2))
    print("Accepted by the shared audio pipeline. Waiting for a real processing result…", flush=True)
    deadline = time.monotonic() + args.timeout
    while time.monotonic() < deadline:
        status = request("GET", f"/sessions/{session['id']}/status")
        if status["status"] in {"complete", "failed"}:
            print(json.dumps(status, indent=2))
            raise SystemExit(0 if status["status"] == "complete" else 2)
        time.sleep(2)
    print("Still processing; inspect conversation " + result["conversation_id"] + " in the dashboard.")
    raise SystemExit(3)
