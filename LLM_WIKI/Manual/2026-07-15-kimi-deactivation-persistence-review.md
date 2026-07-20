# Kimi review: deactivation survives restart

Date: 2026-07-15.

## Scope

Only the disposable empty Home Assistant Core lifecycle check, its local
source guard, and its documentation changed. The HausmanHub integration package did
not change.

## What changed

The first safe HausmanHub setup in the empty Core check is now deactivated immediately
before a temporary restart that replaces only the temporary HausmanHub copy.

- After restart, the saved setup must remain user-disabled and not loaded.
- It must not restore HausmanHub runtime data, its guarded local page, or any of the
  nine count states by itself.
- An explicit activation must restore only the same nine enabled count sensors,
  safe diagnostics, and authenticated GET-only page, still without device,
  service, proxy, or execution capability.

## Review outcome

Kimi session `ses_09a3b6521ffecnFaIIgcpbS89n` returned `NO FINDINGS`. It
confirmed that the assertions match the Home Assistant lifecycle and do not
expand HausmanHub's read-only boundary.

## Verification

- `python3 -m unittest discover -s tests -v` — 76 passed.
- `tools/check_home_assistant_core.py` — passed in isolated Core 2026.6.4 and
  2026.7.0 environments.

No real Home Assistant, Node-RED, device, credential, or live home connection
was used.
