# Controls catalogue

Declared in `controls/controls.yaml`, run by `python src/controls.py`, written to `output/controls_report.csv`.
Every metric is "higher is worse": WARN above the first threshold, FAIL above the second.

| Id | Control | Object | Check | Frequency | WARN above | FAIL above | Owner |
|---|---|---|---|---|---|---|---|
| C01 | Field completeness | transaction feed | null_rate_by_field | daily | 0.001 | 0.01 | Data engineering |
| C02 | Completeness by feed and day (beneficiary bank) | transaction feed, per payment format | null_rate_by_feed_day | daily | 0.001 | 0.01 | Data engineering |
| C03 | Exact duplicate rows | transaction feed | duplicate_rows | daily | 0.0 | 0.01 | Data engineering |
| C04 | Allowed values (currencies, payment formats) | transaction feed | allowed_values | daily | 0.0 | 0.0 | Data engineering |
| C05 | Non-positive amounts | transaction feed | non_positive_amounts | daily | 0.0 | 0.0 | Data engineering |
| C06 | Paid = received when the currency is the same | transaction feed | paid_vs_received | daily | 0.0 | 0.001 | Data engineering |
| C07 | Freshness (feed arrival lag, hours after day end) | feed metadata | freshness | daily | 6.0 | 24.0 | Data engineering |
| C08 | Daily volume against the same weekday | transaction feed | daily_volume_deviation | daily | 0.5 | 1.5 | TM operations |
| C09 | Self-transfers share per day | transaction feed | self_transfer_share | daily | 0.05 | 0.2 | TM operations |
| C10 | Accounts missing from the account master | transaction feed vs account master | referential_integrity | weekly | 0.0 | 0.01 | Data engineering |
| C11 | FX rate available for every currency | FX reference table | fx_coverage | daily | 0.0 | 0.0 | Data engineering |
| C12 | Labelled laundering rows match the typology file | transaction feed vs Patterns file | label_pattern_consistency | per load | 0.01 | 0.05 | Data science |
| C13 | Customers without expected activity | KYC file | kyc_missing_expected_activity | weekly | 0.01 | 0.03 | KYC team |
| C14 | High-risk customers with an overdue review (> 12 months) | KYC file | kyc_high_risk_overdue | weekly | 0.02 | 0.05 | KYC team |
| C15 | Several customer records for one entity | KYC file | kyc_duplicate_entities | weekly | 0.0 | 0.01 | KYC team |

## Operating model
- Daily controls run after each feed load and before the rules. A FAIL on C02, C04, C05 or C06 holds the affected feed and opens an incident.
- Weekly controls feed the KYC remediation backlog (C13-C15) and the data-engineering backlog (C10).
- The report is a table in the Power BI model (page "Data quality"), so status and trend are visible to the TM owner.
- Thresholds are starting points: review them after 3 months of history.

---
*Independent case study based on public and synthetic data · not affiliated with any bank or consultancy. Labels: PUBLIC DATA (synthetic AML benchmark), SIMULATED (Bank N layer), ILLUSTRATIVE (country tiers).*
