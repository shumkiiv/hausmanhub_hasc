# Kimi review: safe mode cycle

Date: 2026-07-16.

## Scope

Independent read-only review of the disposable Home Assistant Core check for
two consecutive allowed HASC settings: `read-only` to `shadow`, then back to
`read-only`. The check must prove that each save reloads only HASC once and
that the final safe mode remains consistent through later lifecycle checks.

## Result

Kimi first noted that an added source-text test was brittle and did not prove
runtime behavior. That test was removed. The final review session
`ses_0983bed9cffempQLaK48Vt7q3g` using `kimi-for-coding/k2p7` returned
**NO FINDINGS**.

It confirmed that the first diagnostics expectation remains `shadow`, all
later expectations after the second save use `read-only`, and the actual
temporary Core check verifies the nine count sensors and one authenticated
GET-only page after each allowed save.

## Evidence

- 115 local synthetic and boundary checks passed.
- Disposable empty Home Assistant Core checks passed with 2026.6.4 and
  2026.7.0.
- The existing safe-options helper records and requires exactly one reload of
  the same HASC entry for each save.
- No integration runtime file, HACS metadata, device command, service,
  proxy, direct execution path, secret, live identifier, or real-home access
  was added.

The review and checks use only repository files, synthetic fixtures, and
temporary empty Home Assistant configurations. They do not connect to a real
home, Node-RED, devices, services, or a remote Home Assistant API.
