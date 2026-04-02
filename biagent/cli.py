"""
BIAgent CLI – compute vehicle/fuel-cell/battery energy & hydrogen metrics
from 1-second sampled CSV logs using a YAML metrics DSL backed by DuckDB.

Usage:
    python -m biagent.cli data1.csv [data2.csv ...] [--metrics config/metrics.yaml]
                                     [--stk-cell-count N] [--stk-h2-corr 0.985]
                                     [--output-dir ./results]
"""

from __future__ import annotations

import argparse
import csv
import os
import re
import sys
from pathlib import Path
from typing import Any, Optional

import duckdb
import yaml


# SQL reserved words that must not be replaced by CSV column name resolution
_SQL_RESERVED = frozenset(
    """
    select from where group by having order limit offset union intersect except
    with as join inner outer left right full cross on using
    insert update delete create drop alter table view index
    case when then else end
    and or not in is null like between exists any all
    true false
    count sum avg min max coalesce nullif try_cast cast
    double integer bigint varchar text float real boolean date timestamp
    asc desc distinct
    pragma
    """.split()
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def load_metrics(metrics_path: str) -> list[dict]:
    with open(metrics_path, encoding="utf-8") as f:
        data = yaml.safe_load(f)
    return data.get("metrics", [])


def substitute_params(sql: str, params: dict[str, Any]) -> str:
    """Replace {{key}} placeholders with their values."""
    for key, value in params.items():
        sql = sql.replace("{{" + key + "}}", str(value))
    return sql


def resolve_columns(csv_columns: list[str], sql: str) -> str:
    """
    Case-insensitive column name resolution.
    For every identifier in the SQL that matches a CSV column name
    (case-insensitively) and is not an SQL reserved word, replace it
    with the actual CSV column name so DuckDB can find it.
    """
    col_map: dict[str, str] = {c.lower(): c for c in csv_columns}

    def replacer(match: re.Match) -> str:
        word = match.group(0)
        lower = word.lower()
        if lower in _SQL_RESERVED:
            return word
        actual = col_map.get(lower)
        return actual if actual else word

    # Match word-boundary identifiers (letters, digits, underscores)
    return re.sub(r"\b[A-Za-z_]\w*\b", replacer, sql)


def run_metrics(
    csv_path: str,
    metrics: list[dict],
    params: dict[str, Any],
) -> list[dict]:
    """Load a CSV into DuckDB as table 't', run every metric SQL, return rows."""
    con = duckdb.connect()
    con.execute(f"CREATE TABLE t AS SELECT * FROM read_csv_auto('{csv_path}', header=True)")
    csv_columns: list[str] = [row[1] for row in con.execute("PRAGMA table_info('t')").fetchall()]

    results = []
    for metric in metrics:
        metric_id = metric.get("id", "")
        sql_template: str = metric.get("prompt_sql", "")
        if not sql_template:
            continue
        sql = substitute_params(sql_template.strip(), params)
        sql = resolve_columns(csv_columns, sql)
        try:
            rows = con.execute(sql).fetchall()
            for row in rows:
                results.append({
                    "metric_id": row[0],
                    "metric_name": row[1],
                    "metric_value": row[2],
                    "metric_unit": row[3],
                })
        except duckdb.Error as exc:
            results.append({
                "metric_id": metric_id,
                "metric_name": metric.get("name", ""),
                "metric_value": f"ERROR: {exc}",
                "metric_unit": metric.get("unit", ""),
            })
    con.close()
    return results


def write_csv(rows: list[dict], out_path: str) -> None:
    if not rows:
        return
    os.makedirs(os.path.dirname(out_path) or ".", exist_ok=True)
    with open(out_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=["metric_id", "metric_name", "metric_value", "metric_unit"])
        writer.writeheader()
        writer.writerows(rows)


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="BIAgent: compute vehicle energy & hydrogen metrics from CSV logs."
    )
    parser.add_argument("csv_files", nargs="+", help="Input CSV file(s)")
    parser.add_argument(
        "--metrics",
        default=str(Path(__file__).parent.parent / "config" / "metrics.yaml"),
        help="Path to metrics YAML (default: config/metrics.yaml)",
    )
    parser.add_argument(
        "--stk-cell-count",
        type=int,
        default=None,
        help="Stack cell count (integer). Prompted if not provided.",
    )
    parser.add_argument(
        "--stk-h2-corr",
        type=float,
        default=0.985,
        help="H2 correction factor (default: 0.985)",
    )
    parser.add_argument(
        "--output-dir",
        default="results",
        help="Output directory for result CSVs (default: results/)",
    )
    return parser


def prompt_stk_cell_count() -> int:
    while True:
        raw = input("请输入电堆片数 (stk_cell_count, 整数): ").strip()
        try:
            value = int(raw)
            if value > 0:
                return value
        except ValueError:
            pass
        print("  输入无效，请重新输入正整数。")


def main(argv: Optional[list[str]] = None) -> None:
    parser = build_parser()
    args = parser.parse_args(argv)

    # Resolve stk_cell_count
    stk_cell_count: int = args.stk_cell_count
    if stk_cell_count is None:
        stk_cell_count = prompt_stk_cell_count()

    params = {
        "stk_cell_count": stk_cell_count,
        "stk_h2_corr": args.stk_h2_corr,
    }

    metrics = load_metrics(args.metrics)
    print(f"已加载 {len(metrics)} 个指标 from {args.metrics}")

    all_results: list[dict] = []

    for csv_file in args.csv_files:
        print(f"\n处理文件: {csv_file}")
        rows = run_metrics(csv_file, metrics, params)
        stem = Path(csv_file).stem
        out_path = os.path.join(args.output_dir, f"{stem}_result.csv")
        write_csv(rows, out_path)
        print(f"  → 结果已写入: {out_path}")
        all_results.extend(rows)

    if len(args.csv_files) > 1:
        combined_path = os.path.join(args.output_dir, "combined_result.csv")
        write_csv(all_results, combined_path)
        print(f"\n合并结果已写入: {combined_path}")

    print("\n完成。")


if __name__ == "__main__":
    main()
