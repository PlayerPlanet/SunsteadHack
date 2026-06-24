# 04 — Open Questions & Spikes

The actual *exploration*: the unknowns that decide whether the Tangled track is real, and the
small experiments ("spikes") to settle each one. Run these **before** writing production code —
each is cheap and kills a big risk. Ordered by de-risk priority.

## Spike 1 — Write a custom record to a PDS

**Question:** Can we write a `com.sunstead.crossing` record into a (test) PDS and read it back?
**Do:** Provision a test ATProto account; via OAuth (or app-password) call
`com.atproto.repo.createRecord` with collection `com.sunstead.crossing`; then `getRecord` it.
**Pass:** The record persists and is retrievable by AT-URI. **Kills:** "can custom lexicons even
be written" risk. *(Spec says yes — verify empirically.)*

## Spike 2 — Firehose pickup of a custom NSID

**Question:** Does our custom record actually appear in the firehose/Jetstream?
**Do:** Subscribe to Jetstream filtered to our NSID; trigger Spike 1's write; watch for the event.
**Pass:** We observe the `com.sunstead.crossing` create event in the stream. **Kills:** the
load-bearing assumption that a third-party appview can see our records. **Risk if it fails:**
explainability stays read-via-PDS only (no live stream); still workable but less slick.

## Spike 3 — Agent identity (DID) on ATProto  ⚠️ highest uncertainty

**Question:** How does a *non-human* actor (the Data-Agent) get a DID and the ability to write
signed records? Can it OAuth, or do we use an app-password / dedicated PDS account per agent?
**Do:** Stand up a DID for "agent-builder-001"; confirm it can sign + write a `com.sunstead.*`
record. **Pass:** Agent-signed records exist with a distinct DID from the human judge. **Kills:**
the entire "DID-attributed agent judgement" claim. **This is the one most likely to surprise us.**

## Spike 4 — Spindle runtime for the agent

**Question:** Can a `.tangled` spindle workflow step invoke an external long-running service (the
Data-Agent), or call back to the homeserver receiver — or is it limited to short nixery steps?
**Do:** Add a workflow step that POSTs to the homeserver webhook (already deployed) and confirm
round-trip. **Pass:** Spindle can trigger the agent out-of-band. **Decides:** runtime topology —
agent-in-spindle vs agent-as-homeserver-service (we currently lean homeserver service).

## Spike 5 — Cross-lexicon linking

**Question:** Can a `com.sunstead.crossing` reference a `sh.tangled.repo.pull` / `.issue` by
AT-URI, and can an appview resolve both? **Do:** Create a crossing whose `subject` points at a
real Tangled pull AT-URI; resolve both from one consumer. **Pass:** The join works end-to-end.

## Spike 6 — Minimal alternative appview (the demo)

**Question:** Can a ~100-line Jetstream consumer render the explainability timeline?
**Do:** Consume `sh.tangled.*` + `com.sunstead.*`, join by AT-URI, render
PR → crossing → judgment → outcome. **Pass:** A working second appview that explains what the
agent org did and why, with DID attribution. *Only attempt after Spikes 1–3 pass.*

## Cross-cutting open questions

- **NSID domain.** `com.sunstead.*` is a placeholder — which domain do we actually control?
- **OAuth UX for the demo.** Authorizing agent + judge DIDs once each — acceptable for a 3-min
  demo? Pre-authorize before stage.
- **Hosted vs self-hosted knot/spindle.** Is there a hosted knot/spindle we can use, or must we
  self-host (on AWS — see the AWS layer notes in the memory playbook)?
- **Relationship to the Aiven track.** If Aiven wins as the submission, does any of this ship, or
  is it purely the "v2 / what's next" narrative? (Decision gate, not a spike.)

## Recommended order

`Spike 1 → Spike 3 → Spike 2 → Spike 5 → Spike 4 → Spike 6`. If Spike 3 (agent DID) fails or
is too heavy for the timebox, fall back to: agent records signed by a single service DID, with
`actor` recorded as a field — less elegant, still auditable.
