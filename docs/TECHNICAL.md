# Technical documentation

> How the tool works inside — for maintainers. The step-by-step user
> guide is the repository [README](../README.md).

Python/pandas port of the Excel + Power Query automation that computes the
**delta between the previous and the current catalogue release** and prepares
the Salesforce loader files. It replaces:

- the Power Query queries embedded in `Apttus Files/*.xlsx` (per-dataset
  ingest + delta),
- the consolidation queries and the `Split_Country_Files()` VBA macro in
  `Validation/Data Validation.xlsm`,
- the `00. Global All Files.xlsx` / `L02_05. CFD Localization.xlsx`
  consolidation workbooks.

The logic was transcribed 1:1 from the M code embedded in the workbooks
(check keys, null handling, trims, renames, date reformatting), so the
Python outputs are drop-in replacements for the Power Query results.

## Setup

```bash
pip install -e .          # installs pandas, openpyxl, PyYAML + the apttus-delta CLI
```

**The data lives outside the repo.** The repo carries the code; the release
snapshots live in your local "Apttus Automation" folder (the synced
SharePoint/OneDrive one, with `00. Previous Release/`, `01. Current
Release/`, etc. inside). Point the pipeline at it in `config.yaml`:

```yaml
data_dir: "C:/Users/<you>/Philips/PST Onboard Business and Markets - Documents/Catalogue Releases/Apttus Automation"
```

or per run with `--data-dir`. All data folders (releases, `SOQL Exports/`,
`Output/`, `Split/`, and the legacy `Apttus Files/`/`Validation/` used by
`verify`) resolve inside `data_dir`; any of them can be overridden with an
absolute path under `paths:`. The copies of the data checked into this repo
(Git LFS) are a reference snapshot for development — `data_dir: "."` runs
against them.

## The two comparison modes

| Mode | Datasets | Compares |
|---|---|---|
| Local comparison | G01 Product_Structure, G08 Rule 1, G09 Rule 5, G10 Rule 7, G11 Rule 8, L08 Market Inclusions, L09 Rule 3 | `01. Current Release/` vs `00. Previous Release/` |
| SOQL | G00 Product2, G02 CVG, G03 CVG Mapping, G04 Product Options, G05 cCRM Product Mapping, G06 CFD Exhibits, G07 Global Eq Models, L01 Eq Price Relevant List, L02–L05 translations, L06 Sales Text, L07 Service Price Matrix | `01. Current Release/` (loader shape) vs a Salesforce org export |

## SOQL workaround: the export drop folder

There is no Salesforce API connection, so the org side of every SOQL-mode
comparison is a **manual export** (this replaces the table you used to paste
into each `Apttus Files` workbook):

1. Run the dataset's query — the canonical field list is in
   `docs/soql/<ExportKey>.soql` (Workbench, Data Loader, or a report).
2. Export as **CSV** and save it as
   `SOQL Exports/<prod|itest4>/<ExportKey>_<YYYY-MM-DD>.csv`
   where the date is the day you took the export
   (e.g. `SOQL Exports/prod/Service_Price_Matrix_2026-07-02.csv`).
3. `python -m apttus_delta check-exports` tells you per dataset whether the
   file is found, fresh, and has the expected columns.

Rules enforced by the pipeline (it fails loudly rather than guessing):

- **Missing export** → error listing every missing dataset at once.
- **Stale export** (older than `export_max_age_days`, default 7) → error.
- **Schema drift** (missing/unexpected columns vs the workbook's cCRM
  query) → error showing the exact difference.
- Two files with the same date for one dataset → error (ambiguous).
- The newest date wins when several dated exports exist.
- CSVs are read with everything as text (codes keep leading zeros, nothing
  goes scientific), empty fields become nulls like empty Excel cells, and
  numeric columns (prices, quantities, terms) are compared numerically so
  `2` in Excel equals `2.0` in a Salesforce export.

The `itest4` profile (`--org itest4` or `org_profile: itest4`) is the same
pipeline pointed at the iTest4 sandbox exports; for the Service Price
Matrix it also applies the 15-significant-digit price rounding the iTest4
workbook variant has.

## Running

```bash
python -m apttus_delta run                    # everything: deltas + consolidated workbooks
python -m apttus_delta run --datasets L07,L09 # a subset
python -m apttus_delta split                  # per-country split (replaces the VBA macro)
python -m apttus_delta verify                 # parity checks vs the old Excel pipeline
```

`run` writes to `Output/<DD.Mon.YY>/`:

- `<key>_<label>_delta.xlsx` per dataset — one sheet per result, named
  exactly like the Power Query query it replaces (`Extra`, `Not Matching`,
  `Changed Models Rule 3`, `Extra in cCRM (Deactivate)`, …).
- `Global_All_Files.xlsx` — the six loader sheets of `00. Global All
  Files.xlsx` (the `CFD Exhibit` sheet uses G06's fuller `Not Matching`
  set).
- `CFD_Localization.xlsx` — the union of the four translation `Not
  Matching` sets (replaces `L02_05. CFD Localization.xlsx`; uses the active
  org profile's results).
- `manifest.json` + `report.md` — row counts per output and whether each
  sheet is an **upsert** set, a **deactivate** set (`Extra in cCRM
  (Deactivate)`, `Extra in cCRM to be removed`, `Extra in cCRM`), or an
  **info** comparison reviewed manually (the rule/local-comparison
  outputs).

`split` rebuilds what `Split_Country_Files()` produced: for each of the 15
configured countries, nine `Split/<CC>/<CC>_<Dataset>_<DDMMM>.xlsx`
workbooks, filtered by country prefix on the same column the macro
filtered, from the current release folders.

## Data-fidelity rules (why results match Power Query)

- Nothing is ever numerically type-inferred; every cell goes through one
  text conversion matching M's `type text` (booleans → `TRUE/FALSE`,
  integral floats → `120`, decimals → shortest round-trip).
- No implicit trimming: NBSP and trailing spaces are preserved except in
  the exact columns where the M code has an NBSP+TrimEnd step (CVG/RSM
  translated values, sales-text short/long).
- Composite keys replicate each query's null policy: `null`-or-empty →
  literal `"null"` (Rule 3, Product Structure, SPM ext-id), null-only →
  `"null"` (Rule 1, Rule 5), and plain `&` concatenation propagating null
  (Rule 8, Market Inclusions, ext-ids) — and joins match null with null,
  like Power Query.
- Repeated header rows from concatenated country files are dropped with
  the same column filters the M code uses.
- The one date field (`Pricebook Simulation Date`) is reformatted with the
  exact M algorithm; a real datetime cell raises instead of guessing.

## Known intentional differences vs the Excel pipeline

- **Decimal text**: Power Query rendered some prices with 17 digits
  (`1708.3333333333301`); this pipeline writes the shortest text for the
  same double (`1708.33333333333`). Identical numeric value, and all price
  comparisons parse numerically, so deltas are unaffected.
- **`L01 Extra in cCRM to be removed`** now contains the actual org rows to
  remove; the old workbook sheet was empty by construction (Excel cannot
  load a RightAnti nested join).
- **Header drift tolerance**: a country file whose header row text differs
  from the first file's (e.g. DK's CVG_Translation) is ingested positionally
  with a warning — Power Query silently swallowed this.
- **`CFD_Localization.xlsx`** consolidates the active org profile's
  translation results; the old workbook happened to also union the iTest4
  RSM output into the prod file because of a filename filter.

## Release cutover

Unchanged from the Excel process: when a new release lands, move the
contents of `01. Current Release/` into `00. Previous Release/`, drop the
new files into `01. Current Release/`, refresh the SOQL exports, and run.

## Verification

`python -m apttus_delta verify` re-runs every dataset against the repo
folders and diffs the results, row by row, against the materialized Power
Query sheets inside `Apttus Files/*.xlsx` (using each workbook's embedded
org snapshot as the Salesforce side), the consolidated sheets in
`Validation/Data Validation.xlsm`, and the existing `Split/<CC>/` files.
Workbook sheets show the last Excel refresh, so a DIFF can also mean the
folders changed after that refresh. Unit tests: `python -m pytest tests/`.
