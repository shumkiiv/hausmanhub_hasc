# Kimi review: unsafe direct-execution repeat-repair restart closure

Date: 2026-07-16.

## Scope

Independent read-only review of the disposable lifecycle that saves unsafe
direct-execution data again after the second safe repair and a full empty
Home Assistant restart.

## Result

Kimi session `ses_097d2dcefffeeugl6hD8knxtZr` using
`kimi-for-coding/k2p7` returned **NO FINDINGS**.

It confirmed that this final repeat closure is available only after the safe
restart. The restarted saved-setting guard closes HASC while all home-summary
readers deliberately fail. The check requires cleared sensor records and
states, closed diagnostics and local page, no service or device, preserved
unsafe saved data for manual repair, an unchanged collision record, and the
existing final removal restart.

## Evidence

- 116 local synthetic and boundary checks passed.
- Disposable empty Home Assistant checks passed with 2026.6.4 and 2026.7.0.
- The new flag is rejected without the preceding repeat-repair restart and
  leaves the earlier lifecycle branches unchanged.
- The reattached update listener is exercised only through repository code and
  temporary empty Home Assistant configurations.

The review and checks use only repository files, synthetic fixtures, and
temporary empty Home Assistant configurations. They do not connect to a real
home, Node-RED, devices, services, or a remote Home Assistant API.
