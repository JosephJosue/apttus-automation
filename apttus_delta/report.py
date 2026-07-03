"""Run manifest and human-readable report."""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path


class RunReport:
    def __init__(self, cfg):
        self.cfg = cfg
        self.datasets: dict[str, dict] = {}
        self.split: dict[str, int] = {}
        self.consolidated: dict[str, dict[str, int]] = {}

    def record(self, key: str, label: str, mode: str, files: dict[str, int],
               input_rows: dict[str, int], outputs: dict[str, tuple[int, str]],
               workbook: Path) -> None:
        self.datasets[key] = {
            "label": label,
            "mode": mode,
            "source_files": files,
            "input_rows": input_rows,
            "outputs": {name: {"rows": rows, "action": action}
                        for name, (rows, action) in outputs.items()},
            "workbook": str(workbook),
        }

    def write(self, out_dir: Path) -> Path:
        out_dir.mkdir(parents=True, exist_ok=True)
        manifest = {
            "generated": datetime.now().isoformat(timespec="seconds"),
            "org_profile": self.cfg.org_profile,
            "release_date": self.cfg.release_date.isoformat(),
            "datasets": self.datasets,
            "consolidated": self.consolidated,
            "split": self.split,
        }
        (out_dir / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")

        lines = [
            f"# Release delta run — {self.cfg.release_stamp} (org: {self.cfg.org_profile})",
            "",
            "| Dataset | Mode | Input rows | Output sheet | Rows | Action |",
            "|---|---|---|---|---|---|",
        ]
        for key, d in self.datasets.items():
            rows_in = " / ".join(f"{k}: {v:,}" for k, v in d["input_rows"].items())
            first = True
            for name, o in d["outputs"].items():
                head = f"{key} {d['label']} | {d['mode']} | {rows_in}" if first else " | | "
                lines.append(f"| {head} | {name} | {o['rows']:,} | {o['action']} |")
                first = False
        if self.consolidated:
            lines += ["", "## Consolidated loader workbooks", ""]
            for wb, sheets in self.consolidated.items():
                for sheet, rows in sheets.items():
                    lines.append(f"- {wb} :: {sheet}: {rows:,} rows")
        if self.split:
            lines += ["", f"## Country split ({len(self.split)} files)", ""]
            for f, rows in self.split.items():
                lines.append(f"- {f}: {rows:,} rows")
        (out_dir / "report.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
        return out_dir / "report.md"

    def print_summary(self) -> None:
        for key, d in self.datasets.items():
            outs = ", ".join(f"{n}={o['rows']:,}" for n, o in d["outputs"].items())
            print(f"  {key} {d['label']}: {outs}")
        if self.split:
            print(f"  split: {len(self.split)} country files written")
