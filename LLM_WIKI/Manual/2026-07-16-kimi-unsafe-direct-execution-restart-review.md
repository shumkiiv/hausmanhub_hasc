# Kimi review: unsafe direct-execution restart

Date: 2026-07-16.

## Scope

Independent read-only review of the disposable Home Assistant lifecycle that
saves `direct_execution_status: allowed` on a user-disabled HASC setup, stops
the temporary Core completely, starts a new empty Core from the same temporary
configuration, and then attempts user activation.

## Result

Kimi session `ses_097ff6d5dffe2Z4xRr3bA40s0y` using
`kimi-for-coding/k2p7` returned **NO FINDINGS**.

It confirmed that the restart branch keeps the saved entry user-disabled and
not loaded, preserves the deliberately damaged data only for manual repair,
and leaves no runtime data or local summary route. The later activation is
rejected, attempts exactly one reload, and ends in `SETUP_ERROR` without
creating a display or authority. The existing in-process closed-route checks
remain active for the non-restart scenarios.

## Evidence

- 116 local synthetic and boundary checks passed.
- The disposable empty Home Assistant check passed with 2026.6.4 and
  2026.7.0.
- Before activation after the restart, the check requires nine disabled
  registry records with no count states, no service, no device, no runtime
  data, no local page, and closed diagnostics.
- During activation all three temporary home-summary readers fail if called.
  The check then requires no count records or states, no available diagnostics
  or page, and no HASC service before removing the temporary entry and proving
  it remains absent after another empty restart.

The review and checks use only repository files, synthetic fixtures, and
temporary empty Home Assistant configurations. They do not connect to a real
home, Node-RED, devices, services, or a remote Home Assistant API.
