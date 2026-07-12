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

## Template

The required template JSON is:

`demo_data/templates/apis_standard_19_v2.json`

It is version `2` and starts in `draft` status. It must remain separate from the
existing v1 teaching template. Existing annotations stay pinned to their exact
original template.

An analysis model can become active only after:

1. The template exists in the database.
2. The template has been reviewed and published by an administrator.
3. The model build validates successfully.
4. `python -m wing_repository.reference_data activate-models --model-version N`
   is run.

## Single-wing limitation

Every report displays:

> Results from a single wing are less reliable than results based on the mean
> shape of multiple workers from one colony or locality.

Future sample-level analysis can combine 10–20 workers from one colony or
locality, but hindwings remain out of scope.

## No-reliable-match outcome

If the query is outside the model's validated reference-distance distribution,
the geographical section displays an outlier interpretation and the warning:

> No reliable geographical reference match within the current European reference
> dataset.

The lineage section may still be shown, but it carries the same outlier warning.
