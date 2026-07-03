# SOQL export drop folder

Drop manual Salesforce exports here as
`<prod|itest4>/<ExportKey>_<YYYY-MM-DD>.csv` — e.g.
`prod/Service_Price_Matrix_2026-07-02.csv`.

The query for each dataset is in `docs/soql/<ExportKey>.soql`. Validate the
folder with `python -m apttus_delta check-exports`. The CSV files are
git-ignored on purpose (org data, refreshed every release).
