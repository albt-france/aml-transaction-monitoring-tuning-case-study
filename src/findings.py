"""Collect the headline numbers from output/*.csv into output/findings.json.

Every number quoted in the PDF, the dashboard and the README comes from this file, so the text matches the code.
    python src/findings.py
"""
import json
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "output"
PUB = ROOT / "data" / "public"


def csv(n):
    return pd.read_csv(OUT / f"{n}.csv")


def main():
    f = {}
    po = csv("profile_overview").iloc[0]
    f["data"] = {k: (v.item() if hasattr(v, "item") else v) for k, v in po.items()}
    ing = csv("ingest_log")
    d = ing[(ing.engine == "dask") & (ing.dataset == "HI-Medium")]
    f["ingest"] = {"dask_medium": d.iloc[0].to_dict() if len(d) else None,
                   "dask_small": ing[(ing.engine == "dask") & (ing.dataset == "HI-Small")].iloc[0].to_dict(),
                   "duckdb_small": ing[(ing.engine == "duckdb") & (ing.dataset == "HI-Small")].iloc[0].to_dict()}
    c = csv("controls_report")
    f["controls"] = {"n": len(c), "pass": int((c.status == "PASS").sum()), "warn": int((c.status == "WARN").sum()),
                     "fail": int((c.status == "FAIL").sum()),
                     "detail": c.set_index("control_id")[["status", "metric", "detail"]].to_dict("index")}
    ss = csv("system_summary").set_index("ruleset")
    f["system"] = ss.to_dict("index")
    rp = csv("rule_performance")
    f["rules_implemented"] = rp[rp.ruleset == "implemented"].set_index("rule_id").to_dict("index")
    f["rules_documented"] = rp[rp.ruleset == "documented"].set_index("rule_id").to_dict("index")
    f["doc_vs_code"] = csv("doc_vs_code").set_index("rule_id").to_dict("index")
    f["r04"] = csv("r04_self_transfer_effect").iloc[0].to_dict()
    f["feed_defect"] = csv("feed_defect_impact").iloc[0].to_dict()
    cw = csv("capacity_weekly").set_index("wk")
    f["capacity"] = cw.to_dict("index")
    ai = pd.read_parquet(ROOT / "data" / "sim" / "alerts.parquet")
    ai["wk"] = ((pd.to_datetime(ai.created_ts).dt.normalize() - pd.Timestamp(f["data"]["first_day"])).dt.days // 7) + 1
    wk2 = ai[ai.wk == 2]
    f["r09_share_week2"] = float((wk2.rule_id == "R09").mean())
    f["tuning"] = csv("tuning_summary").iloc[0].to_dict()
    f["tuning_rules"] = csv("tuning_proposal_impact").set_index("rule_id").to_dict("index")
    curve = csv("atl_btl_curve")
    f["atl_btl"] = {r: g.set_index("mult")[["threshold", "alerts_per_week", "tp_accounts", "precision",
                                             "lost_unique_tp_accounts"]].to_dict("index") for r, g in curve.groupby("rule_id")}
    cov = csv("typology_coverage")
    f["coverage"] = {"summary": csv("coverage_summary").iloc[0].to_dict(), "by_typology": cov.set_index("typology").to_dict("index")}
    f["network"] = {"performance": csv("network_scenario_performance").set_index("pattern").to_dict("index"),
                    "coverage": csv("network_typology_coverage").set_index("typology").to_dict("index")}
    f["payroll"] = csv("payroll_verdict").iloc[0].to_dict()
    f["kyc"] = csv("kyc_gaps").set_index("gap").to_dict("index")
    f["kyc_impact"] = csv("kyc_gap_impact").iloc[0].to_dict()
    f["dispositions"] = csv("disposition_summary").set_index("rule_id").to_dict("index")
    f["model"] = {"metrics": csv("model_metrics").set_index("version").to_dict("index"),
                  "capacity": csv("model_capacity").set_index("approach").to_dict("index"),
                  "simpson": csv("model_simpson").to_dict("records"),
                  "importance": csv("model_importance").head(8).to_dict("records"),
                  "base": csv("model_base").iloc[0].to_dict()}
    ecb = pd.read_csv(PUB / "ecb_credit_transfer_fraud.csv")
    f["ecb"] = {"rows": ecb[["zone", "zone_label", "period", "value_eur_m", "series_key"]].to_dict("records"),
                "extracted_on": str(ecb.extracted_on.iloc[0])}
    f["amlr"] = pd.read_csv(PUB / "amlr_articles.csv")[["article", "title"]].to_dict("records")
    (OUT / "findings.json").write_text(json.dumps(f, indent=1, default=str), encoding="utf-8")
    print("findings.json written:", ", ".join(f.keys()))


if __name__ == "__main__":
    main()
