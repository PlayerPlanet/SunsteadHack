# Green-bond data-quality findings

_100 bonds · 1,062 rows scanned · 255 findings · mode: **Tier 0 (deterministic, no API key)** · 2026-06-25_

**How to read this.** Three buckets by what *you* need to do:

- **Auto-correct (3)** — recomputed exactly from other stored values; apply or spot-check.
- **Flag (17)** — a real inconsistency whose *fix* is debatable; needs a human call.
- **Escalate (235)** — only the source PDF settles it; the agent abstained on purpose.

Per-finding evidence (the conflicting numbers, trail excerpts) lives in `findings.jsonl` for tooling — this page stays one line per finding.

## Auto-correct — objective fixes (3)

_Recomputed from primitives; the value is determined._

| sev | isin | field | check | why | proposed |
|-----|------|-------|-------|-----|----------|
| low | `US45505MLF13` | post_allocation_share_of_total | share_def | Allocation share disagrees with USD÷bond (0.0001 stored vs 0.0001 recomputed). | `5.4e-05` |
| low | `US45506DQ995` | post_allocation_share_of_total | share_def | Allocation share disagrees with USD÷bond (0.0000 stored vs 0.0000 recomputed). | `7e-06` |
| low | `US6174468B80` | post_allocation_share_of_total | share_def | Allocation share disagrees with USD÷bond (0.0003 stored vs 0.0003 recomputed). | `0.000274` |

## Flag — needs a human call (17)

_Inconsistent, but which side is wrong is a judgment._

| sev | isin | field | check | why | proposed |
|-----|------|-------|-------|-----|----------|
| high | `BE0000346552` | impact_value | trail_value_mismatch | Annual renewable energy generation: stored impact_value 9.89e+08 disagrees with the 989000 its own source_trail derives. |  |
| medium | `BE0000346552` | bond_USD_amount | fx_consensus | Implied EUR->USD rate 1.2320 is 6% off the corpus median 1.1613 for EUR. |  |
| medium | `CND10004PTX1` | bond_USD_amount | fx_consensus | Implied CNY->USD rate 0.1568 is 10% off the corpus median 0.1428 for CNY. |  |
| medium | `XS2388386810` | bond_USD_amount | fx_consensus | Implied JPY->USD rate 0.0091 is 19% off the corpus median 0.0077 for JPY. |  |
| medium | `SE0006371324` | bond_USD_amount | fx_consensus | Implied SEK->USD rate 0.1393 is 11% off the corpus median 0.1252 for SEK. |  |
| medium | `BRSSCFDBS030` | bond_USD_amount | fx_consensus | Implied BRL->USD rate 0.2395 is 44% off the corpus median 0.4256 for BRL. |  |
| medium | `MX94CO0H00D7` | bond_USD_amount | fx_consensus | Implied MXN->USD rate 0.0470 is 11% off the corpus median 0.0527 for MXN. |  |
| medium | `XS0608302583` | bond_USD_amount | fx_consensus | Implied BRL->USD rate 0.6117 is 44% off the corpus median 0.4256 for BRL. |  |
| medium | `XS3283529405` | bond_USD_amount | fx_consensus | Implied SEK->USD rate 0.1110 is 11% off the corpus median 0.1252 for SEK. |  |
| medium | `NO0013735175` | bond_USD_amount | fx_consensus | Implied NOK->USD rate 0.1049 is 7% off the corpus median 0.0982 for NOK. |  |
| medium | `CND10000JSF1` | bond_USD_amount | fx_consensus | Implied CNY->USD rate 0.1511 is 6% off the corpus median 0.1428 for CNY. |  |
| medium | `MX91CM2S0009` | bond_USD_amount | fx_consensus | Implied MXN->USD rate 0.0584 is 11% off the corpus median 0.0527 for MXN. |  |
| medium | `NO0013391615` | bond_USD_amount | fx_consensus | Implied NOK->USD rate 0.0914 is 7% off the corpus median 0.0982 for NOK. |  |
| medium | `JP363340AP67` | bond_USD_amount | fx_consensus | Implied JPY->USD rate 0.0072 is 6% off the corpus median 0.0077 for JPY. |  |
| medium | `CND10004SSX7` | bond_USD_amount | fx_consensus | Implied CNY->USD rate 0.1574 is 10% off the corpus median 0.1428 for CNY. |  |
| medium | `IDA0001547A1` | bond_USD_amount | fx_consensus | Implied IDR->USD rate 0.0001 is 9% off the corpus median 0.0001 for IDR. |  |
| medium | `CND10004VH09` | bond_USD_amount | fx_consensus | Implied CNY->USD rate 0.1577 is 10% off the corpus median 0.1428 for CNY. |  |

## Escalate — open the source PDF (235)

_Ambiguous or unverifiable from extracted data alone._

| sev | isin | field | check | why | proposed |
|-----|------|-------|-------|-----|----------|
| medium | `BE0000346552` | impact_value | impact_plausibility | Lifetime GHG emissions reduced/avoided: can't verify from extracted data — no LLM available; semantic plausibility unresolved. |  |
| medium | `BE0000346552` | impact_value | impact_plausibility | Annual renewable energy generation: can't verify from extracted data — no LLM available; semantic plausibility unresolved. |  |
| medium | `CND10004PTX1` | impact_value | impact_plausibility | Installed renewable energy capacity: can't verify from extracted data — no LLM available; semantic plausibility unresolved. |  |
| medium | `CND10004PTX1` | impact_value | impact_plausibility | Annual renewable energy generation: can't verify from extracted data — no LLM available; semantic plausibility unresolved. |  |
| medium | `CND10004PTX1` | impact_value | impact_plausibility | Annual GHG emissions reduced/avoided/sequestered: can't verify from extracted data — no LLM available; semantic plausibility unresolved. |  |
| medium | `XS2168683824` | impact_value | impact_plausibility | Annual GHG emissions reduced/avoided/sequestered: can't verify from extracted data — no LLM available; semantic plausibility unresolved. |  |
| medium | `XS3358268251` | impact_value | impact_plausibility | Annual energy savings: can't verify from extracted data — no LLM available; semantic plausibility unresolved. |  |
| medium | `XS3358268251` | impact_value | impact_plausibility | Area under biodiversity management: can't verify from extracted data — no LLM available; semantic plausibility unresolved. |  |
| medium | `XS3358268251` | impact_value | impact_plausibility | Annual renewable energy generation: can't verify from extracted data — no LLM available; semantic plausibility unresolved. |  |
| medium | `XS3358268251` | impact_value | impact_plausibility | Annual renewable energy generation: can't verify from extracted data — no LLM available; semantic plausibility unresolved. |  |
| medium | `XS3358268251` | impact_value | impact_plausibility | Annual renewable energy generation: can't verify from extracted data — no LLM available; semantic plausibility unresolved. |  |
| medium | `XS3358268251` | impact_value | impact_plausibility | Volume of water treated: can't verify from extracted data — no LLM available; semantic plausibility unresolved. |  |
| medium | `XS3358268251` | impact_value | impact_plausibility | Annual GHG emissions reduced/avoided/sequestered: can't verify from extracted data — no LLM available; semantic plausibility unresolved. |  |
| medium | `XS2272847141` | impact_value | impact_plausibility | Annual GHG emissions reduced/avoided/sequestered: can't verify from extracted data — no LLM available; semantic plausibility unresolved. |  |
| medium | `XS2272847141` | impact_value | impact_plausibility | Annual energy savings: can't verify from extracted data — no LLM available; semantic plausibility unresolved. |  |
| medium | `KR6032711E85` | impact_value | impact_plausibility | : can't verify from extracted data — no LLM available; semantic plausibility unresolved. |  |
| medium | `XS2388386810` | impact_value | impact_plausibility | : can't verify from extracted data — no LLM available; semantic plausibility unresolved. |  |
| medium | `US02765ULG75` | impact_value | impact_plausibility | Installed renewable energy capacity: can't verify from extracted data — no LLM available; semantic plausibility unresolved. |  |
| medium | `US02765ULG75` | impact_value | impact_plausibility | Annual renewable energy generation: can't verify from extracted data — no LLM available; semantic plausibility unresolved. |  |
| medium | `US02765ULG75` | impact_value | impact_plausibility | Installed renewable energy capacity: can't verify from extracted data — no LLM available; semantic plausibility unresolved. |  |
| medium | `US02765ULG75` | impact_value | impact_plausibility | Annual renewable energy generation: can't verify from extracted data — no LLM available; semantic plausibility unresolved. |  |
| medium | `US02765ULG75` | impact_value | impact_plausibility | Installed renewable energy capacity: can't verify from extracted data — no LLM available; semantic plausibility unresolved. |  |
| medium | `US02765ULG75` | impact_value | impact_plausibility | Annual renewable energy generation: can't verify from extracted data — no LLM available; semantic plausibility unresolved. |  |
| medium | `CND10008Q588` | impact_value | impact_plausibility | Annual GHG emissions reduced/avoided/sequestered: can't verify from extracted data — no LLM available; semantic plausibility unresolved. |  |
| medium | `CND10008Q588` | impact_value | impact_plausibility | Added passenger capacity: can't verify from extracted data — no LLM available; semantic plausibility unresolved. |  |
| medium | `CND10008Q588` | impact_value | impact_plausibility | Annual energy savings: can't verify from extracted data — no LLM available; semantic plausibility unresolved. |  |
| medium | `CND10008Q588` | impact_value | impact_plausibility | Added passenger capacity: can't verify from extracted data — no LLM available; semantic plausibility unresolved. |  |
| medium | `TH012803FC01` | impact_value | impact_plausibility | GHG emissions (footprint, scope 1-3): can't verify from extracted data — no LLM available; semantic plausibility unresolved. |  |
| medium | `TH012803FC01` | impact_value | impact_plausibility | Annual energy savings: can't verify from extracted data — no LLM available; semantic plausibility unresolved. |  |
| medium | `TH012803FC01` | impact_value | impact_plausibility | Area under biodiversity management: can't verify from extracted data — no LLM available; semantic plausibility unresolved. |  |
| medium | `XS2406607098` | impact_value | impact_plausibility | GHG emissions (footprint, scope 1-3): can't verify from extracted data — no LLM available; semantic plausibility unresolved. |  |
| medium | `XS2406607098` | impact_value | impact_plausibility | Beneficiaries reached: can't verify from extracted data — no LLM available; semantic plausibility unresolved. |  |
| medium | `BRSSCFDBS030` | impact_value | impact_plausibility | : can't verify from extracted data — no LLM available; semantic plausibility unresolved. |  |
| medium | `CND10007KF01` | impact_value | impact_plausibility | : can't verify from extracted data — no LLM available; semantic plausibility unresolved. |  |
| medium | `US89602HFH57` | impact_value | impact_plausibility | : can't verify from extracted data — no LLM available; semantic plausibility unresolved. |  |
| medium | `US02765MAJ18` | impact_value | impact_plausibility | Installed renewable energy capacity: can't verify from extracted data — no LLM available; semantic plausibility unresolved. |  |
| medium | `US02765MAJ18` | impact_value | impact_plausibility | Annual renewable energy generation: can't verify from extracted data — no LLM available; semantic plausibility unresolved. |  |
| medium | `US02765MAJ18` | impact_value | impact_plausibility | Installed renewable energy capacity: can't verify from extracted data — no LLM available; semantic plausibility unresolved. |  |
| medium | `US02765MAJ18` | impact_value | impact_plausibility | Annual renewable energy generation: can't verify from extracted data — no LLM available; semantic plausibility unresolved. |  |
| medium | `US02765MAJ18` | impact_value | impact_plausibility | Annual GHG emissions reduced/avoided/sequestered: can't verify from extracted data — no LLM available; semantic plausibility unresolved. |  |
| medium | `US02765MAJ18` | impact_value | impact_plausibility | Installed renewable energy capacity: can't verify from extracted data — no LLM available; semantic plausibility unresolved. |  |
| medium | `US02765MAJ18` | impact_value | impact_plausibility | Annual renewable energy generation: can't verify from extracted data — no LLM available; semantic plausibility unresolved. |  |
| medium | `US02765MAJ18` | impact_value | impact_plausibility | Installed renewable energy capacity: can't verify from extracted data — no LLM available; semantic plausibility unresolved. |  |
| medium | `US02765MAJ18` | impact_value | impact_plausibility | Annual renewable energy generation: can't verify from extracted data — no LLM available; semantic plausibility unresolved. |  |
| medium | `CA459058HF31` | impact_value | impact_plausibility | Annual energy savings: can't verify from extracted data — no LLM available; semantic plausibility unresolved. |  |
| medium | `CA459058HF31` | impact_value | impact_plausibility | Annual GHG emissions reduced/avoided/sequestered: can't verify from extracted data — no LLM available; semantic plausibility unresolved. |  |
| medium | `XS0739956042` | impact_value | impact_plausibility | Annual GHG emissions reduced/avoided/sequestered: can't verify from extracted data — no LLM available; semantic plausibility unresolved. |  |
| medium | `XS0739956042` | impact_value | impact_plausibility | Area under biodiversity management: can't verify from extracted data — no LLM available; semantic plausibility unresolved. |  |
| medium | `XS0739956042` | impact_value | impact_plausibility | Beneficiaries reached: can't verify from extracted data — no LLM available; semantic plausibility unresolved. |  |
| medium | `XS2314316162` | impact_value | impact_plausibility | Annual energy savings: can't verify from extracted data — no LLM available; semantic plausibility unresolved. |  |
| medium | `XS2314316162` | impact_value | impact_plausibility | Area under biodiversity management: can't verify from extracted data — no LLM available; semantic plausibility unresolved. |  |
| medium | `XS2314316162` | impact_value | impact_plausibility | Annual GHG emissions reduced/avoided/sequestered: can't verify from extracted data — no LLM available; semantic plausibility unresolved. |  |
| medium | `XS2314316162` | impact_value | impact_plausibility | Annual GHG emissions reduced/avoided/sequestered: can't verify from extracted data — no LLM available; semantic plausibility unresolved. |  |
| medium | `XS2314316162` | impact_value | impact_plausibility | Area of land managed: can't verify from extracted data — no LLM available; semantic plausibility unresolved. |  |
| medium | `USY4841PAD43` | impact_value | impact_plausibility | Affordable housing units: can't verify from extracted data — no LLM available; semantic plausibility unresolved. |  |
| medium | `US20775HQC06` | impact_value | impact_plausibility | : can't verify from extracted data — no LLM available; semantic plausibility unresolved. |  |
| medium | `US53945CGQ78` | impact_value | impact_plausibility | : can't verify from extracted data — no LLM available; semantic plausibility unresolved. |  |
| medium | `US59259N4P52` | impact_value | impact_plausibility | : can't verify from extracted data — no LLM available; semantic plausibility unresolved. |  |
| medium | `US797661XR11` | impact_value | impact_plausibility | : can't verify from extracted data — no LLM available; semantic plausibility unresolved. |  |
| medium | `CND10008R9V6` | impact_value | impact_plausibility | Installed renewable energy capacity: can't verify from extracted data — no LLM available; semantic plausibility unresolved. |  |
| medium | `CND10008R9V6` | impact_value | impact_plausibility | Annual renewable energy generation: can't verify from extracted data — no LLM available; semantic plausibility unresolved. |  |
| medium | `CND10008R9V6` | impact_value | impact_plausibility | Installed renewable energy capacity: can't verify from extracted data — no LLM available; semantic plausibility unresolved. |  |
| medium | `CND10008R9V6` | impact_value | impact_plausibility | Annual GHG emissions reduced/avoided/sequestered: can't verify from extracted data — no LLM available; semantic plausibility unresolved. |  |
| medium | `NZHNZD0230L2` | impact_value | impact_plausibility | Affordable housing units: can't verify from extracted data — no LLM available; semantic plausibility unresolved. |  |
| medium | `NZHNZD0230L2` | impact_value | impact_plausibility | Affordable housing units: can't verify from extracted data — no LLM available; semantic plausibility unresolved. |  |
| medium | `NZHNZD0230L2` | impact_value | impact_plausibility | Number of jobs created/retained: can't verify from extracted data — no LLM available; semantic plausibility unresolved. |  |
| medium | `MX91CM2S0009` | impact_value | impact_plausibility | Area under biodiversity management: can't verify from extracted data — no LLM available; semantic plausibility unresolved. |  |
| medium | `MX91CM2S0009` | impact_value | impact_plausibility | Area under biodiversity management: can't verify from extracted data — no LLM available; semantic plausibility unresolved. |  |
| medium | `MX91CM2S0009` | impact_value | impact_plausibility | Annual energy savings: can't verify from extracted data — no LLM available; semantic plausibility unresolved. |  |
| medium | `MX91CM2S0009` | impact_value | impact_plausibility | Annual GHG emissions reduced/avoided/sequestered: can't verify from extracted data — no LLM available; semantic plausibility unresolved. |  |
| medium | `MX91CM2S0009` | impact_value | impact_plausibility | Amount of waste treated: can't verify from extracted data — no LLM available; semantic plausibility unresolved. |  |
| medium | `US46143NAB64` | impact_value | impact_plausibility | Installed renewable energy capacity: can't verify from extracted data — no LLM available; semantic plausibility unresolved. |  |
| medium | `US46143NAB64` | impact_value | impact_plausibility | Annual renewable energy generation: can't verify from extracted data — no LLM available; semantic plausibility unresolved. |  |
| medium | `US46143NAB64` | impact_value | impact_plausibility | Annual renewable energy generation: can't verify from extracted data — no LLM available; semantic plausibility unresolved. |  |
| medium | `JP304451AP17` | impact_value | impact_plausibility | GHG emissions (footprint, scope 1-3): can't verify from extracted data — no LLM available; semantic plausibility unresolved. |  |
| medium | `CND10006XHZ0` | impact_value | impact_plausibility | : can't verify from extracted data — no LLM available; semantic plausibility unresolved. |  |
| medium | `US271015QR35` | impact_value | impact_plausibility | Area of land managed: can't verify from extracted data — no LLM available; semantic plausibility unresolved. |  |
| medium | `US271015QX03` | impact_value | impact_plausibility | Area of land managed: can't verify from extracted data — no LLM available; semantic plausibility unresolved. |  |
| medium | `CND10004VH09` | impact_value | impact_plausibility | Annual GHG emissions reduced/avoided/sequestered: can't verify from extracted data — no LLM available; semantic plausibility unresolved. |  |
| medium | `US45202BTT34` | impact_value | impact_plausibility | Affordable housing units: can't verify from extracted data — no LLM available; semantic plausibility unresolved. |  |
| medium | `US575829ET94` | impact_value | impact_plausibility | Volume of water treated: can't verify from extracted data — no LLM available; semantic plausibility unresolved. |  |
| medium | `US67766WH393` | impact_value | impact_plausibility | Households served: can't verify from extracted data — no LLM available; semantic plausibility unresolved. |  |
| medium | `CND10004SSX7` | impact_value | impact_plausibility | : can't verify from extracted data — no LLM available; semantic plausibility unresolved. |  |
| medium | `CND10005RJ77` | impact_value | impact_plausibility | : can't verify from extracted data — no LLM available; semantic plausibility unresolved. |  |
| medium | `DE000A19MFH4` | impact_value | impact_plausibility | : can't verify from extracted data — no LLM available; semantic plausibility unresolved. |  |
| medium | `IDA0001173A6` | impact_value | impact_plausibility | : can't verify from extracted data — no LLM available; semantic plausibility unresolved. |  |
| medium | `IDA0001342A7` | impact_value | impact_plausibility | : can't verify from extracted data — no LLM available; semantic plausibility unresolved. |  |
| medium | `IDA0001547A1` | impact_value | impact_plausibility | : can't verify from extracted data — no LLM available; semantic plausibility unresolved. |  |
| medium | `IDJ000019609` | impact_value | impact_plausibility | : can't verify from extracted data — no LLM available; semantic plausibility unresolved. |  |
| medium | `US13034A4P28` | impact_value | impact_plausibility | : can't verify from extracted data — no LLM available; semantic plausibility unresolved. |  |
| medium | `US13049SEU42` | impact_value | impact_plausibility | : can't verify from extracted data — no LLM available; semantic plausibility unresolved. |  |
| medium | `US438687DE29` | impact_value | impact_plausibility | : can't verify from extracted data — no LLM available; semantic plausibility unresolved. |  |
| medium | `US438687DN28` | impact_value | impact_plausibility | : can't verify from extracted data — no LLM available; semantic plausibility unresolved. |  |
| medium | `US441178CN86` | impact_value | impact_plausibility | : can't verify from extracted data — no LLM available; semantic plausibility unresolved. |  |
| medium | `US45203MJQ50` | impact_value | impact_plausibility | : can't verify from extracted data — no LLM available; semantic plausibility unresolved. |  |
| medium | `US45505MLF13` | impact_value | impact_plausibility | : can't verify from extracted data — no LLM available; semantic plausibility unresolved. |  |
| medium | `US45506EPL10` | impact_value | impact_plausibility | : can't verify from extracted data — no LLM available; semantic plausibility unresolved. |  |
| medium | `US545149JX57` | impact_value | impact_plausibility | : can't verify from extracted data — no LLM available; semantic plausibility unresolved. |  |
| medium | `US575829DR48` | impact_value | impact_plausibility | : can't verify from extracted data — no LLM available; semantic plausibility unresolved. |  |
| medium | `US59261AK221` | impact_value | impact_plausibility | : can't verify from extracted data — no LLM available; semantic plausibility unresolved. |  |
| medium | `US677632M244` | impact_value | impact_plausibility | : can't verify from extracted data — no LLM available; semantic plausibility unresolved. |  |
| medium | `US786005G854` | impact_value | impact_plausibility | : can't verify from extracted data — no LLM available; semantic plausibility unresolved. |  |
| medium | `US924258S980` | impact_value | impact_plausibility | : can't verify from extracted data — no LLM available; semantic plausibility unresolved. |  |
| medium | `XS1908374322` | impact_value | impact_plausibility | : can't verify from extracted data — no LLM available; semantic plausibility unresolved. |  |
| low | `BE0000346552` | post_icma_category | category_mapping | Category mapping unresolved: no LLM available; mapping unresolved |  |
| low | `BE0000346552` | post_icma_category | category_mapping | Category mapping unresolved: no LLM available; mapping unresolved |  |
| low | `BE0000346552` | post_icma_category | category_mapping | Category mapping unresolved: no LLM available; mapping unresolved |  |
| low | `BE0000346552` | post_icma_category | category_mapping | Category mapping unresolved: no LLM available; mapping unresolved |  |
| low | `BE0000346552` | post_icma_category | category_mapping | Category mapping unresolved: no LLM available; mapping unresolved |  |
| low | `BE0000346552` | post_icma_category | category_mapping | Category mapping unresolved: no LLM available; mapping unresolved |  |
| low | `XS3358268251` | post_icma_category | category_mapping | Category mapping unresolved: no LLM available; mapping unresolved |  |
| low | `XS3358268251` | post_icma_category | category_mapping | Category mapping unresolved: no LLM available; mapping unresolved |  |
| low | `XS3358268251` | post_icma_category | category_mapping | Category mapping unresolved: no LLM available; mapping unresolved |  |
| low | `XS3358268251` | post_icma_category | category_mapping | Category mapping unresolved: no LLM available; mapping unresolved |  |
| low | `XS3358268251` | post_icma_category | category_mapping | Category mapping unresolved: no LLM available; mapping unresolved |  |
| low | `XS3358268251` | post_icma_category | category_mapping | Category mapping unresolved: no LLM available; mapping unresolved |  |
| low | `XS3358268251` | post_icma_category | category_mapping | Category mapping unresolved: no LLM available; mapping unresolved |  |
| low | `KR6032711E85` | post_icma_category | category_mapping | Category mapping unresolved: no LLM available; mapping unresolved |  |
| low | `XS2272847141` | post_icma_category | category_mapping | Category mapping unresolved: no LLM available; mapping unresolved |  |
| low | `XS2272847141` | post_icma_category | category_mapping | Category mapping unresolved: no LLM available; mapping unresolved |  |
| low | `XS2272847141` | post_icma_category | category_mapping | Category mapping unresolved: no LLM available; mapping unresolved |  |
| low | `XS2272847141` | post_icma_category | category_mapping | Category mapping unresolved: no LLM available; mapping unresolved |  |
| low | `XS2272847141` | post_icma_category | category_mapping | Category mapping unresolved: no LLM available; mapping unresolved |  |
| low | `AU3CB0281046` | post_icma_category | category_mapping | Category mapping unresolved: no LLM available; mapping unresolved |  |
| low | `AU3CB0281046` | post_icma_category | category_mapping | Category mapping unresolved: no LLM available; mapping unresolved |  |
| low | `AU3CB0281046` | post_icma_category | category_mapping | Category mapping unresolved: no LLM available; mapping unresolved |  |
| low | `AU3CB0281046` | post_icma_category | category_mapping | Category mapping unresolved: no LLM available; mapping unresolved |  |
| low | `US50050GAM06` | post_icma_category | category_mapping | Category mapping unresolved: no LLM available; mapping unresolved |  |
| low | `US50050GAM06` | post_icma_category | category_mapping | Category mapping unresolved: no LLM available; mapping unresolved |  |
| low | `US50050GAM06` | post_icma_category | category_mapping | Category mapping unresolved: no LLM available; mapping unresolved |  |
| low | `US50050GAM06` | post_icma_category | category_mapping | Category mapping unresolved: no LLM available; mapping unresolved |  |
| low | `SE0006371324` | post_icma_category | category_mapping | Category mapping unresolved: no LLM available; mapping unresolved |  |
| low | `SE0006371324` | post_icma_category | category_mapping | Category mapping unresolved: no LLM available; mapping unresolved |  |
| low | `US20775HH227` | post_icma_category | category_mapping | Category mapping unresolved: no LLM available; mapping unresolved |  |
| low | `US20775HH227` | post_icma_category | category_mapping | Category mapping unresolved: no LLM available; mapping unresolved |  |
| low | `US20775HH227` | post_icma_category | category_mapping | Category mapping unresolved: no LLM available; mapping unresolved |  |
| low | `US20775HH227` | post_icma_category | category_mapping | Category mapping unresolved: no LLM available; mapping unresolved |  |
| low | `US20775HH227` | post_icma_category | category_mapping | Category mapping unresolved: no LLM available; mapping unresolved |  |
| low | `US20775HH227` | post_icma_category | category_mapping | Category mapping unresolved: no LLM available; mapping unresolved |  |
| low | `US20775HH227` | post_icma_category | category_mapping | Category mapping unresolved: no LLM available; mapping unresolved |  |
| low | `US20775HH227` | post_icma_category | category_mapping | Category mapping unresolved: no LLM available; mapping unresolved |  |
| low | `US20775JHG76` | post_icma_category | category_mapping | Category mapping unresolved: no LLM available; mapping unresolved |  |
| low | `DE000DB9WMP1` | post_icma_category | category_mapping | Category mapping unresolved: no LLM available; mapping unresolved |  |
| low | `DE000DB9WMP1` | post_icma_category | category_mapping | Category mapping unresolved: no LLM available; mapping unresolved |  |
| low | `XS0608302583` | post_icma_category | category_mapping | Category mapping unresolved: no LLM available; mapping unresolved |  |
| low | `XS0608302583` | post_icma_category | category_mapping | Category mapping unresolved: no LLM available; mapping unresolved |  |
| low | `XS0608302583` | post_icma_category | category_mapping | Category mapping unresolved: no LLM available; mapping unresolved |  |
| low | `XS3283529405` | post_icma_category | category_mapping | Category mapping unresolved: no LLM available; mapping unresolved |  |
| low | `XS3283529405` | post_icma_category | category_mapping | Category mapping unresolved: no LLM available; mapping unresolved |  |
| low | `XS3283529405` | post_icma_category | category_mapping | Category mapping unresolved: no LLM available; mapping unresolved |  |
| low | `XS3283529405` | post_icma_category | category_mapping | Category mapping unresolved: no LLM available; mapping unresolved |  |
| low | `XS3283529405` | post_icma_category | category_mapping | Category mapping unresolved: no LLM available; mapping unresolved |  |
| low | `XS3283529405` | post_icma_category | category_mapping | Category mapping unresolved: no LLM available; mapping unresolved |  |
| low | `DE000DHY5108` | post_icma_category | category_mapping | Category mapping unresolved: no LLM available; mapping unresolved |  |
| low | `DE000DHY5108` | post_icma_category | category_mapping | Category mapping unresolved: no LLM available; mapping unresolved |  |
| low | `DE000DHY5108` | post_icma_category | category_mapping | Category mapping unresolved: no LLM available; mapping unresolved |  |
| low | `DE000DHY5108` | post_icma_category | category_mapping | Category mapping unresolved: no LLM available; mapping unresolved |  |
| low | `NO0013735175` | post_icma_category | category_mapping | Category mapping unresolved: no LLM available; mapping unresolved |  |
| low | `NO0013735175` | post_icma_category | category_mapping | Category mapping unresolved: no LLM available; mapping unresolved |  |
| low | `NO0013735175` | post_icma_category | category_mapping | Category mapping unresolved: no LLM available; mapping unresolved |  |
| low | `US53945CGQ78` | post_icma_category | category_mapping | Category mapping unresolved: no LLM available; mapping unresolved |  |
| low | `US20775HQC06` | post_icma_category | category_mapping | Category mapping unresolved: no LLM available; mapping unresolved |  |
| low | `US20775HQC06` | post_icma_category | category_mapping | Category mapping unresolved: no LLM available; mapping unresolved |  |
| low | `US20775HQC06` | post_icma_category | category_mapping | Category mapping unresolved: no LLM available; mapping unresolved |  |
| low | `US20775HQC06` | post_icma_category | category_mapping | Category mapping unresolved: no LLM available; mapping unresolved |  |
| low | `US20775HQC06` | post_icma_category | category_mapping | Category mapping unresolved: no LLM available; mapping unresolved |  |
| low | `US20775HQC06` | post_icma_category | category_mapping | Category mapping unresolved: no LLM available; mapping unresolved |  |
| low | `US20775HQC06` | post_icma_category | category_mapping | Category mapping unresolved: no LLM available; mapping unresolved |  |
| low | `US20775HQC06` | post_icma_category | category_mapping | Category mapping unresolved: no LLM available; mapping unresolved |  |
| low | `CA459058HF31` | post_icma_category | category_mapping | Category mapping unresolved: no LLM available; mapping unresolved |  |
| low | `CA459058HF31` | post_icma_category | category_mapping | Category mapping unresolved: no LLM available; mapping unresolved |  |
| low | `CA459058HF31` | post_icma_category | category_mapping | Category mapping unresolved: no LLM available; mapping unresolved |  |
| low | `CA459058HF31` | post_icma_category | category_mapping | Category mapping unresolved: no LLM available; mapping unresolved |  |
| low | `CA459058HF31` | post_icma_category | category_mapping | Category mapping unresolved: no LLM available; mapping unresolved |  |
| low | `CA459058HF31` | post_icma_category | category_mapping | Category mapping unresolved: no LLM available; mapping unresolved |  |
| low | `CA459058HF31` | post_icma_category | category_mapping | Category mapping unresolved: no LLM available; mapping unresolved |  |
| low | `CA459058HF31` | post_icma_category | category_mapping | Category mapping unresolved: no LLM available; mapping unresolved |  |
| low | `XS0739956042` | post_icma_category | category_mapping | Category mapping unresolved: no LLM available; mapping unresolved |  |
| low | `XS0739956042` | post_icma_category | category_mapping | Category mapping unresolved: no LLM available; mapping unresolved |  |
| low | `XS0739956042` | post_icma_category | category_mapping | Category mapping unresolved: no LLM available; mapping unresolved |  |
| low | `XS0739956042` | post_icma_category | category_mapping | Category mapping unresolved: no LLM available; mapping unresolved |  |
| low | `XS2314316162` | post_icma_category | category_mapping | Category mapping unresolved: no LLM available; mapping unresolved |  |
| low | `XS2314316162` | post_icma_category | category_mapping | Category mapping unresolved: no LLM available; mapping unresolved |  |
| low | `XS2314316162` | post_icma_category | category_mapping | Category mapping unresolved: no LLM available; mapping unresolved |  |
| low | `USY4841PAD43` | post_icma_category | category_mapping | Category mapping unresolved: no LLM available; mapping unresolved |  |
| low | `CND10006XHZ0` | post_icma_category | category_mapping | Category mapping unresolved: no LLM available; mapping unresolved |  |
| low | `CND10008R9V6` | post_icma_category | category_mapping | Category mapping unresolved: no LLM available; mapping unresolved |  |
| low | `CND10008R9V6` | post_icma_category | category_mapping | Category mapping unresolved: no LLM available; mapping unresolved |  |
| low | `CND10008R9V6` | post_icma_category | category_mapping | Category mapping unresolved: no LLM available; mapping unresolved |  |
| low | `CND10008R9V6` | post_icma_category | category_mapping | Category mapping unresolved: no LLM available; mapping unresolved |  |
| low | `NZHNZD0230L2` | post_icma_category | category_mapping | Category mapping unresolved: no LLM available; mapping unresolved |  |
| low | `NZHNZD0230L2` | post_icma_category | category_mapping | Category mapping unresolved: no LLM available; mapping unresolved |  |
| low | `MX91CM2S0009` | post_icma_category | category_mapping | Category mapping unresolved: no LLM available; mapping unresolved |  |
| low | `MX91CM2S0009` | post_icma_category | category_mapping | Category mapping unresolved: no LLM available; mapping unresolved |  |
| low | `JP363340AP67` | post_icma_category | category_mapping | Category mapping unresolved: no LLM available; mapping unresolved |  |
| low | `HK0001221396` | post_icma_category | category_mapping | Category mapping unresolved: no LLM available; mapping unresolved |  |
| low | `HK0001221396` | post_icma_category | category_mapping | Category mapping unresolved: no LLM available; mapping unresolved |  |
| low | `HK0001221396` | post_icma_category | category_mapping | Category mapping unresolved: no LLM available; mapping unresolved |  |
| low | `HK0001221396` | post_icma_category | category_mapping | Category mapping unresolved: no LLM available; mapping unresolved |  |
| low | `HK0001221396` | post_icma_category | category_mapping | Category mapping unresolved: no LLM available; mapping unresolved |  |
| low | `HK0001221396` | post_icma_category | category_mapping | Category mapping unresolved: no LLM available; mapping unresolved |  |
| low | `HK0001221396` | post_icma_category | category_mapping | Category mapping unresolved: no LLM available; mapping unresolved |  |
| low | `US438687DN28` | post_icma_category | category_mapping | Category mapping unresolved: no LLM available; mapping unresolved |  |
| low | `US545149JX57` | post_icma_category | category_mapping | Category mapping unresolved: no LLM available; mapping unresolved |  |
| low | `US271015QR35` | post_icma_category | category_mapping | Category mapping unresolved: no LLM available; mapping unresolved |  |
| low | `US271015QX03` | post_icma_category | category_mapping | Category mapping unresolved: no LLM available; mapping unresolved |  |
| low | `US271015QX03` | post_icma_category | category_mapping | Category mapping unresolved: no LLM available; mapping unresolved |  |
| low | `US45203MJQ50` | post_icma_category | category_mapping | Category mapping unresolved: no LLM available; mapping unresolved |  |
| low | `US45203MJQ50` | post_icma_category | category_mapping | Category mapping unresolved: no LLM available; mapping unresolved |  |
| low | `US45203MJQ50` | post_icma_category | category_mapping | Category mapping unresolved: no LLM available; mapping unresolved |  |
| low | `US45505MHH25` | post_icma_category | category_mapping | Category mapping unresolved: no LLM available; mapping unresolved |  |
| low | `US45506EPL10` | post_icma_category | category_mapping | Category mapping unresolved: no LLM available; mapping unresolved |  |
| low | `US67766WH393` | post_icma_category | category_mapping | Category mapping unresolved: no LLM available; mapping unresolved |  |
| low | `US67766WH393` | post_icma_category | category_mapping | Category mapping unresolved: no LLM available; mapping unresolved |  |
| low | `US67766WH393` | post_icma_category | category_mapping | Category mapping unresolved: no LLM available; mapping unresolved |  |
| low | `US786005G854` | post_icma_category | category_mapping | Category mapping unresolved: no LLM available; mapping unresolved |  |
| low | `IDA0001173A6` | post_icma_category | category_mapping | Category mapping unresolved: no LLM available; mapping unresolved |  |
| low | `IDA0001173A6` | post_icma_category | category_mapping | Category mapping unresolved: no LLM available; mapping unresolved |  |
| low | `IDA0001173A6` | post_icma_category | category_mapping | Category mapping unresolved: no LLM available; mapping unresolved |  |
| low | `US924258S980` | post_icma_category | category_mapping | Category mapping unresolved: no LLM available; mapping unresolved |  |
| low | `US13034A7X25` | post_icma_category | category_mapping | Category mapping unresolved: no LLM available; mapping unresolved |  |
| low | `US13034A7X25` | post_icma_category | category_mapping | Category mapping unresolved: no LLM available; mapping unresolved |  |
| low | `US873519PV83` | post_icma_category | category_mapping | Category mapping unresolved: no LLM available; mapping unresolved |  |
| low | `US873519PV83` | post_icma_category | category_mapping | Category mapping unresolved: no LLM available; mapping unresolved |  |
| low | `US34446ABM99` | post_icma_category | category_mapping | Category mapping unresolved: no LLM available; mapping unresolved |  |
| low | `US34446ABM99` | post_icma_category | category_mapping | Category mapping unresolved: no LLM available; mapping unresolved |  |
| low | `US45203M3T64` | post_icma_category | category_mapping | Category mapping unresolved: no LLM available; mapping unresolved |  |
| low | `US45203MKZ31` | post_icma_category | category_mapping | Category mapping unresolved: no LLM available; mapping unresolved |  |
| low | `US45203MKZ31` | post_icma_category | category_mapping | Category mapping unresolved: no LLM available; mapping unresolved |  |
| low | `US45203MKZ31` | post_icma_category | category_mapping | Category mapping unresolved: no LLM available; mapping unresolved |  |
| low | `US45203MRS25` | post_icma_category | category_mapping | Category mapping unresolved: no LLM available; mapping unresolved |  |
| low | `US20364NFM48` | post_icma_category | category_mapping | Category mapping unresolved: no LLM available; mapping unresolved |  |
| low | `US91802RJK68` | post_icma_category | category_mapping | Category mapping unresolved: no LLM available; mapping unresolved |  |
| low | `US91802RJK68` | post_icma_category | category_mapping | Category mapping unresolved: no LLM available; mapping unresolved |  |
| low | `US958792FJ70` | post_icma_category | category_mapping | Category mapping unresolved: no LLM available; mapping unresolved |  |

## Rollup

**By check:** category_mapping (131), impact_plausibility (104), fx_consensus (16), share_def (3), trail_value_mismatch (1)

**By table:** cat_allocations (134), impacts (105), issuances (16)
