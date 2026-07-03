"""Parity harness: prove the Python port reproduces the Excel pipeline.

Three checks, all against artifacts already in the repository:

1. Delta parity — run every dataset builder with the release folders as
   input and, for SOQL datasets, the org snapshot materialized on each
   workbook's `cCRM` sheet (the loaded result of the query the drop-folder
   contract replaces). Diff our outputs against the workbook's
   materialized result sheets.
2. Consolidation parity — rebuild the nine Data Validation.xlsm queries
   from the `Validation/` folder and diff against its loaded sheets.
3. Split parity — recompute the per-country split from `Validation/` and
   diff against the workbooks in `Split/<CC>/`.

The materialized sheets reflect the *last Excel refresh*; a mismatch can
mean the release folders changed since that refresh, so differences are
reported, not raised."""

from __future__ import annotations

from collections import Counter
from pathlib import Path

import pandas as pd

from .datasets import DATASETS
from .io_excel import IngestError, discover_files, read_dataset, read_sheet_rows
from .normalize import to_text
from .split import SPLIT_SPECS, consolidate

WORKBOOKS = {
    "G00": "G00. Product2.xlsx",
    "G01": "G01. Product_Structure.xlsx",
    "G02": "G02. CVG.xlsx",
    "G03": "G03. CVG Mapping.xlsx",
    "G04": "G04. Product_Options.xlsx",
    "G05": "G05. cCRM Product_Mapping.xlsx",
    "G06": "G06. CFD_Exhibits_Definitions.xlsx",
    "G07": "G07. Global Eq Models.xlsx",
    "G08": "G08. Rule 1.xlsx",
    "G09": "G09. Rule 5.xlsx",
    "G10": "G10. Rule 7.xlsx",
    "G11": "G11. Rule 8.xlsx",
    "L01": "L01. cCRM Equip Price Relevant List.xlsx",
    "L02": "L02. CVG Translation.xlsx",
    "L03": "L03. RSM Translation.xlsx",
    "L04": "L04. Service Plan Type Translation.xlsx",
    "L05": "L05. Start Month Translation.xlsx",
    "L06": "L06. Sales Text Translation.xlsx",
    "L07": "L07. Service Price Matrix.xlsx",
    "L08": "L08. Market Inclusions.xlsx",
    "L09": "L09. Rule 3.xlsx",
}
ITEST4_WORKBOOKS = {"L03": "L03. RSM Translation iTest4.xlsx",
                    "L07": "L07. Service Price Matrix iTest4.xlsx"}

# G01's loaded sheets were renamed by hand in the workbook.
SHEET_ALIASES = {("G01", "Extra"): "New Options",
                 ("G01", "Changed Models"): "Changed Models-NPI",
                 ("G01", "Changed Model Structure"): "Model Structure-NPI"}

# Outputs whose workbook sheet is not comparable: Excel loads a RightAnti
# NestedJoin as zero left-shaped rows (the actual result sits in the nested
# column), so the sheet is empty by construction.
NOT_COMPARABLE = {("L01", "Extra in cCRM to be removed"):
                  "workbook sheet is an empty RightAnti load artifact"}


def _cell(v) -> str:
    if v is None or v != v:  # None or NaN
        return ""
    t = to_text(v)
    return "" if t is None else str(t)


def _tuples(rows) -> Counter:
    return Counter(tuple(_cell(v) for v in row) for row in rows)


def _df_tuples(df: pd.DataFrame) -> Counter:
    return _tuples(df.itertuples(index=False, name=None))


def _compare(name: str, ours: pd.DataFrame, sheet_rows: list[tuple]) -> str:
    """Diff on the columns both sides share — workbook sheets sometimes carry
    manually added helper columns next to the loaded query result."""
    theirs_header = [to_text(v) for v in sheet_rows[0]] if sheet_rows else []
    shared = [c for c in ours.columns if c in theirs_header]
    if not shared:
        return (f"DIFF {name}: no shared columns\n"
                f"       ours:   {list(ours.columns)}\n       theirs: {theirs_header}")
    idx = [theirs_header.index(c) for c in shared]
    note = "" if len(shared) == len(ours.columns) else \
        f" [compared {len(shared)}/{len(ours.columns)} shared columns]"
    ours_c = _df_tuples(ours[shared])
    theirs_c = _tuples(tuple(r[i] if i < len(r) else None for i in idx) for r in sheet_rows[1:])
    if ours_c == theirs_c:
        return f"OK   {name}: {len(ours):,} rows match{note}"
    missing = sum((theirs_c - ours_c).values())
    extra = sum((ours_c - theirs_c).values())
    return (f"DIFF {name}: ours={sum(ours_c.values()):,} theirs={sum(theirs_c.values()):,} "
            f"(rows only in workbook: {missing:,}; only in ours: {extra:,}){note}")


def _org_from_workbook(path: Path, ds) -> pd.DataFrame:
    rows = read_sheet_rows(path, "cCRM")
    header = [to_text(v) for v in rows[0]]
    data = [[to_text(v) for v in row[: len(header)]] + [None] * (len(header) - len(row))
            for row in rows[1:]]
    df = pd.DataFrame(data, columns=header, dtype=object)
    for col in ds.org_upper:  # the sheet may predate the query's Text.Upper step
        if col in df.columns:
            df[col] = df[col].map(lambda v: v.upper() if isinstance(v, str) else v)
    for col in set(ds.org_optional) - set(df.columns):
        df[col] = None
    return df


def verify(cfg) -> int:
    apttus_files = cfg.base_dir / "Apttus Files"
    validation_root = cfg.base_dir / "Validation"
    lines: list[str] = []

    print("== Delta parity vs Apttus Files workbooks ==")
    workbooks = dict(WORKBOOKS)
    if cfg.org_profile == "itest4":
        workbooks.update(ITEST4_WORKBOOKS)
    for key, ds in DATASETS.items():
        wb_path = apttus_files / workbooks[key]
        try:
            new = read_dataset(discover_files(cfg.current_release, ds.file_contains,
                                              ds.file_excludes),
                               ds.sheet, ds.columns, ds.drop_header_on)
            if ds.mode == "release":
                other = read_dataset(discover_files(cfg.previous_release, ds.file_contains,
                                                    ds.file_excludes),
                                     ds.sheet, ds.columns, ds.drop_header_on)
            else:
                other = _org_from_workbook(wb_path, ds)
            outputs = ds.builder(new, other, cfg)
            for name, df in outputs.items():
                if (key, name) in NOT_COMPARABLE:
                    lines.append(f"SKIP {key} {name}: {NOT_COMPARABLE[(key, name)]} "
                                 f"(ours: {len(df):,} rows)")
                    continue
                sheet = SHEET_ALIASES.get((key, name), name)[:31]
                try:
                    rows = read_sheet_rows(wb_path, sheet)
                except IngestError as e:
                    lines.append(f"SKIP {key} {name}: {e}")
                    continue
                lines.append(f"{'':1}{_compare(f'{key} {ds.label} :: {name}', df, rows)}")
        except IngestError as e:
            lines.append(f"SKIP {key} {ds.label}: {e}")
    print("\n".join(lines))

    print("\n== Consolidation parity vs Validation/Data Validation.xlsm ==")
    xlsm = validation_root / "Data Validation.xlsm"
    cons_lines = []
    for spec in SPLIT_SPECS:
        try:
            ours = consolidate(spec, validation_root)
            rows = read_sheet_rows(xlsm, spec.sheet_name)
            cons_lines.append(_compare(spec.sheet_name, ours, rows))
        except IngestError as e:
            cons_lines.append(f"SKIP {spec.sheet_name}: {e}")
    print("\n".join(cons_lines))

    print("\n== Split parity vs Split/<CC>/ ==")
    split_lines = []
    for spec in SPLIT_SPECS:
        try:
            df = consolidate(spec, validation_root)
        except IngestError as e:
            split_lines.append(f"SKIP {spec.sheet_name}: {e}")
            continue
        col = df.columns[spec.filter_column - 1]
        prefixes = df[col].map(lambda v: v if isinstance(v, str) else "")
        for country in cfg.split_countries:
            part = df[prefixes.str.startswith(country)]
            existing = sorted((cfg.split / country).glob(f"{country}_{spec.sheet_name}_*.xlsx"))
            if not existing:
                continue
            try:
                rows = read_sheet_rows(existing[-1], spec.sheet_name[:31])
            except IngestError as e:
                split_lines.append(f"SKIP {existing[-1].name}: {e}")
                continue
            split_lines.append(_compare(existing[-1].name, part, rows))
    print("\n".join(split_lines))

    all_lines = lines + cons_lines + split_lines
    diffs = sum(1 for l in all_lines if l.strip().startswith("DIFF"))
    skips = sum(1 for l in all_lines if l.strip().startswith("SKIP"))
    oks = sum(1 for l in all_lines if l.strip().startswith("OK"))
    print(f"\n{oks} OK, {diffs} DIFF, {skips} SKIP")
    if diffs:
        print("note: workbook sheets show the last Excel refresh; a DIFF can also mean "
              "the release folders changed after that refresh.")
    return 1 if diffs else 0
