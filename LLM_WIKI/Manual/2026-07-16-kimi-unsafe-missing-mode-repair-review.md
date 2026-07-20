# Kimi review: unsafe missing-mode repair

Date: 2026-07-16.

## Scope

The disposable Home Assistant lifecycle now separately covers a
user-disabled HausmanHub entry whose saved main data lacks the required `mode`.
Explicit activation must fail closed.  A manual exact repair must remain
closed until one explicit reload restores only the approved nine-count
surface.

## Independent review

Kimi session `ses_097b7bd27ffeTkir107qB8Ufh2` using
`kimi-for-coding/k2p7` returned **NO FINDINGS**.

It confirmed that:

- the existing generic lifecycle helper separately covers missing main mode;
- safe options cannot fill the missing required main value;
- repair blocks home-summary reads until the explicit reload;
- the helper retains the nine counts, blocked direct execution, guarded
  diagnostics and local page, no service or device, collision protection, and
  final removal with restart;
- the static scenario count and marker changed only for this case.

## Local evidence

- `python3 -m py_compile tools/check_home_assistant_core.py tests/test_read_only_skeleton.py`
- `python3 -m unittest discover -s tests -v` — 116 tests passed.
- temporary empty Home Assistant Core 2026.6.4 and 2026.7.0 checks passed.

No live Home Assistant, device, Node-RED, service, or remote API was used.
