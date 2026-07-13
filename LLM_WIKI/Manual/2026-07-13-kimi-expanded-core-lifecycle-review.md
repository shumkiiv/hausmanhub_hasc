# Kimi review: expanded isolated Core lifecycle check

Date: 2026-07-13.

## Scope

Read-only review of the expanded `tools/check_home_assistant_core.py` check
and the matching guide. The check uses a disposable, empty Home Assistant Core
2026.7.0 configuration in an isolated Python 3.14.3 environment. It has no
credentials, real identifiers, live Home Assistant configuration, Node-RED,
devices, services, deployment, or network API access.

## What the final check covers

- creates and loads each approved initial mode: `read-only` and `shadow`;
- rejects `proxy` at both the initial flow and options schema boundaries;
- proves rejected options leave the loaded entry and persisted options intact;
- accepts only a change between the two approved modes, then reloads the real
  Core entry;
- requires direct execution to remain blocked, with no HASC service or
  config-entry entity; and
- removes each temporary entry and checks that no entry or attached entity is
  left behind.

This is compatibility and safety-boundary coverage only. It does not prove
shadow parity and does not grant proxy or direct-execution authority.

## Review and remediation

Kimi's iterative read-only review asked for the lifecycle assertions above:
loaded state after options, exact persistence checks, symmetric safe-mode
coverage, rejection cleanup, reload, and removal. The final review confirmed
that the selector rejects the unsafe options input before the options-flow
handler; the check explicitly treats that `InvalidData` result as the expected
safe outcome and aborts the temporary flow.

## Final Kimi result

- Blocking findings: none.
- Non-blocking findings: none.

Final review session: `ses_0a37fec05ffeYPB0Z5kYJMX12N`. The reviewer did not
modify repository files.

## Verification to run before commit

- `python3 -m compileall -q custom_components hasc_validation tools tests`
- `python3 -m unittest discover -s tests -v`
- `/tmp/hasc-core-2026.7.0/bin/python tools/check_home_assistant_core.py`
- `git diff --check`
