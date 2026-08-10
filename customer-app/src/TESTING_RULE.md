# Frontend testing — what "100%" on the scoreboard claims (and what it does not)

Applies to BOTH apps (customer-app and agency-dashboard; same wording, kept here).

**100% =** `npm test` (vitest, jsdom) is green AND critical user flows have component/interaction tests through Testing Library — customer-app: traveller OTP login (TravellerLoginPage) and onboarding OTP entry (OtpPage); agency-dashboard: dashboard login (LoginPage) and the live-call takeover panel (TakeoverControls, incl. no-optimistic-state and the confirm-before-human-handoff rules) — AND unit suites stay pinned to live backend contracts (passwordValidation ↔ `_PASSWORD_RULES`, takeoverMachine ↔ `takeover_service.py:34`), AND `npm run build` still passes.

**Not claimed:** no E2E against a real backend yet (API modules are mocked at the module boundary), no visual regression, no WebSocket integration tests — the WS contract is enforced by types plus the backend-mirror unit suites, not by a live socket.
