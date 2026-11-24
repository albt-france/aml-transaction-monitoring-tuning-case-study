# Model validation note: challenger score

## Purpose
Rank Bank N's alert queue by risk so that analysts review the most suspicious account-days first, within capacity.
The documented rules stay in place as the explainable layer; the score is a challenger, not a replacement.

## Design
- Unit: one Bank N account on one day with activity (373,215 account-days; 1,122 positives,
  base rate 0.30%). Label: the account sent or received a laundering-labelled transfer that day (IBM, synthetic).
- Model: scikit-learn `HistGradientBoostingClassifier` (300 iterations max, early stopping, learning rate 0.05).
- Features: that day's activity (counts, amounts, counterparties, formats, currencies, cross-bank share, round amounts, cash,
  conversions) and the 7 days before (counts, counterparties, active days, 2-day pass-through). **Not used:** KYC risk rating
  and segment (SIMULATED and partly built from the labels, they would leak).

## Leakage: the first draft
| Version | Features | Validation | ROC AUC | Average precision |
|---|---|---|---|---|
| v1 first draft | as-of + whole-period aggregates (future) | random split of account-days | 0.986 | 0.568 |
| v1 features, temporal test | as-of + whole-period aggregates (future) | train <= 2022-09-10, test after | 0.983 | 0.558 |
| v2 challenger | as-of only (that day + 7 days before) | train <= 2022-09-10, test after | 0.942 | 0.251 |

The first draft adds whole-period aggregates and two features built from **all** cases in the extract: whether the account was ever
escalated, and the share of its counterparties that are known bad. Both use information from after the scoring day.
Its AUC (0.986) looks excellent. **A temporal split alone does not fix it**
(0.983), because the leak is in the features, not in the split.
With as-of features and a temporal split (train 1-10 Sep, test 11-16 Sep), the honest AUC is
**0.942** and the average precision falls from 0.57 to 0.25.

## Threshold set by capacity
Analysts can review 257 alerts a day (12 analysts, 30 h/week, 12 min median). Each test day, the top
257 account-days by score form the queue (mean score cut-off 0.039).

| Approach | Alerts / day | Precision | Laundering accounts found | Share of the 410 in test |
|---|---|---|---|---|
| Tuned rules (all alerts) | 278 | 2.8% | 39 | 10% |
| Challenger top 257 per day (capacity) | 257 | 15.5% | 187 | 46% |
| Tuned rules + challenger (union) |  |  | 208 | 51% |

## Simpson's paradox: read precision by segment AND risk tier
| Segment | Risk tier | Alerts | True positives | Precision |
|---|---|---|---|---|
| retail | all | 963 | 138 | 14.3% |
| retail | low | 599 | 30 | 5.0% |
| retail | medium | 259 | 51 | 19.7% |
| retail | high | 105 | 57 | 54.3% |
| sme | all | 345 | 74 | 21.4% |
| sme | low | 69 | 0 | 0.0% |
| sme | medium | 112 | 17 | 15.2% |
| sme | high | 164 | 57 | 34.8% |

SME alerts look more precise than retail overall, yet SME precision is lower in every risk tier. The reason: SMEs sit mostly
in the high-risk tier, where precision is high for everyone. A segment-only report would wrongly conclude that the model works
better for SMEs. Governance reports must break precision down by risk tier.

## Top drivers (permutation importance on average precision, test set)
- share_ach_out: 0.334 (± 0.005)
- share_ach_in: 0.179 (± 0.006)
- in_usd: 0.109 (± 0.005)
- n_currencies_out: 0.069 (± 0.005)
- in_cp: 0.058 (± 0.004)
- out_max_usd: 0.046 (± 0.008)
- out_cnt: 0.042 (± 0.004)
- out_cp: 0.034 (± 0.004)

The ACH share dominates because AMLSim generates most laundering through ACH. In real data, expect weaker and more varied drivers:
re-estimate before any use.

## Limits
- 16 days of synthetic data; the test covers 6 days. Absolute AUC is optimistic for real data; the comparisons are the message.
- Labels are benchmark labels, not confirmed cases; 40% of them have no documented typology.
- The score ranks account-days; case consolidation by customer is a next step.

## Governance
- Model card (purpose, data, features, exclusions, metrics, limits) owned by the first line, reviewed by the second line.
- Monthly drift checks: score distribution, feature shares (formats, currencies), alert-to-SAR conversion by risk tier.
- Quarterly back-test on closed cases; champion/challenger before any switch; re-validation after any change to rules or feeds.
- No feature computed after the scoring date: an automated test should check the as-of timestamp of every feature.

---
*Independent case study based on public and synthetic data · not affiliated with any bank or consultancy. Labels: PUBLIC DATA (synthetic AML benchmark), SIMULATED (Bank N layer), ILLUSTRATIVE (country tiers).*
