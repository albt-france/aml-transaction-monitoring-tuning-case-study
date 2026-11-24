# Recommendations and 30/60/90-day roadmap

Ranked by impact on detection and workload, then by effort. Figures: 16-day measurement window.

| # | Recommendation | Impact | Effort | When | Owner |
|---|---|---|---|---|---|
| 1 | Exclude self-transfers in R04, as documented | 8,906 alerts with no business meaning removed | Low | 30 days | TM engineering |
| 2 | Fix the ACH feed (beneficiary bank) and gate loads on control C02 | Corridor logic sees all ACH rows again; 24 laundering rows in the book regain the field | Low-Medium | 30 days | Data engineering |
| 3 | Convert R02 to USD and restore R10's 7-day lookback | Code matches documentation; R10 finds 5 more laundering accounts | Low | 30 days | TM engineering |
| 4 | Known-payroll exclusion on R05; do not escalate the 14 Sep spike | 47 alerts in one day avoided, no risk change | Low | 30 days | TM operations |
| 5 | Retune with ATL/BTL: retire R01, R09 to 5,000, R11 to 375,000, R03 and R06 to 10 counterparties | Alerts -65% overall, precision x2.5; normal week under capacity | Medium | 60 days | TM owner + 2nd line sign-off |
| 6 | Deploy R13 (cycles and scatter-gather) in shadow mode, then live | 48 alerts in 16 days at 29% precision, 10 new laundering accounts | Medium | 60 days | TM engineering |
| 7 | Close KYC gaps: expected activity for all customers, overdue high-risk reviews, entity duplicates | R12 covers 4.0% more customers; fresher risk ratings | Medium | 90 days | KYC team |
| 8 | Challenger score to rank the queue, within capacity, with model governance | At capacity: 46% of laundering accounts found vs 10% for the tuned rules | High | 90 days | Data science + model risk |

## Sequencing
- **Day 0-30, stop the noise:** items 1-4. Low effort, no change in risk appetite, mostly code and data fixes.
- **Day 31-60, retune and extend:** items 5-6, with ATL/BTL evidence documented for the second line and a shadow run for R13.
- **Day 61-90, prioritise:** items 7-8. The score goes live only after a temporal back-test on closed cases and drift monitoring.

## What to measure every month
Alerts per week vs capacity, precision by rule and by risk tier, recall on confirmed cases, control FAIL count, KYC gap shares.
All are in the Power BI model (`docs/powerbi_measures.md`).

---
*Independent case study based on public and synthetic data · not affiliated with any bank or consultancy. Labels: PUBLIC DATA (synthetic AML benchmark), SIMULATED (Bank N layer), ILLUSTRATIVE (country tiers).*
