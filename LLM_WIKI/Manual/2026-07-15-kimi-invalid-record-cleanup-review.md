# Kimi review: invalid-record cleanup

Date: 2026-07-15.

## Scope

Version 0.3.3 makes an invalid saved HASC setup fail closed more completely.
It may remove only the old HASC count states and old HASC entity records that
belong to the same temporary setup. It does not add any home-control feature.

## Review findings and corrections

The review cycle found and corrected three small but important details:

- A rejected saved setup could leave nine empty HASC entity records behind.
  Cleanup now removes both the HASC state and its matching HASC entity record.
- The cleanup queued for Home Assistant startup needed the framework's
  loop-safety marker. It now uses `@callback`; the isolated local fake refuses
  an unmarked startup callback.
- A no-longer-reachable test branch and an outdated callback name were removed
  or renamed. The restart check now separately confirms that the same old nine
  HASC state IDs are absent.

The separate temporary lifecycle helpers for saved `data` and saved `options`
remain intentionally explicit. They make it clear which saved block is made
unsafe, without adding a hidden switch to a safety test.

## Final outcome

Kimi session `ses_099b2ba01ffe9YS1RBppbo5e9o` (model `k2p7`) returned
`NO FINDINGS`. It confirmed the loop-safe startup callback, the ownership
boundary, and the absence of device control, service calls, or changes to an
unrelated temporary record.

## Verification

- `python3 -m compileall -q custom_components tools tests` — passed.
- `python3 -m unittest discover -s tests -v` — 81 passed.
- `tools/check_home_assistant_core.py` — passed in isolated Core 2026.6.4 and
  2026.7.0 environments.

Every check used synthetic data or a disposable empty Home Assistant
configuration. No real Home Assistant, Node-RED, device, credential, or home
data was accessed.
