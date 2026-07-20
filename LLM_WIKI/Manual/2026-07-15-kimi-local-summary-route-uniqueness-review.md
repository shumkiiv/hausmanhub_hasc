# Kimi review: one local summary page

Date: 2026-07-15.

## Scope

Only the disposable empty Home Assistant Core lifecycle check, its local source
guard, and its documentation changed. The HausmanHub integration package did not
change.

## What changed

The isolated lifecycle check now collects every route that has HausmanHub's fixed
local-summary address instead of stopping at the first one.

- While a safe HausmanHub setup is active, there must be exactly one authenticated
  GET-only local-summary page.
- After deactivation or removal in the same temporary Home Assistant process,
  that one retained page must remain unavailable and return no count values.
- After a full temporary restart with HausmanHub disabled or removed, no local-summary
  page may exist.

## Review outcome

Kimi session `ses_09a31df42ffeju24YdMuCftyej` returned `NO FINDINGS`. It
confirmed that the check counts every matching route, does not incorrectly
require zero routes before a full restart, and does not expand HausmanHub's
read-only boundary.

## Verification

- `python3 -m unittest discover -s tests -v` — 77 passed.
- `tools/check_home_assistant_core.py` — passed in isolated Core 2026.6.4 and
  2026.7.0 environments.

No real Home Assistant, Node-RED, device, credential, or live home connection
was used.
