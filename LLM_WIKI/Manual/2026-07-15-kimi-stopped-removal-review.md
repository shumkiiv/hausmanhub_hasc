# Kimi review: removal after an ordinary HASC stop

Date: 2026-07-15.

## Scope

The disposable Home Assistant lifecycle now checks one missing safe case:
an enabled HASC setup is ordinarily stopped, rather than disabled by the
owner, and is removed before it starts again.

The check requires the saved settings and exactly nine enabled HASC registry
records to remain intact while stopped, but all count values, diagnostics, and
the local count-only page to stay unavailable. It then removes the setup,
requires both read paths to remain closed, and verifies that an unrelated
temporary record with a similar name is unchanged.

## Final result

Kimi session `ses_098b7c2b9ffenyV0RpHQn0uHqe` (model `k2p7`) reviewed the
final uncommitted change and returned `NO FINDINGS`.

The review confirmed that this is test-only coverage in a disposable empty
Home Assistant configuration. It adds no HASC runtime capability, device,
service, proxy, direct execution path, remote connection, or real-home read.

## Verification

- `python3 -m unittest discover -s tests -v` — 108 passed.
- `tools/check_home_assistant_core.py` — passed in isolated Core 2026.6.4 and
  2026.7.0 environments.

No real Home Assistant, Node-RED, device, credential, or home data was used.
