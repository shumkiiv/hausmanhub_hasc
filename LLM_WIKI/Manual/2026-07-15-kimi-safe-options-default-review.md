# Kimi review: safe options-form default

Date: 2026-07-15.

## Scope

Version 0.3.6 makes the HASC mode-choice screen safe when old saved settings
are broken. The screen may show only a safe default; it must not write,
repair, or otherwise change the saved setting merely because a person opened
the screen.

## What the check proves

The isolated form test supplies a saved `proxy` choice, an unknown saved main
mode, and a main setting without a mode. Each screen opens with the safe
`read-only` default while preserving the original in-memory settings exactly.
It also proves that a valid saved `shadow` choice remains selected. The form
still offers only the two approved modes.

## Review outcome

Kimi session `ses_0996b067bffe5Yo3AFYhO59Zuf` first found that the test did
not explicitly retain the valid `shadow` default. That test was added. Final
Kimi session `ses_099675bdeffeafj4syrIOrClWD` (model `k2p7`) returned
`NO FINDINGS`.

## Verification

- `python3 -m compileall -q custom_components tools tests` — passed.
- `python3 -m unittest discover -s tests -v` — 89 passed.
- `tools/check_home_assistant_core.py` — passed in disposable empty Core
  2026.6.4 and 2026.7.0 environments on Python 3.14.3.
- `python3 tools/check_local_release.py` — passed against the staged version
  0.3.6 change.

No real Home Assistant, Node-RED, device, credential, home data, deploy, or
live API was used.
