# Kimi review: external collision cleanup check

Date: 2026-07-15.

## Scope

Only the disposable empty Home Assistant Core check, its local source guard,
and its documentation changed. The integration package did not change.

## What changed

The empty check reserves one external record with an HausmanHub-like name. It now
saves the record's identity, source, and lack of HausmanHub or device ownership.
After HausmanHub is removed, the check requires the same external record to remain
unchanged.

## Review outcome

Kimi returned `NO FINDINGS`. It confirmed that the new check runs after HausmanHub
removal, covers the intended identity and ownership fields, and adds no HausmanHub
runtime capability, home data, control, or network access.

## Verification

- `python3 -m unittest discover -s tests -v` — 67 passed.
- `python3 tools/check_local_release.py` — passed.
- `tools/check_home_assistant_core.py` — passed in isolated Core 2026.6.4 and
  2026.7.0 environments.

No real Home Assistant, Node-RED, device, or live home connection was used.
