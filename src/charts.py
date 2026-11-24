"""Matplotlib charts for the PDF and the README (docs/img/*.png). Every number is read from output/ or data/.

Style (same as the earlier case studies): light page, white cards, blue for the data, grey for comparison,
red for thresholds and capacity, Segoe UI. The data type (PUBLIC DATA / SIMULATED / ILLUSTRATIVE) is shown on
each PDF card.
"""
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.dates as mdates
import matplotlib.pyplot as plt
import matplotlib.ticker as mtick
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "output"
PUB = ROOT / "data" / "public"
IMG = ROOT / "docs" / "img"

BLUE, GREY, RED, INK, MUTED, GRID, ORANGE, AQUA = "#2A78D6", "#A3A19A", "#D03B3B", "#0B0B0B", "#52514E", "#E1E0D9", "#EB6834", "#1BAF7A"
LIGHT = "#C9DDF5"
plt.rcParams.update({
    "font.family": "Segoe UI", "font.size": 10, "axes.edgecolor": GRID, "axes.labelcolor": MUTED,
    "xtick.color": MUTED, "ytick.color": MUTED, "axes.spines.top": False, "axes.spines.right": False,
    "axes.grid": True, "grid.color": GRID, "grid.linewidth": 0.6, "axes.axisbelow": True,
    "figure.facecolor": "white", "axes.facecolor": "white", "legend.frameon": False,
    "axes.titlesize": 11, "axes.titleweight": "semibold", "axes.titlecolor": INK, "axes.titlelocation": "left",
})
PCT = mtick.PercentFormatter(1.0, decimals=0)


def csv(n):
    return pd.read_csv(OUT / f"{n}.csv")


def save(fig, name):
    IMG.mkdir(parents=True, exist_ok=True)
    fig.tight_layout()
    fig.savefig(IMG / f"{name}.png", dpi=200)
    plt.close(fig)
    return name


def day_axis(ax):
    ax.xaxis.set_major_locator(mdates.DayLocator(interval=3))
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%d %b"))


def ecb():
    e = pd.read_csv(PUB / "ecb_credit_transfer_fraud.csv")
    e = e[e.period >= "2022-S1"]
    fig, ax = plt.subplots(figsize=(6.4, 3.4))
    for z, c in [("B0", BLUE), ("FR", GREY), ("ES", ORANGE)]:
        s = e[e.zone == z]
        ax.plot(s.period, s.value_eur_m, marker="o", color=c, lw=2, label=s.zone_label.iloc[0])
        ax.annotate(f"{s.value_eur_m.iloc[-1]:,.0f}", (s.period.iloc[-1], s.value_eur_m.iloc[-1]), xytext=(4, 0),
                    textcoords="offset points", fontsize=9, color=c, va="center")
    ax.set_title("Fraudulent credit transfers, EUR million per half-year")
    ax.legend(loc="upper left", ncol=3)
    ax.tick_params(axis="x", labelsize=8.5)
    return save(fig, "ecb_fraud")


def daily_volume():
    d = csv("profile_daily")
    d["day"] = pd.to_datetime(d.day)
    fig, ax = plt.subplots(figsize=(6.4, 3.4))
    ax.bar(d.day, d.n_rows / 1e6, color=np.where(d.in_window, BLUE, GREY), width=0.8)
    ax.set_title("Transactions per day, million (grey: sparse tail, excluded)")
    ax.annotate("1 Sep: 1.9M self-transfers\n('Reinvestment' batch)", (d.day.iloc[0], d.n_rows.iloc[0] / 1e6),
                xytext=(40, -8), textcoords="offset points", fontsize=8.5, color=RED, arrowprops=dict(arrowstyle="-", color=RED))
    day_axis(ax)
    return save(fig, "daily_volume")


def feed_nulls():
    g = csv("null_rate_by_feed_day")
    g["day"] = pd.to_datetime(g.day)
    fig, ax = plt.subplots(figsize=(6.4, 3.4))
    for f, s in g.groupby("payment_format"):
        ax.plot(s.day, s.null_rate, color=RED if f == "ACH" else GREY, lw=2.2 if f == "ACH" else 1, label=f if f == "ACH" else None)
    ax.axhline(0.01, color=MUTED, ls="--", lw=1)
    ax.text(g.day.min(), 0.012, "FAIL threshold 1%", fontsize=8.5, color=MUTED)
    ax.yaxis.set_major_formatter(PCT)
    ax.set_title("Beneficiary bank missing, share of rows by feed and day")
    ax.legend(["ACH feed"], loc="upper left")
    day_axis(ax)
    return save(fig, "feed_nulls")


def self_transfers():
    d = csv("bm_self_transfers_by_day")
    d["day"] = pd.to_datetime(d.day)
    fig, ax = plt.subplots(figsize=(6.4, 3.4))
    ax.bar(d.day, d.share_self, color=np.where(d.share_self > 0.2, RED, GREY), width=0.8)
    ax.yaxis.set_major_formatter(PCT)
    ax.set_title("Self-transfers (same account both sides), share of rows")
    day_axis(ax)
    return save(fig, "self_transfers")


def rule_perf():
    r = csv("rule_performance")
    r = r[r.ruleset == "implemented"].copy()
    base = csv("system_summary").set_index("ruleset").loc["implemented", "base_rate_account_days"]
    r["label"] = r.rule_id + " " + r.name.str.slice(0, 22)
    r = r.sort_values("rule_id", ascending=False)
    fig, axes = plt.subplots(1, 2, figsize=(7.4, 3.9), sharey=True)
    axes[0].barh(r.label, r.share_of_alerts, color=np.where(r.rule_id.isin(["R04", "R09"]), RED, BLUE))
    axes[0].xaxis.set_major_formatter(PCT)
    axes[0].set_title("Share of all alerts")
    axes[1].barh(r.label, r.precision.fillna(0), color=BLUE)
    axes[1].axvline(base, color=RED, ls="--", lw=1)
    axes[1].text(base, -0.9, f" base rate {base:.1%}", color=RED, fontsize=8)
    axes[1].xaxis.set_major_formatter(mtick.PercentFormatter(1.0, decimals=0))
    axes[1].set_title("Precision (true-positive alerts)")
    for ax in axes:
        ax.tick_params(axis="y", labelsize=8.5)
    return save(fig, "rule_perf")


def coverage_matrix():
    m = csv("typology_coverage_matrix")
    p = m.pivot(index="typology", columns="rule_id", values="share_detected")
    p = p.drop(columns=[c for c in p.columns if p[c].sum() == 0 and c in ("R03", "R08")], errors="ignore")
    fig, ax = plt.subplots(figsize=(7.4, 3.9))
    ax.imshow(p.values, cmap="Blues", vmin=0, vmax=max(0.15, np.nanmax(p.values)), aspect="auto")
    ax.set_xticks(range(len(p.columns)), p.columns)
    ax.set_yticks(range(len(p.index)), p.index)
    ax.grid(False)
    for i in range(p.shape[0]):
        for j in range(p.shape[1]):
            v = p.values[i, j]
            ax.text(j, i, f"{v:.0%}" if v > 0 else "-", ha="center", va="center", fontsize=8,
                    color="white" if v > 0.1 else INK)
    ax.set_title("Share of visible laundering attempts detected, by typology and rule")
    return save(fig, "coverage_matrix")


def atl_btl():
    c = csv("atl_btl_curve")
    fig, axes = plt.subplots(1, 2, figsize=(7.4, 3.6))
    s = c[c.rule_id == "R09"]
    ax = axes[0]
    ax.plot(s.threshold, s.alerts_per_week, color=BLUE, marker="o", lw=2, label="alerts / week")
    ax.set_xscale("log")
    ax.set_title("R09 round amounts: threshold (USD)")
    ax2 = ax.twinx()
    ax2.plot(s.threshold, s.lost_unique_tp_accounts, color=RED, marker="s", lw=1.5, label="unique laundering accounts lost")
    ax2.grid(False)
    ax2.spines["right"].set_visible(True)
    ax.axvline(1000, color=MUTED, ls=":", lw=1)
    ax.axvline(5000, color=RED, ls="--", lw=1)
    h1, l1 = ax.get_legend_handles_labels()
    h2, l2 = ax2.get_legend_handles_labels()
    ax.legend(h1 + h2, l1 + l2, loc="upper right", fontsize=8)
    ax = axes[1]
    for r, col in [("R03", ORANGE), ("R06", BLUE)]:
        s = c[c.rule_id == r]
        ax.plot(s.threshold, s.precision, color=col, marker="o", lw=2, label=f"{r} precision")
    ax.yaxis.set_major_formatter(PCT)
    ax.axvline(20, color=MUTED, ls=":", lw=1)
    ax.axvline(10, color=RED, ls="--", lw=1)
    ax.set_title("Fan-out / fan-in: distinct counterparties")
    ax.legend(fontsize=8)
    return save(fig, "atl_btl")


def capacity():
    w = csv("capacity_weekly")
    fig, ax = plt.subplots(figsize=(6.4, 3.4))
    x = np.arange(len(w))
    ax.bar(x - 0.2, w.alerts_implemented, 0.4, color=GREY, label="current rules")
    ax.bar(x + 0.2, w.alerts_tuned, 0.4, color=BLUE, label="after fixes and tuning")
    ax.scatter(x, w.alert_capacity, marker="_", s=900, color=RED, linewidths=2.5, label="analyst capacity", zorder=3)
    ax.set_xticks(x, [f"Week {k} ({d} days)" for k, d in zip(w.wk, w.days_in_week)])
    ax.set_yscale("log")
    ax.yaxis.set_major_formatter(mtick.FuncFormatter(lambda v, _: f"{v:,.0f}"))
    ax.set_title("Alerts per week vs capacity (12 analysts)")
    ax.legend(fontsize=8.5, loc="upper right")
    return save(fig, "capacity")


def payroll():
    d = csv("payroll_corporate_daily")
    d["day"] = pd.to_datetime(d.day)
    d = d[d.day > d.day.min()]
    fig, ax = plt.subplots(figsize=(6.4, 3.4))
    ax.bar(d.day, d.corporate_alerts - d.payroll_driven_alerts, color=GREY, width=0.8, label="other corporate alerts")
    ax.bar(d.day, d.payroll_driven_alerts, bottom=d.corporate_alerts - d.payroll_driven_alerts, color=ORANGE, width=0.8,
           label="payroll batch (known in KYC)")
    ax.axhline(d.baseline.iloc[0], color=MUTED, ls="--", lw=1)
    ax.text(d.day.min(), d.baseline.iloc[0] * 1.04, "Tue-Thu baseline", fontsize=8.5, color=MUTED)
    ax.set_title("Corporate alerts per day (from 2 Sep)")
    ax.legend(fontsize=8.5, loc="upper left")
    day_axis(ax)
    return save(fig, "payroll")


def network():
    c = csv("network_typology_coverage")
    fig, ax = plt.subplots(figsize=(6.4, 3.4))
    x = np.arange(len(c))
    ax.bar(x - 0.27, c.rules_now, 0.27, color=GREY, label="current rules")
    ax.bar(x, c.tuned_rules, 0.27, color=LIGHT, label="tuned rules")
    ax.bar(x + 0.27, c.tuned_rules_plus_r13, 0.27, color=BLUE, label="tuned + R13 network")
    ax.set_xticks(x, [t.replace("-", "-\n") for t in c.typology], fontsize=8)
    ax.yaxis.set_major_formatter(PCT)
    ax.set_title("Visible laundering attempts detected, by typology")
    ax.legend(fontsize=8, ncol=3, loc="upper left")
    return save(fig, "network")


def model_auc():
    m = csv("model_metrics")
    fig, ax = plt.subplots(figsize=(6.4, 3.4))
    lab = ["v1 draft\nrandom split", "v1 features\ntemporal test", "v2 challenger\ntemporal test"]
    ax.bar(lab, m.roc_auc, color=[RED, ORANGE, BLUE], width=0.55)
    for i, (a, p) in enumerate(zip(m.roc_auc, m.avg_precision)):
        ax.text(i, a + 0.005, f"AUC {a:.3f}\nAP {p:.2f}", ha="center", fontsize=9)
    ax.set_ylim(0.85, 1.01)
    ax.set_title("ROC AUC and average precision (AP)")
    return save(fig, "model_auc")


def pr_curve():
    c = csv("model_pr_curve")
    base = csv("model_base").iloc[0].base_rate
    fig, ax = plt.subplots(figsize=(6.4, 3.4))
    for (n, s), col in zip(c.groupby("model", sort=False), [RED, BLUE]):
        ax.plot(s.recall, s.precision, color=col, lw=2, label=n)
    ax.axhline(base, color=GREY, ls="--", lw=1)
    ax.text(0.6, base + 0.02, f"base rate {base:.1%}", color=MUTED, fontsize=8.5)
    ax.xaxis.set_major_formatter(PCT)
    ax.yaxis.set_major_formatter(PCT)
    ax.set_xlabel("recall")
    ax.set_title("Precision-recall on the test set")
    ax.legend(fontsize=8.5)
    return save(fig, "pr_curve")


def simpson():
    s = csv("model_simpson")
    s = s[s.segment.isin(["retail", "sme"])]
    fig, ax = plt.subplots(figsize=(6.4, 3.4))
    cats = ["all", "low", "medium", "high"]
    x = np.arange(len(cats))
    for k, (seg, col) in enumerate([("retail", GREY), ("sme", BLUE)]):
        v = s[s.segment == seg].set_index("risk_rating").reindex(cats).precision
        ax.bar(x + (k - 0.5) * 0.38, v, 0.38, color=col, label=seg)
        for i, val in enumerate(v):
            ax.text(x[i] + (k - 0.5) * 0.38, val + 0.01, f"{val:.0%}", ha="center", fontsize=8)
    ax.set_xticks(x, ["all customers", "low risk", "medium risk", "high risk"])
    ax.yaxis.set_major_formatter(PCT)
    ax.set_title("Challenger precision: SME looks better overall, worse in every tier")
    ax.legend(fontsize=8.5)
    return save(fig, "simpson")


def model_capacity():
    c = csv("model_capacity")
    fig, ax = plt.subplots(figsize=(6.4, 3.4))
    lab = ["Tuned rules", "Challenger\n(capacity)", "Rules +\nchallenger"]
    ax.bar(lab, c.recall_accounts, color=[GREY, BLUE, AQUA], width=0.55)
    for i, (r, p) in enumerate(zip(c.recall_accounts, c.precision)):
        ax.text(i, r + 0.01, f"{r:.0%}" + (f"\nprecision {p:.1%}" if pd.notna(p) else ""), ha="center", fontsize=9)
    ax.yaxis.set_major_formatter(PCT)
    ax.set_ylim(0, max(c.recall_accounts) * 1.3)
    ax.set_title("Laundering accounts found in the 6 test days")
    return save(fig, "model_capacity")


def build_all():
    return {f.__name__: f() for f in [ecb, daily_volume, feed_nulls, self_transfers, rule_perf, coverage_matrix,
                                      atl_btl, capacity, payroll, network, model_auc, pr_curve, simpson, model_capacity]}


if __name__ == "__main__":
    print(build_all())
