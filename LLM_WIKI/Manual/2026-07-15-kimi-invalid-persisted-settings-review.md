# Kimi review: invalid saved settings fail closed

Date: 2026-07-15.

## Scope

The HASC outer Home Assistant adapter, its isolated Core lifecycle check, local
test fakes, version note, and documentation changed. The inner domain rules,
the approved nine-count boundary, and all execution boundaries did not change.

## What changed

Home Assistant can create an unavailable placeholder for a previously known
entity while it starts, even when HASC rejects invalid saved settings. HASC now
waits until startup has finished, then removes only state entries belonging to
that invalid HASC config entry.

- An invalid saved setup rejects an immediate reload and its local page returns
  only unavailable, without counts.
- After a full empty restart, it cannot restore HASC runtime data, services,
  devices, local page, or count states.
- The cleanup is limited to HASC's own registered state IDs. It does not touch
  another integration, a device, Climate, Automation, or any command path.

## Review outcome

Kimi session `ses_09a253d8dffe2mxgCO2uRsCRdd` returned `NO FINDINGS`. It
confirmed the Core startup ordering, API compatibility with Core 2026.6.4 and
2026.7.0, state ownership boundary, reload behaviour, and test fakes.

## Verification

- `python3 -m unittest discover -s tests -v` — 79 passed.
- `tools/check_home_assistant_core.py` — passed in isolated Core 2026.6.4 and
  2026.7.0 environments.

No real Home Assistant, Node-RED, device, credential, or live home connection
was used.
