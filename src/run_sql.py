"""Run the SQL layer (DuckDB on the Parquet files and the SIMULATED Bank N tables) in order.

    python src/run_sql.py            # all files
    python src/run_sql.py 04 06      # only the files whose name starts with these prefixes (after 03 has run once)

Named SELECT statements ('-- name: x') are written to output/x.csv. sql/99_tests.sql fails loudly on any broken
assertion. Requires src/ingest_dask.py, src/simulate_bank_layer.py and src/controls.py to have run.
"""
import re
import sys
import time

import pandas as pd

from db import PARQ, SIM, SQL, connect, run_file
from simulate_bank_layer import simulate_dispositions

# Proposals read off output/atl_btl_curve.csv and output/doc_vs_code.csv (see docs/threshold_tuning_report.md).
# action: fix = make the code match the documentation; tune = move the threshold; retire = stop alerting;
#         exclude = add an exclusion. 'tune' and 'retire' change rules_tuned; fixes come from the documented code.
PROPOSALS = [
    ("R01", "retire", 1e12, "Precision equals the base rate and 1 unique laundering account; R12 covers large flows relative to the profile"),
    ("R02", "fix", None, "Convert amounts to USD before the 8,000-9,999.99 band, as documented"),
    ("R03", "tune", 10, "Below-the-line test: 10 distinct beneficiaries finds laundering accounts at 15x the base rate"),
    ("R04", "fix", None, "Exclude self-transfers, as documented"),
    ("R05", "exclude", None, "Known-payroll exclusion for customers whose KYC declares salary batches"),
    ("R06", "tune", 10, "Below-the-line test: 10 distinct remitters doubles the laundering accounts found, precision stays ~7%"),
    ("R09", "tune", 5000, "Largest rule in a normal week at the system's average precision; raise the floor, recover misses with the score"),
    ("R10", "fix", None, "Restore the documented 7-day accumulation"),
    ("R11", "tune", 375000, "Above-the-line test: -22% volume for 1 unique laundering account"),
]

FILES = ["01_profile", "02_business_meaning", "03_rule_engine", "04_rule_performance", "05_typology_coverage",
         "06_atl_btl_tuning", "07_capacity", "08_kyc_gaps", "09_corporate_payroll_false_signal",
         "10_network_cycles", "99_tests"]


def tuned_rules(con):
    doc = con.execute("SELECT * FROM rules_documented").df()
    imp = con.execute("SELECT * FROM rules_implemented").df().set_index("rule_id")
    rows = []
    for rid, action, thr, why in PROPOSALS:
        if thr is not None:
            doc.loc[doc.rule_id == rid, "threshold"] = thr
        rows.append({"rule_id": rid, "action": action, "current_threshold": float(imp.threshold[rid]),
                     "proposed_threshold": None if thr is None or action == "retire" else float(thr), "rationale": why})
    con.register("tuned_df", doc)
    con.execute("CREATE OR REPLACE TABLE rules_tuned AS SELECT * FROM tuned_df")
    con.register("prop_df", pd.DataFrame(rows))
    con.execute("CREATE OR REPLACE TABLE tuning_proposal AS SELECT * FROM prop_df")


def load_sim(con):
    for t in ["rules_documented", "rules_implemented", "customers", "capacity", "feeds"]:
        con.execute(f"CREATE OR REPLACE TABLE {t} AS SELECT * FROM read_parquet('{SIM.as_posix()}/{t}.parquet')")
    con.register("pat_df", parse_patterns(PARQ / "patterns.txt"))
    con.execute("CREATE OR REPLACE TABLE patterns AS SELECT * FROM pat_df")


def parse_patterns(path):
    """IBM Patterns file: one block per laundering attempt, with its typology and its transactions."""
    rows, attempt, typ = [], 0, None
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.startswith("BEGIN LAUNDERING ATTEMPT"):
            attempt += 1
            typ = re.match(r"BEGIN LAUNDERING ATTEMPT - ([A-Z\-]+)", line).group(1)
        elif line.startswith("END") or not line.strip():
            continue
        else:
            f = line.split(",")
            rows.append({"attempt_id": attempt, "typology": typ, "ts": pd.to_datetime(f[0], format="%Y/%m/%d %H:%M"),
                         "from_key": f"{int(f[1])}|{f[2]}", "to_key": f"{int(f[3])}|{f[4]}",
                         "amount_paid": float(f[7]), "payment_currency": f[8], "payment_format": f[9]})
    return pd.DataFrame(rows)


def main():
    only = sys.argv[1:]
    con = connect()
    load_sim(con)
    for f in FILES:
        if only and not any(f.startswith(p) for p in only):
            continue
        t0 = time.perf_counter()
        if f == "03_rule_engine":
            tuned_rules(con)
            for rs in ["documented", "implemented", "tuned"]:
                run_file(con, SQL / f"{f}.sql", RULESET=rs)
            n = simulate_dispositions(con)
            print(f"  simulated analyst decisions for {n:,} alerts")
        else:
            res = run_file(con, SQL / f"{f}.sql")
            if f == "99_tests":
                bad = [k for k, df in res.items() if not df.empty and not bool(df.iloc[0, 0])]
                for k, df in res.items():
                    print(f"  {'PASS' if bool(df.iloc[0, 0]) else 'FAIL'} {k}")
                if bad:
                    raise SystemExit(f"tests failed: {bad}")
        print(f"{f}: {time.perf_counter() - t0:.1f} s")
    con.close()


if __name__ == "__main__":
    main()
