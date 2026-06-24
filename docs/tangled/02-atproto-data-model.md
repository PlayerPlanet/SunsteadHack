# 02 — Tangled / ATProto Data Model (Confirmed)

What we've verified about how Tangled stores data, and what it means for building an external
explainability app. **Verdict: an external app CAN read Tangled data as ATProto records, and we
CAN define our own custom lexicon and write records that coexist with Tangled's.** Caveats below.

> Confirmed via primary sources 2026-06-24. Lexicon JSON read from the mirror
> `github.com/ilyagr/tangled-core` (fork of `tangled.org/core`); re-pull from the canonical host
> for production.

## Records & lexicons — `sh.tangled.*`

Tangled defines lexicons under the **`sh.tangled.*`** NSID prefix; definitions live in the
`lexicons/` dir of the `tangled.org/core` monorepo. Confirmed record types:

- `sh.tangled.repo` — repo pointer (`name`, `owner` DID, `knot`, `spindle`, `description`, `source`)
- `sh.tangled.repo.issue`, `sh.tangled.repo.issue.comment`, `sh.tangled.repo.pull`
- `sh.tangled.repo.collaborator` (deprecating — see caveats), `sh.tangled.repo.artifact`
- `sh.tangled.feed.star`, `sh.tangled.feed.reaction`, `sh.tangled.graph.follow`
- `sh.tangled.knot`, `sh.tangled.knot.member` (deprecating), `sh.tangled.spindle`, `sh.tangled.spindle.member`
- `sh.tangled.pipeline`, `sh.tangled.git.refUpdate`, `sh.tangled.actor.profile`
- plus XRPC **method** lexicons (queries/procedures, not records) under `repo/`, `knot/`, `pipeline/`

## Where records live — SPLIT (PDS + knot + appview)

- **PDS (standard ATProto records):** repo pointers, issues, comments, pulls, stars, follows,
  reactions, knot/spindle registration, actor profile. Metadata in the *user's* PDS; the
  `sh.tangled.repo` record carries `owner` (DID) + `knot` (where the git data lives).
- **Knot (self-hosted git server, "like a PDS but for code"):** actual git repo contents /
  commit graph, served over Git protocol + XRPC (e.g. `sh.tangled.git.temp.getBlob`). **Not**
  ATProto records. As of **v1.15.0-alpha** the knot also became source-of-truth for its own
  members & per-repo collaborators, served over XRPC instead of firehose records.
- **Appview (`tangled.sh`/`tangled.org`):** indexes `sh.tangled.*` from the firehose/Jetstream
  and serves the unified view. Their appview ("Bobbin") is read-only; a backfill service
  ("Hydrant") feeds it the event stream.

**Summary:** git → knot; collaboration metadata/identity/social → PDS records; unified view →
appview.

## Firehose / readability — PUBLIC, ungated

Tangled records are ordinary public ATProto records. The firehose
(`com.atproto.sync.subscribeRepos`) / relays are unauthenticated, and **relays do not validate
records against lexicons** — so `sh.tangled.*` (and any custom NSID) flows through the generic
firehose/Jetstream just like `app.bsky.*`. A third party can:
- subscribe to the firehose/Jetstream and filter for collections, and/or
- read directly via `com.atproto.repo.getRecord` / `listRecords` (public, unauthenticated).

## Custom lexicons — YES (standard ATProto)

Nothing Tangled-specific blocks minting a new NSID under a domain you control (e.g.
`com.sunstead.crossing`) and writing those records into a PDS alongside `sh.tangled.*`. Relays
don't validate against lexicons, so custom records propagate through the *same* firehose and are
readable by the same consumers. This is how WhiteWind/Tangled/Bluesky all coexist.

## Appview model — CONFIRMED

Standard ATProto pattern: the appview holds no privileged data, only an index; records live in
PDSes (source of truth). **Therefore anyone can build an alternative appview** over the same
`sh.tangled.*` + `com.sunstead.*` records — this *is* the plural-explainability story. (A fully
equivalent appview also needs to talk to knots over XRPC for git contents and, on v1.15+,
member/collaborator data.)

## Spindles — PARTIALLY on-network

- `sh.tangled.spindle` / `sh.tangled.spindle.member` = records.
- `sh.tangled.pipeline` IS a record (captures trigger + workflows).
- **Live run results/logs** are streamed out-of-band over WebSocket — *not* ATProto records.

## Caveats that affect us

1. **Writes need user OAuth.** Reading is open; writing `com.sunstead.*` records on a DID's
   behalf needs that DID to authorize our app (standard ATProto OAuth scopes).
2. **Git contents + (v1.15+) collaborator data are knot-XRPC, not firehose.** Only matters if our
   app needs diffs or permissions data; for the crossing/judgment trail it's irrelevant.
3. **Network-wide discovery needs a Jetstream consumer**, not `listRecords` (which is per-DID +
   per-collection).
4. **Lexicon source is a mirror.** Re-pull from `tangled.org/core/lexicons` before writing
   production code.

## Sources

- `github.com/ilyagr/tangled-core/tree/master/lexicons` (mirror of `tangled.sh/@tangled.sh/core`)
- `docs.tangled.org/single-page`, `blog.tangled.org/intro/`
- `atproto.com/specs/sync` (lexicon-agnostic relay behavior)
- `finxol.io/posts/embracing-atproto-pt-2-tangled-knot/`
