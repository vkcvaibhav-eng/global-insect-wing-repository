# External Reference Data

External published records are not native repository specimens. They are stored
in `external_reference_datasets`, `external_reference_shapes`, and
`external_reference_import_issues`.

## Local directory configuration

The app never downloads published research datasets during normal Streamlit
startup. Download the source files manually, then point the CLI to local
directories:

```powershell
$env:WBR_OLEKSA_REFERENCE_DIR = "C:\reference-data\oleksa-zenodo-7244070"
$env:WBR_NAWROCKA_REFERENCE_DIR = "C:\reference-data\nawrocka-zenodo-7567336"
$env:WBR_APIS_WORKFLOW_DIR = "C:\reference-data\workflowhub-422"
$env:WBR_ANALYSIS_ARTIFACT_DIR = "data\analysis-artifacts"
```

Do not commit these directories. `.gitignore` excludes common reference-data and
artifact paths.

## Expected Oleksa files

From Zenodo DOI `10.5281/zenodo.7244070`:

- `EU-raw-coordinates.csv`
- `EU-geo-data.csv`
- `EU-lineage-classification.csv`
- `EU-aligned-coordinates.csv`
- `readme.txt`

The importer records source-file SHA-256 checksums in dataset manifests. The
published Zenodo record lists MD5 values, but the application stores SHA-256 for
local provenance.

## Expected Nawrocka files

From Zenodo DOI `10.5281/zenodo.7567336`, provide local CSV files containing
19 ordered x,y landmark coordinate pairs and lineage labels A, C, M and O.

The importer detects coordinate columns using names such as `x1`, `y1`,
`LM01_x`, `LM01_y`, or a first-38-numeric-columns fallback. It does not invent a
left/right reflection rule.

## Import commands

```powershell
python -m wing_repository.reference_data inspect-oleksa
python -m wing_repository.reference_data import-oleksa
python -m wing_repository.reference_data inspect-nawrocka
python -m wing_repository.reference_data import-nawrocka
python -m wing_repository.reference_data validate-import
```

Inspection commands report detected columns before modifying the database.

## Preserved provenance

Each external dataset stores:

- dataset code
- title, authors, year
- dataset DOI, article DOI and workflow DOI when available
- version/licence text
- taxonomic and geographic scope
- associated landmark-template version
- manifest JSON
- import timestamp

Each external shape stores:

- original source identifier
- source filename / row identifier
- sample identifier when available
- taxon name
- country, region and lineage labels when available
- original wing orientation text when available
- original coordinate JSON
- analytical coordinate JSON
- source metadata JSON for unrecognized columns
- source-row SHA-256

Malformed rows are inserted into `external_reference_import_issues` rather than
silently discarded.

## Orientation handling

Native repository submissions require right forewings. External source
orientation is preserved. The current Python preprocessing uses a preserve
orientation policy: centering, unit centroid size and rotation are allowed;
reflection is not applied unless a future documented reproduction of the
published workflow requires it.

Any future left/right transformation must preserve the original coordinate JSON
and write transformed coordinates only to `analytical_coordinate_json`.
