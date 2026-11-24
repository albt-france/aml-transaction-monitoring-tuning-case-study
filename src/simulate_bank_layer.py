"""SIMULATED "Bank N" layer on top of the IBM AML benchmark (PUBLIC DATA, synthetic). Seed 42.

Bank N is a fictional mid-sized European bank. Its book is a deterministic 4% sample of IBM entities (md5 of the
Entity ID), minus institutional-scale entities (any transfer above USD 1M); its customers, KYC records, documented and implemented rules, analyst capacity, feed metadata and
analyst decisions are SIMULATED. Country risk tiers are ILLUSTRATIVE (random draw, not an assessment of a country).

    python src/simulate_bank_layer.py            # customers, KYC, rules, payroll batch, feed defect, feeds
    (analyst decisions are simulated by simulate_dispositions(), called from src/run_sql.py after the rule engine)

Outputs: data/sim/*.parquet (published, pseudonymous refs only: CUS..., ACC_..., ENT_..., AN..),
         data/_hidden_truth.csv (the 8 planted events, removed before publication),
         data/parquet/work.duckdb (raw keys + id maps, never published).
"""
import json

import numpy as np
import pandas as pd

from db import OUT, PARQ, ROOT, SIM, SQL, connect, q, render, run_file

SEED = 42
BOOK_PERMIL = 40                      # 4% of IBM entities are sampled for Bank N's book ...
MAX_TRANSFER_USD = 1_000_000          # ... minus institutional-scale entities (any transfer above USD 1M)
AS_OF = pd.Timestamp("2022-09-16")    # last complete day of the HI files
DEFECT = {"format": "ACH", "start": "2022-09-09", "bp": 600}   # 6.00% of ACH rows lose the beneficiary bank
PAYROLL = {"day": "2022-09-14", "usual_day": "2022-09-15", "n_customers": 26, "staff": (11, 18)}
ANALYSTS, HOURS_PER_WEEK, MEDIAN_MIN = 12, 30, 12

# ---------------------------------------------------------------- rules: documentation vs implementation
# basis: 'usd' = USD-equivalent amount, 'raw' = amount in the original payment currency (no conversion)
RULES = [
    # id, name, typology, description, threshold, currency, lookback_days, segment_scope, basis, exclude_self
    ("R01", "Large single transfer", "Large value", "One outgoing transfer of at least the threshold", 750000, "USD", 1, "all", "usd", True),
    ("R02", "Structuring below 10k", "Structuring", "3+ outgoing transfers between 8,000 and 9,999.99 in 7 days", 10000, "USD", 7, "all", "usd", True),
    ("R03", "Fan-out", "FAN-OUT; GATHER-SCATTER; BIPARTITE", "Payments to at least N distinct beneficiaries in one day", 20, "count", 1, "all", "usd", True),
    ("R04", "Rapid movement of funds", "STACK; RANDOM", "Receives >= threshold and sends 80-120% of it on within 2 days", 20000, "USD", 2, "all", "usd", True),
    ("R05", "Activity spike", "Behaviour change", "Daily outgoing count >= 10 and >= 5x the account's prior 7-day daily mean", 5, "x baseline", 7, "all", "usd", True),
    ("R06", "Fan-in", "FAN-IN; GATHER-SCATTER; BIPARTITE", "Payments from at least N distinct remitters in one day", 20, "count", 1, "all", "usd", True),
    ("R07", "High-risk corridor", "Geography", "Transfer >= threshold to or from a bank in a high-risk tier country (ILLUSTRATIVE tiers)", 500000, "USD", 1, "all", "usd", True),
    ("R08", "Crypto / cross-currency", "Conversion", "Bitcoin transfer or currency conversion >= threshold", 10000, "USD", 1, "all", "usd", True),
    ("R09", "Round amounts", "Generic red flag", "Outgoing transfer of a whole amount (no cents) >= threshold", 1000, "USD", 1, "all", "usd", True),
    ("R10", "Cash activity", "Cash", "Cash in + out >= threshold over the lookback", 750000, "USD", 7, "all", "usd", True),
    ("R11", "High-risk customer outflow", "KYC risk", "Outgoing transfer >= threshold by a high-risk-rated customer", 250000, "USD", 1, "all", "usd", True),
    ("R12", "Activity above expected profile", "KYC profile", "7-day outflow > 4x the expected weekly volume declared at KYC", 4, "x profile", 7, "all", "usd", True),
]
# deliberate gaps between the documentation and the code (found in sql/03 by running both versions)
IMPLEMENTED_OVERRIDES = {
    "R02": {"basis": "raw"},          # coded on the raw amount: no conversion to USD
    "R04": {"exclude_self": False},   # self-transfers ('Reinvestment') not excluded
    "R10": {"lookback_days": 1},      # documented 7-day accumulation, coded as a single day
}
COLS = ["rule_id", "name", "typology", "description", "threshold", "currency", "lookback_days", "segment_scope",
        "basis", "exclude_self"]


def rules_tables():
    doc = pd.DataFrame(RULES, columns=COLS)
    imp = doc.copy()
    for rid, ch in IMPLEMENTED_OVERRIDES.items():
        for k, v in ch.items():
            imp.loc[imp.rule_id == rid, k] = v
    return doc, imp


def save(df: pd.DataFrame, name: str):
    SIM.mkdir(parents=True, exist_ok=True)
    df.to_parquet(SIM / f"{name}.parquet", index=False)


def main():
    rng = np.random.default_rng(SEED)
    con = connect()
    run_file(con, SQL / "00_base.sql", save=False)
    d0, d1 = con.execute("SELECT d0, d1 FROM period").fetchone()

    # ---- book and pseudonymous ids ------------------------------------------------------------------------
    # Bank N serves retail, SME and mid-market clients: sampled entities with any transfer above
    # MAX_TRANSFER_USD in the window (institutional-scale flows) are outside its book.
    con.execute(f"""CREATE OR REPLACE TEMP TABLE book0 AS
        SELECT acct_key, entity_id, bank_country FROM accounts WHERE md5_number(entity_id) % 1000 < {BOOK_PERMIL}""")
    con.execute(f"""CREATE OR REPLACE TEMP TABLE big_entities AS
        WITH s AS (
            SELECT CAST(CAST(from_bank AS BIGINT) AS VARCHAR) || '|' || from_account AS k,
                   greatest(amount_paid_usd, amount_received_usd) AS a
            FROM tx_raw WHERE day BETWEEN (SELECT d0 FROM period) AND (SELECT d1 FROM period)
            UNION ALL
            SELECT CAST(CAST(to_bank AS BIGINT) AS VARCHAR) || '|' || to_account,
                   greatest(amount_paid_usd, amount_received_usd)
            FROM tx_raw WHERE day BETWEEN (SELECT d0 FROM period) AND (SELECT d1 FROM period))
        SELECT DISTINCT b.entity_id FROM s JOIN book0 b ON b.acct_key = s.k WHERE s.a > {MAX_TRANSFER_USD}""")
    con.execute("""CREATE OR REPLACE TABLE book AS
        SELECT acct_key, entity_id, bank_country,
               'ACC_' || lpad(CAST(row_number() OVER (ORDER BY md5(acct_key)) AS VARCHAR), 6, '0') AS account_ref
        FROM book0 WHERE entity_id NOT IN (SELECT entity_id FROM big_entities)""")
    con.execute("CREATE OR REPLACE TABLE id_accounts AS SELECT acct_key, account_ref FROM book")
    # truth per account (laundering involvement inside the window) and observed outflow, from IBM rows only
    acc = q(con, """
        WITH inv AS (
            SELECT from_bank || '|' || from_account AS k, is_laundering, amount_paid_usd AS out_usd,
                   (from_bank = to_bank AND from_account = to_account) AS self FROM (
              SELECT CAST(CAST(from_bank AS BIGINT) AS VARCHAR) from_bank, from_account,
                     CAST(CAST(to_bank AS BIGINT) AS VARCHAR) to_bank, to_account, is_laundering, amount_paid_usd
              FROM tx_raw WHERE day BETWEEN (SELECT d0 FROM period) AND (SELECT d1 FROM period))
            UNION ALL
            SELECT CAST(CAST(to_bank AS BIGINT) AS VARCHAR) || '|' || to_account, is_laundering, 0, false
            FROM tx_raw WHERE day BETWEEN (SELECT d0 FROM period) AND (SELECT d1 FROM period))
        SELECT b.acct_key, b.entity_id, b.account_ref, b.bank_country,
               coalesce(max(inv.is_laundering), 0) AS laundering,
               coalesce(sum(inv.out_usd) FILTER (WHERE NOT inv.self), 0) AS out_usd,
               count(inv.k) AS n_tx
        FROM book b LEFT JOIN inv ON inv.k = b.acct_key
        GROUP BY ALL""")
    ent = (acc.groupby("entity_id")
              .agg(laundering=("laundering", "max"), out_usd=("out_usd", "sum"), n_accounts=("acct_key", "size"))
              .reset_index())
    ent = ent.iloc[np.argsort([hash_str(e) for e in ent.entity_id])].reset_index(drop=True)
    n = len(ent)
    ent["customer_id"] = [f"CUS{i + 1:06d}" for i in range(n)]
    ent["entity_ref"] = [f"ENT_{i + 1:06d}" for i in range(n)]

    # ---- risk rating and segment (SIMULATED; partly correlated with the labels so that ratings carry signal)
    lab = ent.laundering.values == 1
    p_tier = np.where(lab[:, None], [[0.10, 0.30, 0.60]], [[0.62, 0.30, 0.08]])
    tier = np.array([rng.choice(["low", "medium", "high"], p=p) for p in p_tier])
    seg_p = {  # (laundering, tier) -> P(retail, sme, corporate); SMEs sit mostly in the high-risk tier
        (False, "low"): [0.80, 0.08, 0.12], (False, "medium"): [0.55, 0.30, 0.15], (False, "high"): [0.15, 0.72, 0.13],
        (True, "low"): [0.85, 0.05, 0.10], (True, "medium"): [0.70, 0.15, 0.15], (True, "high"): [0.30, 0.57, 0.13]}
    seg = np.array([rng.choice(["retail", "sme", "corporate"], p=seg_p[(l, t)]) for l, t in zip(lab, tier)])
    ent["segment"], ent["risk_rating"] = seg, tier
    ent["onboarding_date"] = pd.to_datetime("2008-01-01") + pd.to_timedelta(rng.integers(0, 5300, n), unit="D")
    max_age = {"low": 36, "medium": 24, "high": 12}
    months = np.array([rng.uniform(0, max_age[t]) for t in tier])
    overdue = (tier == "high") & (rng.random(n) < 0.09)            # 9% of high-risk files past their 12-month review
    months[overdue] = rng.uniform(12.5, 30, overdue.sum())
    ent["last_review_date"] = (AS_OF - pd.to_timedelta(months * 30.4, unit="D")).normalize()
    ent["last_review_date"] = ent[["last_review_date", "onboarding_date"]].max(axis=1)
    codes = ["NL", "DE", "FR", "BE", "ES", "IT", "AT", "PT", "IE", "LU", "GB", "CH", "US", "AE", "HK", "SG", "TR", "XX"]
    w = np.array([30, 14, 12, 8, 6, 6, 3, 3, 2, 2, 3, 2, 2, 1.5, 1.5, 1, 1, 2]); w = w / w.sum()
    ent["country_code"] = rng.choice(codes, n, p=w)            # ILLUSTRATIVE residence
    monthly = ent.out_usd.values * 30 / 16 * rng.lognormal(0, 0.6, n)
    ent["expected_monthly_volume"] = np.round(np.maximum(monthly, 500), -2)
    missing = rng.random(n) < 0.04                                  # 4% without expected activity
    ent.loc[missing, "expected_monthly_volume"] = np.nan
    ent["kyc_complete_flag"] = ~missing & ~overdue
    ent["known_payroll"] = (ent.segment == "corporate") & (rng.random(n) < 0.35)

    # duplicate customer records sharing one entity (onboarding duplicates; a KYC gap, not hidden)
    dup = ent.sample(frac=0.002, random_state=SEED).copy()
    dup["customer_id"] = [f"CUS{n + i + 1:06d}" for i in range(len(dup))]
    dup["onboarding_date"] = dup["onboarding_date"] + pd.Timedelta(days=400)
    customers = pd.concat([ent, dup], ignore_index=True)
    cols = ["customer_id", "entity_ref", "segment", "risk_rating", "last_review_date", "onboarding_date",
            "country_code", "expected_monthly_volume", "kyc_complete_flag", "known_payroll"]
    save(customers[cols], "customers")
    con.register("ent_df", ent[["entity_id", "customer_id", "entity_ref", "segment", "risk_rating",
                                "expected_monthly_volume", "known_payroll", "laundering"]])
    con.execute("CREATE OR REPLACE TABLE id_customers AS SELECT * FROM ent_df")
    con.execute("""CREATE OR REPLACE TABLE book AS
        SELECT b.*, c.customer_id, c.segment, c.risk_rating, c.expected_monthly_volume, c.known_payroll
        FROM book b JOIN id_customers c USING (entity_id)""")

    # ---- SIMULATED payroll batches, brought forward one day by a bank holiday --------------------------------
    eur = float(pd.read_csv(PARQ / "fx_rates.csv").set_index("currency").usd_per_unit["Euro"])
    cand = acc.drop(columns="laundering").merge(ent[["entity_id", "customer_id", "known_payroll", "laundering"]], on="entity_id")
    # low-activity accounts: a salary batch is a visible spike against their usual daily volume
    cand = cand[cand.known_payroll & (cand.laundering == 0) & cand.n_tx.between(6, 30)].sort_values("account_ref")
    cand = cand.drop_duplicates("customer_id").head(PAYROLL["n_customers"])
    rows, emp = [], 0
    for ref in cand.account_ref:
        k = int(rng.integers(PAYROLL["staff"][0], PAYROLL["staff"][1] + 1))
        start = pd.Timestamp(PAYROLL["day"]) + pd.Timedelta(minutes=int(rng.integers(300, 420)))
        for j in range(k):
            emp += 1
            amt = round(float(rng.lognormal(np.log(2900), 0.25)), 2)
            rows.append({"account_ref": ref, "employee_ref": f"EMP{emp:06d}", "ts": start + pd.Timedelta(seconds=j),
                         "amount_paid": amt, "payment_currency": "Euro", "amount_paid_usd": round(amt * eur, 2)})
    save(pd.DataFrame(rows), "payroll_batch")

    # ---- Bank N feed (with the defect), feeds lineage table --------------------------------------------------
    run_file(con, SQL / "00_bank_feed.sql", save=False, DEFECT_FORMAT=DEFECT["format"],
             DEFECT_START=DEFECT["start"], DEFECT_BP=DEFECT["bp"])
    (SIM / "feed_config.json").write_text(json.dumps({"bank_feed_built_from": "sql/00_bank_feed.sql",
                                                      "defect": DEFECT}, indent=1))
    feeds = q(con, """
        SELECT payment_format, day, count(*) AS row_count,
               avg(CASE WHEN to_bank IS NULL THEN 1 ELSE 0 END) AS null_rate_beneficiary_bank,
               avg(CASE WHEN from_bank IS NULL THEN 1 ELSE 0 END) AS null_rate_originator_bank,
               avg(CASE WHEN amount_paid IS NULL THEN 1 ELSE 0 END) AS null_rate_amount,
               avg(CASE WHEN payment_currency IS NULL THEN 1 ELSE 0 END) AS null_rate_currency
        FROM tx GROUP BY 1, 2 ORDER BY 1, 2""")
    feeds.insert(0, "feed_id", ["FD_" + f[:3].upper() + "_" + d.strftime("%m%d") for f, d in zip(feeds.payment_format, feeds.day)])
    feeds["arrival_ts"] = (pd.to_datetime(feeds.day) + pd.Timedelta(days=1, hours=2)
                           + pd.to_timedelta(rng.integers(0, 90, len(feeds)), unit="min"))
    save(feeds, "feeds")

    # ---- rules, ILLUSTRATIVE corridor tiers, capacity -------------------------------------------------------
    doc, imp = rules_tables()
    save(doc, "rules_documented")
    save(imp, "rules_implemented")
    groups = sorted(q(con, "SELECT DISTINCT bank_country FROM bank_country").bank_country)
    high = set(rng.choice([g for g in groups if g != "Unspecified"], 4, replace=False))
    tiers = pd.DataFrame({"bank_country": groups, "corridor_tier": ["high" if g in high else "standard" for g in groups]})
    con.register("tiers_df", tiers)
    con.execute("CREATE OR REPLACE TABLE corridor_tier AS SELECT * FROM tiers_df")
    n_weeks = int(np.ceil(((d1 - d0).days + 1) / 7))
    cap = []
    for wk in range(1, n_weeks + 1):
        days = min(7, (d1 - d0).days + 1 - 7 * (wk - 1))
        hours = ANALYSTS * HOURS_PER_WEEK * days / 7
        cap.append({"wk": wk, "days_in_week": days, "analysts": ANALYSTS, "hours_available": round(hours, 1),
                    "median_minutes_per_alert": MEDIAN_MIN, "alert_capacity": int(hours * 60 / MEDIAN_MIN)})
    save(pd.DataFrame(cap), "capacity")
    con.register("cap_df", pd.DataFrame(cap))
    con.execute("CREATE OR REPLACE TABLE capacity AS SELECT * FROM cap_df")

    hidden_truth(doc)
    nb = con.execute("SELECT count(*), sum(CASE WHEN source='payroll_sim' THEN 1 ELSE 0 END) FROM tx").fetchone()
    nbk = con.execute("SELECT count(*) FROM tx_book").fetchone()[0]
    print(f"window {d0}..{d1}; book: {len(ent):,} customers, {len(acc):,} accounts "
          f"({int(ent.laundering.sum()):,} customers with laundering); bank feed {nb[0]:,} rows "
          f"({nb[1]:,} payroll), {nbk:,} touching the book")
    con.close()


def hash_str(s: str) -> str:
    import hashlib
    return hashlib.md5(s.encode()).hexdigest()


def hidden_truth(doc):
    ev = [
        (1, "Feed defect", f"From {DEFECT['start']} {DEFECT['bp'] / 100:.0f}% of {DEFECT['format']} rows lose the beneficiary bank; R07 is blind on them",
         "controls C02 null rate by feed and day; sql/02"),
        (2, "Documentation vs code", "R02 documented on USD-equivalent amounts, coded on the raw amount (no conversion)",
         "sql/03 both versions; sql/04 missed true positives"),
        (3, "Self-transfers", "R04 implementation keeps self-transfers ('Reinvestment'), inflating rapid-movement alerts",
         "sql/02 self-transfers; sql/04 R04 share explained by self-transfers"),
        (4, "Over-alerting rule", "R09 round amounts: large share of alerts, precision near the base rate",
         "sql/04, sql/06 ATL/BTL"),
        (5, "Coverage gap", "No rule targets CYCLE or SCATTER-GATHER typologies", "sql/05 matrix; sql/10 network scenario"),
        (6, "False signal", f"Corporate payroll batches moved from {PAYROLL['usual_day']} to {PAYROLL['day']} by a bank holiday trigger R05; all known payroll, no risk increase",
         "sql/09: do NOT escalate; add a known-payroll exclusion"),
        (7, "Simpson's paradox", "Challenger precision looks higher for sme than retail overall but is lower within each risk rating",
         "src/challenger_model.py segment x risk table"),
        (8, "Leakage", "First challenger uses whole-period account aggregates and a random split; AUC collapses under temporal validation",
         "src/challenger_model.py leaky vs temporal"),
    ]
    pd.DataFrame(ev, columns=["event", "name", "what_was_planted", "where_it_should_be_found"]).to_csv(
        ROOT / "data" / "_hidden_truth.csv", index=False)


def simulate_dispositions(con):
    """Analyst decisions for every alert of the IMPLEMENTED rule set (SIMULATED from the labels, with noise)."""
    rng = np.random.default_rng(SEED + 1)
    a = q(con, """SELECT a.rule_id, b.customer_id, b.account_ref, a.day, a.is_tp, a.metric, a.payroll_driven
                  FROM alerts_implemented a JOIN book b USING (acct_key)
                  ORDER BY a.day, a.rule_id, b.account_ref""")
    a["alert_id"] = [f"ALT{i + 1:07d}" for i in range(len(a))]
    a["created_ts"] = pd.to_datetime(a.day) + pd.Timedelta(hours=23) + pd.to_timedelta(rng.integers(0, 50, len(a)), unit="min")
    a["score"] = (a.groupby("rule_id").metric.rank(pct=True).fillna(1.0) * 100).round(0).astype(int)
    a["status"] = "closed"
    tp = a.is_tp.values == 1
    u = rng.random(len(a))
    dec = np.where(tp, np.where(u < 0.55, "sar_filed", np.where(u < 0.90, "escalated", "closed_no_issue")),
                   np.where(u < 0.93, "closed_no_issue", np.where(u < 0.99, "escalated", "sar_filed")))
    dec = np.where(a.payroll_driven.values, "closed_no_issue", dec)
    minutes = np.where(tp, rng.lognormal(np.log(30), 0.5, len(a)), rng.lognormal(np.log(12), 0.5, len(a)))
    d = pd.DataFrame({"alert_id": a.alert_id, "analyst_id": [f"AN{i:02d}" for i in rng.integers(1, ANALYSTS + 1, len(a))],
                      "decision": dec, "handling_minutes": np.round(minutes, 1),
                      "closed_ts": a.created_ts + pd.to_timedelta(rng.exponential(36, len(a)), unit="h")})
    save(a[["alert_id", "rule_id", "customer_id", "account_ref", "created_ts", "score", "status"]], "alerts")
    save(d, "dispositions")
    con.register("alerts_df", a[["alert_id", "rule_id", "customer_id", "account_ref", "day", "created_ts", "score", "is_tp", "payroll_driven"]])
    con.execute("CREATE OR REPLACE TABLE alerts AS SELECT * FROM alerts_df")
    con.register("disp_df", d)
    con.execute("CREATE OR REPLACE TABLE dispositions AS SELECT * FROM disp_df")
    return len(a)


if __name__ == "__main__":
    main()
