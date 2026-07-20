# Kimi review: live duplicate fail-closed

Date: 2026-07-15.

## Scope

Version 0.3.7 closes HausmanHub when a damaged second saved setup appears, including
while the first setup is already running. It stops only the active HausmanHub
display, clears only HausmanHub count records, and retains both saved setups for
manual repair.

## Final result

Kimi session `ses_09907dabcffexFBNBQCG4bj5Zn` (model `k2p7`) returned
`NO FINDINGS`.

The review checked the live and restart paths, the fail-closed local GET route,
manual reload or activation after repair, the HausmanHub-only cleanup boundary, and
the absence of device control, services, commands, or home access.

## Verification

- `python3 -m unittest discover -s tests -v` — 96 passed.
- `tools/check_home_assistant_core.py` — passed in isolated Core 2026.6.4 and
  2026.7.0 environments.

Every check used disposable empty configurations or synthetic data. No real
Home Assistant, Node-RED, device, credential, or home data was accessed.
