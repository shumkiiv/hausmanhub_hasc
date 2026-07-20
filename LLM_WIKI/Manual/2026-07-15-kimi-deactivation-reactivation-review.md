# Kimi review: safe deactivation and reactivation

Date: 2026-07-15.

## Scope

Only the disposable empty Home Assistant Core lifecycle check, its local
source guard, and its documentation changed. The HausmanHub integration package did
not change.

## What changed

The empty Core check now uses Home Assistant's normal user deactivation path
for an already safe HausmanHub setup, then activates it again.

- While deactivated, the saved setup must be unloaded, the nine HausmanHub count
  records must be marked disabled by that setup, and the authenticated local
  count page must answer only that it is unavailable, with no count key.
- After reactivation, exactly the same nine enabled count records, fixed safe
  diagnostics, and authenticated GET-only page must return. No device, service,
  proxy, or execution surface may appear.

Home Assistant keeps disabled entity records in its own registry. The check
therefore verifies the official disabled marker rather than incorrectly
claiming that Home Assistant deletes those records when the user chooses
deactivation.

## Review outcome

Kimi session `ses_09a5018c8ffeaf5fh6R6TjHcO0` returned `NO FINDINGS`. It found
no blocking, important, or minor issue in the deactivation/reactivation flow,
the fixed nine-count boundary, the closed local page, or the updated
documentation.

## Verification

- `python3 -m unittest discover -s tests -v` — 74 passed.
- `python3 tools/check_local_release.py` — passed.
- `tools/check_home_assistant_core.py` — passed in isolated Core 2026.6.4 and
  2026.7.0 environments.

No real Home Assistant, Node-RED, device, credential, or live home connection
was used.
