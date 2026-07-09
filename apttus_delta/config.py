"""Run configuration, loaded from config.yaml (all keys optional).

The pipeline runs against a *data directory* — the local folder (e.g. the
synced SharePoint/OneDrive "Apttus Automation" folder) that contains the
release snapshots. The code lives in a `python-automation/` subfolder of
that data directory, so `data_dir` defaults to `..` (the parent of this
repo). Override it in config.yaml or with --data-dir if the data lives
elsewhere. Every data path below resolves relative to `data_dir` unless
given as absolute."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

import yaml

# The 15 countries the VBA Split_Country_Files macro produces.
DEFAULT_SPLIT_COUNTRIES = ["BE", "NL", "PT", "ES", "DK", "FI", "SE", "NO", "FR", "DE", "CH",
                           "AT", "IT", "GB", "IE"]

# Paths that live inside the data directory.
_DATA_PATHS = ("current_release", "previous_release", "soql_exports", "output", "split",
               "apttus_files", "validation")


@dataclass
class Config:
    base_dir: Path = Path(".")          # where config.yaml lives; resolves a relative data_dir
    data_dir: Path = Path("..")         # the "Apttus Automation" folder (parent of this repo)
    current_release: Path = Path("01. Current Release")
    previous_release: Path = Path("00. Previous Release")
    soql_exports: Path = Path("SOQL Exports")
    output: Path = Path("Output")
    split: Path = Path("Split")
    apttus_files: Path = Path("Apttus Files")   # legacy workbooks, used by `verify`
    validation: Path = Path("Validation")       # legacy validation folder, used by `verify`
    org_profile: str = "prod"  # "prod" | "itest4"
    release_date: date = field(default_factory=date.today)
    split_countries: list[str] = field(default_factory=lambda: list(DEFAULT_SPLIT_COUNTRIES))
    export_max_age_days: int = 7
    strict_columns: bool = True
    datasets: list[str] | str = "all"

    def __post_init__(self):
        # YAML 1.1 reads an unquoted NO (Norway) as boolean False.
        self.split_countries = ["NO" if c is False else str(c) for c in self.split_countries]
        bad = [c for c in self.split_countries if len(c) != 2 or not c.isupper()]
        if bad:
            raise ValueError(f"split_countries must be ISO-2 codes, got {bad}")
        self.base_dir = Path(self.base_dir)
        data = Path(self.data_dir).expanduser()
        self.data_dir = data if data.is_absolute() else self.base_dir / data
        for name in _DATA_PATHS:
            p = Path(getattr(self, name)).expanduser()
            setattr(self, name, p if p.is_absolute() else self.data_dir / p)

    @property
    def release_stamp(self) -> str:
        """`02.Jul.26` — the release-file date convention."""
        return self.release_date.strftime("%d.%b.%y")

    @property
    def split_stamp(self) -> str:
        """`02JUL` — the VBA macro's Format(Date, "ddmmm") uppercased."""
        return self.release_date.strftime("%d%b").upper()


def load_config(path: Path | None, data_dir: Path | None = None) -> Config:
    if path is None:
        return Config(data_dir=data_dir or Path(".."))
    raw = yaml.safe_load(Path(path).read_text(encoding="utf-8")) or {}
    paths = raw.pop("paths", {})
    if "release_date" in raw and raw["release_date"]:
        raw["release_date"] = date.fromisoformat(str(raw["release_date"]))
    else:
        raw.pop("release_date", None)
    if data_dir is not None:  # --data-dir overrides the config file
        raw["data_dir"] = data_dir
    return Config(base_dir=Path(path).resolve().parent, **paths, **raw)
