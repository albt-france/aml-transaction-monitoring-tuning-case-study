"""Shared DuckDB helpers. The working database data/parquet/work.duckdb holds raw keys and is never published."""
import re
from pathlib import Path

import duckdb
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
PARQ = ROOT / "data" / "parquet"
SIM = ROOT / "data" / "sim"
SQL = ROOT / "sql"
OUT = ROOT / "output"
DB = PARQ / "work.duckdb"


def connect(read_only=False):
    con = duckdb.connect(str(DB), read_only=read_only)
    con.execute("SET preserve_insertion_order=false")
    return con


def render(sql: str, **kw) -> str:
    kw = {"PARQ": PARQ.as_posix(), "SIM": SIM.as_posix(), "OUT": OUT.as_posix(), **kw}
    for k, v in kw.items():
        sql = sql.replace("{" + k + "}", str(v))
    return sql


def statements(path: Path, **kw):
    """Split a .sql file into (name, statement) pairs. A '-- name: x' line names the next statement's output."""
    text = render(path.read_text(encoding="utf-8"), **kw)
    out, name, buf = [], None, []
    for line in text.splitlines():
        m = re.match(r"--\s*name:\s*(\S+)", line)
        if m:
            name = m.group(1)
            continue
        buf.append(line)
        if line.rstrip().endswith(";"):
            stmt = "\n".join(buf).strip()
            if re.sub(r"--[^\n]*", "", stmt).strip(" ;\n"):
                out.append((name, stmt))
            name, buf = None, []
    return out


def run_file(con, path: Path, save=True, **kw) -> dict:
    """Execute a .sql file. Named SELECT statements are saved to output/<name>.csv and returned."""
    res = {}
    for name, stmt in statements(path, **kw):
        if name:
            df = con.execute(stmt).df()
            res[name] = df
            if save:
                OUT.mkdir(exist_ok=True)
                df.to_csv(OUT / f"{name}.csv", index=False)
        else:
            con.execute(stmt)
    return res


def q(con, sql: str) -> pd.DataFrame:
    return con.execute(render(sql)).df()
