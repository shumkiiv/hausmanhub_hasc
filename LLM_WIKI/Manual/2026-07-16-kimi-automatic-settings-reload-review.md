# Kimi review: automatic saved-setting reload

Date: 2026-07-16.

## Scope

Independent read-only review of HASC 0.3.13. A normal safe mode change must
reload only the one HASC entry. If a saved main setting or saved mode choice is
unsafe, HASC must close immediately without reading a home summary or gaining
any authority over the home.

## Result

Kimi session `ses_09855387bffeHtFsE0LzH3ns6g` using
`kimi-for-coding/k2p7` first found one medium-strength gap in the temporary
Core check: it did not directly prove that no home-summary reader ran in the
short interval while HASC was closing.

The check now replaces the sensor, diagnostics, and local-summary readers with
a function that fails before each unsafe saved update and restores them only
after the automatic reload finishes. Kimi's follow-up review returned
**NO FINDINGS**.

## Evidence

- 114 local synthetic and boundary checks passed.
- Disposable empty Home Assistant Core checks passed with 2026.6.4 and
  2026.7.0.
- The safe options flow records exactly one reload, for the same HASC entry.
- All unsafe saved main-setting and mode-choice variants close their count
  states, HASC-only registry records, diagnostics, and local page before any
  HASC home-summary reader can run.

The review and all checks use only repository files, synthetic fixtures, and
temporary empty Home Assistant configurations. They do not connect to a real
home, Node-RED, devices, services, or a remote Home Assistant API.
