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

Primary European reference:

Oleksa, A. et al. (2023). Honey bee (`Apis mellifera`) wing images: a tool for
identification and conservation. `GigaScience` 12: giad019.

- Article DOI: `10.1093/gigascience/giad019`
- Dataset DOI: `10.5281/zenodo.7244070`
- Workflow DOI: `10.48546/workflowhub.workflow.422.1`

Lineage reference:

Nawrocka, A., Kandemir, I., Fuchs, S. and Tofilski, A. (2018).

- Dataset DOI: `10.5281/zenodo.7567336`

## Application page

The Streamlit page is named `Published Apis Reference Analysis`. Before running,
it displays:

- Taxon: `Apis mellifera`
- Wing analysed: right forewing
- Landmarks: 19 fixed landmarks
- Reference: Oleksa et al. (2023), Zenodo 7244070
- Analysis: shape only; physical size excluded
- Input mode: single wing — preliminary result

The output has three sections:

1. Geographical wing-shape affinity
2. Evolutionary-lineage wing-shape affinity
3. Closest published forewing shapes

External matches are labelled `External published reference`; they are not
native Global Insect Wing Repository specimens and never receive WBR accessions.

## Activation status

The code is updated, but the analysis is not yet automatically active. It still
requires:

1. Downloading the Oleksa, Nawrocka and WorkflowHub reference files.
2. Running the database migration.
3. Importing the coordinates.
4. Validating the imported data.
5. Confirming the bundled 19-landmark template is published.
6. Building and activating the models.

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
