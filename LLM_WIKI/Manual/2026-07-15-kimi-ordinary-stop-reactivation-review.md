# Kimi review: ordinary-stop reactivation

Date: 2026-07-15.

## Scope

Independent read-only review of the test-only HASC lifecycle addition. In an
empty temporary Home Assistant, it covers an ordinary HASC stop, user
deactivation, immediate user reactivation without a restart, and one final
deactivation for the existing restart-and-removal path.

## Result

Kimi session `ses_098733d22ffe5OhWSFaNTkqw7B` using
`kimi-for-coding/k2p7` returned **NO FINDINGS** after two small coverage gaps
from its first pass were corrected.

The reviewer confirmed that the new sequence preserves the unchanged saved
settings, restores only the same nine aggregate-count sensors and the guarded
local page after reactivation, and closes diagnostics and that page again
after the second deactivation. The runtime integration is unchanged; no data
category, command, device, service, Node-RED connection, proxy, or
direct-execution capability was added.

## Evidence

- 112 local synthetic and boundary checks passed.
- The disposable empty Home Assistant Core checks passed with 2026.6.4 and
  2026.7.0.
- The lifecycle check explicitly requires the ordinary stop before the first
  deactivation, validates the closed state, reactivates without a restart, and
  then validates both the restored nine counts and the second closed state.

All checks use only the repository, synthetic fixtures, and temporary empty
Home Assistant configurations. They do not connect to a real home, Node-RED,
devices, services, or remote Home Assistant API.
