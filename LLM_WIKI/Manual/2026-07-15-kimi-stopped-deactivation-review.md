# Kimi review: user deactivation after an ordinary HausmanHub stop

Date: 2026-07-15.

## Scope

The disposable Home Assistant lifecycle now covers one additional safe
sequence: a user-enabled HausmanHub setup is ordinarily stopped first and is then
deactivated by the user before the temporary Home Assistant restarts.

The check requires the ordinary stop to keep the exact safe settings and nine
enabled registry records while clearing count values, diagnostics, and the
local page. User deactivation must then disable those same records, keep both
read paths closed, persist through the empty restart, and allow later removal.

## Final result

Kimi session `ses_098a3ae5bffeRRUzTkU7LSCvjZ` (model `k2p7`) reviewed the
final uncommitted test-only change and returned `NO FINDINGS`.

The review confirmed that this closes a lifecycle coverage gap without changing
HausmanHub runtime behavior or adding a device, service, proxy, direct execution,
network connection, or real-home access.

## Verification

- `python3 -m unittest discover -s tests -v` — 111 passed.
- `tools/check_home_assistant_core.py` — passed in isolated Core 2026.6.4 and
  2026.7.0 environments.

All checks used synthetic data or disposable empty configurations. No real
Home Assistant, Node-RED, device, credential, or home data was used.
