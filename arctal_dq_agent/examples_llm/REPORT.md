# Green-bond data-quality findings

_100 bonds · 1,062 rows scanned · 203 findings · mode: **Tier 0+1 (deterministic + LLM)** · 2026-06-25_

**How to read this.** Three buckets by what *you* need to do:

- **Auto-correct (3)** — recomputed exactly from other stored values; apply or spot-check.
- **Flag (153)** — a real inconsistency whose *fix* is debatable; needs a human call.
- **Escalate (47)** — only the source PDF settles it; the agent abstained on purpose.

Per-finding evidence (the conflicting numbers, trail excerpts) lives in `findings.jsonl` for tooling — this page stays one line per finding.

## Auto-correct — objective fixes (3)

_Recomputed from primitives; the value is determined._

| sev | isin | field | check | why | proposed |
|-----|------|-------|-------|-----|----------|
| low | `US45505MLF13` | post_allocation_share_of_total | share_def | Allocation share disagrees with USD÷bond (0.0001 stored vs 0.0001 recomputed). | `5.4e-05` |
| low | `US45506DQ995` | post_allocation_share_of_total | share_def | Allocation share disagrees with USD÷bond (0.0000 stored vs 0.0000 recomputed). | `7e-06` |
| low | `US6174468B80` | post_allocation_share_of_total | share_def | Allocation share disagrees with USD÷bond (0.0003 stored vs 0.0003 recomputed). | `0.000274` |

## Flag — needs a human call (153)

_Inconsistent, but which side is wrong is a judgment._

| sev | isin | field | check | why | proposed |
|-----|------|-------|-------|-----|----------|
| high | `CND10004PTX1` | impact_value | impact_plausibility | Impact value implausible: VERDICT=IMPLAUSIBLE conf=0.95 reason=Trail conversion error: 19亿千瓦时 = 1,900 GWh, not 13,819 GWh. ~7× overstatement. |  |
| high | `US02765ULG75` | impact_value | impact_plausibility | Impact value implausible: VERDICT=IMPLAUSIBLE conf=0.95 reason: Bond coverage 0% yet full $3.2M allocation used. Denominator error. |  |
| high | `US02765MAJ18` | impact_value | impact_plausibility | Impact value implausible: VERDICT=IMPLAUSIBLE conf=0.95 reason: Portfolio-level capacity wrongly attributed to bond; violates additionality principle. ~4σ outlier. |  |
| high | `US02765MAJ18` | impact_value | impact_plausibility | Impact value implausible: VERDICT=IMPLAUSIBLE conf=0.95 reason=Intensity 672,630 MWh/$M vastly exceeds cap (50,000) and peer median (1,096); likely full project misattributed to bond. |  |
| high | `US02765MAJ18` | impact_value | impact_plausibility | Impact value implausible: VERDICT=IMPLAUSIBLE conf=0.95 reason: Intensity 270,405 tCO2e/$M is ~7,600× peer median (35.5). Unit conversion error likely (short tons vs metric tons mishandled). |  |
| high | `XS2314316162` | impact_value | impact_plausibility | Impact value implausible: VERDICT=IMPLAUSIBLE conf=0.95 reason: Intensity 378 ha/$M is ~24× peer median (15.6). Derivation is arithmetically sound but source value (4.75M ha) is implausibly large for |  |
| high | `USY4841PAD43` | impact_value | impact_plausibility | Impact value implausible: VERDICT=IMPLAUSIBLE conf=0.95 reason: Intensity 7009 loans/$M is ~1140× peer median (6.1/$M); violates cap of 500 units/$M by 14×. |  |
| high | `MX91CM2S0009` | impact_value | impact_plausibility | Impact value implausible: VERDICT=IMPLAUSIBLE conf=0.95 reason: Intensity 285× peer median; 415k ha for $93M bond implausibly large area allocation per dollar. |  |
| high | `US271015QX03` | impact_value | impact_plausibility | Impact value implausible: VERDICT=IMPLAUSIBLE conf=0.95 reason: Intensity 34.29 ha/$M is 19× peer median (1.8 ha/$M). Extreme outlier suggests unit or allocation error. |  |
| high | `US575829ET94` | impact_value | impact_plausibility | Impact value implausible: VERDICT=IMPLAUSIBLE conf=0.95 reason: Intensity 574,891 m³/$M is ~943σ above peer median (600.8). Likely unit error in source portfolio estimate. |  |
| high | `CND10008Q588` | impact_value | impact_plausibility | Impact value implausible: VERDICT=IMPLAUSIBLE conf=0.92 reason: Intensity 441 MWh/$M is ~36σ above peer median (12.2). Portfolio-level allocation methodology unclear; likely mislabeled or scope error. |  |
| high | `TH012803FC01` | impact_value | impact_plausibility | Impact value implausible: VERDICT=IMPLAUSIBLE conf=0.92 reason: Intensity 369x peer median suggests unit error or massive scope creep. Verify source footnotes for tCO2e vs ktCO2e labeling. |  |
| high | `US02765MAJ18` | impact_value | impact_plausibility | Impact value implausible: VERDICT=IMPLAUSIBLE conf=0.92 reason: Intensity 224.9k MWh/$M is 205× peer median; exceeds physical cap by 4.5×. |  |
| high | `US02765MAJ18` | impact_value | impact_plausibility | Impact value implausible: VERDICT=IMPLAUSIBLE conf=0.92 reason: Intensity 413,758 MWh/$M is 8.3× peer median and violates stated cap by 8.3×. Unit mislabel suspected (MWh vs kWh). |  |
| high | `CA459058HF31` | impact_value | impact_plausibility | Impact value implausible: VERDICT=IMPLAUSIBLE conf=0.92 reason: Negative emissions (sequestration) with ~18σ outlier intensity. Bond size ($188M) cannot justify -880/M magnitude vs peer median +35.5/M |  |
| high | `XS0739956042` | impact_value | impact_plausibility | Impact value implausible: VERDICT=IMPLAUSIBLE conf=0.92 reason: Intensity 1,739 $/M is ~49× peer median (35.5); extreme outlier suggests unit/portfolio mislabeling. |  |
| high | `XS2314316162` | impact_value | impact_plausibility | Impact value implausible: VERDICT=IMPLAUSIBLE conf=0.92 reason: Intensity 615 MWh/$M is ~50× peer median (12.2). Derivation arithmetically sound but source allocation implausibly high. |  |
| high | `XS2314316162` | impact_value | impact_plausibility | Impact value implausible: VERDICT=IMPLAUSIBLE conf=0.92 reason: Intensity 51.1 ha/$M is 28× peer median (1.8). Likely allocation share or category mislabeling. |  |
| high | `CND10008R9V6` | impact_value | impact_plausibility | Impact value implausible: VERDICT=IMPLAUSIBLE conf=0.92 reason: Intensity 22,207 MWh/$M is ~20× peer median (1,096); extreme outlier suggests denominator error or project scale mislabeling. |  |
| high | `CND10008R9V6` | impact_value | impact_plausibility | Impact value implausible: VERDICT=IMPLAUSIBLE conf=0.92 reason: Critical unit conversion error. 11.24万 = 112,400, but review notes flag source as 1.24万 = 12,400. Intensity 2,423/$M is ~68× peer median |  |
| high | `MX91CM2S0009` | impact_value | impact_plausibility | Impact value implausible: VERDICT=IMPLAUSIBLE conf=0.92 reason=Intensity 276× peer median; group-level 2022 figure misattributed to single 2024 bond allocation. |  |
| high | `MX91CM2S0009` | impact_value | impact_plausibility | Impact value implausible: VERDICT=IMPLAUSIBLE conf=0.92 reason: Intensity 128 MWh/$M is ~10.5σ above peer median (12.2). Outlier magnitude implausible unless project portfolio fundamentally different. |  |
| high | `MX91CM2S0009` | impact_value | impact_plausibility | Impact value implausible: VERDICT=IMPLAUSIBLE conf=0.92 reason=Metric labeled "Annual" but sourced as lifetime figure; 473k tCO2e is lifetime not annualized; unit mislabeling. |  |
| high | `CND10008Q588` | impact_value | impact_plausibility | Impact value implausible: VERDICT=IMPLAUSIBLE conf=0.85 reason=Intensity 652,784/\$M is ~4× peer median 154,253/\$M; likely unit mislabel. |  |
| high | `XS2314316162` | impact_value | impact_plausibility | Impact value implausible: VERDICT=IMPLAUSIBLE conf=0.85 reason=Source entry is ~5M tCO2e/project; bond_share likely misapplied to wrong category. |  |
| high | `XS2314316162` | impact_value | impact_plausibility | Impact value implausible: VERDICT=IMPLAUSIBLE conf=0.85 reason=6,000,000 tCO2e source figure likely ktCO2e mislabel; intensity 13× peer median. |  |
| high | `CND10008R9V6` | impact_value | impact_plausibility | Impact value implausible: VERDICT=IMPLAUSIBLE conf=0.85 reason=Intensity 32x peer median; likely solar-only subset, not total capacity. |  |
| high | `US46143NAB64` | impact_value | impact_plausibility | Impact value implausible: VERDICT=IMPLAUSIBLE conf=0.85 reason=435 MWh/$M is 400× below peer median of 1096 MWh/$M. Wait, let me reconsider. The peer median is 1096.4 MWh/$M, and this bond shows 435.7 |  |
| high | `US02765ULG75` | impact_value | impact_plausibility | Impact value implausible: VERDICT=IMPLAUSIBLE conf=0.82 reason=Intensity 35x peer median; likely bond_USD denominator is wrong (project vs portfolio). |  |
| high | `US02765ULG75` | impact_value | impact_plausibility | Impact value implausible: VERDICT=IMPLAUSIBLE conf=0.82 reason=No bond_share applied to project-level generation; intensity 67× peer median. |  |
| high | `US46143NAB64` | impact_value | impact_plausibility | Impact value implausible: VERDICT=IMPLAUSIBLE conf=0.82 reason=Source stated 2,214.3 MWh; GWh conversion assumption is unverified speculation. |  |
| high | `BE0000346552` | impact_value | trail_value_mismatch | Annual renewable energy generation: stored impact_value 9.89e+08 disagrees with the 989000 its own source_trail derives. |  |
| medium | `AU3CB0281046` | post_icma_category | category_mapping | Possible misattribution: VERDICT=MISMATCH conf=0.95 reason=Not in ICMA list. Could be Climate Change Adaptation if disaster-focused. |  |
| medium | `US50050GAM06` | post_icma_category | category_mapping | Possible misattribution: VERDICT=MISMATCH conf=0.95 reason="Employment Generation and socioeconomic advancement are not ICMA green categories. Reclassify or reject." |  |
| medium | `US50050GAM06` | post_icma_category | category_mapping | Possible misattribution: VERDICT=MISMATCH conf=0.95 reason="Employment Generation and Socioeconomic Advancement are not ICMA green categories. Ineligible for green bonds." |  |
| medium | `US20775HH227` | post_icma_category | category_mapping | Possible misattribution: VERDICT=MISMATCH conf=0.95 reason=Social housing support; not an ICMA green category. Should be excluded or reclassified. |  |
| medium | `US20775HH227` | post_icma_category | category_mapping | Possible misattribution: VERDICT=MISMATCH conf=0.95 reason=Affordable Housing is not an ICMA green category. This is a social bond, not green-bond eligible. |  |
| medium | `US20775HH227` | post_icma_category | category_mapping | Possible misattribution: VERDICT=MISMATCH conf=0.95 reason=Affordable Housing not ICMA category. Consider Green Buildings if certified. |  |
| medium | `US20775HH227` | post_icma_category | category_mapping | Possible misattribution: VERDICT=MISMATCH conf=0.95 reason: "Affordable Housing" is not an ICMA green category. Project belongs to social finance, outside scope. |  |
| medium | `US20775HH227` | post_icma_category | category_mapping | Possible misattribution: VERDICT=MISMATCH conf=0.95 reason: Affordable Housing not in ICMA green categories. Better category: Social/excluded from green bonds. |  |
| medium | `US20775HH227` | post_icma_category | category_mapping | Possible misattribution: VERDICT=MISMATCH conf=0.95 reason: "Affordable Housing" is not an ICMA green category. Should be reclassified as "Social" or rejected. |  |
| medium | `US20775HH227` | post_icma_category | category_mapping | Possible misattribution: VERDICT=MISMATCH conf=0.95 reason=Social housing program. Better category: Social (not ICMA green-eligible). |  |
| medium | `US20775JHG76` | post_icma_category | category_mapping | Possible misattribution: VERDICT=MISMATCH conf=0.95 reason=Assigned category "Affordable Housing" not in ICMA list. Better category: "Green Buildings" if energy-efficient multifamily housing. |  |
| medium | `XS0608302583` | post_icma_category | category_mapping | Possible misattribution: VERDICT=MISMATCH conf=0.95 reason=Public lighting with LED technology is Energy Efficiency, not Clean Transportation. |  |
| medium | `US20775HQC06` | post_icma_category | category_mapping | Possible misattribution: VERDICT=MISMATCH conf=0.95 reason: Teacher loan program doesn't fit green bond categories. Should be excluded or reclassified as non-environmental social bond. |  |
| medium | `US20775HQC06` | post_icma_category | category_mapping | Possible misattribution: VERDICT=MISMATCH conf=0.95 reason=Assigned category "Affordable Housing" not in ICMA green bond categories. Does not fit any official ICMA category. |  |
| medium | `US20775HQC06` | post_icma_category | category_mapping | Possible misattribution: VERDICT=MISMATCH conf=0.95 reason: "Affordable Housing" is not an ICMA green category. Better fit: Green Buildings (if energy-efficient) or ineligible. |  |
| medium | `US20775HQC06` | post_icma_category | category_mapping | Possible misattribution: VERDICT=MISMATCH conf=0.95 reason=Not ICMA green category. Affordable housing/socioeconomic programs excluded from ICMA framework. |  |
| medium | `US20775HQC06` | post_icma_category | category_mapping | Possible misattribution: VERDICT=MISMATCH conf=0.95 reason=Not in ICMA green categories. Consider Green Buildings if retrofitting/efficiency standards apply. |  |
| medium | `US20775HQC06` | post_icma_category | category_mapping | Possible misattribution: VERDICT=MISMATCH conf=0.95 reason=Affordable Housing not ICMA category. Better fit: Green Buildings if energy-efficient; otherwise ineligible. |  |
| medium | `CA459058HF31` | post_icma_category | category_mapping | Possible misattribution: VERDICT=MISMATCH conf=0.95 reason=Assigned category not in ICMA list. Health Care fits no standard green category. |  |
| medium | `CA459058HF31` | post_icma_category | category_mapping | Possible misattribution: VERDICT=MISMATCH conf=0.95 reason="Employment Generation is not an ICMA category. Social/labor focus, not environmental." |  |
| medium | `CA459058HF31` | post_icma_category | category_mapping | Possible misattribution: VERDICT=MISMATCH conf=0.95 reason="Food Security not ICMA category. Better fit: Environmentally Sustainable Management of Living Natural Resources." |  |
| medium | `CA459058HF31` | post_icma_category | category_mapping | Possible misattribution: VERDICT=MISMATCH conf=0.95 reason=Not a green bond category. Reassign to ineligible or social bond framework. |  |
| medium | `CND10008R9V6` | post_icma_category | category_mapping | Possible misattribution: VERDICT=MISMATCH conf=0.95 reason=Renewable Energy storage facilities belong to Renewable Energy category, not Energy Efficiency. |  |
| medium | `CND10008R9V6` | post_icma_category | category_mapping | Possible misattribution: VERDICT=MISMATCH conf=0.95 reason=Issuer reports circular economy products; better category is Eco-efficient/Circular Economy products. |  |
| medium | `NZHNZD0230L2` | post_icma_category | category_mapping | Possible misattribution: VERDICT=MISMATCH conf=0.95 reason=Affordable Housing not ICMA green category. Better: Green Buildings if construction focus. |  |
| medium | `NZHNZD0230L2` | post_icma_category | category_mapping | Possible misattribution: VERDICT=MISMATCH conf=0.95 reason=Assigned category (Affordable Housing) not in ICMA list. Better fit: Green Buildings. |  |
| medium | `HK0001221396` | post_icma_category | category_mapping | Possible misattribution: VERDICT=MISMATCH conf=0.95 reason=Telecom digital inclusion doesn't fit ICMA categories. Not green-bond eligible. |  |
| medium | `HK0001221396` | post_icma_category | category_mapping | Possible misattribution: VERDICT=MISMATCH conf=0.95 reason=Assigned category "Affordable Housing" not in ICMA list. Reclassify as ineligible or "Green Buildings" if retrofitting. |  |
| medium | `HK0001221396` | post_icma_category | category_mapping | Possible misattribution: VERDICT=MISMATCH conf=0.95 reason=Project is Renewable Energy generation, not Energy Efficiency. Reclassify to Renewable Energy. |  |
| medium | `US45203MJQ50` | post_icma_category | category_mapping | Possible misattribution: VERDICT=MISMATCH conf=0.95 reason=Neither category fits ICMA framework. Not an eligible green bond use-of-proceeds. |  |
| medium | `US45203MJQ50` | post_icma_category | category_mapping | Possible misattribution: VERDICT=MISMATCH conf=0.95 reason: Neither category fits ICMA framework. Project ineligible for green bonds; suggest reclassification or exclusion. |  |
| medium | `US45203MJQ50` | post_icma_category | category_mapping | Possible misattribution: VERDICT=MISMATCH conf=0.95 reason=Affordable Housing is not an ICMA category. Should be classified as Access to Essential Services or excluded. |  |
| medium | `US45505MHH25` | post_icma_category | category_mapping | Possible misattribution: VERDICT=MISMATCH conf=0.95 reason: Assigned category "Affordable Basic Infrastructure" is not ICMA-eligible. Should be "Sustainable Water and Wastewater Management." |  |
| medium | `US34446ABM99` | post_icma_category | category_mapping | Possible misattribution: VERDICT=MISMATCH conf=0.95 reason=Telecommunications infrastructure does not align with ICMA categories. No eligible match found. |  |
| medium | `US34446ABM99` | post_icma_category | category_mapping | Possible misattribution: VERDICT=MISMATCH conf=0.95 reason=Neither category is ICMA-eligible. Should classify as Clean Transportation or Energy Efficiency if infrastructure-related. |  |
| medium | `US45203M3T64` | post_icma_category | category_mapping | Possible misattribution: VERDICT=MISMATCH conf=0.95 reason="Financial education isn't green bond eligible. No environmental benefit identified." |  |
| medium | `US45203MKZ31` | post_icma_category | category_mapping | Possible misattribution: VERDICT=MISMATCH conf=0.95 reason=Assigned category "Affordable Housing" not in ICMA list. Better: "Green Buildings" or excluded. |  |
| medium | `US45203MKZ31` | post_icma_category | category_mapping | Possible misattribution: VERDICT=MISMATCH conf=0.95 reason=Affordable Housing not ICMA category. Better fit: Green Buildings (if accessibility features included) or none. |  |
| medium | `US45203MKZ31` | post_icma_category | category_mapping | Possible misattribution: VERDICT=MISMATCH conf=0.95 reason=Affordable Housing is not an ICMA category. Better fit: Green Buildings or Climate Change Adaptation. |  |
| medium | `US45203MRS25` | post_icma_category | category_mapping | Possible misattribution: VERDICT=MISMATCH conf=0.95 reason: "Affordable Housing" is not an ICMA category. Reclassify as "Green Buildings" per issuer's reporting. |  |
| medium | `BE0000346552` | post_icma_category | category_mapping | Possible misattribution: VERDICT=MISMATCH conf=0.9 reason=Reusable packaging aligns better with Eco-efficient/Circular Economy products category. |  |
| medium | `XS3358268251` | post_icma_category | category_mapping | Possible misattribution: VERDICT=MISMATCH conf=0.9 reason=Issuer reports Energy Efficiency; 35% energy consumption reduction aligns better with that category. |  |
| medium | `AU3CB0281046` | post_icma_category | category_mapping | Possible misattribution: VERDICT=MISMATCH conf=0.9 reason=Lithium extraction is Renewable Energy; transport electrification support is Clean Transportation. |  |
| medium | `HK0001221396` | post_icma_category | category_mapping | Possible misattribution: VERDICT=MISMATCH conf=0.9 reason=Issuer description is socioeconomic, not renewable energy. Subcategory mentions renewable but issuer framing differs fundamentally. |  |
| medium | `BE0000346552` | post_icma_category | category_mapping | Possible misattribution: VERDICT=MISMATCH conf=0.85 reason=Better category: Environmentally Sustainable Management of Living Natural Resources or Terrestrial and Aquatic Biodiversity. |  |
| medium | `BE0000346552` | post_icma_category | category_mapping | Possible misattribution: VERDICT=MISMATCH conf=0.85 reason=Issuer correctly reports Energy Efficiency; assigned Green Buildings is less precise given focus on efficiency improvements. |  |
| medium | `XS3358268251` | post_icma_category | category_mapping | Possible misattribution: VERDICT=MISMATCH conf=0.85 reason=Projects fit "Environmentally Sustainable Management of Living Natural Resources" better than Climate Change Adaptation. |  |
| medium | `XS3358268251` | post_icma_category | category_mapping | Possible misattribution: VERDICT=MISMATCH conf=0.85 reason=Issuer reports Energy Efficiency; green hydrogen production is Renewable Energy. Correct category: Renewable Energy. |  |
| medium | `XS3358268251` | post_icma_category | category_mapping | Possible misattribution: VERDICT=MISMATCH conf=0.85 reason=Transmission/distribution infrastructure doesn't reduce consumption. Assign to Renewable Energy. |  |
| medium | `XS3358268251` | post_icma_category | category_mapping | Possible misattribution: VERDICT=MISMATCH conf=0.85 reason=Primary benefit is water infrastructure resilience. Better category: Climate Change Adaptation or Sustainable Water and Wastewater Management |  |
| medium | `XS3358268251` | post_icma_category | category_mapping | Possible misattribution: VERDICT=MISMATCH conf=0.85 reason=Anaerobic digestion of bio-waste is waste treatment/recycling, better fits Pollution Prevention and Control. |  |
| medium | `XS2272847141` | post_icma_category | category_mapping | Possible misattribution: VERDICT=MISMATCH conf=0.85 reason=Data center energy efficiency fits Energy Efficiency better than Green Buildings category. |  |
| medium | `XS2272847141` | post_icma_category | category_mapping | Possible misattribution: VERDICT=MISMATCH conf=0.85 reason=Primary benefit is energy efficiency, not building improvements. Energy Efficiency is better category. |  |
| medium | `SE0006371324` | post_icma_category | category_mapping | Possible misattribution: VERDICT=MISMATCH conf=0.85 reason=Issuer reports Energy Efficiency; subcategory mentions water/sewage. Water category correct. |  |
| medium | `SE0006371324` | post_icma_category | category_mapping | Possible misattribution: VERDICT=MISMATCH conf=0.85 reason=Eligibility criteria describe energy efficiency, not biodiversity. Better category: Energy Efficiency. |  |
| medium | `DE000DB9WMP1` | post_icma_category | category_mapping | Possible misattribution: VERDICT=MISMATCH conf=0.85 reason=Green Buildings better fits BREEAM/LEED certifications. Energy Efficiency is component, not primary category. |  |
| medium | `DE000DB9WMP1` | post_icma_category | category_mapping | Possible misattribution: VERDICT=MISMATCH conf=0.85 reason=Better category is Eco-efficient/Circular Economy products; focuses on production technology innovation, not pollution control. |  |
| medium | `XS3283529405` | post_icma_category | category_mapping | Possible misattribution: VERDICT=MISMATCH conf=0.85 reason=Waste collection/recycling fits Eco-efficient & Circular Economy better than Pollution Prevention. |  |
| medium | `XS3283529405` | post_icma_category | category_mapping | Possible misattribution: VERDICT=MISMATCH conf=0.85 reason=Waste heat recovery is Energy Efficiency, not Renewable Energy. Correct categorization: Energy Efficiency. |  |
| medium | `XS3283529405` | post_icma_category | category_mapping | Possible misattribution: VERDICT=MISMATCH conf=0.85 reason=Storage for renewable energy intermittency management belongs in Renewable Energy, not Energy Efficiency. |  |
| medium | `XS3283529405` | post_icma_category | category_mapping | Possible misattribution: VERDICT=MISMATCH conf=0.85 reason=Project fits Eco-efficient/Circular Economy better; resource recovery is core circular principle. |  |
| medium | `XS3283529405` | post_icma_category | category_mapping | Possible misattribution: VERDICT=MISMATCH conf=0.85 reason=Hazardous waste recovery better fits Eco-efficient/Circular Economy. Reallocation recommended. |  |
| medium | `DE000DHY5108` | post_icma_category | category_mapping | Possible misattribution: VERDICT=MISMATCH conf=0.85 reason=Green Buildings is more specific; energy performance is secondary attribute here. |  |
| medium | `DE000DHY5108` | post_icma_category | category_mapping | Possible misattribution: VERDICT=MISMATCH conf=0.85 reason=Green Buildings is more appropriate; energy efficiency is a component, not primary category. |  |
| medium | `DE000DHY5108` | post_icma_category | category_mapping | Possible misattribution: VERDICT=MISMATCH conf=0.85 reason=Issuer reported Green Buildings; pipeline assigned Energy Efficiency. Green Buildings is more appropriate. |  |
| medium | `DE000DHY5108` | post_icma_category | category_mapping | Possible misattribution: VERDICT=MISMATCH conf=0.85 reason=Green Buildings better fits. Project focuses on building certification standards (LEED, BREEAM), not energy efficiency retrofits. |  |
| medium | `NO0013735175` | post_icma_category | category_mapping | Possible misattribution: VERDICT=MISMATCH conf=0.85 reason=Better fit: Eco-efficient/Circular Economy products. Focus on reuse and waste sorting aligns with circular economy, not pollution prevention. |  |
| medium | `NO0013735175` | post_icma_category | category_mapping | Possible misattribution: VERDICT=MISMATCH conf=0.85 reason=Fish farming operations better fit Environmentally Sustainable Management of Living Natural Resources than Biodiversity Conservation. |  |
| medium | `US53945CGQ78` | post_icma_category | category_mapping | Possible misattribution: VERDICT=MISMATCH conf=0.85 reason=Wastewater facility construction/operation fits Sustainable Water and Wastewater Management, not Pollution Prevention and Control. |  |
| medium | `US20775HQC06` | post_icma_category | category_mapping | Possible misattribution: VERDICT=MISMATCH conf=0.85 reason=Issuer correctly reports Energy Efficiency; assigned Green Buildings category is inappropriate. |  |
| medium | `US20775HQC06` | post_icma_category | category_mapping | Possible misattribution: VERDICT=MISMATCH conf=0.85 reason=Energy Efficiency is more appropriate; Zero Energy Ready Home standards primarily focus on operational energy performance. |  |
| medium | `XS0739956042` | post_icma_category | category_mapping | Possible misattribution: VERDICT=MISMATCH conf=0.85 reason=Food Security not in ICMA list. Better category: Environmentally Sustainable Management of Living Natural Resources. |  |
| medium | `XS2314316162` | post_icma_category | category_mapping | Possible misattribution: VERDICT=MISMATCH conf=0.85 reason=Assigned category "Food Security" not in ICMA list. Better fit: "Environmentally Sustainable Management of Living Natural Resources" or "Clim |  |
| medium | `XS2314316162` | post_icma_category | category_mapping | Possible misattribution: VERDICT=MISMATCH conf=0.85 reason=GHG emission reduction tech aligns better with Renewable Energy or Energy Efficiency than Pollution Prevention and Control. |  |
| medium | `XS2314316162` | post_icma_category | category_mapping | Possible misattribution: VERDICT=MISMATCH conf=0.85 reason=Mixed projects. Energy Efficiency better fits building component; methane management fits Pollution Prevention. |  |
| medium | `USY4841PAD43` | post_icma_category | category_mapping | Possible misattribution: VERDICT=MISMATCH conf=0.85 reason=Issuer reports Energy Efficiency; assigned Green Buildings incorrect. Description fits Energy Efficiency better. |  |
| medium | `CND10006XHZ0` | post_icma_category | category_mapping | Possible misattribution: VERDICT=MISMATCH conf=0.85 reason=Issuer's "Pollution Prevention and Control" is more accurate; equipment manufacturing fits better there. |  |
| medium | `CND10008R9V6` | post_icma_category | category_mapping | Possible misattribution: VERDICT=MISMATCH conf=0.85 reason=Issuer reports circular economy focus; subcategory emphasizes energy efficiency. Better: Eco-efficient/Circular Economy products. |  |
| medium | `MX91CM2S0009` | post_icma_category | category_mapping | Possible misattribution: VERDICT=MISMATCH conf=0.85 reason=Description emphasizes biodiversity/endangered species; better category is "Terrestrial and Aquatic Biodiversity". |  |
| medium | `JP363340AP67` | post_icma_category | category_mapping | Possible misattribution: VERDICT=MISMATCH conf=0.85 reason=Safety technology R&D better fits Pollution Prevention and Control, not Clean Transportation. |  |
| medium | `HK0001221396` | post_icma_category | category_mapping | Possible misattribution: VERDICT=MISMATCH conf=0.85 reason=Manufacturing green construction materials fits Green Buildings, not Circular Economy. |  |
| medium | `HK0001221396` | post_icma_category | category_mapping | Possible misattribution: VERDICT=MISMATCH conf=0.85 reason=Carbon projects fit Renewable Energy or Climate Change Adaptation better than Pollution Prevention and Control. |  |
| medium | `US438687DN28` | post_icma_category | category_mapping | Possible misattribution: VERDICT=MISMATCH conf=0.85 reason=Waste-to-energy is primarily Pollution Prevention and Control, not Renewable Energy. |  |
| medium | `US545149JX57` | post_icma_category | category_mapping | Possible misattribution: VERDICT=MISMATCH conf=0.85 reason=Primary focus is wastewater facilities; should be categorized as Sustainable Water and Wastewater Management, not Pollution Prevention. |  |
| medium | `US271015QR35` | post_icma_category | category_mapping | Possible misattribution: VERDICT=MISMATCH conf=0.85 reason=Park acquisition better fits Terrestrial & Aquatic Biodiversity Conservation than Living Natural Resources Management. |  |
| medium | `US45506EPL10` | post_icma_category | category_mapping | Possible misattribution: VERDICT=MISMATCH conf=0.85 reason=Lead removal is water quality protection, fitting Pollution Prevention and Control better than Sustainable Water and Wastewater Management. |  |
| medium | `US67766WH393` | post_icma_category | category_mapping | Possible misattribution: VERDICT=MISMATCH conf=0.85 reason: "Long-term resource management planning" better fits Environmentally Sustainable Management of Living Natural Resources, not Pollution Preve |  |
| medium | `US67766WH393` | post_icma_category | category_mapping | Possible misattribution: VERDICT=MISMATCH conf=0.85 reason=Stormwater management fits Pollution Prevention and Control better than Sustainable Water and Wastewater Management. |  |
| medium | `US67766WH393` | post_icma_category | category_mapping | Possible misattribution: VERDICT=MISMATCH conf=0.85 reason=Primary benefit is pollution prevention via CSO elimination, not water/wastewater management infrastructure. |  |
| medium | `US786005G854` | post_icma_category | category_mapping | Possible misattribution: VERDICT=MISMATCH conf=0.85 reason=Distribution infrastructure supports renewable integration, not efficiency. Assign Clean Transportation or Renewable Energy instead. |  |
| medium | `US13034A7X25` | post_icma_category | category_mapping | Possible misattribution: VERDICT=MISMATCH conf=0.85 reason=Pipeline correct. Estuary conservation primarily fits Terrestrial & Aquatic Biodiversity, not Wastewater Management. |  |
| medium | `US13034A7X25` | post_icma_category | category_mapping | Possible misattribution: VERDICT=MISMATCH conf=0.85 reason=Watershed projects fit Water and Wastewater Management better than Biodiversity Conservation. |  |
| medium | `US873519PV83` | post_icma_category | category_mapping | Possible misattribution: VERDICT=MISMATCH conf=0.85 reason=LED lighting is Energy Efficiency, not Pollution Prevention and Control. |  |
| medium | `US873519PV83` | post_icma_category | category_mapping | Possible misattribution: VERDICT=MISMATCH conf=0.85 reason=Advanced metering and substation upgrades primarily support grid modernization/energy distribution rather than energy efficiency. **Better ca |  |
| medium | `US20364NFM48` | post_icma_category | category_mapping | Possible misattribution: VERDICT=MISMATCH conf=0.85 reason=Project features energy-efficient building components. Better category: Energy Efficiency. |  |
| medium | `US91802RJK68` | post_icma_category | category_mapping | Possible misattribution: VERDICT=MISMATCH conf=0.85 reason=Better category: Energy Efficiency. Distribution management improves grid resilience and efficiency, not climate adaptation. |  |
| medium | `US91802RJK68` | post_icma_category | category_mapping | Possible misattribution: VERDICT=MISMATCH conf=0.85 reason=Grid infrastructure for renewable integration is Clean Transportation or Energy Efficiency, not Renewable Energy generation itself. |  |
| medium | `US958792FJ70` | post_icma_category | category_mapping | Possible misattribution: VERDICT=MISMATCH conf=0.85 reason=Emergency generators support water infrastructure operations; fits Sustainable Water and Wastewater Management better. |  |
| medium | `XS3358268251` | post_icma_category | category_mapping | Possible misattribution: VERDICT=MISMATCH conf=0.8 reason=Forest/ecosystem restoration fits Terrestrial & Aquatic Biodiversity better than Living Natural Resources Management. |  |
| medium | `XS3283529405` | post_icma_category | category_mapping | Possible misattribution: VERDICT=MISMATCH conf=0.75 reason=Issuer reported "Living Natural Resources & Land Use" but pipeline assigned "Terrestrial & Aquatic Biodiversity." Different ICMA categories. |  |
| medium | `CA459058HF31` | post_icma_category | category_mapping | Possible misattribution: VERDICT=MISMATCH conf=0.75 reason=Description focuses on environmental protection/disaster risk management; better fit is Pollution Prevention and Control or Climate Change Ad |  |
| medium | `CA459058HF31` | post_icma_category | category_mapping | Possible misattribution: VERDICT=MISMATCH conf=0.75 reason="Description too broad. Contains multiple ICMA categories beyond Renewable Energy alone." |  |
| medium | `CND10008R9V6` | post_icma_category | category_mapping | Possible misattribution: VERDICT=MISMATCH conf=0.75 reason=Issuer's category better fits description. Restoration and decontamination align more with Sustainable Management of Living Natural Resources |  |
| medium | `US924258S980` | post_icma_category | category_mapping | Possible misattribution: VERDICT=MISMATCH conf=0.75 reason=Subcategory describes habitat restoration/conservation; better fit is Terrestrial & Aquatic Biodiversity. |  |
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
| medium | `KR6032711E85` | post_icma_category | category_mapping | Possible misattribution: VERDICT=MISMATCH conf=0.65 reason=Description too vague; likely Social/Community project, not environmental pollution control. |  |

## Escalate — open the source PDF (47)

_Ambiguous or unverifiable from extracted data alone._

| sev | isin | field | check | why | proposed |
|-----|------|-------|-------|-----|----------|
| medium | `XS1908374322` | impact_value | impact_plausibility | : can't verify from extracted data — VERDICT=UNSURE conf=0.95 reason=No metric, value, unit, or trail provided to evaluate.. |  |
| medium | `KR6032711E85` | impact_value | impact_plausibility | : can't verify from extracted data — VERDICT=UNSURE conf=0.85 reason=No metric, value, unit, or derivation trail provided to evaluate.. |  |
| medium | `XS2388386810` | impact_value | impact_plausibility | : can't verify from extracted data — VERDICT=UNSURE conf=0.85 reason=No metric, value, or derivable trail provided to verify.. |  |
| medium | `BRSSCFDBS030` | impact_value | impact_plausibility | : can't verify from extracted data — VERDICT=UNSURE conf=0.85 reason=No derivable arithmetic trail or peer baseline to verify claim.. |  |
| medium | `CND10007KF01` | impact_value | impact_plausibility | : can't verify from extracted data — VERDICT=UNSURE conf=0.85 reason=No metric, value, unit, or derivation provided to evaluate.. |  |
| medium | `US89602HFH57` | impact_value | impact_plausibility | : can't verify from extracted data — VERDICT=UNSURE conf=0.85 reason=No metric, value, unit, or derivation trail provided to evaluate.. |  |
| medium | `US53945CGQ78` | impact_value | impact_plausibility | : can't verify from extracted data — VERDICT=UNSURE conf=0.85 reason=No trail or derivation provided; cannot verify the impact claim.. |  |
| medium | `US59259N4P52` | impact_value | impact_plausibility | : can't verify from extracted data — VERDICT=UNSURE conf=0.85 reason=No trail, derivation, or peer baseline to verify the value.. |  |
| medium | `US797661XR11` | impact_value | impact_plausibility | : can't verify from extracted data — VERDICT=UNSURE conf=0.85 reason=No derivable arithmetic trail or peer baseline to verify the value.. |  |
| medium | `CND10006XHZ0` | impact_value | impact_plausibility | : can't verify from extracted data — VERDICT=UNSURE conf=0.85 reason=No derivable arithmetic trail or peer baseline to verify the value.. |  |
| medium | `CND10004SSX7` | impact_value | impact_plausibility | : can't verify from extracted data — VERDICT=UNSURE conf=0.85 reason=No metric, value, or derivable arithmetic trail provided to verify.. |  |
| medium | `CND10005RJ77` | impact_value | impact_plausibility | : can't verify from extracted data — VERDICT=UNSURE conf=0.85 reason=No derivable arithmetic trail; metric/value fields empty, cannot verify anything.. |  |
| medium | `DE000A19MFH4` | impact_value | impact_plausibility | : can't verify from extracted data — VERDICT=UNSURE conf=0.85 reason=No metric, value, unit, or derivation trail provided to evaluate.. |  |
| medium | `IDA0001173A6` | impact_value | impact_plausibility | : can't verify from extracted data — VERDICT=UNSURE conf=0.85 reason=No derivable arithmetic trail; metric/value fields empty, cannot verify.. |  |
| medium | `IDA0001342A7` | impact_value | impact_plausibility | : can't verify from extracted data — VERDICT=UNSURE conf=0.85 reason=No derivation, baseline, or trail to verify the impact claim.. |  |
| medium | `IDA0001547A1` | impact_value | impact_plausibility | : can't verify from extracted data — VERDICT=UNSURE conf=0.85 reason=No derivable arithmetic trail or peer baseline to verify claim.. |  |
| medium | `IDJ000019609` | impact_value | impact_plausibility | : can't verify from extracted data — VERDICT=UNSURE conf=0.85 reason=No metric, value, or derivable arithmetic trail provided to verify.. |  |
| medium | `US13034A4P28` | impact_value | impact_plausibility | : can't verify from extracted data — VERDICT=UNSURE conf=0.85 reason=No metric, value, unit, or derivation trail provided to evaluate.. |  |
| medium | `US13049SEU42` | impact_value | impact_plausibility | : can't verify from extracted data — VERDICT=UNSURE conf=0.85 reason=No metric, value, unit, or derivation trail provided to evaluate.. |  |
| medium | `US438687DE29` | impact_value | impact_plausibility | : can't verify from extracted data — VERDICT=UNSURE conf=0.85 reason=No derivation, baseline, or trail to verify the figure.. |  |
| medium | `US438687DN28` | impact_value | impact_plausibility | : can't verify from extracted data — VERDICT=UNSURE conf=0.85 reason=No derivable arithmetic, metric/value missing; provenance unverifiable.. |  |
| medium | `US441178CN86` | impact_value | impact_plausibility | : can't verify from extracted data — VERDICT=UNSURE conf=0.85 reason=No metric, value, unit, or derivation trail provided to evaluate.. |  |
| medium | `US45203MJQ50` | impact_value | impact_plausibility | : can't verify from extracted data — VERDICT=UNSURE conf=0.85 reason=No trail, derivation, or peer baseline to verify the value.. |  |
| medium | `US45505MLF13` | impact_value | impact_plausibility | : can't verify from extracted data — VERDICT=UNSURE conf=0.85 reason=No derivable arithmetic trail or peer baseline to verify the value.. |  |
| medium | `US45506EPL10` | impact_value | impact_plausibility | : can't verify from extracted data — VERDICT=UNSURE conf=0.85 reason=No trail, derivation, metric, or peer baseline provided to verify.. |  |
| medium | `US545149JX57` | impact_value | impact_plausibility | : can't verify from extracted data — VERDICT=UNSURE conf=0.85 reason=No trail, derivation, or peer baseline to verify the value.. |  |
| medium | `US575829DR48` | impact_value | impact_plausibility | : can't verify from extracted data — VERDICT=UNSURE conf=0.85 reason=No metric, value, unit, or derivation trail provided to evaluate.. |  |
| medium | `US59261AK221` | impact_value | impact_plausibility | : can't verify from extracted data — VERDICT=UNSURE conf=0.85 reason=No trail, derivation, metric, or value provided to evaluate.. |  |
| medium | `US677632M244` | impact_value | impact_plausibility | : can't verify from extracted data — VERDICT=UNSURE conf=0.85 reason=No metric, value, unit, or trail provided to verify any claim.. |  |
| medium | `US786005G854` | impact_value | impact_plausibility | : can't verify from extracted data — VERDICT=UNSURE conf=0.85 reason=No metric, value, or derivable trail provided to verify plausibility.. |  |
| medium | `US924258S980` | impact_value | impact_plausibility | : can't verify from extracted data — VERDICT=UNSURE conf=0.85 reason=No metric, value, unit, or derivation trail provided to evaluate.. |  |
| medium | `CND10004PTX1` | impact_value | impact_plausibility | Installed renewable energy capacity: can't verify from extracted data — VERDICT=UNSURE conf=0.82 reason=Full project capacity claimed but bond share unknown; attribution unverified.. |  |
| medium | `XS2272847141` | impact_value | impact_plausibility | Annual energy savings: can't verify from extracted data — VERDICT=UNSURE conf=0.82 reason=Portfolio-level figure; bond share unavailable, so attribution is unverifiable.. |  |
| medium | `BE0000346552` | impact_value | impact_plausibility | Lifetime GHG emissions reduced/avoided: can't verify from extracted data — VERDICT=UNSURE conf=0.72 reason=Arithmetic checks out but no derivation for the 1,580,000 tCO2e source figure.. |  |
| medium | `CND10004PTX1` | impact_value | impact_plausibility | Annual GHG emissions reduced/avoided/sequestered: can't verify from extracted data — VERDICT=UNSURE conf=0.72 reason=Arithmetic checks out but 8σ peer deviation and pro-rata allocation unverifiable.. |  |
| medium | `XS3358268251` | impact_value | impact_plausibility | Annual renewable energy generation: can't verify from extracted data — VERDICT=UNSURE conf=0.72 reason=Math checks out but metric misattributed to wrong category per review notes.. |  |
| medium | `US02765ULG75` | impact_value | impact_plausibility | Installed renewable energy capacity: can't verify from extracted data — VERDICT=UNSURE conf=0.72 reason=Internally consistent but no bond_share applied; full capacity attributed incorrectly.. |  |
| medium | `US02765ULG75` | impact_value | impact_plausibility | Annual renewable energy generation: can't verify from extracted data — VERDICT=UNSURE conf=0.72 reason=Intensity is 5x peer median; project-level provenance incomplete due to Phoenix limitation.. |  |
| medium | `XS2406607098` | impact_value | impact_plausibility | GHG emissions (footprint, scope 1-3): can't verify from extracted data — VERDICT=UNSURE conf=0.72 reason=Scope 1+2 only; labeled scope 1-3 is misleading/incomplete.. |  |
| medium | `XS0739956042` | impact_value | impact_plausibility | Area under biodiversity management: can't verify from extracted data — VERDICT=UNSURE conf=0.72 reason=Math checks out but 36σ intensity deviation flags upstream portfolio figure reliability.. |  |
| medium | `XS3358268251` | impact_value | impact_plausibility | Area under biodiversity management: can't verify from extracted data — VERDICT=UNSURE conf=0.62 reason=Category misattribution flag undermines provenance despite correct arithmetic.. |  |
| medium | `XS2406607098` | impact_value | impact_plausibility | Beneficiaries reached: can't verify from extracted data — VERDICT=UNSURE conf=0.62 reason=KPI target vs. actual ambiguity; StandardUnit false flags provenance gap.. |  |
| medium | `XS3358268251` | impact_value | impact_plausibility | Annual energy savings: can't verify from extracted data — VERDICT=UNSURE conf=0.6 reason=Category misattribution flag undermines provenance despite correct arithmetic.. |  |
| medium | `NZHNZD0230L2` | impact_value | impact_plausibility | Affordable housing units: can't verify from extracted data — VERDICT=UNSURE conf=0.6 reason=Conflicting source values (808 vs 218 units) undermine derivation reliability.. |  |
| medium | `US46143NAB64` | impact_value | impact_plausibility | Installed renewable energy capacity: can't verify from extracted data — VERDICT=UNSURE conf=0.6 reason=Project-level sum (763 MW) doesn't reconcile with reported total (769.5 MW).. |  |
| medium | `US67766WH393` | impact_value | impact_plausibility | Households served: can't verify from extracted data — VERDICT=UNSURE conf=0.6 reason=Grant-fund linkage unexplained; provenance of 271 households/$M unclear.. |  |
| medium | `NZHNZD0230L2` | impact_value | impact_plausibility | Affordable housing units: can't verify from extracted data — VERDICT=UNSURE conf=0.35 reason=Conflicting source values (808 vs 218 units) undermine derivation reliability.. |  |

## Rollup

**By check:** category_mapping (105), impact_plausibility (78), fx_consensus (16), share_def (3), trail_value_mismatch (1)

**By table:** cat_allocations (108), impacts (79), issuances (16)
