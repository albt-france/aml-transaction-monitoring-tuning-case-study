"""Write the engagement documents in docs/ from output/findings.json and output/*.csv.

    python src/build_docs.py

The documents are generated so that every number matches the code. The judgement in them (what to fix first, why)
is written here, next to the numbers it relies on.
"""
import json
from pathlib import Path

import pandas as pd
import yaml

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "output"
DOCS = ROOT / "docs"
SIM = ROOT / "data" / "sim"
FOOT = "\n---\n*Independent case study based on public and synthetic data · not affiliated with any bank or consultancy. " \
       "Labels: PUBLIC DATA (synthetic AML benchmark), SIMULATED (Bank N layer), ILLUSTRATIVE (country tiers).*\n"


def csv(n):
    return pd.read_csv(OUT / f"{n}.csv")


def pct(x, d=0):
    return f"{x * 100:.{d}f}%"


def n0(x):
    return f"{x:,.0f}"


def md_table(df, cols=None, fmt=None):
    fmt = fmt or {}
    cols = cols or {c: c for c in df.columns}
    out = ["| " + " | ".join(cols.values()) + " |", "|" + "---|" * len(cols)]
    for _, r in df.iterrows():
        cells = []
        for k in cols:
            v = r[k]
            cells.append("" if pd.isna(v) else (fmt[k](v) if k in fmt else str(v)))
        out.append("| " + " | ".join(c.replace("|", "/") for c in cells) + " |")
    return "\n".join(out)


def write(name, text):
    (DOCS / name).write_text(text.strip() + "\n" + FOOT, encoding="utf-8")


def main():
    f = json.loads((OUT / "findings.json").read_text(encoding="utf-8"))
    DOCS.mkdir(exist_ok=True)
    s, sd = f["system"]["implemented"], f["system"]["documented"]
    cap, tu, m = f["capacity"], f["tuning"], f["model"]
    d = f["data"]
    ctl = csv("controls_report")
    dv = f["doc_vs_code"]
    net = f["network"]["performance"]["all R13"]
    nc = f["network"]["coverage"]
    pay = f["payroll"]
    kyc = f["kyc"]
    mm = m["metrics"]
    mc = m["capacity"]
    kc = [k for k in mc if k.startswith("Challenger")][0]

    # ------------------------------------------------------------------ engagement scope
    write("engagement_scope.md", f"""
# Engagement scope: validate and tune Bank N's transaction monitoring

**Client (fictional):** Bank N, a mid-sized European bank (SIMULATED).
**Engagement type:** an anti-financial-crime data-analytics engagement: assessment, validation and optimisation of the
transaction-monitoring (TM) system. Planned duration: 2 to 3 months.

## Objectives
1. Check that the data feeding the TM system is complete and fit for purpose (automated controls).
2. Validate the 12 rules: does the code match the documentation, which typologies are covered, how precise each rule is.
3. Bring the alert volume within analyst capacity without losing detection: threshold tuning (ATL/BTL), segmentation,
   new scenario, risk-based prioritisation.
4. Hand over reusable assets: SQL and Python pipeline, controls, Power BI model, documentation.

## Data received
| Data | Status | Volume |
|---|---|---|
| Transactions: IBM "Transactions for AML" HI-Medium | PUBLIC DATA (synthetic) | {n0(d['rows_in_file'])} rows, 1-28 Sep 2022 ({d['complete_days']} complete days) |
| Account master (Entity Name dropped at ingestion) | PUBLIC DATA (synthetic) | {n0(d['accounts_in_master'])} accounts, {n0(d['entities_in_master'])} entities |
| Laundering typologies (Patterns file) | PUBLIC DATA (synthetic) | 2,756 attempts, 8 typologies |
| Bank N customers and KYC | SIMULATED | {n0(d['bank_n_customers'])} customers, {n0(d['bank_n_accounts'])} accounts |
| Rule documentation and rule code (12 rules) | SIMULATED | `data/sim/rules_documented.parquet`, `rules_implemented.parquet` |
| Alerts, analyst decisions, capacity, feed metadata | SIMULATED | {n0(s['alerts'])} alerts in 16 days |

## Out of scope
Legal interpretation of the AML framework (no legal advice); sanctions screening against named lists; model deployment.

## Plan (10 weeks, adjustable to 3 months)
| Weeks | Work | Deliverable |
|---|---|---|
| 1-2 | Data access, profiling, business meaning, automated controls | `data_quality_assessment.md`, `controls_catalogue.md`, controls report |
| 3-4 | Rule validation: documentation vs code, precision/recall, typology coverage | `scenario_inventory_and_coverage.md` |
| 5-6 | Threshold tuning (ATL/BTL), capacity, false signals | `threshold_tuning_report.md` |
| 7-8 | New network scenario, challenger model with temporal validation | `model_validation_note.md` |
| 9-10 | Client presentation, Power BI handover, roadmap, follow-up proposal | report, dashboard, `recommendations_roadmap.md`, `proposal_onepager.md` |

## Assumptions
See `assumptions.md`. Main ones: 12 analysts, 30 productive hours a week, 12 minutes median per alert; fixed FX rates
implied by the file; country risk tiers ILLUSTRATIVE.
""")

    # ------------------------------------------------------------------ data quality assessment
    impact = {
        "C01": ("Overall null rate hides the problem: only the beneficiary bank is affected.", "Keep the field check, but alert on the feed-day view (C02)."),
        "C02": ("From 9 Sep, the ACH feed delivers about 6% of rows without the beneficiary bank. Corridor logic (R07) cannot evaluate them. "
                f"{int(f['feed_defect']['laundering_rows_among_them'])} laundering rows of Bank N's book lose the field.",
                "Raise an incident with the ACH feed owner; block the load (or flag rows) when the feed-day null rate exceeds 1%; back-fill from the payment system."),
        "C03": ("Negligible: 20 exact duplicate rows.", "Deduplicate at load with a natural key (timestamp, accounts, amount, currency, format)."),
        "C04": ("None: 15 currencies and 7 formats, as expected.", "Keep as a daily gate."),
        "C05": ("None.", "Keep as a daily gate."),
        "C06": ("None: paid = received whenever the currency is the same.", "Keep: a break would reveal a fee or FX booking issue."),
        "C07": ("Feeds arrive within 3.5 h, but the source file carries a sparse tail of late rows up to 28 Sep.",
                "Monitor only complete days; reprocess late rows in a weekly catch-up run."),
        "C08": ("1 Sep has 2.3x the usual Thursday volume (a one-off batch).", "Investigate the batch with the data owner; exclude it from baselines."),
        "C09": ("1.9M self-transfers ('Reinvestment') on 1 Sep only. Counted by the R04 code, they create "
                f"{n0(f['r04']['alerts_only_because_of_self_transfers'])} rapid-movement alerts with no business meaning.",
                "Exclude self-transfers in R04, as documented; tag internal movements at source."),
        "C10": ("None: every account seen in the feed exists in the master.", "Keep weekly."),
        "C11": ("None: every currency has a USD rate.", "Keep daily; switch to official daily FX rates in production."),
        "C12": ("40% of laundering-labelled rows are not in the typology file. Coverage by typology is measured on documented attempts only.",
                "Document the label lineage; measure recall on labels (accounts) and coverage on typologies separately, as done here."),
        "C13": (f"{pct(kyc['Customers without expected activity']['share'], 1)} of customers have no expected activity: R12 cannot run for them.",
                "KYC remediation campaign; make expected activity mandatory at onboarding."),
        "C14": (f"{pct(kyc['High-risk customers with review older than 12 months']['share'], 1)} of high-risk customers are overdue for review.",
                "Prioritised review backlog; dashboard on review ageing."),
        "C15": (f"{n0(kyc['Customer records sharing one entity']['customers'])} customer records share an entity: activity and profiles are split.",
                "Entity resolution; merge duplicate records; monitor at entity level."),
    }
    rows = "\n".join(f"| {r.control_id} | {r['name']} | **{r.status}** | {r.detail} | {impact[r.control_id][0]} | {impact[r.control_id][1]} |"
                     for _, r in ctl.iterrows())
    write("data_quality_assessment.md", f"""
# Data quality assessment

{len(ctl)} automated controls (`controls/controls.yaml`, `src/controls.py`) ran on the Bank N transaction feed
({n0(d['rows_in_window'] + pay['payments'])} rows in the complete-day window: IBM PUBLIC DATA, synthetic, plus a SIMULATED feed layer) and on the
SIMULATED KYC file. Result: **{f['controls']['pass']} PASS, {f['controls']['warn']} WARN, {f['controls']['fail']} FAIL**.

| Id | Control | Status | Result | Impact on detection | Proposed fix |
|---|---|---|---|---|---|
{rows}

## Reading
- Two FAILs change what the rules see: the **ACH feed defect** (C02) blinds corridor logic, and the **day-1 self-transfer
  batch** (C09) inflates R04. Both are invisible in a global null rate (C01 only WARNs at 0.37%).
- The KYC FAILs (C13, C14) matter because two rules depend on KYC: R11 (high-risk customers) and R12 (expected activity).
- C12 is a lineage finding about the benchmark labels, kept because a real engagement would raise the same question about
  the source of its "truth" (confirmed cases, SARs).

Series behind C02: `output/null_rate_by_feed_day.csv`; full report: `output/controls_report.csv`.
""")

    # ------------------------------------------------------------------ data dictionary
    write("data_dictionary_business_meaning.md", f"""
# Data dictionary and business meaning

Source: IBM "Transactions for AML" (PUBLIC DATA, synthetic, AMLSim; licence CDLA-Sharing-1.0), as loaded by
`src/ingest_dask.py` and wrapped as the Bank N feed by `sql/00_bank_feed.sql`.

| Field (after ingestion) | Original column | Business meaning | Trap |
|---|---|---|---|
| ts | Timestamp | Booking time of the transfer (minute precision) | Format `YYYY/MM/DD HH:MM`; the file ends with a sparse tail of late rows ({n0(d['rows_in_sparse_tail'])} rows after 16 Sep) |
| day | (derived) | Booking date, Parquet partition key | The whole file falls in one month, so partitions are by day |
| from_bank / to_bank | From Bank / To Bank | Originator / beneficiary bank code | Leading zeros (`020`, `03196`): read as text, compared as integers with the account master |
| from_account / to_account | Account / Account | Originator / beneficiary account | **Two columns are both named "Account"**: renamed at read time. Never published (pseudonymous `ACC_` refs only) |
| amount_paid, payment_currency | Amount Paid, Payment Currency | What left the originator, in its currency | 15 currencies incl. Bitcoin: convert before any threshold |
| amount_received, receiving_currency | Amount Received, Receiving Currency | What the beneficiary got | Differs from paid only when currencies differ (C06 PASS) |
| amount_paid_usd / amount_received_usd | (derived) | USD equivalent | Fixed rates implied by the file's own cross-currency rows (`output/fx_rates_implied.csv`) |
| payment_format | Payment Format | Channel: ACH, Cheque, Credit Card, Cash, Wire, Bitcoin, Reinvestment | ACH carries {pct(0.8561)} of laundering rows; 'Reinvestment' appears on 1 Sep only, always as a self-transfer |
| is_laundering | Is Laundering | Benchmark label (truth for validation) | {pct(d['laundering_rate'], 2)} of rows; 40% of labelled rows are not in the typology file (C12) |
| is_self | (derived) | Same account on both sides | {n0(2559376)} rows; no business meaning for rapid-movement logic |
| entity_id | Entity ID (accounts file) | Legal or natural person owning the account | Re-hashed to `ENT_` refs; **Entity Name is dropped at ingestion** |
| bank_country | Bank Name (accounts file) | Country parsed from the bank name ("China Bank #561") | "Savings/First/National" banks have no country; "Crytpo" is a typo in the source |

## Flows in business terms (complete-day window)
{md_table(csv('bm_flow_types'), {'flow_type': 'Flow type', 'n_rows': 'Rows', 'share_rows': 'Share', 'laundering_rows': 'Laundering rows', 'share_of_laundering': 'Share of laundering'}, {'n_rows': n0, 'share_rows': lambda v: pct(v, 1), 'laundering_rows': n0, 'share_of_laundering': lambda v: pct(v, 1)})}

## Payment formats
{md_table(csv('profile_formats'), {'payment_format': 'Format', 'n_rows': 'Rows', 'share_rows': 'Share', 'laundering_rate': 'Laundering rate', 'share_of_laundering': 'Share of laundering'}, {'n_rows': n0, 'share_rows': lambda v: pct(v, 1), 'laundering_rate': lambda v: pct(v, 3), 'share_of_laundering': lambda v: pct(v, 1)})}

## Bank N tables (SIMULATED, `data/sim/`)
`customers`, `rules_documented`, `rules_implemented`, `alerts`, `dispositions`, `capacity`, `feeds`, `payroll_batch`: see
`src/simulate_bank_layer.py` for every column. Identifiers are pseudonymous (`CUS…`, `ACC_…`, `ENT_…`, `ALT…`, `AN01…AN12`).
""")

    # ------------------------------------------------------------------ scenario inventory
    doc = pd.read_parquet(SIM / "rules_documented.parquet")
    rp = csv("rule_performance")
    imp = rp[rp.ruleset == "implemented"].set_index("rule_id")
    doc["alerts"] = doc.rule_id.map(imp.alerts)
    doc["precision"] = doc.rule_id.map(imp.precision)
    doc["recall"] = doc.rule_id.map(imp.recall)
    doc["code_gap"] = doc.rule_id.map({"R02": "raw amount, no FX", "R04": "self-transfers kept", "R10": "1-day lookback"}).fillna("none")
    cov = csv("typology_coverage")
    write("scenario_inventory_and_coverage.md", f"""
# Scenario inventory and typology coverage

## The 12 rules (SIMULATED), documentation vs code, measured on IBM labels (PUBLIC DATA, synthetic)
Precision = true-positive alerts / alerts; recall = laundering accounts with a true-positive alert / {n0(s['laundering_accounts'])}
laundering accounts in Bank N's book. Base rate (account-days with laundering): {pct(s['base_rate_account_days'], 2)}.
R07 uses ILLUSTRATIVE country tiers (4 bank-country groups drawn at random, not an assessment of any country).

{md_table(doc, {'rule_id': 'Rule', 'name': 'Name', 'typology': 'Designed for', 'description': 'Documentation', 'threshold': 'Threshold', 'lookback_days': 'Lookback (days)', 'code_gap': 'Code differs?', 'alerts': 'Alerts (code)', 'precision': 'Precision', 'recall': 'Recall'}, {'threshold': lambda v: f"{v:,.0f}", 'alerts': n0, 'precision': lambda v: pct(v, 2), 'recall': lambda v: pct(v, 1)})}

**System (code as implemented):** {n0(s['alerts'])} alerts in 16 days, precision {pct(s['precision'], 2)}, recall {pct(s['recall'], 1)}.
**System (code as documented):** {n0(sd['alerts'])} alerts, precision {pct(sd['precision'], 2)}, recall {pct(sd['recall'], 1)}.

## Documentation vs code: 3 gaps
| Rule | Documented | Implemented | Effect |
|---|---|---|---|
| R02 | USD-equivalent band 8,000-9,999.99 | raw amount in the payment currency | {n0(dv['R02']['alerts_implemented'])} alerts vs {n0(dv['R02']['alerts_documented'])}; {n0(dv['R02']['alerts_in_both'])} in common. Yuan, rupee or yen amounts fall into the band by accident, while EUR or GBP amounts just below USD 10,000 fall out |
| R04 | self-transfers excluded | self-transfers counted | {n0(f['r04']['alerts_only_because_of_self_transfers'])} of {n0(f['r04']['r04_alerts_implemented'])} alerts ({pct(f['r04']['share_without_business_meaning'])}) exist only because of self-transfers, {n0(f['r04']['of_which_on_first_day'])} of them on 1 Sep |
| R10 | cash accumulated over 7 days | 1 day | {dv['R10']['tp_accounts_missed_by_code']} laundering accounts found by the documented rule are missed |

Two rules never fire on this book: R03 (20 distinct beneficiaries a day) and R08 (no conversion above USD 10,000).
A rule that never fires is either miscalibrated (R03, see the tuning report) or covers a risk the book does not have (R08): both need a decision, not silence.

## Typology coverage
An attempt is visible when one of its accounts is in Bank N's book ({n0(f['coverage']['summary']['visible_attempts'])} attempts);
it is detected when a rule raises a true-positive alert on one of those accounts during the attempt (+2 days).

{md_table(cov, {'typology': 'Typology', 'visible_attempts': 'Visible attempts', 'detected_attempts': 'Detected', 'detection_rate': 'Detection rate', 'rules_designed_for_it': 'Rules designed for it'}, {'detection_rate': lambda v: pct(v)})}

**Gaps.** No rule is designed for CYCLE or SCATTER-GATHER. Their detections are incidental (generic rules firing on the same accounts),
so they would disappear with any tuning of those rules. Fan-in and fan-out, the patterns R03 and R06 were written for,
are among the least detected. The new network scenario R13 (`sql/10_network_cycles.sql`) addresses the first gap: see `threshold_tuning_report.md`.
Full matrix: `output/typology_coverage_matrix.csv`.
""")

    # ------------------------------------------------------------------ threshold tuning
    tp = csv("tuning_proposal_impact")
    ab = csv("atl_btl_curve")
    write("threshold_tuning_report.md", f"""
# Threshold tuning report (ATL/BTL)

## Method
- **Above the line (ATL):** raise a threshold step by step (1.5x to 20x) and count the alerts removed and the laundering
  accounts lost. The cost that matters is the **unique** loss: accounts that no other rule catches.
- **Below the line (BTL):** lower the threshold (0.5x, 0.75x) and count the true positives the current setting misses.
- Truth: IBM labels (PUBLIC DATA, synthetic). Volumes: Bank N alerts (SIMULATED). Curves: `output/atl_btl_curve.csv`.
- Principle: change a threshold only where the evidence is clear; when raising a threshold costs unique detections,
  say so and pair it with a mitigation (here, the challenger score).

## ATL/BTL results (one-day rules)
{md_table(ab, {'rule_id': 'Rule', 'mult': 'x current', 'threshold': 'Threshold', 'alerts_per_week': 'Alerts / week', 'tp_accounts': 'Laundering accounts', 'precision': 'Precision', 'lost_unique_tp_accounts': 'Unique accounts lost'}, {'threshold': lambda v: f"{v:,.0f}", 'alerts_per_week': lambda v: f"{v:,.0f}", 'precision': lambda v: pct(v, 2)})}

## Recommendations per rule
{md_table(tp, {'rule_id': 'Rule', 'name': 'Name', 'action': 'Action', 'current_threshold': 'Now', 'proposed_threshold': 'Proposed', 'alerts_now': 'Alerts now', 'alerts_after': 'Alerts after', 'tp_alerts_now': 'TP alerts now', 'tp_alerts_after': 'TP alerts after', 'rationale': 'Why'}, {'current_threshold': lambda v: f"{v:,.0f}", 'proposed_threshold': lambda v: f"{v:,.0f}", 'tp_alerts_now': n0, 'tp_alerts_after': n0})}

Actions: **fix** (make the code match the documentation), **tune** (move the threshold), **retire** (stop alerting),
**exclude** (add an exclusion), **keep**.

## Overall impact (16 days)
- Alerts: {n0(tu['alerts_now'])} to {n0(tu['alerts_after'])} ({pct(tu['change_in_alerts'])}).
- Precision: {pct(tu['precision_now'], 2)} to {pct(tu['precision_after'], 2)}.
- Laundering accounts with a true-positive alert: {n0(tu['tp_accounts_now'])} to {n0(tu['tp_accounts_after'])}
  ({n0(tu['tp_accounts_lost'])} lost, {n0(tu['tp_accounts_gained'])} gained). The losses come mainly from R09 and from R04 alerts
  that hit laundering accounts by coincidence on the day-1 batch. **Rule changes alone trade some recall for capacity**:
  the network scenario and the challenger score below recover more than they lose.
- Capacity: a normal week (week 2) goes from {n0(cap['2']['alerts_implemented'])} alerts ({cap['2']['load_implemented']:.2f}x capacity) to
  {n0(cap['2']['alerts_tuned'])} ({cap['2']['load_tuned']:.2f}x). Week 1 stays above capacity ({n0(cap['1']['alerts_tuned'])} alerts)
  because 1 Sep carries 2.3x the normal volume.

## R09, the largest rule in a normal week
R09 makes {pct(f['r09_share_week2'])} of week-2 alerts. Its precision ({pct(f['rules_implemented']['R09']['precision'], 2)}) is close to the
system's, so it is not pure noise, and raising the floor above 1,000 starts losing laundering accounts that no other rule finds.
Recommendation: raise it to 5,000 (-52% of R09 alerts) **and** route the accounts it would have caught to the challenger score.
Re-test after 3 months on closed cases.

## A spike that must NOT be escalated (corporate payroll)
On Wednesday 14 Sep, corporate alerts reach {n0(pay['corporate_alerts'])} against a Tuesday-Thursday baseline of
{pay['baseline']:.0f} (+{pct(pay['spike'])}). {n0(pay['payroll_driven_alerts'])} of them come from payroll batches ({n0(pay['payments'])} salary
payments from {n0(pay['paying_accounts'])} accounts, median EUR {pay['median_salary_eur']:,.0f}) brought forward one day by a bank holiday (SIMULATED).
{pct(pay['share_known_payroll'])} are on customers whose KYC declares payroll, {pay['laundering_hits']:.0f} laundering labels, {pay['escalated']:.0f} escalations.
**Verdict:** expected activity, not a risk increase. Add a known-payroll exclusion to R05 and watch the next cycle. Do not escalate.

## New scenario R13: network patterns (`sql/10_network_cycles.sql`)
- Cycles: time-ordered loops (2 to 12 hops, each within 3.5 days, the whole loop within 7 days) that return to a Bank N account,
  each hop passing 80-115% of the previous USD amount. Scatter-gather: 3+ intermediaries passing 85-100% of the amount to the same final account within 5 days.
- Result: {net['alerts']} alerts in 16 days, precision {pct(net['precision'])}, {net['tp_accounts']} laundering accounts, {net['tp_accounts_new_vs_tuned_rules']} not found by the tuned rules.
- Coverage with the tuned rules: SCATTER-GATHER {pct(nc['SCATTER-GATHER']['tuned_rules'])} to {pct(nc['SCATTER-GATHER']['tuned_rules_plus_r13'])},
  CYCLE {pct(nc['CYCLE']['tuned_rules'])} to {pct(nc['CYCLE']['tuned_rules_plus_r13'])}.
- Limit: a bank only sees loops that start and end at its own customer in time order, so cycles remain hard. The parameters were checked
  against the typology file, so recall is optimistic: validate on fresh data before production.
""")

    # ------------------------------------------------------------------ model validation note
    sm = pd.DataFrame(m["simpson"])
    cap_rows = "\n".join(
        f"| {k} | {'' if pd.isna(v['alerts_per_day']) else round(v['alerts_per_day'])} | "
        f"{'' if pd.isna(v['precision']) else pct(v['precision'], 1)} | {v['laundering_accounts_found']:.0f} | {pct(v['recall_accounts'])} |"
        for k, v in mc.items())
    write("model_validation_note.md", f"""
# Model validation note: challenger score

## Purpose
Rank Bank N's alert queue by risk so that analysts review the most suspicious account-days first, within capacity.
The documented rules stay in place as the explainable layer; the score is a challenger, not a replacement.

## Design
- Unit: one Bank N account on one day with activity ({n0(m['base']['account_days'])} account-days; {n0(m['base']['positives'])} positives,
  base rate {pct(m['base']['base_rate'], 2)}). Label: the account sent or received a laundering-labelled transfer that day (IBM, synthetic).
- Model: scikit-learn `HistGradientBoostingClassifier` (300 iterations max, early stopping, learning rate 0.05).
- Features: that day's activity (counts, amounts, counterparties, formats, currencies, cross-bank share, round amounts, cash,
  conversions) and the 7 days before (counts, counterparties, active days, 2-day pass-through). **Not used:** KYC risk rating
  and segment (SIMULATED and partly built from the labels, they would leak).

## Leakage: the first draft
| Version | Features | Validation | ROC AUC | Average precision |
|---|---|---|---|---|
""" + "\n".join(f"| {k} | {v['features']} | {v['validation']} | {v['roc_auc']:.3f} | {v['avg_precision']:.3f} |" for k, v in mm.items()) + f"""

The first draft adds whole-period aggregates and two features built from **all** cases in the extract: whether the account was ever
escalated, and the share of its counterparties that are known bad. Both use information from after the scoring day.
Its AUC ({mm['v1 first draft']['roc_auc']:.3f}) looks excellent. **A temporal split alone does not fix it**
({mm['v1 features, temporal test']['roc_auc']:.3f}), because the leak is in the features, not in the split.
With as-of features and a temporal split (train 1-10 Sep, test 11-16 Sep), the honest AUC is
**{mm['v2 challenger']['roc_auc']:.3f}** and the average precision falls from {mm['v1 first draft']['avg_precision']:.2f} to {mm['v2 challenger']['avg_precision']:.2f}.

## Threshold set by capacity
Analysts can review {m['base']['daily_capacity']:.0f} alerts a day (12 analysts, 30 h/week, 12 min median). Each test day, the top
{m['base']['daily_capacity']:.0f} account-days by score form the queue (mean score cut-off {mc[kc]['score_threshold_mean']:.3f}).

| Approach | Alerts / day | Precision | Laundering accounts found | Share of the {n0(mc[kc]['laundering_accounts_in_test'])} in test |
|---|---|---|---|---|
""" + cap_rows + f"""

## Simpson's paradox: read precision by segment AND risk tier
{md_table(sm[sm.segment.isin(['retail', 'sme'])], {'segment': 'Segment', 'risk_rating': 'Risk tier', 'alerts': 'Alerts', 'true_positives': 'True positives', 'precision': 'Precision'}, {'precision': lambda v: pct(v, 1)})}

SME alerts look more precise than retail overall, yet SME precision is lower in every risk tier. The reason: SMEs sit mostly
in the high-risk tier, where precision is high for everyone. A segment-only report would wrongly conclude that the model works
better for SMEs. Governance reports must break precision down by risk tier.

## Top drivers (permutation importance on average precision, test set)
""" + "\n".join(f"- {r['feature']}: {r['importance']:.3f} (± {r['std']:.3f})" for r in m["importance"]) + f"""

The ACH share dominates because AMLSim generates most laundering through ACH. In real data, expect weaker and more varied drivers:
re-estimate before any use.

## Limits
- 16 days of synthetic data; the test covers 6 days. Absolute AUC is optimistic for real data; the comparisons are the message.
- Labels are benchmark labels, not confirmed cases; 40% of them have no documented typology.
- The score ranks account-days; case consolidation by customer is a next step.

## Governance
- Model card (purpose, data, features, exclusions, metrics, limits) owned by the first line, reviewed by the second line.
- Monthly drift checks: score distribution, feature shares (formats, currencies), alert-to-SAR conversion by risk tier.
- Quarterly back-test on closed cases; champion/challenger before any switch; re-validation after any change to rules or feeds.
- No feature computed after the scoring date: an automated test should check the as-of timestamp of every feature.
""")

    # ------------------------------------------------------------------ controls catalogue
    spec = yaml.safe_load((ROOT / "controls" / "controls.yaml").read_text(encoding="utf-8"))["controls"]
    cc = pd.DataFrame(spec)
    write("controls_catalogue.md", f"""
# Controls catalogue

Declared in `controls/controls.yaml`, run by `python src/controls.py`, written to `output/controls_report.csv`.
Every metric is "higher is worse": WARN above the first threshold, FAIL above the second.

{md_table(cc, {'id': 'Id', 'name': 'Control', 'object': 'Object', 'check': 'Check', 'frequency': 'Frequency', 'warn': 'WARN above', 'fail': 'FAIL above', 'owner': 'Owner'})}

## Operating model
- Daily controls run after each feed load and before the rules. A FAIL on C02, C04, C05 or C06 holds the affected feed and opens an incident.
- Weekly controls feed the KYC remediation backlog (C13-C15) and the data-engineering backlog (C10).
- The report is a table in the Power BI model (page "Data quality"), so status and trend are visible to the TM owner.
- Thresholds are starting points: review them after 3 months of history.
""")

    # ------------------------------------------------------------------ roadmap
    write("recommendations_roadmap.md", f"""
# Recommendations and 30/60/90-day roadmap

Ranked by impact on detection and workload, then by effort. Figures: 16-day measurement window.

| # | Recommendation | Impact | Effort | When | Owner |
|---|---|---|---|---|---|
| 1 | Exclude self-transfers in R04, as documented | {n0(f['r04']['alerts_only_because_of_self_transfers'])} alerts with no business meaning removed | Low | 30 days | TM engineering |
| 2 | Fix the ACH feed (beneficiary bank) and gate loads on control C02 | Corridor logic sees all ACH rows again; {int(f['feed_defect']['laundering_rows_among_them'])} laundering rows in the book regain the field | Low-Medium | 30 days | Data engineering |
| 3 | Convert R02 to USD and restore R10's 7-day lookback | Code matches documentation; R10 finds {dv['R10']['tp_accounts_missed_by_code']} more laundering accounts | Low | 30 days | TM engineering |
| 4 | Known-payroll exclusion on R05; do not escalate the 14 Sep spike | {n0(pay['payroll_driven_alerts'])} alerts in one day avoided, no risk change | Low | 30 days | TM operations |
| 5 | Retune with ATL/BTL: retire R01, R09 to 5,000, R11 to 375,000, R03 and R06 to 10 counterparties | Alerts {pct(tu['change_in_alerts'])} overall, precision x{tu['precision_after'] / tu['precision_now']:.1f}; normal week under capacity | Medium | 60 days | TM owner + 2nd line sign-off |
| 6 | Deploy R13 (cycles and scatter-gather) in shadow mode, then live | {net['alerts']} alerts in 16 days at {pct(net['precision'])} precision, {net['tp_accounts_new_vs_tuned_rules']} new laundering accounts | Medium | 60 days | TM engineering |
| 7 | Close KYC gaps: expected activity for all customers, overdue high-risk reviews, entity duplicates | R12 covers {pct(kyc['Customers without expected activity']['share'], 1)} more customers; fresher risk ratings | Medium | 90 days | KYC team |
| 8 | Challenger score to rank the queue, within capacity, with model governance | At capacity: {pct(mc[kc]['recall_accounts'])} of laundering accounts found vs {pct(mc['Tuned rules (all alerts)']['recall_accounts'])} for the tuned rules | High | 90 days | Data science + model risk |

## Sequencing
- **Day 0-30, stop the noise:** items 1-4. Low effort, no change in risk appetite, mostly code and data fixes.
- **Day 31-60, retune and extend:** items 5-6, with ATL/BTL evidence documented for the second line and a shadow run for R13.
- **Day 61-90, prioritise:** items 7-8. The score goes live only after a temporal back-test on closed cases and drift monitoring.

## What to measure every month
Alerts per week vs capacity, precision by rule and by risk tier, recall on confirmed cases, control FAIL count, KYC gap shares.
All are in the Power BI model (`docs/powerbi_measures.md`).
""")

    # ------------------------------------------------------------------ proposal
    write("proposal_onepager.md", f"""
# Proposal: follow-up engagement "TM optimisation, phase 2"

**Client:** Bank N (fictional). **Format:** one data analyst plus part-time senior oversight, remote. **Duration:** 8 weeks.

## Objective
Implement and prove the first wave of the roadmap, so that the normal-week alert volume stays under analyst capacity
without losing detection, with evidence the second line can sign off.

## Scope and deliverables
| Week | Work | Deliverable |
|---|---|---|
| 1-2 | R02/R04/R10 code fixes in a test environment; ACH feed incident follow-up; C02 load gate | Fix log, before/after alert counts |
| 3-4 | Threshold changes (R01, R03, R06, R09, R11) with ATL/BTL evidence on 3 months of production data | Tuning pack for the second line |
| 5-6 | R13 network scenario in shadow mode; alert quality review with the analysts | Shadow-run report, go/no-go |
| 7-8 | Challenger score back-test on closed cases; model card; Power BI monitoring pages in production | Model validation pack, live dashboard |

## Effort
About 40 analyst-days plus 4 days of senior review. Client time: about 6 days (TM owner, data engineer, 2 analysts for the review sessions).

## Expected outcome (based on this assessment)
Normal-week alerts from {n0(cap['2']['alerts_implemented'])} to about {n0(cap['2']['alerts_tuned'])}; precision from
{pct(tu['precision_now'], 1)} to about {pct(tu['precision_after'], 1)}; network typologies covered; a ranked queue.

## Risks and mitigations
| Risk | Mitigation |
|---|---|
| Production data behaves differently from the assessment data | Re-run every ATL/BTL test on production history before any change |
| Raising thresholds loses unique detections | Pair each raise with the score; monitor recall on confirmed cases monthly |
| Feed fixes depend on another team | Load gate on C02 first, so the defect is visible even before the fix |
| Model risk | Shadow mode, champion/challenger, model card, second-line review |

*Indicative proposal written as part of a case study; no commercial terms.*
""")

    # ------------------------------------------------------------------ regulatory context
    ecb = pd.DataFrame(f["ecb"]["rows"])
    last = ecb[ecb.period.isin(["2024-S2", "2025-S1", "2025-S2"])].pivot(index="zone_label", columns="period", values="value_eur_m").round(1).reset_index()
    arts = "\n".join(f"- Article {a['article']}: *{a['title']}*" for a in f["amlr"])
    write("regulatory_context.md", f"""
# Regulatory and market context

**No legal advice.** This note only cites texts to frame the engagement; any interpretation is for the bank's compliance and legal functions.

## Regulation (EU) 2024/1624 (AMLR)
Source: Publications Office of the EU, CELEX 32024R1624, English text (retrieved {f['ecb']['extracted_on']}).
Articles relevant to transaction monitoring, as titled in the text:
{arts}

Article 26 is the anchor for this engagement: monitoring of the business relationship and of the transactions customers perform.
Article 77 matters for the data work: what is kept, and for how long, determines what back-testing is possible.

Commission Delegated Regulation (EU) 2016/1675 (high-risk third countries) is cited for context only. Its list has been amended
many times, so **no current country list is derived from it**: the country tiers in this study are ILLUSTRATIVE.

## Payment fraud in the EU (ECB, real statistics)
Value of fraudulent credit transfers, EUR million per half-year (ECB Data Portal, dataset PAY, series
`PAY/H.<zone>.W0.CT0.1.F.N.EUR`, UNIT_MULT = 6, extracted {f['ecb']['extracted_on']}).

{md_table(last)}

Fraudulent credit transfers in the EU reached EUR {ecb[(ecb.zone == 'B0') & (ecb.period == '2025-S2')].value_eur_m.iloc[0]:,.1f} million in 2025-S2.
Spain went from {ecb[(ecb.zone == 'ES') & (ecb.period == '2024-S2')].value_eur_m.iloc[0]:.1f} to {ecb[(ecb.zone == 'ES') & (ecb.period == '2025-S2')].value_eur_m.iloc[0]:.1f}
in a year. Fraud is not money laundering, but the proceeds of payment fraud are what TM systems must then see moving.
""")

    # ------------------------------------------------------------------ data issues log
    issues = [
        ("DI-01", "Two columns named 'Account' in the transaction file", "Ingestion", "Renamed from_account / to_account at read time", "Closed"),
        ("DI-02", "Bank codes with leading zeros ('020', '03196')", "Ingestion", "Read as text; compared as integers with the account master", "Closed"),
        ("DI-03", "Amounts in 15 currencies incl. Bitcoin", "Rules", "Fixed USD rates implied by the file; ECB daily rates in production", "Closed (study)"),
        ("DI-04", f"Sparse tail: {n0(d['rows_in_sparse_tail'])} rows from 17 to 28 Sep", "Freshness", "Complete-day window 1-16 Sep; C07 reports the tail", "Closed"),
        ("DI-05", "1.9M 'Reinvestment' self-transfers on 1 Sep only", "Volume / R04", "C08, C09 flag it; R04 fix excludes self-transfers", "Open: fix in 30 days"),
        ("DI-06", "ACH feed loses the beneficiary bank on ~6% of rows from 9 Sep (SIMULATED)", "Completeness / R07", "C02 FAIL; incident and load gate", "Open: owner data engineering"),
        ("DI-07", "40% of labelled rows not in the typology file", "Label lineage", "Recall measured on labels, coverage on documented attempts", "Accepted (documented)"),
        ("DI-08", "20 exact duplicate rows", "Uniqueness", "C03 WARN; deduplicate at load", "Open: low"),
        ("DI-09", f"{pct(kyc['Customers without expected activity']['share'], 1)} of customers without expected activity (SIMULATED)", "KYC / R12", "C13 FAIL; remediation", "Open"),
        ("DI-10", f"{pct(kyc['High-risk customers with review older than 12 months']['share'], 1)} of high-risk customers overdue for review (SIMULATED)", "KYC", "C14 FAIL; review backlog", "Open"),
        ("DI-11", f"{n0(kyc['Customer records sharing one entity']['customers'])} customer records share an entity (SIMULATED)", "KYC / entity", "C15 WARN; entity resolution", "Open"),
        ("DI-12", "Entity names present in the account master", "Privacy", "Column dropped at ingestion; never stored", "Closed"),
        ("DI-13", "Bank names carry the country ('China Bank #561'); 'Crytpo' typo; 3 generic names without country", "Reference data", "Parsed; generic names = 'Unspecified'", "Closed"),
    ]
    write("data_issues_log.md", """
# Data issues log

| Id | Issue | Area | Action | Status |
|---|---|---|---|---|
""" + "\n".join(f"| {a} | {b} | {c} | {e} | {g} |" for a, b, c, e, g in issues))

    # ------------------------------------------------------------------ assumptions
    ing = f["ingest"]
    write("assumptions.md", f"""
# Assumptions

## Data (PUBLIC DATA, synthetic)
- IBM "Transactions for AML" HI-Medium is synthetic (AMLSim). It is never presented as real bank data.
- Analysis window: the {d['complete_days']} complete days (1-16 Sep 2022), i.e. days with at least 20% of the median daily volume.
- FX: one fixed USD rate per currency, the mean of `amount_received / amount_paid` on rows paid in that currency and received in
  US Dollar (AMLSim uses fixed rates; the IBM dates are fictitious, so ECB rates of 2022 would not match). Rates: `output/fx_rates_implied.csv`.
- Amount thresholds are set on this file's distribution (1% of transfers exceed USD 2.8M). Read them as positions in this
  dataset, not as real-world calibrations.

## Bank N (SIMULATED, seed 42)
- Book: entities whose md5(Entity ID) falls in a 4% bucket, minus entities with any transfer above USD 1M in the window
  (institutional-scale flows, outside a mid-sized retail/SME bank). Result: {n0(d['bank_n_customers'])} customers, {n0(d['bank_n_accounts'])} accounts.
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
- Dask, HI-Medium (3.0 GB CSV to Parquet): {ing['dask_medium']['seconds']} s, peak memory {ing['dask_medium']['peak_rss_gb']} GB, {ing['dask_medium']['cores']} cores, {ing['dask_medium']['ram_gb']} GB RAM.
- HI-Small (0.5 GB): Dask {ing['dask_small']['seconds']} s, DuckDB {ing['duckdb_small']['seconds']} s.
""")
    print("docs written:", sorted(p.name for p in DOCS.glob("*.md")))


if __name__ == "__main__":
    main()
