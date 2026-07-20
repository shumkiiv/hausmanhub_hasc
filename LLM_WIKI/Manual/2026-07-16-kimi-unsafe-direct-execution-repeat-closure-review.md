# Kimi review: unsafe direct-execution repeat closure

Date: 2026-07-16.

## Scope

Independent read-only review of the disposable lifecycle that first rejects a
user activation from unsafe saved direct-execution data, repairs the exact
safe data, explicitly reloads HausmanHub, and then saves the same unsafe marker
again.

## Result

Kimi session `ses_097ebfe38ffeKO7pDzY4TmSpvl` using
`kimi-for-coding/k2p7` returned **NO FINDINGS**.

It confirmed that the second unsafe save is allowed only after a completed
safe recovery. The saved-setting guard again closes HausmanHub while every
home-summary reader is deliberately made to fail. The check proves that no
count, diagnostics, local page, service, or device remains available, while
the bad saved value remains available only for a later manual repair.

## Evidence

- 116 local synthetic and boundary checks passed.
- The disposable empty Home Assistant check passed with 2026.6.4 and
  2026.7.0.
- The repeat-closure flag cannot be used without the earlier safe repair.
  After the second closure, the temporary entry is removed and a fresh empty
  restart proves it remains absent while the unrelated temporary collision
  record is unchanged.
- The static checks cover the new guard, the preserved unsafe value, and the
  repeat-closure call.

The review and checks use only repository files, synthetic fixtures, and
temporary empty Home Assistant configurations. They do not connect to a real
home, Node-RED, devices, services, or a remote Home Assistant API.
