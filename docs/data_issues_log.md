# Data issues log

| Id | Issue | Area | Action | Status |
|---|---|---|---|---|
| DI-01 | Two columns named 'Account' in the transaction file | Ingestion | Renamed from_account / to_account at read time | Closed |
| DI-02 | Bank codes with leading zeros ('020', '03196') | Ingestion | Read as text; compared as integers with the account master | Closed |
| DI-03 | Amounts in 15 currencies incl. Bitcoin | Rules | Fixed USD rates implied by the file; ECB daily rates in production | Closed (study) |
| DI-04 | Sparse tail: 6,987 rows from 17 to 28 Sep | Freshness | Complete-day window 1-16 Sep; C07 reports the tail | Closed |
| DI-05 | 1.9M 'Reinvestment' self-transfers on 1 Sep only | Volume / R04 | C08, C09 flag it; R04 fix excludes self-transfers | Open: fix in 30 days |
| DI-06 | ACH feed loses the beneficiary bank on ~6% of rows from 9 Sep (SIMULATED) | Completeness / R07 | C02 FAIL; incident and load gate | Open: owner data engineering |
| DI-07 | 40% of labelled rows not in the typology file | Label lineage | Recall measured on labels, coverage on documented attempts | Accepted (documented) |
| DI-08 | 20 exact duplicate rows | Uniqueness | C03 WARN; deduplicate at load | Open: low |
| DI-09 | 4.0% of customers without expected activity (SIMULATED) | KYC / R12 | C13 FAIL; remediation | Open |
| DI-10 | 8.7% of high-risk customers overdue for review (SIMULATED) | KYC | C14 FAIL; review backlog | Open |
| DI-11 | 80 customer records share an entity (SIMULATED) | KYC / entity | C15 WARN; entity resolution | Open |
| DI-12 | Entity names present in the account master | Privacy | Column dropped at ingestion; never stored | Closed |
| DI-13 | Bank names carry the country ('China Bank #561'); 'Crytpo' typo; 3 generic names without country | Reference data | Parsed; generic names = 'Unspecified' | Closed |

---
*Independent case study based on public and synthetic data · not affiliated with any bank or consultancy. Labels: PUBLIC DATA (synthetic AML benchmark), SIMULATED (Bank N layer), ILLUSTRATIVE (country tiers).*
