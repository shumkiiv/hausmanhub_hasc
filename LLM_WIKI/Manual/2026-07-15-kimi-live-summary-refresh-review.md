# Kimi review: live count-refresh closure

Date: 2026-07-15.

## Scope

Independent read-only review of the upcoming HausmanHub 0.3.12 change. When a
running HausmanHub setup has damaged saved settings, its next scheduled refresh must
close before reading the local home summary. All nine aggregate-count sensors
must then become unavailable until the owner repairs the saved settings.

## Result

Kimi session `ses_0987a8205ffe5TCnczA0Zz4gVD` using
`kimi-for-coding/k2p7` returned **NO FINDINGS**.

The reviewer confirmed that `sensor.py` validates the complete saved data and
options before it can call the home-summary reader. A damaged configuration
therefore produces a local update failure and makes the nine coordinator
sensors unavailable. The review found no new data category, command, device,
service, Node-RED connection, proxy, or direct-execution capability.

## Evidence

- 111 local synthetic and boundary checks passed.
- The disposable empty Home Assistant Core checks passed with 2026.6.4 and
  2026.7.0.
- The Core check damages every existing bad main-setting and mode-choice
  variant while HausmanHub is running, replaces the reader with a function that
  fails if used, forces the live refresh, and requires all nine sensors to be
  unavailable.

All checks use only the repository, synthetic fixtures, and temporary empty
Home Assistant configurations. They do not connect to a real home, Node-RED,
devices, services, or remote Home Assistant API.
