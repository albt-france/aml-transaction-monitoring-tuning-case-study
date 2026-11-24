# Assumptions

## Data (PUBLIC DATA, synthetic)
- IBM "Transactions for AML" HI-Medium is synthetic (AMLSim). It is never presented as real bank data.
- Analysis window: the 16 complete days (1-16 Sep 2022), i.e. days with at least 20% of the median daily volume.
- FX: one fixed USD rate per currency, the mean of `amount_received / amount_paid` on rows paid in that currency and received in
  US Dollar (AMLSim uses fixed rates; the IBM dates are fictitious, so ECB rates of 2022 would not match). Rates: `output/fx_rates_implied.csv`.
- Amount thresholds are set on this file's distribution (1% of transfers exceed USD 2.8M). Read them as positions in this
  dataset, not as real-world calibrations.

## Bank N (SIMULATED, seed 42)
- Book: entities whose md5(Entity ID) falls in a 4% bucket, minus entities with any transfer above USD 1M in the window
  (institutional-scale flows, outside a mid-sized retail/SME bank). Result: 19,968 customers, 45,089 accounts.
- Bank N sees every transfer touching its book, on both sides. A real bank sees only its own side and the counterparty's identifiers.
- Segments and risk ratings are drawn at random but **partly from the labels** (laundering customers are more often high-risk; SMEs sit mostly
  in the high-risk tier). This gives risk ratings some signal and creates the Simpson's paradox to detect. They are not model features.
- Capacity: 12 analysts, 30 productive hours a week each, 12 minutes median per alert (simulated decisions: lognormal, about 12 min for
  false positives and 30 min for true positives). Capacity = 1,800 alerts a week.
- Analyst decisions are simulated from the labels with noise: true positives 55% SAR, 35% escalated, 10% closed; false positives 93% closed,
  6% escalated, 1% SAR; payroll-driven alerts always closed.
- Planted events (feed defect, documentation gaps, payroll batches) are described in `src/simulate_bank_layer.py`; the analysis finds them
  from the data, without reading those parameters.

## ILLUSTRATIVE
- Country risk tiers: 4 bank-country groups drawn at random (seed 42) form the "high" corridor tier. They are not an assessment of any country.

## Performance (measured)
- Dask, HI-Medium (3.0 GB CSV to Parquet): 98.6 s, peak memory 4.87 GB, 12 cores, 16.8 GB RAM.
- HI-Small (0.5 GB): Dask 15.9 s, DuckDB 2.1 s.

---
*Independent case study based on public and synthetic data · not affiliated with any bank or consultancy. Labels: PUBLIC DATA (synthetic AML benchmark), SIMULATED (Bank N layer), ILLUSTRATIVE (country tiers).*
