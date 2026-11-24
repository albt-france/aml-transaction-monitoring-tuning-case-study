"""Build the Power BI project (PBIP: semantic model in TMDL + report in PBIR) in powerbi/.

    python src/build_powerbi.py

1. exports the model tables to powerbi/data/*.csv (aggregates and pseudonymous alert rows only)
2. writes the semantic model (tables, relationships, DAX measures) as TMDL
3. writes 5 report pages in PBIR (same pages as the HTML dashboard)
Open powerbi/AmlTmAssessment.pbip in Power BI Desktop, then set the DataFolder parameter to the full path of
powerbi/data/ in your clone (Transform data > Edit parameters) and refresh. No .pbix is stored in the repository.
Page and visual helpers are adapted from an earlier case study's PBIR generator.
"""
import json
import shutil
import uuid
from pathlib import Path

import duckdb
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
PBI = ROOT / "powerbi"
DATA = PBI / "data"
OUT = ROOT / "output"
SIM = ROOT / "data" / "sim"
NAME = "AmlTmAssessment"
REPORT = PBI / f"{NAME}.Report"
MODEL = PBI / f"{NAME}.SemanticModel"
PAGES = REPORT / "definition" / "pages"
VC_SCHEMA = "https://developer.microsoft.com/json-schemas/fabric/item/report/definition/visualContainer/2.4.0/schema.json"
PAGE_SCHEMA = "https://developer.microsoft.com/json-schemas/fabric/item/report/definition/page/2.1.0/schema.json"
PAGES_SCHEMA = "https://developer.microsoft.com/json-schemas/fabric/item/report/definition/pagesMetadata/1.1.0/schema.json"
M = "_Measures"
INK, INK2, MUTED = "#0B0B0B", "#52514E", "#898781"
BLUE, GREY, RED = "#2A78D6", "#A3A19A", "#D03B3B"
SEQ = {"100": "#CDE2FB", "250": "#86B6EF", "350": "#5598E7", "450": "#2A78D6", "650": "#104281"}
NEUTRAL, RED_TINT, BLUE_TINT = "#F0EFEC", "#F4C7C6", "#B7D3F6"
AUTHOR = "Independent case study based on public and synthetic data · not affiliated with any bank or consultancy"
NS = uuid.UUID("8f0c1d52-7d1e-4f4e-9a59-2f3c0b6a1e11")


def tag(*parts):
    """Deterministic lineage tag, so that rebuilding the model does not create spurious diffs."""
    return str(uuid.uuid5(NS, "|".join(parts)))


# ---------- expression helpers ----------
def raw(v):
    if isinstance(v, bool):
        s = "true" if v else "false"
    elif isinstance(v, (int, float)):
        s = f"{v}D"
    else:
        s = "'" + str(v).replace("'", "''") + "'"
    return {"Literal": {"Value": s}}

def lit(v):
    return {"expr": raw(v)}

def color(hexv):
    return {"solid": {"color": lit(hexv)}}

def col(table, column):
    return {"Column": {"Expression": {"SourceRef": {"Entity": table}}, "Property": column}}

def meas(name):
    return {"Measure": {"Expression": {"SourceRef": {"Entity": M}}, "Property": name}}

def agg_sum(table, column):
    return {"Aggregation": {"Expression": col(table, column), "Function": 0}}

def qref(field):
    if "Column" in field:
        c = field["Column"]
        return f'{c["Expression"]["SourceRef"]["Entity"]}.{c["Property"]}'
    if "Measure" in field:
        return f'{M}.{field["Measure"]["Property"]}'
    c = field["Aggregation"]["Expression"]["Column"]
    return f'Sum({c["Expression"]["SourceRef"]["Entity"]}.{c["Property"]})'

def proj(field, label=None):
    p = {"field": field, "queryRef": qref(field)}
    if "Column" in field:
        p["nativeQueryRef"] = field["Column"]["Property"]
    elif "Measure" in field:
        p["nativeQueryRef"] = field["Measure"]["Property"]
    else:
        p["nativeQueryRef"] = "Sum of " + field["Aggregation"]["Expression"]["Column"]["Property"]
        p["displayName"] = field["Aggregation"]["Expression"]["Column"]["Property"]
    if label:
        p["displayName"] = label
    return p

def C(t, c): return col(t, c)
def Ms(*names): return [meas(n) for n in names]

def series_color(field, hexv):
    return {"properties": {"fill": color(hexv)}, "selector": {"metadata": qref(field)}}

def ref_line(value, label, hexv=INK2, selector_id="1"):
    v = {"expr": value} if isinstance(value, dict) else lit(value)
    return {"properties": {"show": lit(True), "value": v, "displayName": lit(label), "lineColor": color(hexv),
                           "style": lit("dashed"), "dataLabelShow": lit(True), "dataLabelColor": color(hexv)},
            "selector": {"id": selector_id}}

def bg_rule(field, lo, hi, mid=None, mid_value=None):
    """Background-colour scale (conditional formatting) on a table/matrix value column."""
    rule = {"min": {"color": raw(lo)}, "max": {"color": raw(hi)},
            "nullColoringStrategy": {"strategy": raw("asZero")}}
    key = "linearGradient2"
    if mid:
        key = "linearGradient3"
        rule["mid"] = {"color": raw(mid)}
        if mid_value is not None:
            rule["mid"]["value"] = raw(mid_value)
    return {"properties": {"backColor": {"solid": {"color": {"expr": {"FillRule": {"Input": field, "FillRule": {key: rule}}}}}}},
            "selector": {"data": [{"dataViewWildcard": {"matchingOption": 1}}], "metadata": qref(field)}}


def table_style(extra_values=(), matrix=False):
    """Readable table: 12pt text, no misleading total row/column."""
    fs = {"properties": {"fontSize": lit(12)}}
    objs = {"values": [fs, *extra_values], "columnHeaders": [{"properties": {"fontSize": lit(12), "fontColor": color(INK2)}}]}
    if matrix:
        objs["rowHeaders"] = [fs]
        objs["subTotals"] = [{"properties": {"rowSubtotals": lit(False), "columnSubtotals": lit(False)}}]
    else:
        objs["total"] = [{"properties": {"totals": lit(False)}}]
    return objs


# ---------- page / visual builders ----------
class Page:
    def __init__(self, pid, name):
        self.pid, self.name, self.visuals, self.interactions, self.n = pid, name, [], [], 0

    def _add(self, vid, x, y, w, h, visual):
        self.n += 1
        self.visuals.append({"$schema": VC_SCHEMA, "name": vid,
                             "position": {"x": round(x), "y": round(y), "z": self.n * 1000,
                                          "height": round(h), "width": round(w), "tabOrder": self.n * 1000},
                             "visual": visual})
        return vid

    def chart(self, vid, vtype, x, y, w, h, roles, title=None, objects=None, labels=None,
              sort=None, exclude_organic=False, only=None):
        labels = labels or {}
        visual = {"visualType": vtype,
                  "query": {"queryState": {r: {"projections": [proj(f, labels.get(qref(f))) for f in fs]}
                                           for r, fs in roles.items() if fs}},
                  "drillFilterOtherVisuals": True}
        if sort:
            field, direction = sort
            visual["query"]["sortDefinition"] = {"sort": [{"field": field, "direction": direction}],
                                                 "isDefaultSort": False}
        if objects:
            visual["objects"] = objects
        vco = {"subTitle": [{"properties": {"show": lit(False)}}]}
        vco["title"] = [{"properties": {"show": lit(bool(title)), **({"text": lit(title)} if title else {})}}]
        visual["visualContainerObjects"] = vco
        vid = self._add(vid, x, y, w, h, visual)
        if exclude_organic:
            only = ("Channel", "channel", ["Organic"], True)
        if only:
            table, column, values, negate = only
            cond = {"In": {"Expressions": [{"Column": {"Expression": {"SourceRef": {"Source": "t"}}, "Property": column}}],
                           "Values": [[raw(v)] for v in values]}}
            if negate:
                cond = {"Not": {"Expression": cond}}
            self.visuals[-1]["filterConfig"] = {"filters": [{
                "name": "visualFilter", "type": "Categorical", "field": col(table, column),
                "filter": {"Version": 2, "From": [{"Name": "t", "Entity": table, "Type": 0}],
                           "Where": [{"Condition": cond}]}}]}
        return vid

    def text(self, vid, x, y, w, h, paragraphs, boxed=False):
        """paragraphs: list of paragraphs; each paragraph = list of (text, size, colour, bold) runs."""
        paras = [{"textRuns": [{"value": t, "textStyle": {"fontSize": f"{s}pt", "color": c,
                                                         **({"fontWeight": "bold"} if b else {})}}
                               for t, s, c, b in runs]} for runs in paragraphs]
        visual = {"visualType": "textbox",
                  "objects": {"general": [{"properties": {"paragraphs": paras}}]},
                  "visualContainerObjects": {"background": [{"properties": {"show": lit(boxed)}}],
                                             "border": [{"properties": {"show": lit(boxed)}}],
                                             **({"padding": [{"properties": {"top": lit(16), "bottom": lit(16),
                                                                             "left": lit(20), "right": lit(20)}}]}
                                                if boxed else {})}}
        return self._add(vid, x, y, w, h, visual)

    def header(self, title, conclusion, tag):
        self.text("title", 32, 20, 1500, 56, [[(title, 24, INK, True)]])
        self.text("tag", 1540, 28, 348, 40, [[(tag, 10, INK2, True)]])
        self.text("conclusion", 32, 76, 1856, 64, [[(conclusion, 13, INK2, False)]])

    def footer(self, source):
        self.text("footer", 32, 1040, 1856, 32, [[(source + "   ·   " + AUTHOR, 9, MUTED, False)]])

    def slicer(self, vid, x, y, w, h, field, title, dropdown=True, single=False):
        objs = {"header": [{"properties": {"show": lit(False)}}]}
        if dropdown:
            objs["data"] = [{"properties": {"mode": lit("Dropdown")}}]
        if single:
            objs["selection"] = [{"properties": {"singleSelect": lit(True), "strictSingleSelect": lit(True)}}]
        return self.chart(vid, "slicer", x, y, w, h, {"Values": [field]}, title, objs)

    def card(self, vid, x, y, w, h, measure, title, only=None):
        return self.chart(vid, "card", x, y, w, h, {"Values": [meas(measure)]}, title,
                          {"labels": [{"properties": {"color": color(INK), "fontSize": lit(28)}}],
                           "categoryLabels": [{"properties": {"show": lit(False)}}]}, only=only)

    def no_filter(self, source, target):
        self.interactions.append({"source": source, "target": target, "type": "NoFilter"})

    def write(self):
        d = PAGES / self.pid
        if d.exists():
            shutil.rmtree(d)
        (d / "visuals").mkdir(parents=True)
        page = {"$schema": PAGE_SCHEMA, "name": self.pid, "displayName": self.name,
                "displayOption": "FitToPage", "height": 1080, "width": 1920}
        if self.interactions:
            page["visualInteractions"] = self.interactions
        (d / "page.json").write_text(json.dumps(page, indent=2, ensure_ascii=False), encoding="utf-8")
        for v in self.visuals:
            vd = d / "visuals" / v["name"]
            vd.mkdir()
            (vd / "visual.json").write_text(json.dumps(v, indent=2, ensure_ascii=False), encoding="utf-8")


# ---------- layout grid ----------
L, R, TOP, BOT, GAP = 32, 1888, 156, 1028, 24
W = R - L

def cols(n, x0=L, x1=R):
    w = (x1 - x0 - (n - 1) * GAP) / n
    return [(x0 + i * (w + GAP), w) for i in range(n)]

def kpi_row(p, items, y=TOP, h=120, x0=L, x1=R, only=None):
    for (x, w), (m, t) in zip(cols(len(items), x0, x1), items):
        p.card("kpi_" + "".join(ch for ch in m if ch.isalnum())[:30], x, y, w, h, m, t, only=only)
    return y + h + GAP



# ============================================================== 1. data export
def export():
    DATA.mkdir(parents=True, exist_ok=True)
    con = duckdb.connect(str(ROOT / "data" / "parquet" / "work.duckdb"), read_only=True)
    alerts = con.execute("""
        SELECT 'current rules' AS scenario, a.rule_id, a.day,
               CAST(floor(datediff('day', (SELECT d0 FROM period), a.day) / 7) + 1 AS INTEGER) AS wk,
               c.segment, a.is_tp, a.payroll_driven, d.decision, d.handling_minutes
        FROM alerts a JOIN dispositions d USING (alert_id) JOIN customers c USING (customer_id)
        UNION ALL
        SELECT 'after proposals', t.rule_id, t.day, t.wk, b.segment, t.is_tp, t.payroll_driven, NULL, NULL
        FROM alerts_tuned t JOIN book b USING (acct_key)""").df()
    con.close()
    tables = {
        "alerts": alerts,
        "rule_performance": pd.read_csv(OUT / "rule_performance.csv"),
        "controls": pd.read_csv(OUT / "controls_report.csv"),
        "feed_quality": pd.read_csv(OUT / "null_rate_by_feed_day.csv"),
        "capacity": pd.read_csv(OUT / "capacity_weekly.csv"),
        "coverage_matrix": pd.read_csv(OUT / "typology_coverage_matrix.csv"),
        "typology_coverage": pd.read_csv(OUT / "network_typology_coverage.csv"),
        "atl_btl": pd.read_csv(OUT / "atl_btl_curve.csv"),
        "model_metrics": pd.read_csv(OUT / "model_metrics.csv"),
        "model_capacity": pd.read_csv(OUT / "model_capacity.csv"),
        "model_simpson": pd.read_csv(OUT / "model_simpson.csv"),
        "system": pd.read_csv(OUT / "system_summary.csv"),
        "rule": pd.read_parquet(SIM / "rules_implemented.parquet")[["rule_id", "name", "typology", "threshold", "lookback_days"]],
        "week": pd.DataFrame({"wk": [1, 2, 3], "week_label": ["Week 1 (1-7 Sep)", "Week 2 (8-14 Sep)", "Week 3 (15-16 Sep)"]}),
        "segment": pd.DataFrame({"segment": ["retail", "sme", "corporate"]}),
        "typology": pd.DataFrame({"typology": sorted(pd.read_csv(OUT / "typology_coverage.csv").typology)}),
    }
    for k, d in tables.items():
        d.to_csv(DATA / f"{k}.csv", index=False)
    return tables


# ============================================================== 2. semantic model (TMDL)
TABLE_NAMES = {"alerts": "Alerts", "rule_performance": "Rule Performance", "controls": "Controls", "feed_quality": "Feed Quality",
               "capacity": "Capacity", "coverage_matrix": "Coverage Matrix", "typology_coverage": "Typology Coverage",
               "atl_btl": "ATL BTL", "model_metrics": "Model Metrics", "model_capacity": "Model Capacity",
               "model_simpson": "Model Simpson", "system": "System", "rule": "Rule", "week": "Week", "segment": "Segment",
               "typology": "Typology"}
PCT_COLS = {"precision", "recall", "share_of_alerts", "share_detected", "rules_now", "tuned_rules", "r13_alone",
            "tuned_rules_plus_r13", "null_rate", "load_implemented", "load_tuned", "recall_accounts", "base_rate_account_days"}

MEASURES = [
    ("Alert Volume", "COUNTROWS ( Alerts )", "#,0", "Alerts"),
    ("True Positives", "SUM ( Alerts[is_tp] )", "#,0", "Alerts"),
    ("Precision", "DIVIDE ( [True Positives], [Alert Volume] )", "0.0%", "Alerts"),
    ("Recall", "DIVIDE ( SUM ( 'Rule Performance'[tp_accounts] ), MAX ( System[laundering_accounts] ) )", "0.0%", "Alerts"),
    ("Alerts per Analyst Hour", "DIVIDE ( [Alert Volume], SUM ( Capacity[hours_available] ) )", "0.0", "Capacity"),
    ("Capacity Load", "DIVIDE ( [Alert Volume], SUM ( Capacity[alert_capacity] ) )", "0.00x", "Capacity"),
    ("Alert Capacity", "SUM ( Capacity[alert_capacity] )", "#,0", "Capacity"),
    ("Coverage %", "AVERAGE ( 'Typology Coverage'[rules_now] )", "0%", "Coverage"),
    ("Coverage after R13 %", "AVERAGE ( 'Typology Coverage'[tuned_rules_plus_r13] )", "0%", "Coverage"),
    ("Detection Share", "AVERAGE ( 'Coverage Matrix'[share_detected] )", "0%", "Coverage"),
    ("Control Fail Rate", "DIVIDE ( COUNTROWS ( FILTER ( Controls, Controls[status] = \"FAIL\" ) ), COUNTROWS ( Controls ) )", "0%", "Data quality"),
    ("Controls Failing", "COUNTROWS ( FILTER ( Controls, Controls[status] = \"FAIL\" ) )", "0", "Data quality"),
    ("Max Null Rate", "MAX ( 'Feed Quality'[null_rate] )", "0.0%", "Data quality"),
    ("Challenger Precision", "MAX ( 'Model Simpson'[precision] )", "0%", "Model"),
]


def dtype(s):
    if pd.api.types.is_bool_dtype(s):
        return "boolean", "type logical"
    if pd.api.types.is_integer_dtype(s):
        return "int64", "Int64.Type"
    if pd.api.types.is_float_dtype(s):
        return "double", "type number"
    return "string", "type text"


def table_tmdl(key, df):
    t = TABLE_NAMES[key]
    q = f"'{t}'" if " " in t else t
    lines = [f"table {q}", f"\tlineageTag: {tag('t', t)}", ""]
    types = []
    for c in df.columns:
        dt, mt = dtype(df[c])
        if c in ("day",):
            dt, mt = "dateTime", "type date"
        fmt = "0.0%" if c in PCT_COLS else ("#,0" if dt == "int64" else ("#,0.00" if dt == "double" else None))
        lines += [f"\tcolumn {c}", f"\t\tdataType: {dt}"]
        if fmt and dt != "dateTime":
            lines.append(f"\t\tformatString: {fmt}")
        if dt == "dateTime":
            lines.append("\t\tformatString: dd mmm yyyy")
        lines += [f"\t\tlineageTag: {tag('c', t, c)}", "\t\tsummarizeBy: none", f"\t\tsourceColumn: {c}", ""]
        types.append(f'{{"{c}", {mt}}}')
    lines += [f"\tpartition {q} = m", "\t\tmode: import", "\t\tsource =", "\t\t\t\tlet",
              f'\t\t\t\t\tSource = Csv.Document(File.Contents(DataFolder & "{key}.csv"), [Delimiter=",", Encoding=65001, QuoteStyle=QuoteStyle.Csv]),',
              "\t\t\t\t\tPromoted = Table.PromoteHeaders(Source, [PromoteAllScalars=true]),",
              f'\t\t\t\t\tTyped = Table.TransformColumnTypes(Promoted, {{{", ".join(types)}}}, "en-US")',
              "\t\t\t\tin", "\t\t\t\t\tTyped", ""]
    return "\n".join(lines)


def measures_tmdl():
    lines = [f"table {M}", f"\tlineageTag: {tag('t', M)}", ""]
    for name, expr, fmt, folder in MEASURES:
        n = f"'{name}'" if any(ch in name for ch in " %") else name
        lines += [f"\tmeasure {n} = {expr}", f"\t\tformatString: {fmt}", f"\t\tdisplayFolder: {folder}",
                  f"\t\tlineageTag: {tag('m', name)}", ""]
    lines += ["\tcolumn _", "\t\tdataType: string", "\t\tisHidden", f"\t\tlineageTag: {tag('c', M, '_')}", "\t\tsummarizeBy: none",
              "\t\tsourceColumn: _", "", f"\tpartition {M} = m", "\t\tmode: import", "\t\tsource = #table(type table [_ = text], {})", ""]
    return "\n".join(lines)


RELS = [("Alerts", "rule_id", "Rule", "rule_id"), ("Alerts", "wk", "Week", "wk"), ("Alerts", "segment", "Segment", "segment"),
        ("Rule Performance", "rule_id", "Rule", "rule_id"), ("Capacity", "wk", "Week", "wk"),
        ("Coverage Matrix", "rule_id", "Rule", "rule_id"), ("Coverage Matrix", "typology", "Typology", "typology"),
        ("Typology Coverage", "typology", "Typology", "typology"), ("ATL BTL", "rule_id", "Rule", "rule_id")]


def write_model(tables):
    if MODEL.exists():
        shutil.rmtree(MODEL)
    d = MODEL / "definition" / "tables"
    d.mkdir(parents=True)
    (MODEL / "definition.pbism").write_text(json.dumps({"version": "4.2", "settings": {}}, indent=2), encoding="utf-8")
    (MODEL / ".platform").write_text(json.dumps({
        "$schema": "https://developer.microsoft.com/json-schemas/fabric/gitIntegration/platformProperties/2.0.0/schema.json",
        "metadata": {"type": "SemanticModel", "displayName": NAME}, "config": {"version": "2.0", "logicalId": tag("model")}}, indent=2), encoding="utf-8")
    (MODEL / "definition" / "database.tmdl").write_text("database\n\tcompatibilityLevel: 1606\n\n", encoding="utf-8")
    names = [TABLE_NAMES[k] for k in tables] + [M]
    refs = "\n".join(f"ref table {repr(n) if ' ' in n else n}".replace('"', "'") for n in names)
    (MODEL / "definition" / "model.tmdl").write_text(
        "model Model\n\tculture: en-US\n\tdefaultPowerBIDataSourceVersion: powerBI_V3\n\tsourceQueryCulture: en-US\n"
        "\tdataAccessOptions\n\t\tlegacyRedirects\n\t\treturnErrorValuesAsNull\n\n"
        "annotation __PBI_TimeIntelligenceEnabled = 0\n\n" + refs + "\n", encoding="utf-8")
    (MODEL / "definition" / "expressions.tmdl").write_text(
        'expression DataFolder = "C:\\aml-transaction-monitoring-tuning-case-study\\powerbi\\data\\" '
        'meta [IsParameterQuery=true, Type="Text", IsParameterQueryRequired=true]\n'
        f"\tlineageTag: {tag('e', 'DataFolder')}\n\n\tannotation PBI_ResultType = Text\n\n", encoding="utf-8")
    for k, df in tables.items():
        (d / f"{TABLE_NAMES[k]}.tmdl").write_text(table_tmdl(k, df), encoding="utf-8")
    (d / f"{M}.tmdl").write_text(measures_tmdl(), encoding="utf-8")
    rel = []
    for i, (ft, fc, tt, tc) in enumerate(RELS, 1):
        q = lambda t: f"'{t}'" if " " in t else t
        rel += [f"relationship rel_{i:02d}", f"\tfromColumn: {q(ft)}.{fc}", f"\ttoColumn: {q(tt)}.{tc}", ""]
    (MODEL / "definition" / "relationships.tmdl").write_text("\n".join(rel), encoding="utf-8")


# ============================================================== 3. report (PBIR)
def write_report_shell():
    # report.json (theme settings) and StaticResources (theme files) are versioned in the repository
    for need in [REPORT / "definition" / "report.json", REPORT / "StaticResources"]:
        if not need.exists():
            raise FileNotFoundError(f"{need} is missing: restore it from the repository")
    (REPORT / "definition" / "version.json").write_text(json.dumps({
        "$schema": "https://developer.microsoft.com/json-schemas/fabric/item/report/definition/versionMetadata/1.0.0/schema.json",
        "version": "2.0.0"}, indent=2), encoding="utf-8")
    (REPORT / "definition.pbir").write_text(json.dumps({"version": "4.0", "datasetReference": {"byPath": {"path": f"../{NAME}.SemanticModel"}}}, indent=2), encoding="utf-8")
    (REPORT / ".platform").write_text(json.dumps({
        "$schema": "https://developer.microsoft.com/json-schemas/fabric/gitIntegration/platformProperties/2.0.0/schema.json",
        "metadata": {"type": "Report", "displayName": NAME}, "config": {"version": "2.0", "logicalId": tag("report")}}, indent=2), encoding="utf-8")
    (PBI / f"{NAME}.pbip").write_text(json.dumps({"version": "1.0", "artifacts": [{"report": {"path": f"{NAME}.Report"}}],
                                                  "settings": {"enableAutoRecovery": True}}, indent=2), encoding="utf-8")


SRC_IBM = "Data: IBM AML benchmark (PUBLIC DATA, synthetic) · Bank N layer SIMULATED · country tiers ILLUSTRATIVE"


def pages():
    out = []
    A = "Alerts"
    # ---- 1 Overview
    p = Page("a1000000000000000001", "1 · Overview")
    p.header("Bank N generates 1.6x more alerts than its analysts can review, and sees 15% of laundering attempts",
             "Current rules vs the proposals (code fixes, threshold tuning, payroll exclusion). Truth = IBM labels.", "SIMULATED · PUBLIC DATA (synthetic)")
    y = kpi_row(p, [("Alert Volume", "Alerts (16 days)"), ("Precision", "Precision"), ("Coverage %", "Typology coverage"),
                    ("Controls Failing", "Controls failing (of 15)")])
    p.slicer("slicer_scenario", L, y, 400, 60, C(A, "scenario"), "Scenario", single=True)
    y += 60 + GAP
    (xa, wa), (xb, wb) = cols(2)
    p.chart("alertsByWeek", "clusteredColumnChart", xa, y, wa, BOT - y,
            {"Category": [C("Week", "week_label")], "Y": Ms("Alert Volume", "Alert Capacity")},
            "Alerts per week vs analyst capacity", {"dataPoint": [series_color(meas("Alert Volume"), BLUE), series_color(meas("Alert Capacity"), RED)]})
    p.chart("alertsByRule", "clusteredBarChart", xb, y, wb, BOT - y,
            {"Category": [C("Rule", "name")], "Y": Ms("Alert Volume")}, "Alerts by rule",
            {"dataPoint": [{"properties": {"fill": color(BLUE)}}]}, sort=(meas("Alert Volume"), "Descending"))
    p.footer(SRC_IBM)
    out.append(p)
    # ---- 2 Data quality
    p = Page("a1000000000000000002", "2 · Data quality")
    p.header("5 of 15 automated controls fail: the ACH feed loses the beneficiary bank from 9 Sep",
             "Controls declared in controls/controls.yaml, evaluated by src/controls.py. Null rate by feed and day below.", "SIMULATED")
    y = kpi_row(p, [("Control Fail Rate", "Control fail rate"), ("Max Null Rate", "Worst feed-day null rate")])
    (xa, wa), (xb, wb) = cols(2)
    p.chart("nullRate", "lineChart", xa, y, wa, BOT - y,
            {"Category": [C("Feed Quality", "day")], "Y": Ms("Max Null Rate"), "Series": [C("Feed Quality", "payment_format")]},
            "Beneficiary bank missing, share of rows by feed and day")
    p.chart("controlsTable", "tableEx", xb, y, wb, BOT - y,
            {"Values": [C("Controls", c) for c in ["control_id", "name", "status", "detail", "owner"]]}, "Automated controls", table_style())
    p.footer("Bank N feed = IBM AML (synthetic) + SIMULATED feed layer; KYC file SIMULATED")
    out.append(p)
    # ---- 3 Rules & coverage
    p = Page("a1000000000000000003", "3 · Rules & coverage")
    p.header("3 of 12 rules do not match their documentation, and no rule targets cycles or scatter-gather",
             "Precision and recall per rule as documented and as implemented; share of visible laundering attempts detected.", "SIMULATED · PUBLIC DATA (synthetic)")
    (xa, wa), (xb, wb) = cols(2)
    p.chart("precisionByRule", "clusteredColumnChart", xa, TOP, wa, BOT - TOP,
            {"Category": [C("Rule", "rule_id")], "Y": [agg_sum("Rule Performance", "precision")], "Series": [C("Rule Performance", "ruleset")]},
            "Precision by rule: documented vs implemented (R07 tiers ILLUSTRATIVE)")
    p.chart("coverageMatrix", "pivotTable", xb, TOP, wb, BOT - TOP,
            {"Rows": [C("Typology", "typology")], "Columns": [C("Rule", "rule_id")], "Values": Ms("Detection Share")},
            "Visible attempts detected, typology x rule",
            table_style([bg_rule(meas("Detection Share"), "#FCFCFB", SEQ["450"])], matrix=True))
    p.footer(SRC_IBM)
    out.append(p)
    # ---- 4 Tuning & capacity
    p = Page("a1000000000000000004", "4 · Tuning & capacity")
    p.header("Fixes and ATL/BTL tuning cut alerts by 65% and bring a normal week under capacity",
             "Above the line: what raising a threshold loses. Below the line: what lowering it finds. R13 = new network scenario.", "SIMULATED")
    y = kpi_row(p, [("Capacity Load", "Alerts / capacity"), ("Alerts per Analyst Hour", "Alerts per analyst hour"),
                    ("Coverage after R13 %", "Coverage with R13")])
    (xa, wa), (xb, wb) = cols(2)
    p.chart("atlBtl", "lineChart", xa, y, wa, BOT - y,
            {"Category": [C("ATL BTL", "mult")], "Y": [agg_sum("ATL BTL", "alerts_per_week")], "Series": [C("ATL BTL", "rule_id")]},
            "Alerts per week by threshold multiplier (1 = current)")
    p.chart("atlTable", "tableEx", xb, y, wb, BOT - y,
            {"Values": [C("ATL BTL", c) for c in ["rule_id", "mult", "threshold", "alerts_per_week", "tp_accounts", "lost_unique_tp_accounts"]]},
            "ATL/BTL detail (unique = found by no other rule)", table_style())
    p.footer("Rules, alerts and capacity SIMULATED (12 analysts, 30 h/week, 12 min per alert)")
    out.append(p)
    # ---- 5 Challenger model
    p = Page("a1000000000000000005", "5 · Challenger model")
    p.header("Validated honestly, the challenger scores AUC 0.94 (not 0.99) and finds 46% of laundering accounts at capacity",
             "Leakage check, temporal validation (train 1-10 Sep, test 11-16 Sep), Simpson's paradox by segment and risk tier.", "SIMULATED")
    (xa, wa), (xb, wb), (xc, wc) = cols(3)
    p.chart("modelMetrics", "tableEx", xa, TOP, wa, BOT - TOP,
            {"Values": [C("Model Metrics", c) for c in ["version", "validation", "roc_auc", "avg_precision"]]}, "Leaky draft vs challenger", table_style())
    p.chart("modelCapacity", "clusteredBarChart", xb, TOP, wb, BOT - TOP,
            {"Category": [C("Model Capacity", "approach")], "Y": [agg_sum("Model Capacity", "recall_accounts")]}, "Laundering accounts found (test days)",
            {"dataPoint": [{"properties": {"fill": color(BLUE)}}]})
    p.chart("simpson", "pivotTable", xc, TOP, wc, BOT - TOP,
            {"Rows": [C("Model Simpson", "segment")], "Columns": [C("Model Simpson", "risk_rating")], "Values": Ms("Challenger Precision")},
            "Precision by segment and risk tier (Simpson's paradox)", table_style([bg_rule(meas("Challenger Precision"), "#FCFCFB", SEQ["450"])], matrix=True))
    p.footer("Labels IBM AML (synthetic); segments and risk ratings SIMULATED (not model inputs)")
    out.append(p)
    return out


def write_pages():
    if PAGES.exists():
        shutil.rmtree(PAGES)
    PAGES.mkdir(parents=True)
    ps = pages()
    for pg in ps:
        pg.write()
    meta = {"$schema": PAGES_SCHEMA, "pageOrder": [pg.pid for pg in ps], "activePageName": ps[0].pid}
    (PAGES / "pages.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")
    return ps


def measures_doc():
    lines = ["# Power BI measures", "", "Model: `powerbi/AmlTmAssessment.SemanticModel` (TMDL). Each DAX measure, in plain words.", "",
             "| Measure | DAX | What it means |", "|---|---|---|"]
    plain = {
        "Alert Volume": "Number of alerts in the current filter (scenario, week, rule, segment).",
        "True Positives": "Alerts raised on an account that sent or received a laundering-labelled transfer in the rule's lookback window.",
        "Precision": "Share of alerts that are true positives.",
        "Recall": "Laundering accounts caught by the rule(s) divided by all laundering accounts in Bank N's book.",
        "Alerts per Analyst Hour": "Alerts divided by the analyst hours available in the period.",
        "Capacity Load": "Alerts divided by what 12 analysts can review (1.0 = exactly at capacity).",
        "Alert Capacity": "Alerts the team can review in the period (hours x 60 / 12 minutes).",
        "Coverage %": "Average share of visible laundering attempts detected by the current rules, across typologies.",
        "Coverage after R13 %": "Same, with the tuned rules plus the new network scenario R13.",
        "Detection Share": "Share of visible attempts of a typology detected by a rule (cell of the coverage matrix).",
        "Control Fail Rate": "Share of automated controls in FAIL status.",
        "Controls Failing": "Number of automated controls in FAIL status.",
        "Max Null Rate": "Highest share of rows without a beneficiary bank, by feed and day.",
        "Challenger Precision": "Precision of the challenger's capacity-limited queue for a segment / risk-tier cell.",
    }
    for name, expr, fmt, folder in MEASURES:
        lines.append(f"| {name} | `{expr.replace('|', '¦')}` | {plain[name]} |")
    lines += ["", "Data: `powerbi/data/*.csv`, exported by `src/build_powerbi.py`. Set the `DataFolder` parameter to the full path of",
              "`powerbi/data/` in your clone, then refresh. No `.pbix` is stored in the repository."]
    (ROOT / "docs" / "powerbi_measures.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def main():
    t = export()
    write_model(t)
    write_report_shell()
    ps = write_pages()
    measures_doc()
    print("Power BI project:", f"{len(t)} tables, {len(MEASURES)} measures, pages", [(p.name, len(p.visuals)) for p in ps])


if __name__ == "__main__":
    main()
