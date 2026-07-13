# Kimi review: isolated Home Assistant Core smoke check

Date: 2026-07-13.

## Scope

Read-only review of `tools/check_home_assistant_core.py` and the matching
instructions in `docs/read-only-skeleton.md`. The script runs only against an
empty temporary Home Assistant configuration in a separate Python 3.14
environment. It does not use a live home, credentials, real identifiers,
Home Assistant services, Node-RED, devices, deployment, or network APIs.

## Review and remediation

The first Kimi review found no blocking issue and three test-quality gaps:

- broad comparison of all Core entities could be affected by late Core startup;
- the created entry was not explicitly checked as loaded;
- the text should identify Python 3.14.2 as a minimum version.

The smoke check now looks only for entities attached to the created HASC config
entry, requires `ConfigEntryState.LOADED`, and the guide says Python 3.14.2 or
newer.

## Final Kimi result

The repeat review completed with:

- Blocking findings: none.
- Non-blocking findings: none.

It also confirmed that `loader.async_setup(hass)` is a synchronous Home
Assistant Core API. Review sessions were `ses_0a3b6cb18ffegOaoAcKpTmzu7b` and
`ses_0a3b1740cffeL70qc4TVZrR4Yf`. Reviewers did not modify repository files.

## Verification

- `python3 -m compileall -q custom_components hasc_validation tools tests`
- `python3 -m unittest discover -s tests -v` — 21 passed
- `Python 3.14.3 + Home Assistant Core 2026.7.0` —
  `tools/check_home_assistant_core.py` passed
- `git diff --check`

The Core check creates and removes a temporary local configuration directory.
It verifies rejection of `proxy`, safe `shadow` creation, blocked direct
execution, a loaded entry, safe options, no HASC service, no entity attached
to the entry, and clean removal. It does not prove shadow parity or grant any
runtime authority.
