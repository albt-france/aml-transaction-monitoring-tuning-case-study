# Engagement scope: validate and tune Bank N's transaction monitoring

**Client (fictional):** Bank N, a mid-sized European bank (SIMULATED).
**Engagement type:** an anti-financial-crime data-analytics engagement: assessment, validation and optimisation of the
transaction-monitoring (TM) system. Planned duration: 2 to 3 months.

## Objectives
1. Check that the data feeding the TM system is complete and fit for purpose (automated controls).
2. Validate the 12 rules: does the code match the documentation, which typologies are covered, how precise each rule is.
3. Bring the alert volume within analyst capacity without losing detection: threshold tuning (ATL/BTL), segmentation,
   new scenario, risk-based prioritisation.
4. Hand over reusable assets: SQL and Python pipeline, controls, Power BI model, documentation.

## Data received
| Data | Status | Volume |
|---|---|---|
| Transactions: IBM "Transactions for AML" HI-Medium | PUBLIC DATA (synthetic) | 31,898,238 rows, 1-28 Sep 2022 (16 complete days) |
| Account master (Entity Name dropped at ingestion) | PUBLIC DATA (synthetic) | 2,087,786 accounts, 668,138 entities |
| Laundering typologies (Patterns file) | PUBLIC DATA (synthetic) | 2,756 attempts, 8 typologies |
| Bank N customers and KYC | SIMULATED | 19,968 customers, 45,089 accounts |
| Rule documentation and rule code (12 rules) | SIMULATED | `data/sim/rules_documented.parquet`, `rules_implemented.parquet` |
| Alerts, analyst decisions, capacity, feed metadata | SIMULATED | 18,165 alerts in 16 days |

## Out of scope
Legal interpretation of the AML framework (no legal advice); sanctions screening against named lists; model deployment.

## Plan (10 weeks, adjustable to 3 months)
| Weeks | Work | Deliverable |
|---|---|---|
| 1-2 | Data access, profiling, business meaning, automated controls | `data_quality_assessment.md`, `controls_catalogue.md`, controls report |
| 3-4 | Rule validation: documentation vs code, precision/recall, typology coverage | `scenario_inventory_and_coverage.md` |
| 5-6 | Threshold tuning (ATL/BTL), capacity, false signals | `threshold_tuning_report.md` |
| 7-8 | New network scenario, challenger model with temporal validation | `model_validation_note.md` |
| 9-10 | Client presentation, Power BI handover, roadmap, follow-up proposal | report, dashboard, `recommendations_roadmap.md`, `proposal_onepager.md` |

## Assumptions
See `assumptions.md`. Main ones: 12 analysts, 30 productive hours a week, 12 minutes median per alert; fixed FX rates
implied by the file; country risk tiers ILLUSTRATIVE.

---
*Independent case study based on public and synthetic data · not affiliated with any bank or consultancy. Labels: PUBLIC DATA (synthetic AML benchmark), SIMULATED (Bank N layer), ILLUSTRATIVE (country tiers).*
