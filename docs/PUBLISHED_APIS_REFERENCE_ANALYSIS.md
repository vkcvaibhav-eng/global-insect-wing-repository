# Published Apis Reference Analysis

This module adds a reproducible, versioned reference-analysis path for worker
honey bee right forewings. It is deliberately narrower than the main repository.

## Fixed scope

- Taxon: `Apis mellifera`
- Specimen: worker honey bee
- Wing: right forewing only
- Landmarks: exactly 19 fixed homologous forewing landmarks
- Input mode: one complete wing annotation
- Result wording: preliminary single-wing wing-shape analysis

This is not species identification. The module must not report `Apis cerana`,
`Apis dorsata`, `Apis florea`, or any other species.

## Reference sources

The analysis uses two coordinate datasets plus one workflow/provenance source:

| Source | Role in this app | Contains wing coordinates? |
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

Primary European reference:

Oleksa, A. et al. (2023). Honey bee (`Apis mellifera`) wing images: a tool for
identification and conservation. `GigaScience` 12: giad019.

- Article DOI: `10.1093/gigascience/giad019`
- Dataset DOI: `10.5281/zenodo.7244070`
- Workflow DOI: `10.48546/workflowhub.workflow.422.1`

India reference:

Kaur, H., Ganie, S. A. and Tofilski, A. (2023). Fore wings of honey bees
(`Apis mellifera`) from Jammu and Kashmir, India.

- Dataset DOI: `10.5281/zenodo.8071014`
- Published scope: 350 honey bee forewing images representing 175 workers and
  10 locations in Jammu and Kashmir, India. The current import path uses
  `IN-raw-coordinates.csv` and `IN-data.csv` only, not the image ZIP archive.

Southwest Asia worker reference:

Machlowska, J. et al. (2025). Fore wings of honey bees (`Apis mellifera`) from
southwestern Asia.

- Dataset DOI: `10.5281/zenodo.17075125`
- Article DOI: `10.1038/s41597-025-06234-8`
- Published scope: 17,015 worker forewing images representing 1,535 samples and
  8 countries in southwestern Asia.
- Current use: coordinate-only import of country raw-coordinate and metadata
  CSV pairs; image ZIPs are not imported.

Kazakhstan worker reference:

Temirbayeva, K. et al. (2023). Fore wings of honey bees (`Apis mellifera`) from
Kazakhstan.

- Dataset DOI: `10.5281/zenodo.8128010`
- Article DOI: `10.3390/life13091860`
- Published scope: 1,067 worker forewing images representing 71 colonies and
  17 locations in Kazakhstan.
- Current use: coordinate-only import of `KZ-raw-coordinates.csv` and
  `KZ-data.csv`; image ZIPs are not imported.

Serbia worker reference:

Kaur, H., Nedic, N. and Tofilski, A. (2023). Fore wing images of honey bees
(`Apis mellifera`) from Serbia.

- Dataset DOI: `10.5281/zenodo.10389960`
- Published scope: 2,282 worker forewing images representing 60 colonies from
  60 Serbian locations.
- Current use: coordinate-only import of `RS_21_80-raw-coordinates.csv` and
  `RS_21_80-data.csv`; image ZIPs are not imported. `RS-map.png` is retained as
  provenance when present.

Mexico worker reference:

Payro de la Cruz, E., Valencia Dominguez, M., Ramos Reyes, R. and Tofilski, A.
(2024). Fore wings of honey bees (`Apis mellifera`) from Tabasco, Mexico.

- Dataset DOI: `10.5281/zenodo.13884732`
- Published scope: 2,951 worker right-forewing images representing 245 colonies
  and 33 locations in Tabasco, Mexico.
- Current use: coordinate-only import of `MX-raw-coordinates.csv` and
  `MX-data.csv`; image ZIPs are not imported.

Northwestern Europe worker reference:

Machlowska, J. et al. (2026). Fore wings of honey bees (`Apis mellifera`) from
northwestern Europe.

- Dataset DOI: `10.5281/zenodo.18845767`
- Published scope: 29,043 worker forewing images representing 1,342 samples
  from Belarus, France, Germany, Ireland, Lithuania, the Netherlands, Norway,
  Poland, Spain, and the United Kingdom.
- Current use: coordinate-only import of country raw-coordinate and metadata
  CSV pairs. Poland and Spain use the source filenames
  `PL_254_922-raw-coordinates.csv` and `ES_517_573-raw-coordinates.csv` to
  avoid conflicts with earlier datasets. Image ZIPs are not imported; `_map.png`
  is retained as provenance when present.

Algeria worker reference:

Yamina, H. and Tofilski, A. (2026). Fore wing images of honey bees
(`Apis mellifera`) from Algeria 2025.

- Dataset DOI: `10.5281/zenodo.18360081`
- Published scope: 3,405 worker forewing images representing 86 colonies from
  Algeria.
- Current use: coordinate-only import of `DZ-2025-raw-coordinates.csv` and
  `DZ-2025-data.csv`; image ZIPs are not imported.

Lineage reference:

Nawrocka, A., Kandemir, I., Fuchs, S. and Tofilski, A. (2018).

- Dataset DOI: `10.5281/zenodo.7567336`
- Published scope: 1,832 worker forewings from 187 colonies, representing 25
  subspecies and four evolutionary lineages. This averages approximately 9.8
  wings per colony, but colony-level sample counts should not be assumed to be
  exactly 10.
- Current use: raw worker wing coordinates from `Nawrocka_et_al2018.csv` are
  merged with lineage/subspecies metadata from
  `Nawrocka_et_al2018-geo-data.csv`. The sample-aligned CSV and landmark PNG
  are retained as provenance only.

Queen/drone caste reference:

Tofilski, A., Kaur, H. and Łopuch, S. (2023). Fore wings of queens and drones
of honey bees (`Apis mellifera`).

- Dataset DOI: `10.5281/zenodo.8396176`
- Published scope: 4,117 queen wing images representing 2,086 individuals and
  8,006 drone wing images representing 4,102 individuals.
- Current use: coordinate-only external reference storage. These records are
  deliberately excluded from the worker-only published Apis analysis model.

## Application page

The Streamlit page is named `Published Apis Reference Analysis`. Before running,
it displays:

- Taxon: `Apis mellifera`
- Wing analysed: right forewing
- Landmarks: 19 fixed landmarks
- Reference: published worker coordinate sources listed above
- Analysis: shape only; physical size excluded
- Input mode: single wing — preliminary result

The output has three sections:

1. Geographical wing-shape affinity
2. Evolutionary-lineage wing-shape affinity
3. Closest published forewing shapes

External matches are labelled `External published reference`; they are not
native Global Insect Wing Repository specimens and never receive WBR accessions.

## Activation status

The analysis becomes active only after the external coordinates are imported,
the Version 2 Apis template is published, and one complete model artifact is
built and activated. The required activation steps are:

1. Downloading the Oleksa, Kaur India and Nawrocka coordinate files, plus the
   WorkflowHub RO-Crate for method provenance.
2. Running the database migration.
3. Importing the coordinates.
4. Validating the imported data.
5. Confirming the bundled 19-landmark template is published.
6. Building and activating the models.

For hosted Streamlit deployments, the active model artifact can be loaded from
Cloudflare R2. With `WBR_ANALYSIS_ARTIFACT_BACKEND = "r2"` and the default
prefix `analysis-artifacts/`, the database key `apis_reference/v1/model.pkl`
maps to the R2 object key `analysis-artifacts/apis_reference/v1/model.pkl`.

## Template

The required template JSON is:

`repository_assets/templates/apis_standard_19_v2.json`

It is the only bundled active Apis template and is published by default. Its
internal version remains `2` so any historical Version 1 teaching annotations
stay pinned to their exact original template instead of being silently
reinterpreted.

An analysis model can become active only after:

1. The template exists in the database.
2. The template is published.
3. The model build validates successfully.
4. `python -m wing_repository.reference_data activate-models --model-version N`
   is run.

## Single-wing limitation

Every report displays:

> Results from a single wing are less reliable than results based on the mean
> shape of multiple workers from one colony or locality.

Version 0.1 now records locality sample code, planned sample size, and the wing
number within that 1..N set. Future sample-level analysis can combine those
workers from one colony or locality, but hindwings remain out of scope.

## No-reliable-match outcome

If the query is outside the model's validated reference-distance distribution,
the geographical section displays an outlier interpretation and the warning:

> No reliable geographical reference match within the current European reference
> dataset.

The lineage section may still be shown, but it carries the same outlier warning.
