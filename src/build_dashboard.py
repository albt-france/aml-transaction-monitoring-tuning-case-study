"""Self-contained HTML dashboard with Plotly (5 tabs), built from output/*.csv and output/findings.json.

    python src/build_dashboard.py
Output: site/dashboard/index.html (plotly.js is embedded: the file works offline and on GitHub Pages)
Every chart carries its data label: PUBLIC DATA (synthetic), SIMULATED or ILLUSTRATIVE.
"""
import json
from pathlib import Path

import pandas as pd
import plotly.graph_objects as go
from plotly.offline import get_plotlyjs
from plotly.subplots import make_subplots

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "output"
PUB = ROOT / "data" / "public"
DEST = ROOT / "site" / "dashboard" / "index.html"
BLUE, GREY, RED, ORANGE, AQUA, LIGHT, INK, MUTED = "#2A78D6", "#A3A19A", "#D03B3B", "#EB6834", "#1BAF7A", "#C9DDF5", "#0B0B0B", "#52514E"
FOOT = "Independent case study based on public and synthetic data · not affiliated with any bank or consultancy"
TAGS = {"PUBLIC DATA": "pub", "SIMULATED": "sim", "ILLUSTRATIVE": "ill"}


def csv(n):
    return pd.read_csv(OUT / f"{n}.csv")


def style(fig, title, h=360):
    fig.update_layout(title=dict(text=title, x=0, font=dict(size=14, color=INK)), height=h, template="simple_white",
                      font=dict(family="Segoe UI, Arial", size=12, color=MUTED), margin=dict(l=50, r=20, t=50, b=40),
                      legend=dict(orientation="h", y=-0.18), paper_bgcolor="white", plot_bgcolor="white", autosize=True)
    fig.update_xaxes(showgrid=False)
    fig.update_yaxes(gridcolor="#ECEBE6", showgrid=True)
    return fig


def block(fig, tag, note=""):
    html = fig.to_html(full_html=False, include_plotlyjs=False, default_width="100%", config={"displaylogo": False, "responsive": True})
    return f'<div class="card"><span class="tag {TAGS[tag]}">{tag}{" (synthetic)" if tag == "PUBLIC DATA" else ""}</span>{html}<p class="note">{note}</p></div>'


def kpi(label, value, sub, tag):
    return f'<div class="kpi"><span class="tag {TAGS[tag]}">{tag}</span><div class="kl">{label}</div><div class="kv">{value}</div><div class="ks">{sub}</div></div>'


def table(df, cols, fmt=None):
    fmt = fmt or {}
    head = "".join(f"<th>{c}</th>" for c in cols.values())
    body = ""
    for _, r in df.iterrows():
        cells = ""
        for k in cols:
            v = r[k]
            v = fmt[k](v) if k in fmt and pd.notna(v) else ("" if pd.isna(v) else v)
            cls = f' class="st {str(v).lower()}"' if k == "status" else ""
            cells += f"<td{cls}>{v}</td>"
        body += f"<tr>{cells}</tr>"
    return f"<table><tr>{head}</tr>{body}</table>"


def tab_overview(f):
    s, cap = f["system"]["implemented"], f["capacity"]
    k = "".join([
        kpi("Alerts in a normal week", f"{cap['2']['alerts_implemented']:,.0f}", f"capacity {cap['2']['alert_capacity']:,.0f} · {cap['2']['alerts_tuned']:,.0f} after proposals", "SIMULATED"),
        kpi("Precision of alerts", f"{s['precision']:.1%}", f"base rate {s['base_rate_account_days']:.1%}", "SIMULATED"),
        kpi("Laundering accounts caught", f"{s['recall']:.0%}", f"{s['tp_accounts']:.0f} of {s['laundering_accounts']:.0f}", "SIMULATED"),
        kpi("Typology coverage", f"{f['coverage']['summary']['coverage']:.0%}", f"of {f['coverage']['summary']['visible_attempts']:.0f} visible attempts", "PUBLIC DATA"),
        kpi("Controls failing", f"{f['controls']['fail']} / {f['controls']['n']}", f"{f['controls']['warn']} warnings", "SIMULATED")])
    e = pd.read_csv(PUB / "ecb_credit_transfer_fraud.csv")
    e = e[e.period >= "2022-S1"]
    fe = go.Figure([go.Scatter(x=g.period, y=g.value_eur_m, name=g.zone_label.iloc[0], mode="lines+markers",
                               line=dict(color=c, width=2)) for (z, g), c in zip(e.groupby("zone", sort=False), [BLUE, LIGHT, ORANGE, GREY])])
    style(fe, "Fraudulent credit transfers, EUR million per half-year (ECB)")
    d = csv("profile_daily")
    fd = go.Figure(go.Bar(x=d.day, y=d.n_rows, marker_color=[BLUE if w else GREY for w in d.in_window]))
    style(fd, "IBM HI-Medium: transactions per day (grey = sparse tail, excluded)")
    w = csv("capacity_weekly")
    fc = go.Figure([go.Bar(x=[f"Week {x}" for x in w.wk], y=w.alerts_implemented, name="current rules", marker_color=GREY),
                    go.Bar(x=[f"Week {x}" for x in w.wk], y=w.alerts_tuned, name="after proposals", marker_color=BLUE),
                    go.Scatter(x=[f"Week {x}" for x in w.wk], y=w.alert_capacity, name="capacity", mode="lines+markers",
                               line=dict(color=RED, dash="dash"), marker=dict(size=9, color=RED))])
    style(fc, "Alerts per week vs analyst capacity (week 3 = 2 days)").update_yaxes(type="log", tickformat=",", dtick=1)
    return f'<div class="kpis">{k}</div><div class="grid">{block(fc, "SIMULATED", "Bank N: 12 analysts, 30 h/week, 12 min median per alert.")}{block(fe, "PUBLIC DATA", "Series PAY/H.*.W0.CT0.1.F.N.EUR, UNIT_MULT 6, extracted " + f["ecb"]["extracted_on"] + ". Real ECB statistics (not synthetic).").replace("PUBLIC DATA (synthetic)", "PUBLIC DATA")}{block(fd, "PUBLIC DATA", "31.9M rows; 16 complete days kept.")}</div>'


def tab_quality(f):
    g = csv("null_rate_by_feed_day")
    fn = go.Figure([go.Scatter(x=s.day, y=s.null_rate, name=k, mode="lines", line=dict(color=RED if k == "ACH" else GREY, width=3 if k == "ACH" else 1))
                    for k, s in g.groupby("payment_format")])
    fn.add_hline(y=0.01, line_dash="dash", line_color=MUTED, annotation_text="FAIL 1%")
    style(fn, "Beneficiary bank missing, by feed and day").update_yaxes(tickformat=".0%")
    st = csv("bm_self_transfers_by_day")
    fs = go.Figure(go.Bar(x=st.day, y=st.share_self, marker_color=[RED if v > 0.2 else GREY for v in st.share_self]))
    style(fs, "Self-transfers, share of rows per day").update_yaxes(tickformat=".0%")
    c = csv("controls_report")
    k = csv("kyc_gaps")
    t1 = table(c, {"control_id": "Id", "name": "Control", "status": "status", "detail": "Result", "owner": "Owner", "frequency": "Frequency"})
    t2 = table(k, {"gap": "KYC gap", "customers": "Customers", "share": "Share", "base": "Base", "detection_impact": "Impact on detection"},
               {"share": lambda v: f"{v:.1%}"})
    return (f'<div class="grid">{block(fn, "SIMULATED", "ACH feed defect from 9 Sep (SIMULATED wrapper on synthetic data).")}'
            f'{block(fs, "PUBLIC DATA", "One-off Reinvestment batch on day 1.")}</div>'
            f'<div class="card"><span class="tag sim">SIMULATED</span><h3>Automated controls (controls/controls.yaml)</h3>{t1}</div>'
            f'<div class="card"><span class="tag sim">SIMULATED</span><h3>KYC gaps</h3>{t2}</div>')


def tab_rules(f):
    r = csv("rule_performance")
    fig = make_subplots(rows=1, cols=2, subplot_titles=("Alerts (16 days)", "Precision"))
    for rs, col in [("implemented", GREY), ("documented", BLUE)]:
        s = r[r.ruleset == rs]
        fig.add_bar(x=s.rule_id, y=s.alerts, name=f"as {rs}", marker_color=col, row=1, col=1)
        fig.add_bar(x=s.rule_id, y=s.precision, name=f"as {rs}", marker_color=col, row=1, col=2, showlegend=False)
    fig.update_yaxes(type="log", row=1, col=1)
    fig.update_yaxes(tickformat=".0%", row=1, col=2)
    style(fig, "Rules as documented vs as implemented (R07 uses ILLUSTRATIVE country tiers)")
    m = csv("typology_coverage_matrix").pivot(index="typology", columns="rule_id", values="share_detected")
    fh = go.Figure(go.Heatmap(z=m.values, x=m.columns, y=m.index, colorscale="Blues", zmin=0,
                              text=[[f"{v:.0%}" if v > 0 else "" for v in row] for row in m.values], texttemplate="%{text}"))
    style(fh, "Share of visible laundering attempts detected, typology x rule", 380)
    dv = csv("doc_vs_code")
    t = table(dv[dv.gap], {"rule_id": "Rule", "name": "Name", "documented_basis": "Doc basis", "implemented_basis": "Code basis",
                           "documented_excludes_self": "Doc excl. self", "implemented_excludes_self": "Code excl. self",
                           "documented_lookback": "Doc lookback", "implemented_lookback": "Code lookback",
                           "alerts_documented": "Alerts doc", "alerts_implemented": "Alerts code", "tp_accounts_missed_by_code": "TP accounts missed"})
    return (f'<div class="card"><span class="tag sim">SIMULATED</span><h3>Documentation vs code</h3>{t}</div>'
            f'<div class="grid">{block(fig, "SIMULATED", "Truth: IBM labels. Precision = true-positive alerts / alerts.")}'
            f'{block(fh, "PUBLIC DATA", "CYCLE and SCATTER-GATHER: no rule designed for them.")}</div>')


def tab_tuning(f):
    c = csv("atl_btl_curve")
    fig = make_subplots(rows=1, cols=2, subplot_titles=("Alerts per week by threshold multiplier", "Unique laundering accounts lost"))
    for (rid, s), col in zip(c.groupby("rule_id"), [GREY, ORANGE, BLUE, LIGHT, RED, AQUA]):
        fig.add_scatter(x=s.mult, y=s.alerts_per_week, name=rid, mode="lines+markers", line=dict(color=col), row=1, col=1)
        fig.add_scatter(x=s.mult, y=s.lost_unique_tp_accounts, name=rid, mode="lines+markers", line=dict(color=col), row=1, col=2, showlegend=False)
    fig.update_xaxes(type="log", title="x current threshold")
    fig.update_yaxes(type="log", row=1, col=1)
    style(fig, "ATL/BTL: moving each threshold from 0.5x to 20x")
    p = csv("payroll_corporate_daily")
    fp = go.Figure([go.Bar(x=p.day, y=p.corporate_alerts - p.payroll_driven_alerts, name="other corporate alerts", marker_color=GREY),
                    go.Bar(x=p.day, y=p.payroll_driven_alerts, name="payroll batch (known in KYC)", marker_color=ORANGE)])
    fp.add_hline(y=p.baseline.iloc[0], line_dash="dash", line_color=MUTED, annotation_text="Tue-Thu baseline")
    style(fp.update_layout(barmode="stack"), "Corporate alerts per day: a spike NOT to escalate")
    n = csv("network_typology_coverage")
    fn = go.Figure([go.Bar(x=n.typology, y=n[k], name=lab, marker_color=col) for k, lab, col in
                    [("rules_now", "current rules", GREY), ("tuned_rules", "tuned rules", LIGHT), ("tuned_rules_plus_r13", "tuned + R13", BLUE)]])
    style(fn, "Detection by typology with the new network scenario R13").update_yaxes(tickformat=".0%")
    tp = csv("tuning_proposal_impact")
    t = table(tp, {"rule_id": "Rule", "name": "Name", "action": "Action", "current_threshold": "Now", "proposed_threshold": "Proposed",
                   "alerts_now": "Alerts now", "alerts_after": "Alerts after", "tp_alerts_now": "TP now", "tp_alerts_after": "TP after", "rationale": "Why"},
              {"current_threshold": lambda v: f"{v:,.0f}", "proposed_threshold": lambda v: f"{v:,.0f}",
               "tp_alerts_now": lambda v: f"{v:.0f}", "tp_alerts_after": lambda v: f"{v:.0f}"})
    return (f'<div class="grid">{block(fig, "SIMULATED", "Above the line: alerts removed vs unique detections lost. Below the line: R03/R06 at 10 counterparties.")}'
            f'{block(fp, "SIMULATED", "Payroll batches brought forward to Wed 14 Sep by a bank holiday: 0 laundering labels, 0 escalations.")}</div>'
            f'<div class="grid">{block(fn, "PUBLIC DATA", "R13 = time-ordered cycles and scatter-gather pass-through (sql/10).")}'
            f'<div class="card"><span class="tag sim">SIMULATED</span><h3>Proposals and their impact</h3>{t}</div></div>')


def tab_model(f):
    m = csv("model_metrics")
    fa = go.Figure(go.Bar(x=m.version, y=m.roc_auc, marker_color=[RED, ORANGE, BLUE], text=[f"AUC {a:.3f}<br>AP {p:.2f}" for a, p in zip(m.roc_auc, m.avg_precision)],
                          textposition="outside"))
    style(fa, "Leakage: the first draft vs the honest challenger").update_yaxes(range=[0.85, 1.02])
    pr = csv("model_pr_curve")
    fp = go.Figure([go.Scatter(x=s.recall, y=s.precision, name=k, mode="lines", line=dict(color=c, width=2))
                    for (k, s), c in zip(pr.groupby("model", sort=False), [RED, BLUE])])
    style(fp, "Precision-recall on the test set").update_xaxes(tickformat=".0%", title="recall").update_yaxes(tickformat=".0%")
    s = csv("model_simpson")
    s = s[s.segment.isin(["retail", "sme"])]
    fs = go.Figure([go.Bar(x=g.risk_rating, y=g.precision, name=k, marker_color=c, text=[f"{v:.0%}" for v in g.precision], textposition="outside")
                    for (k, g), c in zip(s.groupby("segment"), [GREY, BLUE])])
    style(fs, "Simpson's paradox: SME better overall, worse in every risk tier").update_yaxes(tickformat=".0%")
    cp = csv("model_capacity")
    fc = go.Figure(go.Bar(x=cp.approach, y=cp.recall_accounts, marker_color=[GREY, BLUE, AQUA], text=[f"{v:.0%}" for v in cp.recall_accounts], textposition="outside"))
    style(fc, "Laundering accounts found in the 6 test days (score threshold set by capacity)").update_yaxes(tickformat=".0%")
    return (f'<div class="grid">{block(fa, "SIMULATED", "v1 uses whole-period aggregates and case outcomes (future). v2: as-of features, trained 1-10 Sep, tested 11-16 Sep.")}'
            f'{block(fp, "SIMULATED")}</div><div class="grid">{block(fc, "SIMULATED", "Top 257 account-days per day = analyst capacity.")}'
            f'{block(fs, "SIMULATED", "Segments and risk ratings are SIMULATED and not used as model inputs.")}</div>')


CSS = """
body { margin: 0; font-family: 'Segoe UI', Arial, sans-serif; background: #F4F4F2; color: #0B0B0B; }
header { padding: 22px 32px 10px; } h1 { font-size: 22px; margin: 0 0 4px; } .sub { color: #52514E; margin: 0; font-size: 14px; }
nav { display: flex; gap: 6px; padding: 0 32px; border-bottom: 1px solid #E1E0D9; }
nav button { border: 0; background: none; padding: 10px 14px; font: inherit; font-size: 14px; color: #52514E; cursor: pointer; border-bottom: 3px solid transparent; }
nav button.on { color: #0B0B0B; border-bottom-color: #2A78D6; font-weight: 600; }
.tab { display: none; padding: 16px 32px; } .tab.on { display: block; }
.grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(520px, 1fr)); gap: 14px; margin-bottom: 14px; }
.card { position: relative; background: #FCFCFB; border: 1px solid #E1E0D9; border-radius: 8px; padding: 12px 14px; margin-bottom: 14px; overflow-x: auto; }
.card h3 { margin: 0 0 8px; font-size: 15px; }
.kpis { display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 12px; margin-bottom: 14px; }
.kpi { position: relative; background: #FCFCFB; border: 1px solid #E1E0D9; border-radius: 8px; padding: 12px 14px; }
.kl { padding-right: 84px; min-height: 30px; font-size: 12px; font-weight: 700; color: #52514E; letter-spacing: .04em; text-transform: uppercase; }
.kv { font-size: 32px; font-weight: 700; margin: 4px 0; } .ks { font-size: 12.5px; color: #52514E; }
.tag { position: absolute; top: 8px; right: 10px; font-size: 10px; font-weight: 700; letter-spacing: .06em; padding: 2px 6px; border-radius: 4px; z-index: 2; }
.pub { background: #E3EEFB; color: #1C5CAB; } .sim { background: #FBE9E0; color: #9A3B12; } .ill { background: #EFE8F8; color: #5B3A8C; }
table { border-collapse: collapse; width: 100%; font-size: 12.5px; } th { text-align: left; color: #52514E; border-bottom: 1px solid #E1E0D9; padding: 4px 6px; }
td { border-bottom: 1px solid #EFEEE9; padding: 4px 6px; vertical-align: top; }
td.st.fail { color: #A32020; font-weight: 700; } td.st.warn { color: #8A5A00; font-weight: 700; } td.st.pass { color: #146B47; font-weight: 700; }
.plotly-graph-div { width: 100% !important; }
.grid > * { min-width: 0; }
.note { font-size: 12px; color: #6B6A65; margin: 4px 0 0; }
footer { padding: 14px 32px 24px; font-size: 12px; color: #898781; }
"""


def main():
    f = json.loads((OUT / "findings.json").read_text(encoding="utf-8"))
    tabs = [("Overview", tab_overview(f)), ("Data quality", tab_quality(f)), ("Rules & coverage", tab_rules(f)),
            ("Tuning & capacity", tab_tuning(f)), ("Challenger model", tab_model(f))]
    nav = "".join(f'<button class="{"on" if i == 0 else ""}" onclick="show({i})">{n}</button>' for i, (n, _) in enumerate(tabs))
    body = "".join(f'<section class="tab {"on" if i == 0 else ""}">{h}</section>' for i, (_, h) in enumerate(tabs))
    html = f"""<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>Transaction-monitoring assessment: dashboard</title><style>{CSS}</style><script>{get_plotlyjs()}</script></head><body>
<header><h1>Tuning a transaction-monitoring system: from 32 million transactions to alerts worth reviewing</h1>
<p class="sub">Bank N (fictional) · IBM AML benchmark (PUBLIC DATA, synthetic) · bank layer SIMULATED · country tiers ILLUSTRATIVE</p></header>
<nav>{nav}</nav>{body}
<footer>{FOOT} · <a href="../report/aml_tm_assessment.pdf">Report (PDF)</a></footer>
<script>function show(i){{document.querySelectorAll('.tab').forEach((t,j)=>t.classList.toggle('on',i===j));
document.querySelectorAll('nav button').forEach((b,j)=>b.classList.toggle('on',i===j));fit();}}
function fit(){{document.querySelectorAll('.tab.on .plotly-graph-div').forEach(g=>Plotly.Plots.resize(g));}}
window.addEventListener('load',fit);setTimeout(fit,300);</script>
</body></html>"""
    DEST.parent.mkdir(parents=True, exist_ok=True)
    DEST.write_text(html, encoding="utf-8")
    print("written", DEST.relative_to(ROOT), f"{DEST.stat().st_size / 1e6:.1f} MB")


if __name__ == "__main__":
    main()
