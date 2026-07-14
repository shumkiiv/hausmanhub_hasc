# Decision record: HACS metadata and distribution

## Status

Approved for option 2 on 2026-07-14. The owner approved private HACS testing
only. The repository stays private and is not submitted to the public HACS
catalog.

## Facts already fixed

- The repository is private: `shumkiiv/hausmanhub_hasc`.
- The license is MIT and the supported baseline is Home Assistant Core 2026.7.0
  or newer.
- The private `custom_components/hausman_hub/` skeleton is limited to
  `read-only` and `shadow`.
- It has no service, entity, device, Node-RED, or execution surface.
- Proxy and direct execution remain unapproved and blocked.

## Decision required

Choose one path:

1. **Keep HACS metadata absent.** Continue private development and local
   verification without HACS distribution.
2. **Approve private HACS testing metadata.** Add only the minimal metadata
   needed for the owner-approved private testing path, with a separate review
   of its exact fields and installation instructions.
3. **Prepare a public distribution decision.** Do not publish anything yet;
   first define release, support, disclosure, and maintenance requirements in
   a separate owner decision.

## Chosen path

Option 2 is approved for the repository owner. The implementation may add
only this root-level metadata:

```json
{
  "name": "HausMan Hub HASC",
  "homeassistant": "2026.7.0"
}
```

The owner installs the private repository manually in HACS as an
**Integration** custom repository. This decision does not install it into a
live Home Assistant instance and does not add a public listing.

## Required approval wording for option 2

An approval for private HACS testing must explicitly confirm all of the
following:

- `hacs.json` may be added to this private repository for the stated testing
  audience only;
- the exact installation method and who may use it;
- the metadata does not add credentials, live identifiers, service paths,
  command payloads, deployment scripts, or runtime configuration;
- it does not expand the approved modes, add proxy, or lift
  `direct_execution_blocked`;
- all verification remains local and read-only, with no live Home Assistant,
  Node-RED, device, or external API calls; and
- the final metadata diff receives Kimi review before commit and push.

## Implementation boundary after approval

The implementation is one isolated metadata-only change. It must not modify
the HASC integration's runtime behavior, alter Climate, Automation, Common,
or Smart Home Center policy, or be combined with another feature. Before it
is committed, re-run the local tests, inspect staged files for prohibited
data, record the Kimi review, and push the dedicated commit only after all
checks pass.

## Explicitly still out of scope

- Public release, marketplace listing, or support promise.
- Proxy approval, rollback procedure, or live source connection.
- Shadow-parity acceptance, canary, authority transfer, or direct execution.
