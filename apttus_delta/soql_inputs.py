"""The SOQL export drop-folder contract.

There is no Salesforce API connection: the org side of every SOQL-mode
comparison is a manual export. Run the dataset's saved SOQL (the canonical
field list lives in docs/soql/<export_key>.soql), export as CSV, and save
it as:

    SOQL Exports/<org_profile>/<export_key>_<YYYY-MM-DD>.csv   (or .xlsx)

where the date is the day the export was taken. The pipeline picks the
newest export per dataset, refuses stale or ambiguous files, validates the
header against the workbook's cCRM query columns, and applies the same
uppercase normalizations that query applies."""

from __future__ import annotations

import csv
import re
from dataclasses import dataclass
from datetime import date
from pathlib import Path

import pandas as pd

from .datasets import Dataset
from .normalize import to_text


class ExportError(ValueError):
    pass


@dataclass
class ExportFile:
    dataset_key: str
    export_key: str
    path: Path
    export_date: date


def _find_export(folder: Path, ds: Dataset) -> ExportFile | None:
    pattern = re.compile(re.escape(ds.export_key) + r"_(\d{4}-\d{2}-\d{2})\.(csv|xlsx)$")
    matches = []
    if folder.is_dir():
        for p in sorted(folder.iterdir()):
            m = pattern.fullmatch(p.name)
            if m:
                matches.append((date.fromisoformat(m.group(1)), p))
    if not matches:
        return None
    newest = max(d for d, _ in matches)
    newest_files = [p for d, p in matches if d == newest]
    if len(newest_files) > 1:
        raise ExportError(
            f"{ds.key} ({ds.export_key}): ambiguous exports for {newest} — "
            + ", ".join(p.name for p in newest_files)
        )
    return ExportFile(ds.key, ds.export_key, newest_files[0], newest)


def check_exports(cfg, datasets: list[Dataset]) -> tuple[list[ExportFile], list[str]]:
    """Locate and freshness-check the export of every SOQL-mode dataset.
    Problems are collected (not fail-on-first) so one run reports every
    missing/stale file."""
    folder = cfg.soql_exports / cfg.org_profile
    found, problems = [], []
    for ds in datasets:
        if ds.mode != "soql":
            continue
        try:
            exp = _find_export(folder, ds)
        except ExportError as e:
            problems.append(str(e))
            continue
        if exp is None:
            problems.append(
                f"{ds.key} ({ds.label}): no export named "
                f"'{ds.export_key}_<YYYY-MM-DD>.csv' in {folder} — run docs/soql/{ds.export_key}.soql"
            )
            continue
        age = (cfg.release_date - exp.export_date).days
        if age > cfg.export_max_age_days:
            problems.append(
                f"{ds.key} ({ds.label}): export {exp.path.name} is {age} days old "
                f"(max {cfg.export_max_age_days}) — re-run docs/soql/{ds.export_key}.soql"
            )
            continue
        found.append(exp)
    return found, problems


def _read_csv(path: Path) -> pd.DataFrame:
    df = pd.read_csv(path, dtype=str, keep_default_na=False, na_values=[],
                     encoding="utf-8-sig", quoting=csv.QUOTE_MINIMAL, engine="python")
    return df.astype(object)


def _read_xlsx(path: Path) -> pd.DataFrame:
    rows = read_sheet_rows_first_sheet(path)
    header = [to_text(v) for v in rows[0]]
    data = [[to_text(v) for v in row] for row in rows[1:]]
    return pd.DataFrame(data, columns=header, dtype=object)


def read_sheet_rows_first_sheet(path: Path) -> list[tuple]:
    import openpyxl

    wb = openpyxl.load_workbook(path, read_only=True, data_only=True)
    try:
        return [tuple(r) for r in wb[wb.sheetnames[0]].iter_rows(values_only=True)]
    finally:
        wb.close()


def load_export(exp: ExportFile, ds: Dataset, strict_columns: bool = True) -> pd.DataFrame:
    df = _read_csv(exp.path) if exp.path.suffix == ".csv" else _read_xlsx(exp.path)
    df.columns = [str(c) for c in df.columns]

    required, optional = set(ds.org_required), set(ds.org_optional)
    have = set(df.columns)
    missing = sorted(required - have)
    extra = sorted(have - required - optional)
    if missing or (extra and strict_columns):
        raise ExportError(
            f"{ds.key} ({ds.label}): schema drift in {exp.path.name}\n"
            f"  missing columns: {missing or '-'}\n"
            f"  unexpected columns: {extra or '-'}\n"
            f"  expected: {sorted(required)}"
        )
    if extra:
        df = df.drop(columns=extra)
    for col in optional - have:
        df[col] = None

    # Empty CSV fields are nulls, like empty Excel cells in the pasted table.
    df = df.where(df.notna(), None)
    for col in df.columns:
        df[col] = [None if v == "" else v for v in df[col]]
    for col in ds.org_upper:
        df[col] = df[col].map(lambda v: v.upper() if isinstance(v, str) else v)
    return df
