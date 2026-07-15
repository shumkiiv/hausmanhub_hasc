# Kimi review: occupied HASC-like name check

Date: 2026-07-15.

## Scope

Only the isolated Home Assistant Core smoke check and its explanation changed.
The HASC integration itself did not change. The test uses a fresh temporary
empty Home Assistant configuration; it has no real home address, credential,
device, entity, reading, or command.

## What the check proves

Before creating a new safe HASC setup, the test reserves one HASC-like sensor
name as an external temporary registry entry. It then requires HASC to create
exactly nine count sensors, keep the protected HASC name prefix, not overwrite
the occupied name, and retain the exact protected names for the other eight
sensors.

## Review outcome

The first Kimi review found one test-quality concern: it should not require a
specific suffix that Home Assistant chooses when a name is already occupied.
The check was corrected to require only a distinct HASC-prefixed name for the
one occupied case, while keeping exact checks for the other eight names.

The final Kimi review found no remaining issue. It confirmed that the change
adds no HASC capability, makes no connection to a real Home Assistant, and is
compatible with the supported Core 2026.6.4 and 2026.7.0 checks.

## Verification

- `python3 -m unittest discover -s tests -v` — 63 passed.
- `python3 tools/check_local_release.py` — passed.
- `tools/check_home_assistant_core.py` — passed in isolated Core 2026.6.4 and
  2026.7.0 environments.
