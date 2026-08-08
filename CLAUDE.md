Arbox Auto-Booking — Session Handoff
Context handoff from a claude.ai chat. Goal, findings, and open next steps for continuing this build in Claude Code. Drop this in the project root (rename to CLAUDE.md to have it auto-load, or @-reference it).
Goal
Automatically register for tomorrow's 08:00 class in Arbox, every day, without manual taps. Original idea was an iOS Shortcut firing at 21:01; that framing has since been revised (see Architecture Decision below).
Key findings so far
Certificate pinning is not a blocker. Pinning is client-side — it protects the app's trust in the server, not the server's trust in the client. A direct API call from a script is just another client; pinning does nothing to stop it. The existence of working open-source Arbox booking scripts confirms the login endpoint accepts plain email/password.

What could block (but evidently doesn't): App Attest / Play Integrity attestation on the login/register endpoints. A gym SaaS almost never implements this. If it did, direct calls would fail — they don't.

The Arbox member app is mobile-only. There is no member web portal, so desktop browser DevTools can't be used to capture requests.

Endpoints are already reverse-engineered in open-source repos:

oribenez/auto-enroll-arbox → endpoints in the lib/ folder
saar120/arbox-automation-v2 → src/arboxAPI.ts
Base host referenced: arboxserver.arboxapp.com. Login typically POST .../user/login with {email, password} and a whitelabel header (default "Arbox" for the standard app; custom-branded gyms differ).

Login response is the discovery mechanism. Authenticating returns a profile object that typically carries the account-specific IDs (box/location ID, membership ID) needed for the schedule and register calls — so interception of the mobile app is likely unnecessary.
Architecture decision
Prefer a server-side cron over the iOS Shortcut. Once the logic is a script, the phone-as-trigger stops earning its keep, and it loses timing races if class spots fill in seconds (cold radio, automation firing ~21:01 not 21:00:00).

Recommended: EventBridge → Lambda, or Cloud Run job + Cloud Scheduler. Fires at 21:00:00 sharp with a warm connection.
Low-cost alt: Raspberry Pi / small VPS with a plain crontab.
The reference repos pre-warm and fire ~30s before the window for exactly this race reason — worth replicating if the 08:00 class fills instantly.

Fallbacks if the phone must be the trigger: Shortcuts Run Script Over SSH (execute on the server), or on-device runners (a-Shell / Pyto / Pythonista), though iOS background throttling makes precise unattended firing unreliable.
Next steps (in order)
Pull the exact login endpoint + required headers from one of the repos above.
Prototype the chain in curl (fast to iterate) before writing real code:
login → confirm token returned; read box/location + membership IDs from the response.
getScheduleBetweenDates (or equivalent) for tomorrow → find the 08:00 entry's schedule_id.
register (e.g. scheduleUser/insert) with that schedule_id (+ membership_user_id) → confirm a booking actually lands.
Port the working chain into a Python script for Lambda + an EventBridge cron rule (daily 21:00 Asia/Jerusalem — mind the cron UTC offset + DST).
Add a success/failure notification (push, email, or log).
Notes / caveats
Credentials: keep the Arbox password out of source. Use env vars / Secrets Manager / SSM, not a hardcoded string. (In a Shortcut it would sit in plaintext on-device — another reason to prefer the server route.)
The member API is unofficial; endpoint paths are versioned and can change without notice. Treat the repo endpoints as a starting hypothesis and verify against your own login response.
Timezone: Israel + DST — schedule the cron carefully.


