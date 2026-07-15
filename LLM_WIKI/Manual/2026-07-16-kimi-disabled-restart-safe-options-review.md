# Kimi review: disabled restart safe options

Date: 2026-07-16.

## Scope

Independent read-only review of the disposable Home Assistant Core check for
saving `shadow` after a full temporary restart while the HASC setup is still
deliberately disabled by its user, before that user explicitly activates it.

## Result

Kimi session `ses_09821d41dffe8VG8gpV75J9cFn` using
`kimi-for-coding/k2p7` returned **NO FINDINGS**.

It confirmed that saving the allowed option keeps HASC user-disabled and not
loaded, with no runtime data, local page, or count values. The Core check
records no reload and makes each HASC home-summary reader fail if called. The
following explicit activation preserves the saved `shadow` mode and restores
only the existing nine count sensors with direct execution still blocked.

## Evidence

- 115 local synthetic and boundary checks passed.
- The disposable empty Home Assistant Core check passed with 2026.6.4 and
  2026.7.0.
- During the disabled-after-restart save, the Core check requires zero calls
  to HASC reload, a `NOT_LOADED` HASC entry, and `disabled_by=USER`.
- No integration runtime file, HACS metadata, device command, service,
  proxy, direct execution path, secret, live identifier, or real-home access
  was added.

The review and checks use only repository files, synthetic fixtures, and
temporary empty Home Assistant configurations. They do not connect to a real
home, Node-RED, devices, services, or a remote Home Assistant API.
