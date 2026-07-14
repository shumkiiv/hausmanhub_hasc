# Private HACS approval

Date: 2026-07-14.

## Owner decision

The owner chose option 2 from `docs/hacs-packaging-decision.md`: allow HACS
installation only for the owner through the private GitHub repository.

## Allowed implementation

- Add the minimal root `hacs.json` with the display name and the Home
  Assistant Core 2026.7.0 baseline.
- Add private-installation instructions and a local test that fixes the exact
  metadata shape.
- Keep the repository private and use the HACS custom-repository path only.

## Still prohibited

- Public HACS catalog listing or any public release decision.
- This repository change does not install or test against a live Home
  Assistant, Node-RED, device, or external API.
- Credentials, live identifiers, service paths, command payloads, deployment,
  proxy, or direct execution.

The metadata change must receive Kimi review, local tests, staged-file safety
inspection, a dedicated commit, and push before it is complete.
