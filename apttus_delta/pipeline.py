"""Orchestration: ingest -> delta -> write workbooks -> consolidate."""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from .datasets import DATASETS, Dataset
from .io_excel import discover_files, read_dataset, write_workbook
from .report import RunReport
from .soql_inputs import ExportError, check_exports, load_export

# Sheets of the original `00. Global All Files.xlsx` -> (dataset, output) that fills them.
GLOBAL_ALL_FILES_SHEETS = {
    "Product2": ("G00", "Extra - SP"),
    "CVG": ("G02", "Not Matching"),
    "CVG Mapping": ("G03", "Extra"),
    "Product Options": ("G04", "Extra"),
    "CFD Exhibit": ("G06", "Not Matching"),
    "Global Eq Models": ("G07", "Not Matching"),
}

# `L02_05. CFD Localization.xlsx` unions the Not Matching set of the four
# translation datasets (in workbook-name order L02, L03, L04, L05).
CFD_LOCALIZATION_PARTS = [("L02", "Not Matching"), ("L03", "Not Matching"),
                          ("L04", "Not Matching"), ("L05", "Not Matching")]


def select_datasets(cfg) -> list[Dataset]:
    if cfg.datasets == "all":
        return list(DATASETS.values())
    unknown = [k for k in cfg.datasets if k not in DATASETS]
    if unknown:
        raise KeyError(f"unknown dataset keys {unknown}; known: {sorted(DATASETS)}")
    return [DATASETS[k] for k in cfg.datasets]


def run(cfg) -> RunReport:
    datasets = select_datasets(cfg)
    report = RunReport(cfg)

    # Validate every needed org export up front so one run reports all problems.
    exports, problems = check_exports(cfg, datasets)
    if problems:
        raise ExportError("SOQL export problems:\n  - " + "\n  - ".join(problems))
    export_by_key = {e.dataset_key: e for e in exports}

    out_dir = cfg.output / cfg.release_stamp
    results: dict[str, dict[str, pd.DataFrame]] = {}
    for ds in datasets:
        new_files = discover_files(cfg.current_release, ds.file_contains, ds.file_excludes)
        new = read_dataset(new_files, ds.sheet, ds.columns, ds.drop_header_on)
        files = {"current": len(new_files)}
        input_rows = {"current": len(new)}

        if ds.mode == "release":
            old_files = discover_files(cfg.previous_release, ds.file_contains, ds.file_excludes)
            other = read_dataset(old_files, ds.sheet, ds.columns, ds.drop_header_on)
            files["previous"] = len(old_files)
            input_rows["previous"] = len(other)
        else:
            exp = export_by_key[ds.key]
            other = load_export(exp, ds, cfg.strict_columns)
            files["org_export"] = 1
            input_rows[f"org ({exp.path.name})"] = len(other)

        outputs = ds.builder(new, other, cfg)
        results[ds.key] = outputs

        workbook = out_dir / f"{ds.key}_{ds.label}_delta.xlsx"
        write_workbook(workbook, outputs)
        report.record(ds.key, ds.label, ds.mode, files, input_rows,
                      {name: (len(df), ds.outputs.get(name, "info"))
                       for name, df in outputs.items()},
                      workbook)

    _consolidate(cfg, results, out_dir, report)
    report.write(out_dir)
    return report


def _consolidate(cfg, results, out_dir: Path, report: RunReport) -> None:
    global_sheets = {
        sheet: results[key][output]
        for sheet, (key, output) in GLOBAL_ALL_FILES_SHEETS.items()
        if key in results
    }
    if global_sheets:
        path = out_dir / "Global_All_Files.xlsx"
        write_workbook(path, global_sheets)
        report.consolidated[str(path)] = {s: len(df) for s, df in global_sheets.items()}

    parts = [results[key][output] for key, output in CFD_LOCALIZATION_PARTS if key in results]
    if parts:
        union = pd.concat(parts, ignore_index=True)
        path = out_dir / "CFD_Localization.xlsx"
        write_workbook(path, {"CFD Localization_SP": union})
        report.consolidated[str(path)] = {"CFD Localization_SP": len(union)}
