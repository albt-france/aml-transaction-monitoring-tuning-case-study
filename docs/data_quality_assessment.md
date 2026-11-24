# Data quality assessment

15 automated controls (`controls/controls.yaml`, `src/controls.py`) ran on the Bank N transaction feed
(31,891,630 rows in the complete-day window: IBM PUBLIC DATA, synthetic, plus a SIMULATED feed layer) and on the
SIMULATED KYC file. Result: **6 PASS, 4 WARN, 5 FAIL**.

| Id | Control | Status | Result | Impact on detection | Proposed fix |
|---|---|---|---|---|---|
| C01 | Field completeness | **WARN** | worst field: to_bank (0.367%); all others 0.000% or less | Overall null rate hides the problem: only the beneficiary bank is affected. | Keep the field check, but alert on the feed-day view (C02). |
| C02 | Completeness by feed and day (beneficiary bank) | **FAIL** | ACH feed loses the beneficiary bank from 2022-09-09 (6.03% of rows on average, 8 days) | From 9 Sep, the ACH feed delivers about 6% of rows without the beneficiary bank. Corridor logic (R07) cannot evaluate them. 24 laundering rows of Bank N's book lose the field. | Raise an incident with the ACH feed owner; block the load (or flag rows) when the feed-day null rate exceeds 1%; back-fill from the payment system. |
| C03 | Exact duplicate rows | **WARN** | 20 exact duplicate rows out of 31,891,251 | Negligible: 20 exact duplicate rows. | Deduplicate at load with a natural key (timestamp, accounts, amount, currency, format). |
| C04 | Allowed values (currencies, payment formats) | **PASS** | 0 rows outside 15 currencies / 7 formats | None: 15 currencies and 7 formats, as expected. | Keep as a daily gate. |
| C05 | Non-positive amounts | **PASS** | 0 rows with an amount <= 0 | None. | Keep as a daily gate. |
| C06 | Paid = received when the currency is the same | **PASS** | 0 same-currency rows where paid and received differ | None: paid = received whenever the currency is the same. | Keep: a break would reveal a fee or FX booking issue. |
| C07 | Freshness (feed arrival lag, hours after day end) | **PASS** | latest feed arrives 3.5 h after day end; the source file also carries 6,987 late rows up to 2022-09-28, outside the complete-day window | Feeds arrive within 3.5 h, but the source file carries a sparse tail of late rows up to 28 Sep. | Monitor only complete days; reprocess late rows in a weekly catch-up run. |
| C08 | Daily volume against the same weekday | **WARN** | largest deviation +131% on 2022-09-01 (4,465,985 rows) | 1 Sep has 2.3x the usual Thursday volume (a one-off batch). | Investigate the batch with the data owner; exclude it from baselines. |
| C09 | Self-transfers share per day | **FAIL** | 45% self-transfers on 2022-09-01 (1,945,611 'Reinvestment' rows, none on other days) | 1.9M self-transfers ('Reinvestment') on 1 Sep only. Counted by the R04 code, they create 8,906 rapid-movement alerts with no business meaning. | Exclude self-transfers in R04, as documented; tag internal movements at source. |
| C10 | Accounts missing from the account master | **PASS** | 0 of 2,076,983 accounts seen in the feed are missing from the master | None: every account seen in the feed exists in the master. | Keep weekly. |
| C11 | FX rate available for every currency | **PASS** | 15 currencies with a fixed USD rate implied by the file; 0 rows without USD amount | None: every currency has a USD rate. | Keep daily; switch to official daily FX rates in production. |
| C12 | Labelled laundering rows match the typology file | **FAIL** | 12,487 of 31,146 labelled rows in the window are not listed in the typology file: coverage by typology is measured on the documented attempts only | 40% of laundering-labelled rows are not in the typology file. Coverage by typology is measured on documented attempts only. | Document the label lineage; measure recall on labels (accounts) and coverage on typologies separately, as done here. |
| C13 | Customers without expected activity | **FAIL** | 792 customers without expected monthly volume (R12 cannot evaluate them) | 4.0% of customers have no expected activity: R12 cannot run for them. | KYC remediation campaign; make expected activity mandatory at onboarding. |
| C14 | High-risk customers with an overdue review (> 12 months) | **FAIL** | 177 high-risk customers last reviewed more than 12 months before 2022-09-16 | 8.7% of high-risk customers are overdue for review. | Prioritised review backlog; dashboard on review ageing. |
| C15 | Several customer records for one entity | **WARN** | 80 customer records share an entity with another record | 80 customer records share an entity: activity and profiles are split. | Entity resolution; merge duplicate records; monitor at entity level. |

## Reading
- Two FAILs change what the rules see: the **ACH feed defect** (C02) blinds corridor logic, and the **day-1 self-transfer
  batch** (C09) inflates R04. Both are invisible in a global null rate (C01 only WARNs at 0.37%).
- The KYC FAILs (C13, C14) matter because two rules depend on KYC: R11 (high-risk customers) and R12 (expected activity).
- C12 is a lineage finding about the benchmark labels, kept because a real engagement would raise the same question about
  the source of its "truth" (confirmed cases, SARs).

Series behind C02: `output/null_rate_by_feed_day.csv`; full report: `output/controls_report.csv`.

---
*Independent case study based on public and synthetic data · not affiliated with any bank or consultancy. Labels: PUBLIC DATA (synthetic AML benchmark), SIMULATED (Bank N layer), ILLUSTRATIVE (country tiers).*
