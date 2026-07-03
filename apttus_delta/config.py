"""Run configuration, loaded from config.yaml (all keys optional)."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

import yaml

# The 15 countries the VBA Split_Country_Files macro produces.
DEFAULT_SPLIT_COUNTRIES = ["BE", "NL", "PT", "ES", "DK", "FI", "SE", "NO", "FR", "DE", "CH",
                           "AT", "IT", "GB", "IE"]


@dataclass
class Config:
    base_dir: Path = Path(".")
    current_release: Path = Path("01. Current Release")
    previous_release: Path = Path("00. Previous Release")
    soql_exports: Path = Path("SOQL Exports")
    output: Path = Path("Output")
    split: Path = Path("Split")
    org_profile: str = "prod"  # "prod" | "itest4"
    release_date: date = field(default_factory=date.today)
    split_countries: list[str] = field(default_factory=lambda: list(DEFAULT_SPLIT_COUNTRIES))
    export_max_age_days: int = 7
    strict_columns: bool = True
    datasets: list[str] | str = "all"

    def __post_init__(self):
        self.base_dir = Path(self.base_dir)
        for name in ("current_release", "previous_release", "soql_exports", "output", "split"):
            p = Path(getattr(self, name))
            setattr(self, name, p if p.is_absolute() else self.base_dir / p)

    @property
    def release_stamp(self) -> str:
        """`02.Jul.26` — the release-file date convention."""
        return self.release_date.strftime("%d.%b.%y")

    @property
    def split_stamp(self) -> str:
        """`02JUL` — the VBA macro's Format(Date, "ddmmm") uppercased."""
        return self.release_date.strftime("%d%b").upper()


def load_config(path: Path | None) -> Config:
    if path is None:
        return Config()
    raw = yaml.safe_load(Path(path).read_text(encoding="utf-8")) or {}
    paths = raw.pop("paths", {})
    if "release_date" in raw and raw["release_date"]:
        raw["release_date"] = date.fromisoformat(str(raw["release_date"]))
    else:
        raw.pop("release_date", None)
    cfg = Config(base_dir=Path(path).resolve().parent, **paths, **raw)
    return cfg
