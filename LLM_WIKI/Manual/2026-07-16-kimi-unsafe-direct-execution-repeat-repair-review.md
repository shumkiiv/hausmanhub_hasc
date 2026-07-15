# Kimi review: unsafe direct-execution repeat repair

Date: 2026-07-16.

## Scope

Independent read-only review of the disposable lifecycle that repairs exact
safe settings after HASC has already recovered once, received unsafe
direct-execution data again, and closed again.

## Result

Kimi session `ses_097e1fc1affek3Z0BzpW3DMumA` using
`kimi-for-coding/k2p7` returned **NO FINDINGS**.

It confirmed that this second repair is allowed only after the earlier repeat
closure. During the saved correction all home-summary readers deliberately
fail, and the helper records exactly one reload: the separate explicit safe
reload. Only after that reload may HASC restore exact safe data and options,
the direct-execution block, the same nine count sensors, fixed diagnostics,
and the guarded local page. No HASC service or device is created.

## Evidence

- 116 local synthetic and boundary checks passed.
- The disposable empty Home Assistant check passed with 2026.6.4 and
  2026.7.0.
- The new flag is rejected without the preceding repeat closure. The existing
  first repair and all no-repair branches remain unchanged.
- After the second recovery, ordinary removal and a fresh empty restart still
  prove that the temporary entry is absent and the unrelated collision record
  is unchanged.

The review and checks use only repository files, synthetic fixtures, and
temporary empty Home Assistant configurations. They do not connect to a real
home, Node-RED, devices, services, or a remote Home Assistant API.
