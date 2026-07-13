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
$env:WBR_KAUR_INDIA_REFERENCE_DIR = "C:\reference-data\kaur-india-zenodo-8071014"
$env:WBR_SOUTHWEST_ASIA_REFERENCE_DIR = "C:\reference-data\southwest-asia-zenodo-17075125"
$env:WBR_KAZAKHSTAN_REFERENCE_DIR = "C:\reference-data\kazakhstan-zenodo-8128010"
$env:WBR_SERBIA_REFERENCE_DIR = "C:\reference-data\serbia-zenodo-10389960"
$env:WBR_MEXICO_REFERENCE_DIR = "C:\reference-data\mexico-tabasco-zenodo-13884732"
$env:WBR_NORTHWESTERN_EUROPE_REFERENCE_DIR = "C:\reference-data\northwestern-europe-zenodo-18845767"
$env:WBR_ALGERIA_REFERENCE_DIR = "C:\reference-data\algeria-zenodo-18360081"
$env:WBR_QUEENS_DRONES_REFERENCE_DIR = "C:\reference-data\queens-drones-zenodo-8396176"
$env:WBR_APIS_WORKFLOW_DIR = "C:\reference-data\workflowhub-422"
$env:WBR_ANALYSIS_ARTIFACT_DIR = "data\analysis-artifacts"
```

Do not commit these directories. `.gitignore` excludes common reference-data and
artifact paths.

Hosted Streamlit deployments may keep the database in Neon/PostgreSQL and the
built model artifact in Cloudflare R2. Set `WBR_ANALYSIS_ARTIFACT_BACKEND =
"r2"` and keep the default `WBR_ANALYSIS_ARTIFACT_R2_PREFIX =
"analysis-artifacts/"` when the uploaded object key is
`analysis-artifacts/apis_reference/v1/model.pkl`.

## Reference-source roles

| Source | Role in the app | Contains wing coordinates? |
|---|---|---|
| Oleksa et al., Zenodo `10.5281/zenodo.7244070` | European geographical/region affinity and closest published shapes | Yes |
| Kaur, Ganie and Tofilski, Zenodo `10.5281/zenodo.8071014` | Jammu and Kashmir, India geographical/nearest-shape reference | Yes |
| Machlowska et al., Zenodo `10.5281/zenodo.17075125` | Southwestern Asia worker geographical/nearest-shape reference | Yes |
| Temirbayeva et al., Zenodo `10.5281/zenodo.8128010` | Kazakhstan worker geographical/nearest-shape reference | Yes |
| Kaur, Nedic and Tofilski, Zenodo `10.5281/zenodo.10389960` | Serbia worker geographical/nearest-shape reference | Yes |
| Payro de la Cruz et al., Zenodo `10.5281/zenodo.13884732` | Tabasco, Mexico worker geographical/nearest-shape reference | Yes |
| Machlowska et al., Zenodo `10.5281/zenodo.18845767` | Northwestern Europe worker geographical/nearest-shape reference | Yes |
| Yamina and Tofilski, Zenodo `10.5281/zenodo.18360081` | Algeria worker geographical/nearest-shape reference | Yes |
| Nawrocka et al., Zenodo `10.5281/zenodo.7567336` | A, C, M and O lineage-affinity reference | Yes |
| Tofilski, Kaur and Łopuch, Zenodo `10.5281/zenodo.8396176` | Queen/drone caste reference coordinates; excluded from worker analysis models by default | Yes |
| WorkflowHub `10.48546/workflowhub.workflow.422.1` | Published R-analysis procedure for GPA, averaging, CVA and classification | No new biological reference collection; it is the workflow |

## Expected Oleksa files

From Zenodo DOI `10.5281/zenodo.7244070`:

- `EU-raw-coordinates.csv`
- `EU-geo-data.csv`
- `EU-lineage-classification.csv`
- `EU-aligned-coordinates.csv`
- `readme.txt`

These EU files are the minimum coordinate/reference files required by the
current importer. The complete Oleksa deposit may also be archived locally with
the country-level files and image ZIP files:

- `{country}-raw-coordinates.csv`
- `{country}-data.csv`
- `{country}-wing-images.zip`
- `_sample-map.png`

for country codes `AT`, `ES`, `GR`, `HR`, `HU`, `MD`, `ME`, `PL`, `PT`, `RO`,
`RS`, `SI`, and `TR`.

The Streamlit analysis currently imports `EU-raw-coordinates.csv` as the
combined Oleksa coordinate table. The country files and image ZIPs are retained
for provenance, auditability, and future image-based work; they are not loaded
into PostgreSQL during the coordinate import.

The importer records source-file SHA-256 checksums in dataset manifests. The
published Zenodo record lists MD5 values, but the application stores SHA-256 for
local provenance.

## Expected Kaur India files

From Zenodo DOI `10.5281/zenodo.8071014`, provide only the coordinate/metadata
CSV files:

- `IN-raw-coordinates.csv`
- `IN-data.csv`

The published record also contains `IN-wing-images.zip`, but this repository
path intentionally does not require or import the image ZIP. The dataset
contains 350 honey bee forewing images representing 175 workers from 10
locations in Jammu and Kashmir, India. Raw coordinates contain 19 wing
landmarks; `IN-data.csv` provides sample, geographic coordinate, date,
resolution and note metadata.

## Expected Southwest Asia files

From Zenodo DOI `10.5281/zenodo.17075125`, provide only country coordinate and
metadata CSV files:

- `{country}-raw-coordinates.csv`
- `{country}-data.csv`

for country codes `AZ`, `CY`, `GE`, `IR`, `IQ`, `SA`, `TJ`, and `TR`.

The current import path preserves `_map.png` and `GE-30-3x.csv` in the dataset
manifest when present, but does not import `GE-30-3x.csv` by default. The
published record also includes `{country}-wing-images.zip` archives, which are
intentionally ignored by coordinate-only imports.

The dataset contains worker honey bee forewing data from 1,535 samples and 8
countries in southwestern Asia. Raw coordinates contain 19 landmarks and each
country data file provides sample, geographic coordinate, date, resolution and
note metadata.

## Expected Kazakhstan files

From Zenodo DOI `10.5281/zenodo.8128010`, provide only the coordinate/metadata
CSV files:

- `KZ-raw-coordinates.csv`
- `KZ-data.csv`

The published record also contains `KZ-wing-images.zip`, which is intentionally
ignored by coordinate-only imports. The dataset contains 1,067 worker honey bee
forewing images representing 71 colonies and 17 locations in Kazakhstan. Raw
coordinates contain 19 landmarks; `KZ-data.csv` provides sample, geographic
coordinate, date, resolution and group metadata.

## Expected Serbia files

From Zenodo DOI `10.5281/zenodo.10389960`, provide only the coordinate/metadata
CSV files and optional map:

- `RS_21_80-raw-coordinates.csv`
- `RS_21_80-data.csv`
- `RS-map.png`

The published record also contains `RS_21_80-wing-images.zip`, which is
intentionally ignored by coordinate-only imports. The dataset contains 2,282
worker honey bee forewing images representing 60 colonies, each collected from
a different location in Serbia. Raw coordinates contain 19 landmarks;
`RS_21_80-data.csv` provides sample, geographic coordinate, date, resolution
and note metadata.

## Expected Mexico files

From Zenodo DOI `10.5281/zenodo.13884732`, provide only the coordinate/metadata
CSV files:

- `MX-raw-coordinates.csv`
- `MX-data.csv`

The published record also contains `MX-wing-images.zip`, which is intentionally
ignored by coordinate-only imports. The dataset contains 2,951 right-forewing
images of worker honey bees representing 245 colonies and 33 locations in
Tabasco, Mexico. Raw coordinates contain 19 landmarks; `MX-data.csv` provides
sample, geographic coordinate, date, resolution and note metadata.

## Expected Northwestern Europe files

From Zenodo DOI `10.5281/zenodo.18845767`, provide only the coordinate/metadata
CSV files and optional map:

- `BY-raw-coordinates.csv`
- `BY-data.csv`
- `DE-raw-coordinates.csv`
- `DE-data.csv`
- `ES_517_573-raw-coordinates.csv`
- `ES_517_573-data.csv`
- `FR-raw-coordinates.csv`
- `FR-data.csv`
- `GB-raw-coordinates.csv`
- `GB-data.csv`
- `IE-raw-coordinates.csv`
- `IE-data.csv`
- `LT-raw-coordinates.csv`
- `LT-data.csv`
- `NL-raw-coordinates.csv`
- `NL-data.csv`
- `NO-raw-coordinates.csv`
- `NO-data.csv`
- `PL_254_922-raw-coordinates.csv`
- `PL_254_922-data.csv`
- `_map.png`

The published record also contains large image archives named `BY.zip`,
`DE.zip`, `ES_517_573.zip`, `FR.zip`, `GB.zip`, `IE.zip`, `LT.zip`, `NL.zip`,
`NO.zip`, and `PL_254_922.zip`. These are intentionally ignored by
coordinate-only imports. The dataset contains 29,043 worker honey bee forewing
images representing 1,342 samples from Belarus, France, Germany, Ireland,
Lithuania, the Netherlands, Norway, Poland, Spain, and the United Kingdom.
Raw coordinate files contain 19 landmarks; data files provide sample,
geographic coordinate, date, resolution and note metadata. Poland and Spain use
sample-number suffixes in their filenames to avoid conflicts with earlier
datasets.

## Expected Algeria files

From Zenodo DOI `10.5281/zenodo.18360081`, provide only the coordinate/metadata
CSV files:

- `DZ-2025-raw-coordinates.csv`
- `DZ-2025-data.csv`

The published record also contains `DZ-2025-wing-images.zip`, which is
intentionally ignored by coordinate-only imports. The dataset contains 3,405
forewing images of worker honey bees representing 86 colonies from Algeria.
Raw coordinates contain 19 landmarks; `DZ-2025-data.csv` provides sample,
geographic coordinate, date, resolution and note metadata.

## Expected queens/drones files

From Zenodo DOI `10.5281/zenodo.8396176`, provide the coordinate CSV files:

- `drones-raw-coordinates.csv`
- `queens-raw-coordinates.csv`

The importer also preserves optional queen measurement metadata if present:

- `queens-wing-length.csv`
- `queens-weight.csv`

The published record also contains `drones-wing-images.zip` and
`queens-wing-images.zip`. These image archives are intentionally ignored by the
coordinate-only import path. The raw coordinate files contain 19 landmarks for
8,006 drone wing images and 4,117 queen wing images. Because this is a
queen/drone caste dataset, its records are not mixed automatically into the
worker-only published Apis analysis model.

## Expected Nawrocka files

From Zenodo DOI `10.5281/zenodo.7567336`, provide the raw coordinate and
metadata CSV files:

- `Nawrocka_et_al2018.csv`
- `Nawrocka_et_al2018-geo-data.csv`

The importer also preserves optional provenance files if present:

- `Nawrocka_et_al2018-sample-aligned.csv`
- `apis-wing-landmarks600.png`

The published Nawrocka reference contains 1,832 worker forewings from 187
colonies, representing 25 subspecies and four evolutionary lineages. This is an
average of approximately 9.8 wings per colony, not a guarantee that every colony
contains exactly 10 wings.

The current import path stores the 1,832 raw worker wing rows from
`Nawrocka_et_al2018.csv` after deriving the sample identifier from each source
filename and merging lineage, subspecies and geographic metadata from
`Nawrocka_et_al2018-geo-data.csv`. The 187-row sample-aligned table is retained
for provenance and method comparison, but it is not imported as additional wing
records.

## Expected WorkflowHub files

From WorkflowHub DOI `10.48546/workflowhub.workflow.422.1`, download and keep
the complete Version 1 RO-Crate. The current importer does not treat WorkflowHub
as an additional coordinate dataset. It is retained for provenance and for
future validation of the Python implementation against the published R Markdown
workflow.

## Import commands

```powershell
python -m wing_repository.reference_data inspect-oleksa
python -m wing_repository.reference_data import-oleksa
python -m wing_repository.reference_data inspect-kaur-india
python -m wing_repository.reference_data import-kaur-india
python -m wing_repository.reference_data inspect-southwest-asia
python -m wing_repository.reference_data import-southwest-asia
python -m wing_repository.reference_data inspect-kazakhstan
python -m wing_repository.reference_data import-kazakhstan
python -m wing_repository.reference_data inspect-serbia
python -m wing_repository.reference_data import-serbia
python -m wing_repository.reference_data inspect-mexico
python -m wing_repository.reference_data import-mexico
python -m wing_repository.reference_data inspect-northwestern-europe
python -m wing_repository.reference_data import-northwestern-europe
python -m wing_repository.reference_data inspect-algeria
python -m wing_repository.reference_data import-algeria
python -m wing_repository.reference_data inspect-queens-drones
python -m wing_repository.reference_data import-queens-drones
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
