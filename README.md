# Apttus Release Delta Tool — User Guide

This tool compares the **new catalogue release** against the **previous
release** and against **what is currently in Salesforce**, and produces the
Excel files you need to load the changes. It replaces the old Power Query
workbooks and the "split countries" macro — same results, one command.

This guide assumes no coding experience. Follow the steps in order the
first time; after that, a normal release run is just Steps 4–7.

> Technical documentation (how the tool works inside) is in
> [docs/TECHNICAL.md](docs/TECHNICAL.md).

---

## Step 1 — Install Python (one time)

1. Go to <https://www.python.org/downloads/> and click **Download Python**
   (any version 3.10 or newer is fine).
2. Run the installer. **Important:** on the first screen, tick the box
   **"Add python.exe to PATH"** before clicking Install.
3. To check it worked: open the **Command Prompt** (press the Windows key,
   type `cmd`, press Enter) and type:

   ```
   python --version
   ```

   You should see something like `Python 3.12.4`. If you see an error,
   restart the computer and try again.

## Step 2 — Install the tool (one time)

1. Download this project: on the GitHub page click the green **Code**
   button → **Download ZIP**, and unzip it somewhere permanent, for example
   `C:\Tools\apttus-automation`. (If you use Git, `git clone` works too.)
2. Open the Command Prompt **in that folder**: open the folder in File
   Explorer, click the address bar, type `cmd` and press Enter.
3. Install the tool by typing:

   ```
   pip install -e .
   ```

   Wait until it finishes (it downloads a few libraries the first time).

## Step 3 — Tell the tool where your data is (one time)

The tool works on your local **"Apttus Automation"** folder — the synced
SharePoint/OneDrive folder that contains `00. Previous Release`,
`01. Current Release`, and so on.

1. In the project folder, open the file **`config.yaml`** with Notepad.
2. Find the line that starts with `data_dir:` and put the full path of
   your Apttus Automation folder between the quotes, using forward
   slashes `/`:

   ```yaml
   data_dir: "C:/Users/<your id>/Philips/PST Onboard Business and Markets - Documents/Catalogue Releases/Apttus Automation"
   ```

   Tip: in File Explorer, right-click the folder → **Copy as path**, paste
   it, then replace every `\` with `/` and remove the surrounding quotes it
   may add.
3. Save and close the file. You won't need to touch it again unless the
   folder moves.

Inside that folder the tool expects the structure you already use:

```
Apttus Automation/
├── 00. Previous Release/     ← last release (Global + Local country folders)
├── 01. Current Release/      ← the new release files
├── SOQL Exports/             ← you create this in Step 4
│   └── prod/
├── Output/                   ← the tool creates this (results)
└── Split/                    ← the tool creates the country files here
```

## Step 4 — Download the Salesforce files (every release)

Some comparisons need to know what is **currently in Salesforce**. Since
the tool cannot connect to Salesforce directly, you download the data
yourself — one CSV file per dataset, 14 in total.

1. In the project folder, open **`docs/soql/`**. There is one small text
   file per dataset (for example `Service_Price_Matrix.soql`). Each file
   contains the query to run and, at the top, the exact file name to save
   the result as.
2. Open **Workbench** (or Data Loader) and log into the org
   (production, or iTest4 if you are doing an iTest4 run).
3. For each of the 14 files: copy the query from the `.soql` file, run it,
   and export the result as **CSV**.
4. Save every CSV into `Apttus Automation/SOQL Exports/prod/` (use an
   `itest4` folder instead of `prod` for iTest4 runs), named exactly:

   ```
   <Name>_<date you exported it>.csv          for example:
   Service_Price_Matrix_2026-07-03.csv
   CVG_Translation_2026-07-03.csv
   ```

   The date must be in `YYYY-MM-DD` form. The 14 names are:

   | File name starts with | Salesforce data |
   |---|---|
   | `Product2` | Service product catalogue |
   | `CVG` | Coverages |
   | `CVG_Mapping` | Equipment → coverage mapping |
   | `Product_Options` | Equipment → commercial system |
   | `cCRM_Product_Mapping` | Apttus ↔ cCRM product codes |
   | `CFD_Exhibits` | CFD exhibit definitions |
   | `Global_EqModels` | Equipment master |
   | `Eq_Price_Relevant_List` | Price-relevant equipment per country |
   | `CVG_Translation` | CVG translations |
   | `RSM_Translation` | RSM type translations |
   | `ServicePlanType_Translation` | Service plan type translations |
   | `StartMonth_Translation` | Start month translations |
   | `Sales_Text` | Sales text translations |
   | `Service_Price_Matrix` | Prices |

Exports older than 7 days are refused (so a run never silently uses last
month's data) — if that happens, just re-export that file with today's
date in the name.

## Step 5 — Check that everything is ready

In the Command Prompt (opened in the project folder), type:

```
python -m apttus_delta check-exports
```

You get one line per dataset:

- `PASS Service_Price_Matrix_2026-07-03.csv: 258,888 rows` — good.
- `FAIL ...` — the message says exactly what's wrong: a file is missing,
  too old, or has the wrong columns. Fix that file and run the check
  again. Nothing is calculated until every line passes.

## Step 6 — Run the comparison

```
python -m apttus_delta run
```

This reads the two release folders and your Salesforce exports, computes
every delta, and writes everything into a dated folder, for example
`Apttus Automation/Output/03.Jul.26/`:

| File | What it is |
|---|---|
| `G00…` to `L09…_delta.xlsx` | One workbook per dataset. Each sheet has the same name as the old Power Query result it replaces (`Extra`, `Not Matching`, `Changed Models`, …). |
| `Global_All_Files.xlsx` | The six global loader sheets, ready for the data loader (replaces *00. Global All Files.xlsx*). |
| `CFD_Localization.xlsx` | The combined translation loader table (replaces *L02_05. CFD Localization.xlsx*). |
| `report.md` | A summary you can read: how many rows were found and produced per dataset, and whether each sheet is something to **upsert** (new/changed records to load), to **deactivate** (records that exist in Salesforce but not in the release), or **info** (rule comparisons to review). |

The screen also shows a short summary at the end. If a run stops with an
error, see "If something goes wrong" below — the message always names the
exact file that caused it.

Useful variations:

```
python -m apttus_delta run --datasets L07,L09     only some datasets
python -m apttus_delta run --org itest4           iTest4 run (uses SOQL Exports/itest4/)
```

## Step 7 — Create the country files

```
python -m apttus_delta split
```

This rebuilds what the old Excel macro did: for each of the 15 European
countries it writes the nine files (Rule 3, prices, translations, …) into
`Apttus Automation/Split/<country>/`, named like `DE_Rule3_03JUL.xlsx`.
Existing files for the same day are replaced.

## When a new release arrives (checklist)

1. In the Apttus Automation folder: move the contents of
   `01. Current Release` into `00. Previous Release` (replacing what's
   there), then put the new release files into `01. Current Release`.
2. Do Step 4 (fresh Salesforce exports).
3. `python -m apttus_delta check-exports` → fix anything that fails.
4. `python -m apttus_delta run`
5. `python -m apttus_delta split`
6. Open `Output/<date>/report.md`, sanity-check the counts, and hand the
   upsert/deactivate files to the data-load step as usual.

## If something goes wrong

| Message contains | What it means | What to do |
|---|---|---|
| `release folder not found` | `data_dir` in `config.yaml` doesn't point at your Apttus Automation folder | Fix the path (Step 3) |
| `no export named …` | A Salesforce CSV is missing | Export it (Step 4) |
| `is … days old` | An export is older than 7 days | Re-export it with today's date in the name |
| `ambiguous exports` | Two files with the same date for one dataset | Delete the wrong one |
| `schema drift` | The CSV's columns don't match what's expected | Re-run the query exactly as written in the `.soql` file and re-export |
| `header mismatch` | A release Excel file has unexpected column headers | Check that file in `01. Current Release` — it was probably edited by hand |
| `python is not recognized` | Python isn't installed or not on PATH | Redo Step 1, tick "Add python.exe to PATH" |
| `warning: … header row differs` | A country file has a slightly wrong header row | Just a warning — the run continues; mention it to whoever produces that file |

Two more commands, for completeness:

```
python -m apttus_delta verify      compares the tool's results against the old
                                   Excel workbooks (used when validating the migration)
python -m pytest tests/            runs the tool's self-tests
```

If you're stuck, send the full error message plus the `report.md` of the
run to whoever maintains the tool — the messages are written to pinpoint
the problem file.
