# Kimi review: extra saved main-data field

Date: 2026-07-15.

## Scope

The disposable Core lifecycle gained one more invalid main saved setting. It
looks safe at first, but contains one extra synthetic field. This is a test
only: HausmanHub runtime code and its approved nine-count surface did not change.

## What the check proves

For the extra-field case, the empty test configuration must show that HausmanHub:

- closes immediately after reload;
- stays closed through a restart with no HausmanHub state, record, device, service,
  runtime data, or local page;
- returns only the same nine aggregate counts after the exact safe setting is
  restored; and
- leaves the unrelated temporary external record unchanged throughout.

## Review outcome

Kimi session `ses_099aba006ffeVcbhIJ0HB2Y2Dw` (model `k2p7`) returned
`NO FINDINGS`. It confirmed the test covers the extra main field without
adding a data source, device control, service call, or execution path.

## Verification

- `python3 -m compileall -q custom_components tools tests` — passed.
- `python3 -m unittest discover -s tests -v` — 81 passed.
- `tools/check_home_assistant_core.py` — passed in isolated Core 2026.6.4 and
  2026.7.0 environments.

No real Home Assistant, Node-RED, device, credential, or home data was used.
