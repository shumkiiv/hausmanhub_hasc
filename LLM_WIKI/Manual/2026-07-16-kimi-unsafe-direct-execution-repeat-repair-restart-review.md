# Kimi review: unsafe direct-execution repeat-repair restart

Date: 2026-07-16.

## Scope

Independent read-only review of a full disposable Home Assistant restart after
the second exact safe repair in the unsafe direct-execution lifecycle.

## Result

Kimi session `ses_097d81ab3ffe1O2oM2CerYgBTD` using
`kimi-for-coding/k2p7` returned **NO FINDINGS**.

It confirmed that the restart is available only after the second safe repair.
The current temporary Home Assistant is stopped before a fresh empty instance
starts, which then must preserve one exact safe HausmanHub entry, the direct-
execution block, the same nine count sensors, fixed diagnostics, and the
guarded local page. The existing removal and final absence restart remain in
place; no HausmanHub service, device, or execution surface appears.

## Evidence

- 116 local synthetic and boundary checks passed.
- Freshly recreated disposable empty Home Assistant checks passed with
  2026.6.4 and 2026.7.0.
- The new restart flag is rejected without the preceding repeat repair and
  does not alter the no-repair branches.
- The restart helper checks exact saved data and options, the active safe
  display, and the unrelated collision record before removal.

The review and checks use only repository files, synthetic fixtures, and
temporary empty Home Assistant configurations. They do not connect to a real
home, Node-RED, devices, services, or a remote Home Assistant API.
