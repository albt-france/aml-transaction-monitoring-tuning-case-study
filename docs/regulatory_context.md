# Regulatory and market context

**No legal advice.** This note only cites texts to frame the engagement; any interpretation is for the bank's compliance and legal functions.

## Regulation (EU) 2024/1624 (AMLR)
Source: Publications Office of the EU, CELEX 32024R1624, English text (retrieved 2026-11-24).
Articles relevant to transaction monitoring, as titled in the text:
- Article 20: *Customer due diligence measures*
- Article 26: *Ongoing monitoring of the business relationship and monitoring of transactions performed by customers*
- Article 34: *Scope of application of enhanced due diligence measures*
- Article 69: *Reporting of suspicions*
- Article 77: *Record retention*

Article 26 is the anchor for this engagement: monitoring of the business relationship and of the transactions customers perform.
Article 77 matters for the data work: what is kept, and for how long, determines what back-testing is possible.

Commission Delegated Regulation (EU) 2016/1675 (high-risk third countries) is cited for context only. Its list has been amended
many times, so **no current country list is derived from it**: the country tiers in this study are ILLUSTRATIVE.

## Payment fraud in the EU (ECB, real statistics)
Value of fraudulent credit transfers, EUR million per half-year (ECB Data Portal, dataset PAY, series
`PAY/H.<zone>.W0.CT0.1.F.N.EUR`, UNIT_MULT = 6, extracted 2026-11-24).

| zone_label | 2024-S2 | 2025-S1 | 2025-S2 |
|---|---|---|---|
| EU | 1227.5 | 1221.0 | 1413.8 |
| Euro area | 1082.7 | 1048.6 | 1239.8 |
| France | 194.4 | 235.2 | 249.4 |
| Spain | 72.2 | 100.5 | 149.8 |

Fraudulent credit transfers in the EU reached EUR 1,413.8 million in 2025-S2.
Spain went from 72.2 to 149.8
in a year. Fraud is not money laundering, but the proceeds of payment fraud are what TM systems must then see moving.

---
*Independent case study based on public and synthetic data · not affiliated with any bank or consultancy. Labels: PUBLIC DATA (synthetic AML benchmark), SIMULATED (Bank N layer), ILLUSTRATIVE (country tiers).*
