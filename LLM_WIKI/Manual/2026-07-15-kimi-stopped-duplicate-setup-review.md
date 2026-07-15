# Kimi review: duplicate setup while HASC is stopped

Date: 2026-07-15.

## Scope

This change extends the disposable Home Assistant lifecycle check. A safe HASC
setup is ordinarily stopped but remains user-enabled and saved. The empty test
then tries to add HASC again and must receive the usual one-setup refusal.

## What the check proves

The existing saved setup remains the one and only HASC setup. Its data and
safe mode choice stay unchanged, it is not user-deactivated, and it remains
ordinarily unloaded. The same nine HASC count records remain enabled but have
no current values, and the guarded page stays unavailable. The following
temporary restart must still auto-load that same safe setup with exactly the
nine permitted counts and no device, service, proxy, or execution path.

## Review outcome

Kimi session `ses_099556f19ffeaM5G2Q6eJGY6PZ` first found one test-only
issue: the new ordering check depended on exact line breaks and indentation.
The test was changed to find semantic markers and their order instead.

Final direct Kimi model `k2p7` review session
`ses_099497fb1ffeU1Tta9V0ugEseD` returned `NO FINDINGS`.

## Verification

- `python3 -m compileall -q custom_components tools tests` — passed.
- `python3 -m unittest discover -s tests -v` — 91 passed after the review fix.
- `tools/check_home_assistant_core.py` — passed in disposable empty Core
  2026.6.4 and 2026.7.0 environments on Python 3.14.3 before the test-only
  review fix. The runtime check source did not change afterward.

No real Home Assistant, Node-RED, device, credential, home data, deploy, or
live API was used.
