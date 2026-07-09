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

   ```text
   python --version
   ```

   You should see something like `Python 3.12.4`. If you see an error,
   restart the computer and try again.

## Step 2 — Install the tool (one time)

The tool lives **inside** your local "Apttus Automation" folder — the
synced SharePoint/OneDrive folder that holds the release data — in a
subfolder called `python-automation`. The finished layout looks like this:

```text
Apttus Automation/
├── 00. Previous Release/     ← last release (Global + Local country folders)
├── 01. Current Release/      ← the new release files
├── SOQL Exports/             ← Salesforce data you paste in (Step 4)
│   ├── prod/                 ← production server data
│   └── itest4/               ← iTest4 sandbox data
├── Output/                   ← the tool creates this (results)
├── Split/                    ← the tool creates the country files here
└── python-automation/        ← the tool itself (this project)
```

1. Get the project into that spot: on the GitHub page click the green
   **Code** button → **Download ZIP**, and unzip it **inside your Apttus
   Automation folder** so the folder is named `python-automation`. (With
   Git: `git clone <url> python-automation` from inside Apttus Automation.)
2. Open the Command Prompt **in the `python-automation` folder**: open it
   in File Explorer, click the address bar, type `cmd` and press Enter.
3. Install the tool by typing:

   ```text
   pip install -e .
   ```

   Wait until it finishes (it downloads a few libraries the first time).

## Step 3 — Check the data location (usually nothing to do)

Because the tool sits inside the Apttus Automation folder, it finds the
release folders **automatically** (they're one level up). You only need to
touch configuration if your data lives somewhere else entirely — in that
case open `config.yaml` with Notepad and set `data_dir:` to the full path
of the data folder, with forward slashes `/`:

```yaml
data_dir: "C:/Users/<your id>/Philips/PST Onboard Business and Markets - Documents/Catalogue Releases/Apttus Automation"
```

Tip: in File Explorer, right-click the folder → **Copy as path**, paste
it, then replace every `\` with `/`.

## Step 4 — Get the Salesforce data (every release)

Some comparisons need to know what is **currently in Salesforce**. Since
the tool cannot connect to Salesforce directly, you fill in **one Excel
workbook** — one sheet per query — by copying and pasting the query
results.

The tool can work with data from **two Salesforce servers**: production
(the `prod` folder, used by default) and the iTest4 sandbox (the `itest4`
folder). You choose which one a run uses with the `--org` option — see
Step 6.

**First time only — create the workbook:**

```text
python -m apttus_delta make-template
```

(add `--org itest4` to create it for the sandbox instead)

This creates `Apttus Automation/SOQL Exports/prod/SOQL_Exports_TEMPLATE.xlsx`.
It has an **Instructions** sheet (containing every query, next to the name
of the sheet its result belongs on) and 14 data sheets whose first row is
already filled with the correct column headers:

| Sheet | Salesforce data |
| --- | --- |
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

**Every release:**

1. Open the template and **save a copy** in the same folder named with
   today's date, for example `SOQL_Exports_2026-07-03.xlsx`
   (the date must be `YYYY-MM-DD`).
2. Log into the Salesforce server whose folder you're filling (production
   → `prod/`, iTest4 sandbox → `itest4/`).
3. For each sheet: run its query (it's on the Instructions sheet), copy
   the **whole result including its header row**, and paste it into cell
   A1 of the sheet, replacing the pre-filled header. Don't worry if your
   result has extra columns (`_`, `Id`, `Product__r`, …) or a different
   column order than the template — columns are matched by name and
   extras are ignored. Codes like `005` keep their leading zeros because
   the sheets are text-formatted; numbers shown as `9.9E+11` are just
   Excel's display, the full value is intact.
4. Save the workbook.

Workbooks older than 7 days are refused (so a run never silently uses last
month's data) — if that happens, save a copy with today's date and
refresh the pasted data.

> Prefer separate files? A CSV export saved as
> `<SheetName>_<YYYY-MM-DD>.csv` in the same folder also works, per
> dataset, and wins over the workbook when it is newer.

## Step 5 — Check that everything is ready

In the Command Prompt (opened in the project folder), type:

```text
python -m apttus_delta check-exports
```

You get one line per dataset:

- `PASS L07 SOQL_Exports_2026-07-03.xlsx :: Service_Price_Matrix: 258,888 rows` — good.
- `FAIL ...` — the message says exactly what's wrong: a sheet is still
  empty, the workbook is too old, or the pasted columns are wrong. Fix it
  and run the check again. Nothing is calculated until every line passes.

## Step 6 — Run the comparison

```text
python -m apttus_delta run
```

This reads the two release folders and your Salesforce exports, computes
every delta, and writes everything into a dated folder, for example
`Apttus Automation/Output/03.Jul.26/`:

| File | What it is |
| --- | --- |
| `G00…` to `L09…_delta.xlsx` | One workbook per dataset. Each sheet has the same name as the old Power Query result it replaces (`Extra`, `Not Matching`, `Changed Models`, …). |
| `Global_All_Files.xlsx` | The six global loader sheets, ready for the data loader (replaces *00. Global All Files.xlsx*). |
| `CFD_Localization.xlsx` | The combined translation loader table (replaces *L02_05. CFD Localization.xlsx*). |
| `report.md` | A summary you can read: how many rows were found and produced per dataset, and whether each sheet is something to **upsert** (new/changed records to load), to **deactivate** (records that exist in Salesforce but not in the release), or **info** (rule comparisons to review). |

The screen also shows a short summary at the end. If a run stops with an
error, see "If something goes wrong" below — the message always names the
exact file that caused it.

**Choosing the Salesforce server:** by default the run uses the
**production** data (`SOQL Exports/prod/`). Add `--org itest4` to use the
iTest4 sandbox data instead (`SOQL Exports/itest4/`) — the `--org` option
works on every command (`make-template`, `check-exports`, `run`, `split`):

```text
python -m apttus_delta run                        production run (default)
python -m apttus_delta run --org itest4           iTest4 run (uses SOQL Exports/itest4/)
python -m apttus_delta run --datasets L07,L09     only some datasets
```

## Step 7 — Create the country files

```text
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
2. Do Step 4 (save a new dated copy of the SOQL workbook and refresh the
   pasted data).
3. `python -m apttus_delta check-exports` → fix anything that fails.
4. `python -m apttus_delta run`
5. `python -m apttus_delta split`
6. Open `Output/<date>/report.md`, sanity-check the counts, and hand the
   upsert/deactivate files to the data-load step as usual.

## If something goes wrong

| Message contains | What it means | What to do |
| --- | --- | --- |
| `release folder not found` | `data_dir` in `config.yaml` doesn't point at your Apttus Automation folder | Fix the path (Step 3) |
| `no data found` | No Salesforce data for a dataset | Paste the query result into that sheet of the dated workbook (Step 4) |
| `sheet … has no data` | A sheet in the workbook is still empty | Paste the query result into it |
| `is … days old` | The workbook/CSV is older than 7 days | Save a copy dated today and refresh the pasted data |
| `ambiguous exports` | Two files with the same date | Delete the wrong one |
| `schema drift` | The pasted columns don't match what's expected | Re-run the query exactly as shown on the Instructions sheet and re-paste |
| `header mismatch` | A release Excel file has unexpected column headers | Check that file in `01. Current Release` — it was probably edited by hand |
| `python is not recognized` | Python isn't installed or not on PATH | Redo Step 1, tick "Add python.exe to PATH" |
| `warning: … header row differs` | A country file has a slightly wrong header row | Just a warning — the run continues; mention it to whoever produces that file |

Two more commands, for completeness:

```text
python -m apttus_delta verify      compares the tool's results against the old
                                   Excel workbooks (used when validating the migration)
python -m pytest tests/            runs the tool's self-tests
```

If you're stuck, send the full error message plus the `report.md` of the
run to whoever maintains the tool — the messages are written to pinpoint
the problem file.
