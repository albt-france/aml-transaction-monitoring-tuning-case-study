"""Build the 7-page client report: charts (src/charts.py) -> HTML (16:9 pages) -> PDF with headless Edge, empty metadata.

Every number comes from output/findings.json (src/findings.py), so the report matches the code.
    python src/build_pdf.py
Output: site/report/aml_tm_assessment.pdf (the HTML draft goes to build/, which is not published)
"""
import json
import shutil
import subprocess
import tempfile
import time
from pathlib import Path

from pypdf import PdfReader, PdfWriter

import charts

ROOT = Path(__file__).resolve().parents[1]
BUILD = ROOT / "build"
PDF = ROOT / "site" / "report" / "aml_tm_assessment.pdf"
FOOT = "Independent case study based on public and synthetic data · not affiliated with any bank or consultancy"
AI_NOTE = ("AI-assisted workflow: I used Claude, mainly to write scripts faster. I drove the project: I defined the "
           "questions, chose and validated the data sources, made the analytical decisions and checked every result.")
N_PAGES = 7


def pct(x, d=0):
    return f"{x * 100:.{d}f}%"


def n0(x):
    return f"{x:,.0f}"


def page(n, title, subtitle, tags, body, sources):
    t = "".join(f'<div class="tag tag-{x.lower().split()[0]}">{x}</div>' for x in tags)
    return f"""
<section class="page">
  <header><div><h1>{title}</h1><p class="sub">{subtitle}</p></div><div class="tags">{t}</div></header>
  <main>{body}</main>
  <footer><span>{sources}</span><span>{FOOT}</span><span>{n} / {N_PAGES - 1}</span></footer>
</section>"""


def card(inner, cls="", tag=None):
    tg = f'<span class="ctag ctag-{tag.lower().split()[0]}">{tag}</span>' if tag else ""
    return f'<div class="card {cls}">{tg}{inner}</div>'


def img(name, tag, cap=""):
    return card(f'<figure><img src="../docs/img/{name}.png"/>{f"<figcaption>{cap}</figcaption>" if cap else ""}</figure>', "fig", tag)


def tile(label, value, text, tag):
    return card(f'<div class="label">{label}</div><div class="big">{value}</div><p>{text}</p>', "tile", tag)


def facts(f):
    s, cap, tu, m = f["system"]["implemented"], f["capacity"], f["tuning"], f["model"]
    g = {
        "rows": f["data"]["rows_in_file"], "days": f["data"]["complete_days"], "tail": f["data"]["rows_in_sparse_tail"],
        "cust": f["data"]["bank_n_customers"], "acc": f["data"]["bank_n_accounts"], "lacc": s["laundering_accounts"],
        "alerts": s["alerts"], "prec": s["precision"], "recall": s["recall"], "base": s["base_rate_account_days"],
        "w1": cap["1"]["alerts_implemented"], "w2": cap["2"]["alerts_implemented"], "capw": cap["2"]["alert_capacity"],
        "w2t": cap["2"]["alerts_tuned"], "cov": f["coverage"]["summary"]["coverage"],
        "vis": f["coverage"]["summary"]["visible_attempts"], "fail": f["controls"]["fail"], "nctl": f["controls"]["n"],
        "tu_change": tu["change_in_alerts"], "tu_prec": tu["precision_after"], "tu_tp_now": tu["tp_accounts_now"],
        "tu_tp_after": tu["tp_accounts_after"], "r04": f["r04"]["share_without_business_meaning"],
        "r09": f["r09_share_week2"], "r09p": f["rules_implemented"]["R09"]["precision"],
        "auc_leak": m["metrics"]["v1 first draft"]["roc_auc"], "auc_ok": m["metrics"]["v2 challenger"]["roc_auc"],
        "ap_leak": m["metrics"]["v1 first draft"]["avg_precision"], "ap_ok": m["metrics"]["v2 challenger"]["avg_precision"],
        "auc_leak_t": m["metrics"]["v1 features, temporal test"]["roc_auc"],
    }
    mc = m["capacity"]
    k = [x for x in mc if x.startswith("Challenger")][0]
    g.update({"m_prec": mc[k]["precision"], "m_rec": mc[k]["recall_accounts"], "r_prec": mc["Tuned rules (all alerts)"]["precision"],
              "r_rec": mc["Tuned rules (all alerts)"]["recall_accounts"], "u_rec": mc["Tuned rules + challenger (union)"]["recall_accounts"],
              "cap_day": m["base"]["daily_capacity"]})
    net = f["network"]["performance"]["all R13"]
    g.update({"r13_alerts": net["alerts"], "r13_prec": net["precision"], "r13_tp": net["tp_accounts"],
              "r13_new": net["tp_accounts_new_vs_tuned_rules"]})
    nc = f["network"]["coverage"]
    g.update({"sg_now": nc["SCATTER-GATHER"]["rules_now"], "sg_after": nc["SCATTER-GATHER"]["tuned_rules_plus_r13"],
              "cy_now": nc["CYCLE"]["rules_now"], "cy_after": nc["CYCLE"]["tuned_rules_plus_r13"]})
    p = f["payroll"]
    g.update({"pay_spike": p["spike"], "pay_alerts": p["payroll_driven_alerts"], "pay_known": p["share_known_payroll"],
              "pay_esc": p["escalated"], "pay_hits": p["laundering_hits"]})
    ecb = {(r["zone"], r["period"]): r["value_eur_m"] for r in f["ecb"]["rows"]}
    g.update({"eu": ecb[("B0", "2025-S2")], "es0": ecb[("ES", "2024-S2")], "es1": ecb[("ES", "2025-S2")],
              "ecb_date": f["ecb"]["extracted_on"]})
    ing = f["ingest"]
    g.update({"dask_s": ing["dask_medium"]["seconds"], "dask_gb": ing["dask_medium"]["peak_rss_gb"],
              "dsm_s": ing["dask_small"]["seconds"], "ddb_s": ing["duckdb_small"]["seconds"]})
    dv = f["doc_vs_code"]
    g.update({"r02_doc": dv["R02"]["alerts_documented"], "r02_imp": dv["R02"]["alerts_implemented"],
              "r02_both": dv["R02"]["alerts_in_both"], "r02_miss": dv["R02"]["tp_accounts_missed_by_code"],
              "r10_miss": dv["R10"]["tp_accounts_missed_by_code"], "r10_doc_tp": dv["R10"]["tp_documented"],
              "r10_imp_tp": dv["R10"]["tp_implemented"]})
    kyc = f["kyc"]
    g.update({"kyc_miss": kyc["Customers without expected activity"]["share"],
              "kyc_over": kyc["High-risk customers with review older than 12 months"]["share"],
              "kyc_dup": kyc["Customer records sharing one entity"]["customers"]})
    fd = f["controls"]["detail"]
    g.update({"c02": fd["C02"]["detail"], "c09": fd["C09"]["detail"], "c12": fd["C12"]["metric"]})
    sm = {(r["segment"], r["risk_rating"]): r["precision"] for r in m["simpson"]}
    tr = f["tuning_rules"]
    g["fix_removed"] = sum(tr[r]["alerts_now"] - tr[r]["alerts_after"] for r in ("R02", "R04", "R10"))
    g.update({"sim": sm})
    return g


def p0(f, g):
    qs = f"""<ol class="qs">
<li><b>Can we trust the data?</b> Not fully: {g['fail']} of {g['nctl']} automated controls fail. The ACH feed loses the beneficiary bank on 6% of rows from 9 Sep, a 1.9M self-transfer batch doubles day 1, and 4% of customers have no expected activity.</li>
<li><b>Does the code do what the documentation says?</b> Not for 3 of 12 rules: structuring ignores currency conversion, rapid movement counts self-transfers, and cash accumulation looks back 1 day instead of 7.</li>
<li><b>Does the system see the right patterns?</b> It detects {pct(g['cov'])} of the laundering attempts Bank N can see. No rule targets cycles or scatter-gather.</li>
<li><b>Can the analysts keep up?</b> No: {n0(g['w2'])} alerts in a normal week for a capacity of {n0(g['capw'])} ({g['w2'] / g['capw']:.1f}x), and {n0(g['w1'])} in week 1.</li>
<li><b>What comes first?</b> Fix the code and the feed, retune 5 thresholds (-{pct(-g['tu_change'])} alerts), add a network scenario, and rank the queue with a validated score.</li></ol>"""
    recs = f"""<ol class="reco">
<li><b>Fix the 3 code gaps and the ACH feed</b> (owners: TM engineering, data engineering). This removes {n0(g['fix_removed'])} alerts with no business meaning, and R10 finds laundering accounts again.</li>
<li><b>Retune with ATL/BTL evidence</b>: retire R01, raise R09 and R11, lower R03 and R06. Alerts fall by {pct(-g['tu_change'])} and precision goes from {pct(g['prec'], 1)} to {pct(g['tu_prec'], 1)}.</li>
<li><b>Add R13, a network scenario</b> (cycles and scatter-gather): {g['r13_alerts']} alerts with {pct(g['r13_prec'])} precision, {g['r13_new']} new laundering accounts.</li>
<li><b>Rank the queue with the challenger score</b>, within capacity: {pct(g['m_rec'])} of laundering accounts found, against {pct(g['r_rec'])} for the tuned rules.</li>
<li><b>Close the KYC gaps</b> (missing profiles, overdue high-risk reviews), and do not escalate known payroll spikes.</li></ol>"""
    body = f"""
<div class="grid4 auto">
{tile("ALERTS IN A NORMAL WEEK", n0(g['w2']), f"vs capacity {n0(g['capw'])} (12 analysts); {n0(g['w2t'])} after the proposals", "SIMULATED")}
{tile("PRECISION OF ALERTS", pct(g['prec'], 1), f"base rate {pct(g['base'], 1)}; recall {pct(g['recall'])} of {n0(g['lacc'])} laundering accounts", "SIMULATED")}
{tile("TYPOLOGY COVERAGE", pct(g['cov']), f"of {n0(g['vis'])} visible laundering attempts; 2 of 8 typologies have no rule", "PUBLIC DATA")}
{tile("CONTROLS FAILING", f"{g['fail']} / {g['nctl']}", "automated data and KYC controls (PASS / WARN / FAIL)", "SIMULATED")}
</div>
<div class="g0">
{card('<h2>Five questions, five answers</h2>' + qs)}
{card('<h2>Recommendations, in order</h2>' + recs + f'<p class="note"><b>Method in 3 lines.</b> {g["rows"] / 1e6:.1f}M synthetic transactions (IBM AML benchmark) processed with Dask and DuckDB. A simulated bank layer (customers, 12 rules, alerts, analyst decisions) sits on top. Every rule is scored against the benchmark labels and every model is validated in time.</p>')}
</div>"""
    return page(0, "Bank N's monitoring generates 1.6x more alerts than its analysts can review, and sees 15% of laundering attempts: fix, retune, then prioritise",
                "Executive summary · transaction-monitoring assessment for Bank N (a fictional mid-sized European bank)",
                ["OVERVIEW"], body, "Sources: IBM Transactions for AML (synthetic, CDLA-Sharing-1.0); Bank N layer SIMULATED; ECB")


def p1(f, g):
    missions = [("Evaluate, validate, optimise detection", "Rule validation, ATL/BTL tuning, R13, challenger"),
                ("Analyse customer and transaction data", "32M-row profile, Bank N book"),
                ("Business meaning of the data", "Data dictionary, flow types, formats"),
                ("Data quality and gaps", "15 automated controls, data issues log"),
                ("Improve customer monitoring", "8-point roadmap (30/60/90 days)"),
                ("Present to the client", "This report, 5-tab dashboard"),
                ("SQL and Python pipelines and controls", "Dask ingest, DuckDB SQL 01-10, tests"),
                ("New visualisations (Power BI)", "PBIP project, TMDL model, 5 pages"),
                ("Help prepare proposals", "Follow-up proposal one-pager")]
    rows = "".join(f"<tr><td>{a}</td><td>{b}</td></tr>" for a, b in missions)
    flow = "".join(f'<div class="step">{s}</div>' for s in ["CSV 3.0 GB", "Dask read (text codes)", "rename + FX to USD",
                                                             "Parquet by day", "DuckDB SQL", "controls + tests"])
    body = f"""
<div class="grid-1-1-1">
{card('<h2>The 9 engagement tasks and what this study delivers</h2><table class="small"><tr><th>Task</th><th>Deliverable</th></tr>' + rows + '</table>')}
{img("ecb_fraud", "PUBLIC DATA", f"ECB Data Portal, series PAY/H.(B0|FR|ES).W0.CT0.1.F.N.EUR, EUR million (UNIT_MULT 6), extracted {g['ecb_date']}. EU {n0(g['eu'])}M in 2025-S2; Spain {g['es0']:.0f}M to {g['es1']:.0f}M in a year.")}
{img("daily_volume", "PUBLIC DATA", f"{g['rows']:,} rows; {g['days']} complete days kept (1-16 Sep 2022); {n0(g['tail'])} late rows excluded.")}
</div>
<div class="grid2">
{card(f'''<h2>The data: synthetic, labelled, large</h2><ul class="facts">
<li>IBM "Transactions for AML" HI-Medium, generated by AMLSim: <b>{g['rows'] / 1e6:.1f}M transfers</b>, 2.1M accounts, labels (Is Laundering) and a file of 8 laundering typologies. <b>Synthetic: not real bank data.</b></li>
<li>Bank N's book (SIMULATED): {n0(g['cust'])} customers and {n0(g['acc'])} accounts (a 4% sample of IBM entities, without institutional-scale flows). {n0(f['data']['bank_n_rows'])} transfers touch the book.</li>
<li>On top of it, everything a real engagement would receive: KYC file, 12 documented rules and their code, alerts, analyst decisions, capacity and feed metadata.</li></ul>''', tag="PUBLIC DATA")}
{card(f'''<h2>The pipeline: Dask for volume, DuckDB for analysis</h2><div class="flow">{flow}</div><ul class="facts">
<li>Dask converts the 3.0 GB CSV in <b>{g['dask_s']:.0f} s</b> with a <b>{g['dask_gb']:.1f} GB</b> memory peak (12 cores, 16 GB laptop). Parquet row count = CSV row count (asserted).</li>
<li>On the 0.5 GB HI-Small file, DuckDB does the same conversion in {g['ddb_s']:.1f} s against {g['dsm_s']:.0f} s for Dask. Dask is kept for files that outgrow one machine; the same code runs on a cluster.</li>
<li>Traps handled: bank codes with leading zeros read as text, two columns both named "Account", amounts in 15 currencies converted with fixed rates implied by the file.</li></ul>''', tag="PUBLIC DATA")}
</div>"""
    return page(1, "The engagement: validate and tune Bank N's transaction monitoring on 32 million transfers, in a context of rising payment fraud",
                "The engagement and the data", ["PUBLIC DATA", "SIMULATED"], body,
                "Sources: IBM AML (Hugging Face mirror OsamaMIT/IBM-AML-HI); ECB Data Portal; Bank N layer SIMULATED")


def p2(f, g):
    c = f["controls"]["detail"]
    sel = ["C02", "C09", "C12", "C13", "C14", "C08", "C03", "C06"]
    rows = "".join(f'<tr><td>{k}</td><td><span class="st st-{c[k]["status"].lower()}">{c[k]["status"]}</span></td><td>{c[k]["detail"]}</td></tr>' for k in sel)
    body = f"""
<div class="grid3">
{img("feed_nulls", "SIMULATED", "Control C02 flags it on the first day. Directly lost to R07: 24 laundering rows lose their beneficiary bank, and any corridor rule is blind on them.")}
{img("self_transfers", "PUBLIC DATA", "Day 1 carries a one-off 'Reinvestment' batch, 45% of the day's rows. The R04 code does not exclude it (see next page).")}
{card(f'''<h2>KYC gaps that blind specific rules</h2><ul class="facts">
<li><b>{pct(g['kyc_miss'], 1)}</b> of customers have no expected activity: R12 (profile breach) cannot run for them, and {int(f['kyc_impact']['laundering_customers_without_profile'])} laundering customers are among them.</li>
<li><b>{pct(g['kyc_over'], 1)}</b> of high-risk customers were last reviewed more than 12 months ago.</li>
<li><b>{g['kyc_dup']}</b> customer records share an entity with another record (duplicate onboarding), which splits activity and limits.</li>
<li>{pct(g['c12'])} of the rows labelled as laundering are not listed in the typology file, so coverage by typology is measured on documented attempts only.</li></ul>''', tag="SIMULATED")}
</div>
<div class="grid1">
{card('<h2>Automated controls (controls/controls.yaml): the 8 that matter, of 15</h2><table class="small"><tr><th>Id</th><th>Status</th><th>Result</th></tr>' + rows + '</table>')}
</div>"""
    return page(2, f"Can we trust the data? Mostly, but {g['fail']} of {g['nctl']} controls fail: a feed that loses the counterparty bank, a day-1 batch and KYC gaps",
                "Data quality: automated controls, lineage and business meaning", ["PUBLIC DATA", "SIMULATED"], body,
                "Sources: Bank N feed = IBM AML (synthetic) + SIMULATED feed layer; controls in src/controls.py")


def p3(f, g):
    dv = f["doc_vs_code"]
    rows = f"""<tr><td>R02 structuring</td><td>USD-equivalent band 8,000-9,999.99</td><td>raw amount, no FX conversion</td><td>{n0(g['r02_imp'])} alerts vs {n0(g['r02_doc'])} documented; only {n0(g['r02_both'])} in common; {g['r02_miss']} documented laundering accounts missed</td></tr>
<tr><td>R04 rapid movement</td><td>self-transfers excluded</td><td>self-transfers counted</td><td>{pct(g['r04'])} of R04 alerts ({n0(f['r04']['alerts_only_because_of_self_transfers'])}) exist only because of self-transfers</td></tr>
<tr><td>R10 cash</td><td>7-day accumulation</td><td>1 day</td><td>{g['r10_miss']} laundering accounts found by the documented rule are missed ({g['r10_doc_tp']:.0f} vs {g['r10_imp_tp']:.0f} true-positive alerts)</td></tr>"""
    body = f"""
<div class="grid1 auto">
{card('<h2>Documentation against code: 3 of 12 rules do something else</h2><table class="small"><tr><th>Rule</th><th>Documentation says</th><th>Code does</th><th>Measured effect (both versions run on the same data)</th></tr>' + rows + '</table>', tag="SIMULATED")}
</div>
<div class="grid2">
{img("rule_perf", "SIMULATED", f"R04 and R09 produce most of the volume. Overall precision is {pct(g['prec'], 1)} against a base rate of {pct(g['base'], 1)}. R03 and R08 never fire.")}
{img("coverage_matrix", "PUBLIC DATA", f"{pct(g['cov'])} of {n0(g['vis'])} visible attempts are detected, mostly by generic rules. CYCLE and SCATTER-GATHER hits are incidental: no rule is designed for them.")}
</div>"""
    return page(3, f"Does the system see the right patterns? It catches {pct(g['recall'])} of laundering accounts, 3 rules do not match their documentation, and 2 typologies have no rule",
                "Rule validation: documentation vs code, precision and recall per rule, typology coverage (R07 country tiers are ILLUSTRATIVE)", ["PUBLIC DATA", "SIMULATED", "ILLUSTRATIVE"], body,
                "Truth = IBM labels (Is Laundering) and Patterns file; rules and alerts SIMULATED; sql/03-05")


def p4(f, g):
    body = f"""
<div class="grid2">
{img("atl_btl", "SIMULATED", "Above the line: raising R09 above 1,000 starts losing laundering accounts that no other rule finds, so the floor goes to 5,000 and the score recovers the misses. Below the line: lowering R03 and R06 to 10 counterparties finds laundering at 15-25x the base rate.")}
{img("capacity", "SIMULATED", f"Normal week: {n0(g['w2'])} alerts become {n0(g['w2t'])}, under the capacity of {n0(g['capw'])}. Week 1 stays high because of day-1 volume (log scale).")}
</div>
<div class="grid2">
{img("payroll", "SIMULATED", f"+{pct(g['pay_spike'])} corporate alerts on Wed 14 Sep: {g['pay_alerts']} come from payroll batches brought forward by a bank holiday, {pct(g['pay_known'])} on customers whose KYC declares payroll. 0 laundering labels, 0 escalations. Verdict: expected activity, not a risk increase. Add a known-payroll exclusion and watch the next cycle.")}
{img("network", "PUBLIC DATA", f"R13 (new): {g['r13_alerts']} alerts in 16 days, {pct(g['r13_prec'])} precision, {g['r13_new']} laundering accounts the tuned rules miss. Scatter-gather detection: {pct(g['sg_now'])} to {pct(g['sg_after'])}. Cycles move little ({pct(g['cy_now'])} to {pct(g['cy_after'])}), because a bank only sees loops that start at its own customer.")}
</div>"""
    return page(4, f"Fewer, better alerts: {pct(-g['tu_change'])} fewer alerts and {g['tu_prec'] / g['prec']:.1f}x the precision, a payroll spike that must not be escalated, and a network scenario",
                "Tuning: ATL/BTL tests, capacity, false signal, new scenario", ["SIMULATED", "PUBLIC DATA"], body,
                f"Tuned scenario = documented code + 5 threshold moves + payroll exclusion; laundering accounts with an alert: {g['tu_tp_now']:.0f} before, {g['tu_tp_after']:.0f} after the rule changes alone; sql/06-10")


def p5(f, g):
    s = g["sim"]
    imp = f["model"]["importance"][:5]
    il = ", ".join(f"{r['feature']} ({r['importance']:.2f})" for r in imp)
    body = f"""
<div class="grid3">
{img("model_auc", "SIMULATED", f"The first draft scores AUC {g['auc_leak']:.3f}. It uses a 'known bad counterparty' share and case outcomes built from all cases, including later ones. A temporal split alone does not fix it ({g['auc_leak_t']:.3f}). With as-of features only, the AUC is {g['auc_ok']:.3f}.")}
{img("pr_curve", "SIMULATED", f"Average precision {g['ap_ok']:.2f} for the honest model vs {g['ap_leak']:.2f} for the leaky one: the leak would have overstated the useful signal by {g['ap_leak'] / g['ap_ok']:.1f}x.")}
{img("model_capacity", "SIMULATED", f"Threshold set by capacity: the top {g['cap_day']:.0f} account-days each day. Precision {pct(g['m_prec'], 1)} vs {pct(g['r_prec'], 1)} for the tuned rules.")}
</div>
<div class="grid2">
{img("simpson", "SIMULATED", f"Simpson's paradox: SME {pct(s[('sme', 'all')])} vs retail {pct(s[('retail', 'all')])} overall, but lower in every risk tier, because SMEs sit mostly in the high-risk tier. Report precision by segment and risk tier, never by segment alone.")}
{card(f'''<h2>How the challenger was validated, and how it should be governed</h2><ul class="facts">
<li><b>Design.</b> Gradient boosting on one row per account and day. Features: that day plus the 7 days before. Trained on 1-10 Sep, tested on 11-16 Sep. KYC risk rating and segment are not inputs: they are simulated and partly built from the labels.</li>
<li><b>Use.</b> The score <b>ranks</b> the queue; the rules stay as the documented, explainable layer. Union of both: {pct(g['u_rec'])} of laundering accounts in the test days.</li>
<li><b>Top drivers</b> (permutation importance, average precision): {il}. The ACH share reflects how AMLSim generates laundering; real data will have weaker, more varied drivers.</li>
<li><b>Governance.</b> Monthly drift check on score distribution and feature shares, quarterly back-test on closed cases, champion/challenger before any switch, and a model card for the second line.</li></ul>''', tag="SIMULATED")}
</div>"""
    return page(5, f"A challenger model, validated honestly: AUC {g['auc_ok']:.2f} (not {g['auc_leak']:.2f}), and at analyst capacity it finds {pct(g['m_rec'])} of laundering accounts vs {pct(g['r_rec'])}",
                "Model validation: leakage, temporal validation, Simpson's paradox, threshold set by capacity", ["SIMULATED"], body,
                "Labels: IBM AML (synthetic); segments, ratings and capacity SIMULATED; src/challenger_model.py")


def p6(f, g):
    arts = ", ".join(f"Art. {a['article']} ({a['title'].split(' of the business')[0]})" for a in f["amlr"] if a["article"] in (20, 26, 69, 77))
    body = f"""
<div class="grid3">
{card(f'''<h2>Sources and licences</h2><ul class="facts">
<li><b>IBM Transactions for Anti Money Laundering</b> (Altman et al., NeurIPS 2023), HI-Medium and HI-Small, Hugging Face mirror OsamaMIT/IBM-AML-HI. Licence <b>CDLA-Sharing-1.0</b>. Synthetic data generated by AMLSim, labelled PUBLIC DATA (synthetic AML benchmark).</li>
<li><b>ECB Data Portal</b>, payment statistics PAY, fraudulent credit transfers. Series keys PAY/H.B0|U2|ES|FR.W0.CT0.1.F.N.EUR, extracted {g['ecb_date']}.</li>
<li><b>Regulation (EU) 2024/1624</b> (AMLR), Publications Office, CELEX 32024R1624. Cited: {arts}. Delegated Regulation (EU) 2016/1675 is cited only for context. <b>No legal advice.</b></li></ul>''')}
{card(f'''<h2>What is real, simulated or illustrative</h2><ul class="facts">
<li><b>PUBLIC DATA (synthetic)</b>: transfers, labels, typologies, account master. Not real bank transactions.</li>
<li><b>SIMULATED</b> (seed 42): Bank N, its customers and KYC, the 12 rules and their code, alerts, analyst decisions, capacity (12 analysts, 30 h/week, 12 min median per alert), the ACH feed defect and the payroll batches. Customer risk ratings and segments are partly built from the labels.</li>
<li><b>ILLUSTRATIVE</b>: country risk tiers (4 bank-country groups drawn at random). They are not an assessment of any country.</li>
<li>Identifiers are pseudonymous (CUS…, ACC_…, ENT_…). Entity names were dropped at ingestion. No account number is published, and no published group has fewer than 5 accounts.</li></ul>''')}
{card(f'''<h2>Limits</h2><ul class="facts">
<li>16 days of data: weekly views have 2 full weeks; the model test covers 6 days.</li>
<li>AMLSim laundering is easier to separate (ACH-heavy) than real laundering, so the absolute AUC is optimistic. The comparisons (leaky vs honest, rules vs score) are the message.</li>
<li>R13's parameters were checked against the typology file, so its recall is optimistic. Validate it on fresh data before production.</li>
<li>Amounts use fixed FX rates implied by the file (AMLSim uses fixed rates).</li>
<li>Bank N sees the whole synthetic market; a real bank sees only its own side of each transfer.</li></ul>''')}
</div>
<div class="grid2 auto">
{card(f'''<h2>Reproduce</h2><pre>python src/ingest_dask.py --size medium   (or small)
python src/simulate_bank_layer.py
python src/controls.py
python src/run_sql.py
python src/challenger_model.py
python src/fetch_public.py
python src/findings.py
python src/build_dashboard.py
python src/build_pdf.py</pre>''')}
{card(f'<h2>AI note</h2><p>{AI_NOTE}</p><p class="note">No large language model is called anywhere in the analysis.</p>')}
</div>"""
    return page(6, "Methods, limits and AI note", "How the study was built, what is real, and what it does not claim",
                ["OVERVIEW"], body, "Repository: aml-transaction-monitoring-tuning-case-study")


CSS = (Path(__file__).with_name("report.css")).read_text(encoding="utf-8")


def build_html() -> Path:
    charts.build_all()
    f = json.loads((ROOT / "output" / "findings.json").read_text(encoding="utf-8"))
    g = facts(f)
    html = f"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<title>Transaction-monitoring assessment</title><style>{CSS}</style></head><body>
{''.join(p(f, g) for p in [p0, p1, p2, p3, p4, p5, p6])}
</body></html>"""
    BUILD.mkdir(exist_ok=True)
    out = BUILD / "report.html"
    out.write_text(html, encoding="utf-8")
    return out


def find_browser() -> str:
    for c in [r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe", r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
              r"C:\Program Files\Google\Chrome\Application\chrome.exe", shutil.which("msedge") or "",
              shutil.which("google-chrome") or "", shutil.which("chromium") or ""]:
        if c and Path(c).exists():
            return c
    raise FileNotFoundError("Edge or Chrome is needed to print the PDF")


def print_pdf(html: Path) -> Path:
    PDF.parent.mkdir(parents=True, exist_ok=True)
    tmp = BUILD / "_print.pdf"
    profile = tempfile.mkdtemp()
    subprocess.run([find_browser(), "--headless=new", "--disable-gpu", "--no-pdf-header-footer", f"--user-data-dir={profile}",
                    "--run-all-compositor-stages-before-draw", "--virtual-time-budget=5000",
                    f"--print-to-pdf={tmp}", html.as_uri()], check=True, timeout=180)
    last = -1
    for _ in range(120):
        time.sleep(1)
        size = tmp.stat().st_size if tmp.exists() else -1
        if size > 0 and size == last:
            break
        last = size
    shutil.rmtree(profile, ignore_errors=True)
    reader, writer = PdfReader(str(tmp)), PdfWriter()
    for pg in reader.pages:
        writer.add_page(pg)
    writer.add_metadata({"/Title": "Transaction-monitoring assessment (case study)", "/Author": "", "/Creator": "", "/Producer": ""})
    with open(PDF, "wb") as fh:
        writer.write(fh)
    tmp.unlink()
    return PDF


def main():
    pdf = print_pdf(build_html())
    print("written", pdf.relative_to(ROOT), len(PdfReader(str(pdf)).pages), "pages")


if __name__ == "__main__":
    main()
