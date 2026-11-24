"""Build and execute the single notebook notebooks/aml_tm_assessment.ipynb (short outputs only).

    python src/build_notebook.py
Requires the pipeline outputs (output/*.csv) and the working DuckDB file from src/run_sql.py.
"""
from pathlib import Path

import nbformat as nbf
from nbconvert.preprocessors import ExecutePreprocessor

ROOT = Path(__file__).resolve().parents[1]
NB = ROOT / "notebooks" / "aml_tm_assessment.ipynb"

cells = [
    ("md", "# Transaction-monitoring assessment for Bank N\n"
           "Data: IBM Transactions for AML HI-Medium (**PUBLIC DATA, synthetic**, AMLSim, CDLA-Sharing-1.0). "
           "Bank N layer (customers, KYC, rules, alerts, decisions): **SIMULATED**. Country tiers: **ILLUSTRATIVE**.\n\n"
           "Order: data, quality, business meaning, rule validation, tuning, network, challenger, recommendations. "
           "Each step reads the outputs of the pipeline (`src/`), so the notebook stays short."),
    ("code", "import json, pandas as pd, duckdb\nfrom pathlib import Path\nROOT = Path.cwd().parent if Path.cwd().name == 'notebooks' else Path.cwd()\n"
             "O = ROOT / 'output'\nf = json.loads((O / 'findings.json').read_text())\npd.set_option('display.width', 160, 'display.max_colwidth', 80)\n"
             "def t(n, k=8): return pd.read_csv(O / f'{n}.csv').head(k)"),
    ("md", "## 1. Data: 32M transfers processed with Dask\nCSV to Parquet partitioned by day; bank codes read as text; amounts converted to USD."),
    ("code", "t('ingest_log')"),
    ("code", "con = duckdb.connect()\ncon.sql(f\"SELECT count(*) AS rows, sum(is_laundering) AS laundering, min(day) AS first_day, max(day) AS last_day \"\n"
             "        f\"FROM read_parquet('{(ROOT / 'data/parquet/trans/**/*.parquet').as_posix()}', hive_partitioning=true)\").df()"),
    ("md", "## 2. Data quality: automated controls"),
    ("code", "t('controls_report', 15)[['control_id', 'name', 'status', 'detail']]"),
    ("md", "## 3. Business meaning: flows and formats"),
    ("code", "t('bm_flow_types')"),
    ("code", "t('profile_formats')[['payment_format', 'n_rows', 'laundering_rate', 'share_of_laundering']]"),
    ("md", "## 4. Rule validation: documentation vs code, precision, recall, coverage"),
    ("code", "t('doc_vs_code', 12).query('gap')[['rule_id', 'name', 'alerts_documented', 'alerts_implemented', 'alerts_in_both', 'tp_accounts_missed_by_code']]"),
    ("code", "r = t('rule_performance', 24)\nr[r.ruleset == 'implemented'][['rule_id', 'name', 'alerts', 'share_of_alerts', 'precision', 'recall', 'unique_tp_accounts']].round(4)"),
    ("code", "t('typology_coverage')"),
    ("md", "## 5. Tuning: ATL/BTL, capacity, and a false signal that must not be escalated"),
    ("code", "t('tuning_proposal_impact', 12)[['rule_id', 'action', 'alerts_now', 'alerts_after', 'tp_alerts_now', 'tp_alerts_after']]"),
    ("code", "t('capacity_weekly')[['wk', 'alert_capacity', 'alerts_implemented', 'alerts_tuned', 'load_implemented', 'load_tuned']].round(2)"),
    ("code", "t('payroll_verdict').T"),
    ("md", "## 6. New network scenario R13 (cycles, scatter-gather)"),
    ("code", "t('network_scenario_performance')"),
    ("code", "t('network_typology_coverage').round(3)"),
    ("md", "## 7. Challenger model: leakage, temporal validation, Simpson's paradox"),
    ("code", "t('model_metrics')[['version', 'validation', 'roc_auc', 'avg_precision']].round(3)"),
    ("code", "t('model_capacity')[['approach', 'alerts_per_day', 'precision', 'recall_accounts']].round(3)"),
    ("code", "t('model_simpson', 12).pivot(index='segment', columns='risk_rating', values='precision').round(3)"),
    ("md", "## 8. Recommendations\nSee `docs/recommendations_roadmap.md`: fix the 3 code gaps and the ACH feed, exclude known payroll, "
           "retune with ATL/BTL evidence, add R13, close KYC gaps, then rank the queue with the challenger score under model governance."),
    ("code", "{k: round(v, 3) if isinstance(v, float) else v for k, v in f['tuning'].items()}"),
]


def main():
    nb = nbf.v4.new_notebook()
    nb.cells = [nbf.v4.new_markdown_cell(c) if k == "md" else nbf.v4.new_code_cell(c) for k, c in cells]
    nb.metadata = {"kernelspec": {"name": "python3", "display_name": "Python 3", "language": "python"}}
    ExecutePreprocessor(timeout=600, kernel_name="python3").preprocess(nb, {"metadata": {"path": str(NB.parent)}})
    NB.parent.mkdir(exist_ok=True)
    nbf.write(nb, NB)
    print("written", NB.relative_to(ROOT), len(nb.cells), "cells")


if __name__ == "__main__":
    main()
