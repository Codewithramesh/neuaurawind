# Secure phone testing

Windows host: start with [Windows setup](WINDOWS_SETUP.md) and `scripts\start.cmd`. The same trusted HTTPS, host allowlist and secure-cookie requirements apply. The Mac paths/commands below describe the original host; native Windows phone acceptance has not been run.

An HTTP URL such as `http://192.168.x.x:8000` does not establish a secure browser context for phone microphone capture. A responsive viewport test does not verify a real mobile microphone.

The recommended private path uses Tailscale Serve, which shares the Mac's loopback service within your authenticated tailnet using an automatically provisioned HTTPS certificate. It needs a Tailscale account and clients on the Mac and phone; no production domain or hosting subscription is required. Availability/account policy may vary. This setup is documented but has NOT been exercised on a physical phone in this build.

## Private HTTPS through Tailscale Serve

1. Install Tailscale on the Mac and phone, sign in to the same authorized tailnet, and apply access rules limiting this app to the intended tester. Enable the tailnet HTTPS feature when prompted. Use **Serve** for private tailnet access.
2. Start the built NEUAURA dashboard with `./scripts/start.sh` on `127.0.0.1:8000`. Complete workspace setup locally first.
3. In another terminal on the Mac:

   ```bash
   tailscale serve --bg --https=443 http://127.0.0.1:8000
   tailscale serve status
   ```

4. Note the exact HTTPS hostname printed by Serve. Edit `.env` to include that host without a scheme or slash:

   ```dotenv
   NEUAURA_ALLOWED_HOSTS=["localhost","127.0.0.1","YOUR-MAC.YOUR-TAILNET.ts.net"]
   NEUAURA_SECURE_COOKIES=true
   ```

   Use the real hostname from your installation. Restart NEUAURA so the allowlist and cookie settings take effect. Use the HTTPS URL for the entire session, including sign-in; do not mix Vite and backend origins.
5. On your phone, keep Tailscale connected and open the exact `https://…ts.net` URL in Safari or Chrome. Confirm a trusted connection and sign in. This single origin serves both frontend and API, including audio playback and cookies.
6. Follow [V1 consent-controlled capture](V1_USER_GUIDE.md): prepare the store/purpose/participant roster with source **Phone microphone**, obtain each participant’s confirmation, revalidate conditions, then explicitly start capture and grant microphone permission. Record a short English conversation in the foreground, stop, preview and analyze.
7. Check real transcript contents, status, evidence, suggestions, mobile navigation and audio behavior. Test an interruption and permission denial. Record the actual phone model, OS, browser and result in `TEST_REPORT.md` before claiming phone integration verified.

Only the loopback HTTP hop stays on the Mac; phone traffic uses the private HTTPS channel. Workspace authentication still applies. The app does not trust Tailscale identity as a replacement for its own session. Private-network control and app sign-in provide separate access boundaries.

## Stop access

```bash
tailscale serve --https=443 off
# If this Mac has no other Serve configuration you need to preserve:
# tailscale serve reset
```

Stop NEUAURA with Ctrl+C. If you return to plain localhost HTTP for development, set `NEUAURA_SECURE_COOKIES=false`, restart and sign in again. Preserve any other services on the Mac when managing Tailscale configuration.

## Troubleshooting

- `Invalid host header`: add the exact phone-facing hostname to `NEUAURA_ALLOWED_HOSTS` and restart.
- `ORIGIN_REJECTED`: use one HTTPS origin for both the UI and API; the proxy must preserve the external Host header. Do not use cross-origin API URLs or disable CSRF protection.
- Sign-in does not persist: verify HTTPS, cookie settings and phone browser storage permissions; sign in again after changing origins.
- Microphone missing/denied: confirm HTTPS trust, phone/browser permission and browser support. iOS may suspend capture on screen lock, navigation, calls or backgrounding.
- Speech succeeds but analysis fails: set up the Mac's configured AI engine, then Retry. Do not treat `AI_UNAVAILABLE` as a phone transport failure.

An alternative is a trusted local CA certificate with a reverse proxy, installing/trusting that CA on each test phone. That requires certificate lifecycle and device trust management; it is not installed here. Public temporary tunnels require explicit access protection and review before exposure. No public tunnel was created.

Command reference checked against [Tailscale's official Serve documentation](https://tailscale.com/docs/reference/tailscale-cli/serve). The docs distinguish private Serve from public Funnel.
