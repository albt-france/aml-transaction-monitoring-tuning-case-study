# Threshold tuning report (ATL/BTL)

## Method
- **Above the line (ATL):** raise a threshold step by step (1.5x to 20x) and count the alerts removed and the laundering
  accounts lost. The cost that matters is the **unique** loss: accounts that no other rule catches.
- **Below the line (BTL):** lower the threshold (0.5x, 0.75x) and count the true positives the current setting misses.
- Truth: IBM labels (PUBLIC DATA, synthetic). Volumes: Bank N alerts (SIMULATED). Curves: `output/atl_btl_curve.csv`.
- Principle: change a threshold only where the evidence is clear; when raising a threshold costs unique detections,
  say so and pair it with a mitigation (here, the challenger score).

## ATL/BTL results (one-day rules)
| Rule | x current | Threshold | Alerts / week | Laundering accounts | Precision | Unique accounts lost |
|---|---|---|---|---|---|---|
| R01 | 0.5 | 375,000 | 2,145 | 14 | 0.31% | 0 |
| R01 | 0.75 | 562,500 | 1,252 | 6 | 0.24% | 0 |
| R01 | 1.0 | 750,000 | 588 | 3 | 0.30% | 0 |
| R03 | 0.5 | 10 | 95 | 6 | 4.61% | 0 |
| R03 | 0.75 | 15 | 7 | 0 | 0.00% | 0 |
| R06 | 0.5 | 10 | 102 | 17 | 7.26% | 0 |
| R06 | 0.75 | 15 | 66 | 11 | 7.24% | 0 |
| R06 | 1.0 | 20 | 36 | 8 | 9.64% | 0 |
| R06 | 1.5 | 30 | 18 | 3 | 7.32% | 5 |
| R06 | 2.0 | 40 | 12 | 3 | 11.11% | 5 |
| R06 | 3.0 | 60 | 4 | 1 | 10.00% | 7 |
| R07 | 0.5 | 250,000 | 553 | 3 | 0.40% | 0 |
| R07 | 0.75 | 375,000 | 388 | 1 | 0.11% | 0 |
| R07 | 1.0 | 500,000 | 267 | 1 | 0.16% | 0 |
| R07 | 1.5 | 750,000 | 123 | 0 | 0.00% | 0 |
| R09 | 0.5 | 500 | 1,861 | 18 | 0.52% | 0 |
| R09 | 0.75 | 750 | 1,662 | 16 | 0.53% | 0 |
| R09 | 1.0 | 1,000 | 1,521 | 16 | 0.58% | 0 |
| R09 | 1.5 | 1,500 | 1,314 | 13 | 0.47% | 2 |
| R09 | 2.0 | 2,000 | 1,155 | 11 | 0.45% | 4 |
| R09 | 3.0 | 3,000 | 951 | 9 | 0.41% | 6 |
| R09 | 5.0 | 5,000 | 724 | 7 | 0.42% | 7 |
| R09 | 10.0 | 10,000 | 535 | 4 | 0.33% | 9 |
| R09 | 20.0 | 20,000 | 418 | 4 | 0.42% | 9 |
| R11 | 0.5 | 125,000 | 530 | 16 | 1.49% | 0 |
| R11 | 0.75 | 187,500 | 399 | 13 | 1.64% | 0 |
| R11 | 1.0 | 250,000 | 301 | 11 | 1.89% | 0 |
| R11 | 1.5 | 375,000 | 234 | 9 | 1.87% | 1 |
| R11 | 2.0 | 500,000 | 164 | 6 | 1.86% | 2 |
| R11 | 3.0 | 750,000 | 66 | 2 | 1.99% | 4 |

## Recommendations per rule
| Rule | Name | Action | Now | Proposed | Alerts now | Alerts after | TP alerts now | TP alerts after | Why |
|---|---|---|---|---|---|---|---|---|---|
| R01 | Large single transfer | retire | 750,000 |  | 1343 | 0 | 4 | 0 | Precision equals the base rate and 1 unique laundering account; R12 covers large flows relative to the profile |
| R02 | Structuring below 10k | fix | 10,000 |  | 786 | 668 | 6 | 3 | Convert amounts to USD before the 8,000-9,999.99 band, as documented |
| R03 | Fan-out | tune | 20 | 10 | 0 | 217 | 0 | 10 | Below-the-line test: 10 distinct beneficiaries finds laundering accounts at 15x the base rate |
| R04 | Rapid movement of funds | fix | 20,000 |  | 9877 | 1067 | 28 | 12 | Exclude self-transfers, as documented |
| R05 | Activity spike | exclude | 5 |  | 47 | 21 | 1 | 1 | Known-payroll exclusion for customers whose KYC declares salary batches |
| R06 | Fan-in | tune | 20 | 10 | 83 | 234 | 8 | 17 | Below-the-line test: 10 distinct remitters doubles the laundering accounts found, precision stays ~7% |
| R07 | High-risk corridor | keep |  |  | 611 | 611 | 1 | 1 |  |
| R08 | Crypto / cross-currency | keep |  |  | 0 | 0 | 0 | 0 |  |
| R09 | Round amounts | tune | 1,000 | 5,000 | 3476 | 1655 | 20 | 7 | Largest rule in a normal week at the system's average precision; raise the floor, recover misses with the score |
| R10 | Cash activity | fix | 750,000 |  | 663 | 675 | 2 | 5 | Restore the documented 7-day accumulation |
| R11 | High-risk customer outflow | tune | 250,000 | 375,000 | 688 | 536 | 13 | 10 | Above-the-line test: -22% volume for 1 unique laundering account |
| R12 | Activity above expected profile | keep |  |  | 591 | 591 | 29 | 29 |  |

Actions: **fix** (make the code match the documentation), **tune** (move the threshold), **retire** (stop alerting),
**exclude** (add an exclusion), **keep**.

## Overall impact (16 days)
- Alerts: 18,165 to 6,275 (-65%).
- Precision: 0.62% to 1.51%.
- Laundering accounts with a true-positive alert: 94 to 85
  (25 lost, 16 gained). The losses come mainly from R09 and from R04 alerts
  that hit laundering accounts by coincidence on the day-1 batch. **Rule changes alone trade some recall for capacity**:
  the network scenario and the challenger score below recover more than they lose.
- Capacity: a normal week (week 2) goes from 2,875 alerts (1.60x capacity) to
  1,543 (0.86x). Week 1 stays above capacity (3,923 alerts)
  because 1 Sep carries 2.3x the normal volume.

## R09, the largest rule in a normal week
R09 makes 40% of week-2 alerts. Its precision (0.58%) is close to the
system's, so it is not pure noise, and raising the floor above 1,000 starts losing laundering accounts that no other rule finds.
Recommendation: raise it to 5,000 (-52% of R09 alerts) **and** route the accounts it would have caught to the challenger score.
Re-test after 3 months on closed cases.

## A spike that must NOT be escalated (corporate payroll)
On Wednesday 14 Sep, corporate alerts reach 114 against a Tuesday-Thursday baseline of
76 (+50%). 47 of them come from payroll batches (379 salary
payments from 26 accounts, median EUR 2,948) brought forward one day by a bank holiday (SIMULATED).
100% are on customers whose KYC declares payroll, 0 laundering labels, 0 escalations.
**Verdict:** expected activity, not a risk increase. Add a known-payroll exclusion to R05 and watch the next cycle. Do not escalate.

## New scenario R13: network patterns (`sql/10_network_cycles.sql`)
- Cycles: time-ordered loops (2 to 12 hops, each within 3.5 days, the whole loop within 7 days) that return to a Bank N account,
  each hop passing 80-115% of the previous USD amount. Scatter-gather: 3+ intermediaries passing 85-100% of the amount to the same final account within 5 days.
- Result: 48 alerts in 16 days, precision 29%, 14 laundering accounts, 10 not found by the tuned rules.
- Coverage with the tuned rules: SCATTER-GATHER 10% to 27%,
  CYCLE 21% to 26%.
- Limit: a bank only sees loops that start and end at its own customer in time order, so cycles remain hard. The parameters were checked
  against the typology file, so recall is optimistic: validate on fresh data before production.

---
*Independent case study based on public and synthetic data · not affiliated with any bank or consultancy. Labels: PUBLIC DATA (synthetic AML benchmark), SIMULATED (Bank N layer), ILLUSTRATIVE (country tiers).*
