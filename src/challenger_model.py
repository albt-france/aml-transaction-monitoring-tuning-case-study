"""Challenger scoring model for Bank N (rules stay; the score ranks the work queue).

    python src/challenger_model.py

Unit: one Bank N account on one day with activity. Label: the account sent or received a transaction labelled
Is Laundering = 1 that day (IBM PUBLIC DATA, synthetic). Model: scikit-learn HistGradientBoostingClassifier.

Two versions, on purpose:
  v1 "first draft"  : adds whole-period account aggregates (computed over all 16 days, i.e. using the future)
                      the account's case outcome (ever escalated / SAR) and a "known bad counterparty" share,
                      both built from all cases in the extract with no time cut, and is
                      validated on a random split of account-days -> leakage, optimistic AUC
  v2 "challenger"   : only as-of features (that day and the 7 days before), validated in time:
                      train on the first 62.5% of days (1-10 Sep on HI-Medium), test on the rest
The KYC risk rating and segment are NOT features (they are SIMULATED and partly built from the labels);
they are only used afterwards to read results by segment (Simpson's paradox check).
Outputs: output/model_*.csv
"""
import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.inspection import permutation_importance
from sklearn.metrics import average_precision_score, precision_recall_curve, roc_auc_score
from sklearn.model_selection import train_test_split

from db import OUT, connect

SEED = 42
TRAIN_SHARE = 0.625   # first 62.5% of the days for training: 1-10 Sep of the 16-day HI-Medium window

FEATURES_SQL = """
WITH f AS (
    SELECT from_key AS acct_key, day,
           count(DISTINCT payment_format) AS n_formats_out,
           count(DISTINCT payment_currency) AS n_currencies_out,
           avg(CASE WHEN payment_format = 'ACH' THEN 1 ELSE 0 END) AS share_ach_out,
           avg(CASE WHEN from_bank <> to_bank THEN 1 ELSE 0 END) AS share_cross_bank_out,
           avg(amount_paid_usd) AS mean_out_usd
    FROM tx_book WHERE from_in_book AND NOT is_self GROUP BY 1, 2
),
g AS (
    SELECT to_key AS acct_key, day, count(*) AS in_cnt,
           avg(CASE WHEN payment_format = 'ACH' THEN 1 ELSE 0 END) AS share_ach_in
    FROM tx_book WHERE to_in_book AND NOT is_self GROUP BY 1, 2
),
d AS (
    SELECT a.acct_key, a.day, b.segment, b.risk_rating,
           a.out_cnt, a.out_usd, a.out_cp, coalesce(a.out_max_usd, 0) AS out_max_usd, a.struct_usd_cnt,
           CASE WHEN a.round_max_usd IS NULL THEN 0 ELSE 1 END AS has_round_amount,
           a.cash_usd, CASE WHEN a.conv_max_usd IS NULL THEN 0 ELSE 1 END AS has_conversion,
           a.in_usd, a.in_cp, coalesce(g.in_cnt, 0) AS in_cnt,
           coalesce(f.n_formats_out, 0) AS n_formats_out, coalesce(f.n_currencies_out, 0) AS n_currencies_out,
           coalesce(f.share_ach_out, 0) AS share_ach_out, coalesce(f.share_cross_bank_out, 0) AS share_cross_bank_out,
           coalesce(f.mean_out_usd, 0) AS mean_out_usd, coalesce(g.share_ach_in, 0) AS share_ach_in,
           a.out_usd / nullif(a.out_usd + a.in_usd, 0) AS out_share,
           CASE WHEN l.acct_key IS NULL THEN 0 ELSE 1 END AS y
    FROM ad_documented a
    JOIN book b USING (acct_key)
    LEFT JOIN f USING (acct_key, day) LEFT JOIN g USING (acct_key, day)
    LEFT JOIN lab_ad l USING (acct_key, day)
),
-- "known bad counterparty" share built from ALL confirmed cases in the extract, including cases confirmed after
-- the scoring day: the classic leak of a first draft
bad AS (SELECT from_key AS k FROM tx WHERE is_laundering = 1 UNION SELECT to_key FROM tx WHERE is_laundering = 1),
cp AS (SELECT from_key AS acct_key, to_key AS cp FROM tx_book WHERE from_in_book AND NOT is_self
       UNION SELECT to_key, from_key FROM tx_book WHERE to_in_book AND NOT is_self),
badcp AS (SELECT acct_key, avg(CASE WHEN cp IN (SELECT k FROM bad) THEN 1 ELSE 0 END) AS share_bad FROM cp GROUP BY 1),
-- case outcomes joined at account level with no time cut
cases AS (
    SELECT DISTINCT acct_key FROM alerts a JOIN dispositions d USING (alert_id) JOIN book b USING (account_ref)
    WHERE d.decision IN ('escalated', 'sar_filed')
)
SELECT *,
    -- as-of history: the 7 days before (no future)
    coalesce(sum(out_cnt) OVER w7, 0) AS out_cnt_prev7,
    coalesce(sum(in_cnt) OVER w7, 0) AS in_cnt_prev7,
    coalesce(sum(out_cp) OVER w7, 0) AS out_cp_prev7,
    coalesce(sum(in_cp) OVER w7, 0) AS in_cp_prev7,
    coalesce(count(*) OVER w7, 0) AS active_days_prev7,
    least(sum(in_usd) OVER w2, sum(out_usd) OVER w2) / nullif(greatest(sum(in_usd) OVER w2, sum(out_usd) OVER w2), 0) AS passthrough_2d,
    -- whole-period aggregates (use the future: leakage, v1 only)
    sum(out_cnt + in_cnt) OVER wall AS leak_total_tx,
    sum(out_cp + in_cp) OVER wall AS leak_total_counterparties,
    count(*) OVER wall AS leak_active_days,
    max(out_cnt) OVER wall AS leak_max_daily_out,
    avg(share_ach_out) OVER wall AS leak_mean_share_ach,
    sum(out_usd) OVER wall / nullif(sum(out_usd + in_usd) OVER wall, 0) AS leak_out_share,
    CASE WHEN d.acct_key IN (SELECT acct_key FROM cases) THEN 1 ELSE 0 END AS leak_ever_escalated,
    coalesce((SELECT share_bad FROM badcp WHERE badcp.acct_key = d.acct_key), 0) AS leak_bad_counterparty_share
FROM d
WINDOW w7 AS (PARTITION BY acct_key ORDER BY day RANGE BETWEEN INTERVAL 7 DAY PRECEDING AND INTERVAL 1 DAY PRECEDING),
       w2 AS (PARTITION BY acct_key ORDER BY day RANGE BETWEEN INTERVAL 1 DAY PRECEDING AND CURRENT ROW),
       wall AS (PARTITION BY acct_key)
"""

ASOF = ["out_cnt", "out_usd", "out_cp", "out_max_usd", "struct_usd_cnt", "has_round_amount", "cash_usd",
        "has_conversion", "in_usd", "in_cp", "in_cnt", "n_formats_out", "n_currencies_out", "share_ach_out",
        "share_cross_bank_out", "mean_out_usd", "share_ach_in", "out_share", "out_cnt_prev7", "in_cnt_prev7",
        "out_cp_prev7", "in_cp_prev7", "active_days_prev7", "passthrough_2d"]
LEAK = ["leak_total_tx", "leak_total_counterparties", "leak_active_days", "leak_max_daily_out",
        "leak_mean_share_ach", "leak_out_share", "leak_ever_escalated",
        "leak_bad_counterparty_share"]


def fit(X, y):
    m = HistGradientBoostingClassifier(max_iter=300, learning_rate=0.05, max_leaf_nodes=31, l2_regularization=1.0,
                                       early_stopping=True, validation_fraction=0.15, random_state=SEED)
    return m.fit(X, y)


def scores(m, X, y):
    p = m.predict_proba(X)[:, 1]
    return p, roc_auc_score(y, p), average_precision_score(y, p)


def main():
    con = connect(read_only=True)
    df = con.execute(FEATURES_SQL).df().sort_values(["acct_key", "day"]).reset_index(drop=True)  # deterministic order
    cap = con.execute("SELECT alert_capacity / days_in_week FROM capacity WHERE days_in_week = 7 LIMIT 1").fetchone()[0]
    tuned = con.execute("SELECT acct_key, day, is_tp FROM alerts_tuned").df()
    con.close()
    df[ASOF + LEAK] = df[ASOF + LEAK].astype(float).round(6)   # removes float noise from parallel SQL sums
    df["day"] = pd.to_datetime(df.day)
    days = sorted(df.day.unique())
    TRAIN_LAST_DAY = pd.Timestamp(days[int(round(len(days) * TRAIN_SHARE)) - 1]).strftime("%Y-%m-%d")
    tr = df.day <= TRAIN_LAST_DAY
    te = ~tr
    metrics, curves = [], []

    # v1: leaky features + random split
    Xa = df[ASOF + LEAK]
    Xtr, Xte, ytr, yte = train_test_split(Xa, df.y, test_size=0.375, random_state=SEED, stratify=df.y)
    m1 = fit(Xtr, ytr)
    p1, auc1, ap1 = scores(m1, Xte, yte)
    metrics.append({"version": "v1 first draft", "features": "as-of + whole-period aggregates (future)",
                    "validation": "random split of account-days", "roc_auc": auc1, "avg_precision": ap1,
                    "n_train": len(Xtr), "n_test": len(Xte), "pos_train": int(ytr.sum()), "pos_test": int(yte.sum())})
    # v1 features, but evaluated honestly in time (shows the leak, not the split, is the main driver)
    m1t = fit(df.loc[tr, ASOF + LEAK], df.y[tr])
    _, auc1t, ap1t = scores(m1t, df.loc[te, ASOF + LEAK], df.y[te])
    metrics.append({"version": "v1 features, temporal test", "features": "as-of + whole-period aggregates (future)",
                    "validation": f"train <= {TRAIN_LAST_DAY}, test after", "roc_auc": auc1t, "avg_precision": ap1t,
                    "n_train": int(tr.sum()), "n_test": int(te.sum()), "pos_train": int(df.y[tr].sum()), "pos_test": int(df.y[te].sum())})
    # v2: as-of features + temporal split
    m2 = fit(df.loc[tr, ASOF], df.y[tr])
    p2, auc2, ap2 = scores(m2, df.loc[te, ASOF], df.y[te])
    metrics.append({"version": "v2 challenger", "features": "as-of only (that day + 7 days before)",
                    "validation": f"train <= {TRAIN_LAST_DAY}, test after", "roc_auc": auc2, "avg_precision": ap2,
                    "n_train": int(tr.sum()), "n_test": int(te.sum()), "pos_train": int(df.y[tr].sum()), "pos_test": int(df.y[te].sum())})
    for name, y, p in [("v1 first draft (random split)", yte, p1), ("v2 challenger (temporal)", df.y[te], p2)]:
        pr, rc, _ = precision_recall_curve(y, p)
        idx = np.unique(np.linspace(0, len(pr) - 1, 200).astype(int))
        curves.append(pd.DataFrame({"model": name, "recall": rc[idx], "precision": pr[idx]}))

    # capacity: each test day, analysts can review `cap` alerts; compare the score's top-cap with the tuned rules
    t = df.loc[te, ["acct_key", "day", "y", "segment", "risk_rating"]].copy()
    t["score"] = p2
    t["rank"] = t.groupby("day").score.rank(ascending=False, method="first")
    top = t[t["rank"] <= cap]
    n_days = t.day.nunique()
    lab_acc = set(t.loc[t.y == 1, "acct_key"])
    tuned["day"] = pd.to_datetime(tuned.day)
    tu = tuned[tuned.day > TRAIN_LAST_DAY]
    found_model = set(top.loc[top.y == 1, "acct_key"])
    found_rules = set(tu.loc[tu.is_tp == 1, "acct_key"])
    capacity = pd.DataFrame([
        {"approach": "Tuned rules (all alerts)", "alerts_per_day": len(tu) / n_days, "precision": tu.is_tp.mean(),
         "laundering_accounts_found": len(found_rules & lab_acc), "laundering_accounts_in_test": len(lab_acc)},
        {"approach": f"Challenger top {int(cap)} per day (capacity)", "alerts_per_day": len(top) / n_days,
         "precision": top.y.mean(), "laundering_accounts_found": len(found_model),
         "laundering_accounts_in_test": len(lab_acc)},
        {"approach": "Tuned rules + challenger (union)", "alerts_per_day": np.nan, "precision": np.nan,
         "laundering_accounts_found": len((found_rules & lab_acc) | found_model), "laundering_accounts_in_test": len(lab_acc)},
    ])
    capacity["recall_accounts"] = capacity.laundering_accounts_found / capacity.laundering_accounts_in_test
    capacity["score_threshold_mean"] = [np.nan, top.groupby("day").score.min().mean(), np.nan]

    # Simpson's paradox check on the challenger queue
    rows = []
    for seg in ["retail", "sme", "corporate"]:
        s = top[top.segment == seg]
        rows.append({"segment": seg, "risk_rating": "all", "alerts": len(s), "true_positives": int(s.y.sum()),
                     "precision": s.y.mean() if len(s) else np.nan})
        for r in ["low", "medium", "high"]:
            s2 = s[s.risk_rating == r]
            rows.append({"segment": seg, "risk_rating": r, "alerts": len(s2), "true_positives": int(s2.y.sum()),
                         "precision": s2.y.mean() if len(s2) else np.nan})
    simpson = pd.DataFrame(rows)
    mix = top.groupby("segment").risk_rating.value_counts(normalize=True).rename("share").reset_index()

    # permutation importance (temporal test set, sample for speed)
    rs = np.random.default_rng(SEED)
    te_idx = np.where(te)[0]
    pos = te_idx[df.y.values[te_idx] == 1]
    neg = rs.choice(te_idx[df.y.values[te_idx] == 0], size=min(40000, (df.y.values[te_idx] == 0).sum()), replace=False)
    smp = np.concatenate([pos, neg])
    pi = permutation_importance(m2, df.iloc[smp][ASOF], df.y.iloc[smp], scoring="average_precision",
                                n_repeats=5, random_state=SEED, n_jobs=1)
    imp = pd.DataFrame({"feature": ASOF, "importance": pi.importances_mean, "std": pi.importances_std}
                       ).sort_values("importance", ascending=False)

    base = pd.DataFrame([{"account_days": len(df), "positives": int(df.y.sum()), "base_rate": df.y.mean(),
                          "train_days": int(df.loc[tr, "day"].nunique()), "test_days": n_days,
                          "daily_capacity": cap}])
    for name, d in [("model_metrics", pd.DataFrame(metrics)), ("model_pr_curve", pd.concat(curves)),
                    ("model_capacity", capacity), ("model_simpson", simpson), ("model_simpson_mix", mix),
                    ("model_importance", imp), ("model_base", base)]:
        d.to_csv(OUT / f"{name}.csv", index=False)
    print(pd.DataFrame(metrics)[["version", "roc_auc", "avg_precision", "pos_test"]].round(3).to_string(index=False))
    print(capacity.round(3).to_string(index=False))
    print(simpson.round(3).to_string(index=False))
    print(imp.head(6).round(4).to_string(index=False))


if __name__ == "__main__":
    main()
