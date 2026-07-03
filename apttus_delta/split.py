"""Per-country split — the Python port of `Split_Country_Files()` (VBA in
Validation/Data Validation.xlsm) fed by the nine consolidation queries of
that workbook.

Each consolidated dataset is filtered per country with a prefix match on
its designated column (the macro's `AutoFilter Criteria1:=country & "*"`)
and written to `Split/<CC>/<CC>_<SheetName>_<DDMMM>.xlsx`."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import pandas as pd

from .datasets import DATASETS
from .io_excel import discover_files, read_dataset, write_workbook
from .normalize import NULL_OR_EMPTY, PROPAGATE, key_series
from .transforms import _L09_KEY_COLS


@dataclass(frozen=True)
class SplitSpec:
    sheet_name: str       # consolidated sheet name in the .xlsm = output file part
    dataset_key: str      # registry entry providing file pattern / columns
    filter_column: int    # 1-based country column the macro filters on


SPLIT_SPECS = [
    SplitSpec("cCRM_Eq_Price_Relevant_List", "L01", 1),
    SplitSpec("CVG_Translation", "L02", 3),
    SplitSpec("RSMType_Translation", "L03", 3),
    SplitSpec("ServicePlanType_Translation", "L04", 2),
    SplitSpec("StartMonth_Translation", "L05", 2),
    SplitSpec("Sales_Text", "L06", 4),
    SplitSpec("Service_Price_Matrix", "L07", 1),
    SplitSpec("Rule3", "L09", 1),
    SplitSpec("Market_Inclusions", "L08", 3),
]


def consolidate(spec: SplitSpec, source_root: Path) -> pd.DataFrame:
    """Replicates the matching ingest query of Data Validation.xlsm."""
    ds = DATASETS[spec.dataset_key]
    files = discover_files(source_root, ds.file_contains, ds.file_excludes)
    df = read_dataset(files, ds.sheet, ds.columns, ds.drop_header_on)
    if spec.sheet_name in ("CVG_Translation", "ServicePlanType_Translation",
                           "StartMonth_Translation"):
        df = df.drop(columns=["Country"])
    elif spec.sheet_name == "Service_Price_Matrix":
        df = df[df["Price Type"] == "Recurring"].reset_index(drop=True)
    elif spec.sheet_name == "Market_Inclusions":
        df = df.copy()
        df["Key"] = key_series(df, ["Option Code", "Service Model Code", "Country", "Default",
                                    "Product Range", "MPC Entitlement"], PROPAGATE)
    elif spec.sheet_name == "Rule3":
        df = df.copy()
        df["Check Key"] = key_series(df, _L09_KEY_COLS, NULL_OR_EMPTY)
    return df


def split_countries(cfg, source_root: Path | None = None,
                    specs: list[SplitSpec] | None = None) -> dict[str, int]:
    """Write the per-country workbooks. Returns {output file: rows}."""
    source_root = source_root or cfg.current_release
    written: dict[str, int] = {}
    for spec in specs or SPLIT_SPECS:
        df = consolidate(spec, source_root)
        col = df.columns[spec.filter_column - 1]
        prefixes = df[col].map(lambda v: v if isinstance(v, str) else "")
        for country in cfg.split_countries:
            part = df[prefixes.str.startswith(country)]
            if len(part) == 0:  # the macro skips countries with no visible rows
                continue
            out = cfg.split / country / f"{country}_{spec.sheet_name}_{cfg.split_stamp}.xlsx"
            write_workbook(out, {spec.sheet_name: part})
            written[str(out)] = len(part)
    return written
