# Decision: direct local Home Assistant observation for Codex

Date: 2026-07-14.

## Owner approval

The owner explicitly approved direct local observation of Home Assistant by
Codex through a dedicated local non-administrator account. This is separate
from HausmanHub itself: it does not give the public HausmanHub integration any new
authority, device-control capability, service, proxy, or direct-execution
path.

## Guardrails

- The credential stays in a local non-repository file with owner-only file
  permissions. It is never sent in chat, committed, logged, or copied into
  HausmanHub configuration.
- Codex may send only HTTP GET requests to a local-network Home Assistant
  address. It must not call service, action, configuration-changing, or other
  mutating endpoints.
- Live responses are reduced immediately to the smallest fact needed for the
  check. Names, identifiers, readings, attributes, histories, addresses, and
  raw response bodies must not enter the repository or durable project notes.
- The access account is not a technical read-only role in the current Home
  Assistant interface. The owner understands that the no-command rule is
  enforced by this operating procedure, not by a Home Assistant permission
  switch.

## Initial verification

The local address and credential passed a harmless Home Assistant availability
check and a version-only check. A count-only current-state snapshot was then
read without retaining raw objects. HausmanHub's own nine-count route correctly
refused this ordinary account, confirming that the integration's stricter
`system-read-only` guard remains active.
