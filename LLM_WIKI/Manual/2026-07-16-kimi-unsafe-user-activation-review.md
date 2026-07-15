# Kimi review: unsafe user activation

Date: 2026-07-16.

## Scope

Independent read-only review of the disposable Home Assistant check for a
user-disabled HASC setup whose saved mode is deliberately changed to the
unapproved `proxy` value before the user attempts to enable it.

## Result

The first Kimi review, session `ses_09819829fffeeA4jZzBV0TEW1L`, found one
minor duplicate test helper. It was replaced with the shared
`async_block_home_summary_reads` guard.

Final Kimi session `ses_09812fcfbffeYfHZwDoegKxHCC` using
`kimi-for-coding/k2p7` returned **NO FINDINGS**.

It confirmed that the guard restores all three temporary readers even if the
checked action fails. The activation API must return `False`, attempt exactly
one reload of the same HASC entry, and leave it in `SETUP_ERROR` with direct
execution still blocked. The unsafe saved option is retained for manual
repair, rather than silently repaired or used to start HASC.

## Evidence

- 115 local synthetic and boundary checks passed.
- The disposable empty Home Assistant check passed with 2026.6.4 and
  2026.7.0.
- The scenario replaces every HASC home-summary reader with a failure before
  the unsafe save and activation. It then requires closed diagnostics, an
  unavailable local page, no count states, no HASC registry rows, and no HASC
  services.
- After removal and a fresh empty restart, the temporary HASC setup remains
  absent while the unrelated temporary collision record is unchanged.

The review and checks use only repository files, synthetic fixtures, and
temporary empty Home Assistant configurations. They do not connect to a real
home, Node-RED, devices, services, or a remote Home Assistant API.
