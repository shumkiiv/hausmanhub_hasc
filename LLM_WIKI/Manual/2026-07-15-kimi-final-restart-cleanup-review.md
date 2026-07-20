# Kimi review: final restart cleanup

Date: 2026-07-15.

## Scope

Only the disposable empty Home Assistant Core check, its local source guard,
and its documentation changed. The integration package did not change.

## What changed

After the final HausmanHub removal, the check stops its current empty Home Assistant
instance and starts a third one using the same temporary configuration. The
third instance must not restore any HausmanHub setup, entity, device, service, count
state, runtime data, or local route. The unrelated temporary external record
must remain unchanged.

## Review outcome

Kimi returned `NO FINDINGS`. It confirmed the stop/start order, use of only
temporary internal names and IDs, absence checks without reading values, the
route-table check without HTTP, and the unchanged no-control boundary.

## Verification

- `python3 -m unittest discover -s tests -v` — 71 passed.
- `python3 tools/check_local_release.py` — passed.
- `tools/check_home_assistant_core.py` — passed in isolated Core 2026.6.4 and
  2026.7.0 environments.

No real Home Assistant, Node-RED, device, or live home connection was used.
