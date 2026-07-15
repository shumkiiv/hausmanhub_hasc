# Kimi review: unsafe direct-execution activation

Date: 2026-07-16.

## Scope

Independent read-only review of the disposable Home Assistant check for a
user-disabled HASC setup whose saved main data is deliberately changed to
`direct_execution_status: allowed` before the user attempts to enable it.

## Result

Kimi session `ses_0980a1270ffef3bXpJWIMG3uDW` using
`kimi-for-coding/k2p7` returned **NO FINDINGS**.

It confirmed that the shared lifecycle helper still covers the earlier unsafe
`proxy` option and now separately covers unsafe main data. For the bad main
data, activation returns `False`, attempts exactly one reload of the same
HASC entry, and leaves it in `SETUP_ERROR`. The damaged data is retained for
manual repair; it is not silently repaired or turned into runtime authority.

## Evidence

- 115 local synthetic and boundary checks passed.
- The disposable empty Home Assistant check passed with 2026.6.4 and
  2026.7.0.
- Before the unsafe save and activation, every HASC home-summary reader is
  replaced with a failure. The scenario requires no registered HASC service,
  device, count state, registry row, available diagnostics, or available local
  page.
- It removes the temporary entry and proves it remains absent after a fresh
  empty restart while the unrelated temporary collision record is unchanged.

The review and checks use only repository files, synthetic fixtures, and
temporary empty Home Assistant configurations. They do not connect to a real
home, Node-RED, devices, services, or a remote Home Assistant API.
