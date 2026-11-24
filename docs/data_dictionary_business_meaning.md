# Data dictionary and business meaning

Source: IBM "Transactions for AML" (PUBLIC DATA, synthetic, AMLSim; licence CDLA-Sharing-1.0), as loaded by
`src/ingest_dask.py` and wrapped as the Bank N feed by `sql/00_bank_feed.sql`.

| Field (after ingestion) | Original column | Business meaning | Trap |
|---|---|---|---|
| ts | Timestamp | Booking time of the transfer (minute precision) | Format `YYYY/MM/DD HH:MM`; the file ends with a sparse tail of late rows (6,987 rows after 16 Sep) |
| day | (derived) | Booking date, Parquet partition key | The whole file falls in one month, so partitions are by day |
| from_bank / to_bank | From Bank / To Bank | Originator / beneficiary bank code | Leading zeros (`020`, `03196`): read as text, compared as integers with the account master |
| from_account / to_account | Account / Account | Originator / beneficiary account | **Two columns are both named "Account"**: renamed at read time. Never published (pseudonymous `ACC_` refs only) |
| amount_paid, payment_currency | Amount Paid, Payment Currency | What left the originator, in its currency | 15 currencies incl. Bitcoin: convert before any threshold |
| amount_received, receiving_currency | Amount Received, Receiving Currency | What the beneficiary got | Differs from paid only when currencies differ (C06 PASS) |
| amount_paid_usd / amount_received_usd | (derived) | USD equivalent | Fixed rates implied by the file's own cross-currency rows (`output/fx_rates_implied.csv`) |
| payment_format | Payment Format | Channel: ACH, Cheque, Credit Card, Cash, Wire, Bitcoin, Reinvestment | ACH carries 86% of laundering rows; 'Reinvestment' appears on 1 Sep only, always as a self-transfer |
| is_laundering | Is Laundering | Benchmark label (truth for validation) | 0.11% of rows; 40% of labelled rows are not in the typology file (C12) |
| is_self | (derived) | Same account on both sides | 2,559,376 rows; no business meaning for rapid-movement logic |
| entity_id | Entity ID (accounts file) | Legal or natural person owning the account | Re-hashed to `ENT_` refs; **Entity Name is dropped at ingestion** |
| bank_country | Bank Name (accounts file) | Country parsed from the bank name ("China Bank #561") | "Savings/First/National" banks have no country; "Crytpo" is a typo in the source |

## Flows in business terms (complete-day window)
| Flow type | Rows | Share | Laundering rows | Share of laundering |
|---|---|---|---|---|
| between banks | 28,986,700 | 90.9% | 29,939 | 96.1% |
| self-transfer (same account) | 2,559,376 | 8.0% | 60 | 0.2% |
| same bank, different account | 242,618 | 0.8% | 247 | 0.8% |
| beneficiary bank missing | 102,557 | 0.3% | 900 | 2.9% |

## Payment formats
| Format | Rows | Share | Laundering rate | Share of laundering |
|---|---|---|---|---|
| Cheque | 12,280,058 | 38.5% | 0.018% | 7.1% |
| Credit Card | 8,777,816 | 27.5% | 0.015% | 4.3% |
| ACH | 3,861,424 | 12.1% | 0.690% | 85.6% |
| Cash | 3,217,531 | 10.1% | 0.021% | 2.1% |
| Reinvestment | 1,945,611 | 6.1% | 0.000% | 0.0% |
| Wire | 1,119,774 | 3.5% | 0.000% | 0.0% |
| Bitcoin | 689,037 | 2.2% | 0.035% | 0.8% |

## Bank N tables (SIMULATED, `data/sim/`)
`customers`, `rules_documented`, `rules_implemented`, `alerts`, `dispositions`, `capacity`, `feeds`, `payroll_batch`: see
`src/simulate_bank_layer.py` for every column. Identifiers are pseudonymous (`CUS…`, `ACC_…`, `ENT_…`, `ALT…`, `AN01…AN12`).

---
*Independent case study based on public and synthetic data · not affiliated with any bank or consultancy. Labels: PUBLIC DATA (synthetic AML benchmark), SIMULATED (Bank N layer), ILLUSTRATIVE (country tiers).*
