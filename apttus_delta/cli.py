"""Command line interface.

    python -m apttus_delta run            # full delta run + consolidations
    python -m apttus_delta check-exports  # validate the SOQL drop folder only
    python -m apttus_delta split          # per-country split of the current release
    python -m apttus_delta verify         # parity checks against the Excel pipeline
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from .config import load_config
from .datasets import DATASETS


def _add_common(p):
    p.add_argument("--config", type=Path, default=None,
                   help="path to config.yaml (default: ./config.yaml if present)")
    p.add_argument("--data-dir", type=Path, default=None,
                   help="local data folder holding the release snapshots "
                        "(overrides data_dir in config.yaml)")
    p.add_argument("--datasets", type=str, default=None,
                   help="comma-separated dataset keys (default: all), e.g. L07,L09")
    p.add_argument("--org", type=str, default=None, choices=["prod", "itest4"],
                   help="org profile override")


def _config(args):
    path = args.config
    if path is None and Path("config.yaml").is_file():
        path = Path("config.yaml")
    cfg = load_config(path, data_dir=args.data_dir)
    if getattr(args, "datasets", None):
        cfg.datasets = [k.strip() for k in args.datasets.split(",") if k.strip()]
    if getattr(args, "org", None):
        cfg.org_profile = args.org
    return cfg


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog="apttus-delta", description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    _add_common(sub.add_parser("run", help="compute all deltas and write output workbooks"))
    _add_common(sub.add_parser("check-exports", help="validate the SOQL export drop folder"))
    _add_common(sub.add_parser("split", help="write per-country split workbooks"))
    verify_p = sub.add_parser("verify", help="parity checks against the Excel pipeline")
    _add_common(verify_p)

    args = parser.parse_args(argv)
    cfg = _config(args)

    if args.command == "run":
        from .pipeline import run

        report = run(cfg)
        report.print_summary()
        print(f"\nOutputs in {cfg.output / cfg.release_stamp}")
        return 0

    if args.command == "check-exports":
        from .pipeline import select_datasets
        from .soql_inputs import check_exports, load_export

        datasets = [d for d in select_datasets(cfg) if d.mode == "soql"]
        exports, problems = check_exports(cfg, datasets)
        for exp in exports:
            ds = DATASETS[exp.dataset_key]
            try:
                df = load_export(exp, ds, cfg.strict_columns)
                print(f"  PASS {exp.dataset_key} {exp.path.name}: {len(df):,} rows "
                      f"(exported {exp.export_date})")
            except Exception as e:  # noqa: BLE001
                problems.append(str(e))
        for p in problems:
            print(f"  FAIL {p}", file=sys.stderr)
        return 1 if problems else 0

    if args.command == "split":
        from .split import split_countries

        written = split_countries(cfg)
        for f, rows in written.items():
            print(f"  {f}: {rows:,} rows")
        print(f"{len(written)} files written")
        return 0

    if args.command == "verify":
        from .verify import verify

        return verify(cfg)

    return 2  # pragma: no cover


if __name__ == "__main__":
    raise SystemExit(main())
