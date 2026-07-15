# Kimi review: ordinary unload and setup

Date: 2026-07-15.

## Scope

This change adds one disposable Core lifecycle check. It temporarily unloads
one safe HASC setup without disabling it, checks the safe middle state, then
starts the same saved setup again. It does not change the integration package,
HACS metadata, or HASC runtime authority.

## What the check proves

While the safe setup is ordinarily unloaded, its saved setup and nine enabled
registry records remain, but all nine temporary count states are absent and the
guarded local page returns only an unavailable response without count keys.
Starting the same setup must preserve its safe data and options, restore only
the same nine count sensors, fixed diagnostics, and one authenticated GET-only
page. This is distinct from user deactivation, which marks the setup disabled.

## Review outcome

Kimi session `ses_0997292a2ffe3wshWIg8hztjw3` (model `k2p7`) returned
`NO FINDINGS`. It confirmed the Core API sequence, the wait points, the
separate user-deactivation path, the exact nine-count boundary, and the absence
of device, service, network, real-home, or control access.

## Verification

- `python3 -m compileall -q custom_components tools tests` — passed.
- `python3 -m unittest discover -s tests -v` — 87 passed.
- `tools/check_home_assistant_core.py` — passed in disposable empty Core
  2026.6.4 and 2026.7.0 environments on Python 3.14.3.
- `python3 tools/check_local_release.py` — passed against the staged change.

No real Home Assistant, Node-RED, device, credential, home data, deploy, or
live API was used.
