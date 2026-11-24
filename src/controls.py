"""Automated data controls declared in controls/controls.yaml, evaluated with DuckDB.

    python src/controls.py

Runs after src/simulate_bank_layer.py (it checks the Bank N feed and the SIMULATED KYC file).
Writes output/controls_report.csv (one row per control: metric, thresholds, PASS / WARN / FAIL, detail)
and output/null_rate_by_feed_day.csv (the series behind control C02).
"""
import pandas as pd
import yaml

from db import OUT, PARQ, ROOT, connect
from run_sql import load_sim


def status(v, c):
    return "FAIL" if v > c["fail"] else "WARN" if v > c["warn"] else "PASS"


def evaluate(con, c):
    k = c["check"]
    if k == "null_rate_by_field":
        exprs = ", ".join(f"avg(CASE WHEN {f} IS NULL THEN 1 ELSE 0 END) AS {f}" for f in c["fields"])
        r = con.execute(f"SELECT {exprs} FROM tx").df().iloc[0]
        return r.max(), f"worst field: {r.idxmax()} ({r.max():.3%}); all others {r.drop(r.idxmax()).max():.3%} or less"
    if k == "null_rate_by_feed_day":
        g = con.execute(f"""SELECT payment_format, day, count(*) AS n_rows,
                                   avg(CASE WHEN {c['field']} IS NULL THEN 1 ELSE 0 END) AS null_rate
                            FROM tx GROUP BY 1, 2 ORDER BY 1, 2""").df()
        g.to_csv(OUT / "null_rate_by_feed_day.csv", index=False)
        bad = g[g.null_rate > c["fail"]]
        if bad.empty:
            return g.null_rate.max(), "no feed-day above the threshold"
        f = bad.payment_format.mode()[0]
        b = bad[bad.payment_format == f]
        return g.null_rate.max(), (f"{f} feed loses the beneficiary bank from {b.day.min():%Y-%m-%d} "
                                   f"({b.null_rate.mean():.2%} of rows on average, {len(b)} days)")
    if k == "duplicate_rows":
        n, d = con.execute("""SELECT count(*), count(*) - (SELECT count(*) FROM (SELECT DISTINCT ts, from_key, to_key,
                                  amount_paid, payment_currency, amount_received, receiving_currency, payment_format
                              FROM tx WHERE source = 'ibm')) FROM tx WHERE source = 'ibm'""").fetchone()
        return d / n, f"{d:,} exact duplicate rows out of {n:,}"
    if k == "allowed_values":
        cur = "', '".join(c["currencies"])
        fmt = "', '".join(c["formats"])
        n, bad = con.execute(f"""SELECT count(*), count(*) FILTER (WHERE payment_currency NOT IN ('{cur}')
                                     OR receiving_currency NOT IN ('{cur}') OR payment_format NOT IN ('{fmt}')) FROM tx""").fetchone()
        return bad / n, f"{bad:,} rows outside {len(c['currencies'])} currencies / {len(c['formats'])} formats"
    if k == "non_positive_amounts":
        n, bad = con.execute("SELECT count(*), count(*) FILTER (WHERE amount_paid <= 0 OR amount_received <= 0) FROM tx").fetchone()
        return bad / n, f"{bad:,} rows with an amount <= 0"
    if k == "paid_vs_received":
        n, bad = con.execute(f"""SELECT count(*), count(*) FILTER (WHERE abs(amount_paid - amount_received) > {c['tolerance']})
                                 FROM tx WHERE payment_currency = receiving_currency""").fetchone()
        return bad / n, f"{bad:,} same-currency rows where paid and received differ"
    if k == "freshness":
        f = con.execute("""SELECT max(datediff('minute', CAST(day AS TIMESTAMP) + INTERVAL 1 DAY, arrival_ts)) / 60.0,
                                  (SELECT sum(n_rows) FROM daily_volume WHERE day > (SELECT d1 FROM period)),
                                  (SELECT max(day) FROM daily_volume) FROM feeds""").fetchone()
        return f[0], (f"latest feed arrives {f[0]:.1f} h after day end; the source file also carries {int(f[1]):,} "
                      f"late rows up to {f[2]:%Y-%m-%d}, outside the complete-day window")
    if k == "daily_volume_deviation":
        g = con.execute("""SELECT day, n_rows, n_rows / median(n_rows) OVER (PARTITION BY dayofweek(day)) - 1 AS dev
                           FROM daily_volume WHERE day BETWEEN (SELECT d0 FROM period) AND (SELECT d1 FROM period)""").df()
        w = g.loc[g.dev.abs().idxmax()]
        return abs(w.dev), f"largest deviation {w.dev:+.0%} on {w.day:%Y-%m-%d} ({int(w.n_rows):,} rows)"
    if k == "self_transfer_share":
        g = con.execute("""SELECT day, avg(CASE WHEN is_self THEN 1 ELSE 0 END) AS s,
                                  count(*) FILTER (WHERE payment_format = 'Reinvestment') AS r
                           FROM tx GROUP BY 1 ORDER BY s DESC LIMIT 1""").fetchone()
        return g[1], f"{g[1]:.0%} self-transfers on {g[0]:%Y-%m-%d} ({g[2]:,} 'Reinvestment' rows, none on other days)"
    if k == "referential_integrity":
        n, miss = con.execute("""WITH k AS (SELECT from_key AS key FROM tx WHERE source = 'ibm'
                                            UNION SELECT to_key FROM tx WHERE source = 'ibm')
                                 SELECT count(*), count(*) FILTER (WHERE key NOT IN (SELECT acct_key FROM accounts)) FROM k""").fetchone()
        return miss / n, f"{miss:,} of {n:,} accounts seen in the feed are missing from the master"
    if k == "fx_coverage":
        n, miss = con.execute(f"""SELECT count(*), count(*) FILTER (WHERE amount_paid_usd IS NULL) FROM tx""").fetchone()
        rates = pd.read_csv(PARQ / "fx_rates.csv")
        return miss / n, f"{len(rates)} currencies with a fixed USD rate implied by the file; {miss:,} rows without USD amount"
    if k == "label_pattern_consistency":
        n, miss = con.execute("""
            WITH p AS (SELECT DISTINCT ts, from_key, to_key, amount_paid FROM patterns)
            SELECT count(*), count(*) FILTER (WHERE p.ts IS NULL)
            FROM tx t LEFT JOIN p ON p.ts = t.ts AND p.from_key = t.from_key AND p.to_key = t.to_key AND p.amount_paid = t.amount_paid
            WHERE t.is_laundering = 1""").fetchone()
        return miss / n, (f"{miss:,} of {n:,} labelled rows in the window are not listed in the typology file: "
                          "coverage by typology is measured on the documented attempts only")
    if k == "kyc_missing_expected_activity":
        r = con.execute("SELECT avg(CASE WHEN expected_monthly_volume IS NULL THEN 1 ELSE 0 END), count(*) FILTER (WHERE expected_monthly_volume IS NULL) FROM customers").fetchone()
        return r[0], f"{r[1]:,} customers without expected monthly volume (R12 cannot evaluate them)"
    if k == "kyc_high_risk_overdue":
        r = con.execute("""SELECT avg(CASE WHEN last_review_date < DATE '2021-09-16' THEN 1 ELSE 0 END),
                                  count(*) FILTER (WHERE last_review_date < DATE '2021-09-16')
                           FROM customers WHERE risk_rating = 'high'""").fetchone()
        return r[0], f"{r[1]:,} high-risk customers last reviewed more than 12 months before 2022-09-16"
    if k == "kyc_duplicate_entities":
        r = con.execute("""SELECT count(*) FILTER (WHERE n > 1) / count(*), sum(n) FILTER (WHERE n > 1)
                           FROM (SELECT entity_ref, count(*) AS n FROM customers GROUP BY 1)""").fetchone()
        return r[0], f"{int(r[1]):,} customer records share an entity with another record"
    raise ValueError(k)


def main():
    spec = yaml.safe_load((ROOT / "controls" / "controls.yaml").read_text(encoding="utf-8"))["controls"]
    con = connect()
    load_sim(con)
    rows = []
    for c in spec:
        v, detail = evaluate(con, c)
        rows.append({"control_id": c["id"], "name": c["name"], "object": c["object"], "metric": round(float(v), 6),
                     "warn_above": c["warn"], "fail_above": c["fail"], "status": status(float(v), c),
                     "frequency": c["frequency"], "owner": c["owner"], "detail": detail})
    rep = pd.DataFrame(rows)
    OUT.mkdir(exist_ok=True)
    rep.to_csv(OUT / "controls_report.csv", index=False)
    print(rep[["control_id", "status", "name"]].to_string(index=False))
    print(rep.status.value_counts().to_dict())
    con.close()


if __name__ == "__main__":
    main()
