# Kimi review: unsafe missing-execution-block repair

Date: 2026-07-16.

## Scope

Independent read-only review of the disposable lifecycle where a user-disabled
HASC entry has main data without the required direct-execution block, the
user's activation is rejected, and the exact safe main data is repaired
manually.

## Result

Kimi session `ses_097c10dd4ffeAerfhoNp4IWuZm` using
`kimi-for-coding/k2p7` returned **NO FINDINGS**.

It confirmed that the missing-field case uses the main-data repair branch.
All home-summary readers fail during the saved correction, and only one
separate explicit reload may restore exact safe data and options, the
direct-execution block, nine count sensors, diagnostics, and the guarded local
page. No HASC service or device is created.

## Evidence

- 116 local synthetic and boundary checks passed.
- Disposable empty Home Assistant checks passed with 2026.6.4 and 2026.7.0.
- The static user-activation scenario count changes only from six to seven and
  pins the missing-execution-block repair scenario.
- The existing collision, removal, and final absence restart checks remain in
  the lifecycle.

The review and checks use only repository files, synthetic fixtures, and
temporary empty Home Assistant configurations. They do not connect to a real
home, Node-RED, devices, services, or a remote Home Assistant API.
