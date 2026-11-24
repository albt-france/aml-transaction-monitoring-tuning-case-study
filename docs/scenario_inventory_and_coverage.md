# Scenario inventory and typology coverage

## The 12 rules (SIMULATED), documentation vs code, measured on IBM labels (PUBLIC DATA, synthetic)
Precision = true-positive alerts / alerts; recall = laundering accounts with a true-positive alert / 877
laundering accounts in Bank N's book. Base rate (account-days with laundering): 0.30%.
R07 uses ILLUSTRATIVE country tiers (4 bank-country groups drawn at random, not an assessment of any country).

| Rule | Name | Designed for | Documentation | Threshold | Lookback (days) | Code differs? | Alerts (code) | Precision | Recall |
|---|---|---|---|---|---|---|---|---|---|
| R01 | Large single transfer | Large value | One outgoing transfer of at least the threshold | 750,000 | 1 | none | 1,343 | 0.30% | 0.3% |
| R02 | Structuring below 10k | Structuring | 3+ outgoing transfers between 8,000 and 9,999.99 in 7 days | 10,000 | 7 | raw amount, no FX | 786 | 0.76% | 0.7% |
| R03 | Fan-out | FAN-OUT; GATHER-SCATTER; BIPARTITE | Payments to at least N distinct beneficiaries in one day | 20 | 1 | none | 0 |  | 0.0% |
| R04 | Rapid movement of funds | STACK; RANDOM | Receives >= threshold and sends 80-120% of it on within 2 days | 20,000 | 2 | self-transfers kept | 9,877 | 0.28% | 3.2% |
| R05 | Activity spike | Behaviour change | Daily outgoing count >= 10 and >= 5x the account's prior 7-day daily mean | 5 | 7 | none | 47 | 2.13% | 0.1% |
| R06 | Fan-in | FAN-IN; GATHER-SCATTER; BIPARTITE | Payments from at least N distinct remitters in one day | 20 | 1 | none | 83 | 9.64% | 0.9% |
| R07 | High-risk corridor | Geography | Transfer >= threshold to or from a bank in a high-risk tier country (ILLUSTRATIVE tiers) | 500,000 | 1 | none | 611 | 0.16% | 0.1% |
| R08 | Crypto / cross-currency | Conversion | Bitcoin transfer or currency conversion >= threshold | 10,000 | 1 | none | 0 |  | 0.0% |
| R09 | Round amounts | Generic red flag | Outgoing transfer of a whole amount (no cents) >= threshold | 1,000 | 1 | none | 3,476 | 0.58% | 1.8% |
| R10 | Cash activity | Cash | Cash in + out >= threshold over the lookback | 750,000 | 7 | 1-day lookback | 663 | 0.30% | 0.2% |
| R11 | High-risk customer outflow | KYC risk | Outgoing transfer >= threshold by a high-risk-rated customer | 250,000 | 1 | none | 688 | 1.89% | 1.3% |
| R12 | Activity above expected profile | KYC profile | 7-day outflow > 4x the expected weekly volume declared at KYC | 4 | 7 | none | 591 | 4.91% | 3.3% |

**System (code as implemented):** 18,165 alerts in 16 days, precision 0.62%, recall 10.7%.
**System (code as documented):** 9,249 alerts, precision 1.04%, recall 9.0%.

## Documentation vs code: 3 gaps
| Rule | Documented | Implemented | Effect |
|---|---|---|---|
| R02 | USD-equivalent band 8,000-9,999.99 | raw amount in the payment currency | 786 alerts vs 668; 337 in common. Yuan, rupee or yen amounts fall into the band by accident, while EUR or GBP amounts just below USD 10,000 fall out |
| R04 | self-transfers excluded | self-transfers counted | 8,906 of 9,877 alerts (90%) exist only because of self-transfers, 8,751 of them on 1 Sep |
| R10 | cash accumulated over 7 days | 1 day | 5 laundering accounts found by the documented rule are missed |

Two rules never fire on this book: R03 (20 distinct beneficiaries a day) and R08 (no conversion above USD 10,000).
A rule that never fires is either miscalibrated (R03, see the tuning report) or covers a risk the book does not have (R08): both need a decision, not silence.

## Typology coverage
An attempt is visible when one of its accounts is in Bank N's book (526 attempts);
it is detected when a rule raises a true-positive alert on one of those accounts during the attempt (+2 days).

| Typology | Visible attempts | Detected | Detection rate | Rules designed for it |
|---|---|---|---|---|
| FAN-OUT | 54 | 4 | 7% | R03 |
| FAN-IN | 69 | 6 | 9% | R06 |
| BIPARTITE | 70 | 8 | 11% | R03, R06 |
| RANDOM | 47 | 6 | 13% | R04 |
| GATHER-SCATTER | 85 | 14 | 16% | R03, R06 |
| SCATTER-GATHER | 60 | 10 | 17% |  |
| STACK | 94 | 16 | 17% | R04 |
| CYCLE | 47 | 13 | 28% |  |

**Gaps.** No rule is designed for CYCLE or SCATTER-GATHER. Their detections are incidental (generic rules firing on the same accounts),
so they would disappear with any tuning of those rules. Fan-in and fan-out, the patterns R03 and R06 were written for,
are among the least detected. The new network scenario R13 (`sql/10_network_cycles.sql`) addresses the first gap: see `threshold_tuning_report.md`.
Full matrix: `output/typology_coverage_matrix.csv`.

---
*Independent case study based on public and synthetic data · not affiliated with any bank or consultancy. Labels: PUBLIC DATA (synthetic AML benchmark), SIMULATED (Bank N layer), ILLUSTRATIVE (country tiers).*
