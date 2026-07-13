# Model Validation and Activation

Model records live in `analysis_models`. Result records live in
`wing_analysis_runs`, `region_probabilities`, `lineage_probabilities`, and
`published_shape_matches`.

## Model statuses

- `BUILDING`
- `VALIDATION_FAILED`
- `VALIDATED`
- `ACTIVE`
- `RETIRED`

Only `VALIDATED` models can be activated. Activating a version retires older
active models for the same template.

## Build commands

After importing external data:

```powershell
python -m wing_repository.reference_data validate-import
python -m wing_repository.reference_data build-analysis-models --model-version 1
```

The build saves a versioned artifact under `WBR_ANALYSIS_ARTIFACT_DIR` when
`WBR_ANALYSIS_ARTIFACT_BACKEND = "local"`. Hosted deployments can instead use
`WBR_ANALYSIS_ARTIFACT_BACKEND = "r2"` and store the same artifact under the R2
prefix configured by `WBR_ANALYSIS_ARTIFACT_R2_PREFIX`. Artifacts are never
overwritten.

## Activation command

After confirming the bundled Apis 19-landmark template is published, run:

```powershell
python -m wing_repository.reference_data activate-models --model-version 1
```

Activation fails if the model set is incomplete or the template is not published.

## Stored validation metrics

The artifact/model manifest stores:

- GPA convergence status and iteration count
- reflection/orientation policy
- region leave-one-sample-out cross-validation
- lineage leave-one-sample-out cross-validation
- confusion matrices
- overall accuracy where estimable
- outlier distance quantile
- software versions
- source hashes

## Published aligned-file reproduction

`EU-aligned-coordinates.csv` is a validation target, not a training shortcut.
Exact reproduction requires inspecting and running the downloaded WorkflowHub R
Markdown workflow (`10.48546/workflowhub.workflow.422.1`) and recording any
orientation/layout transformations.

The current Python implementation records a conservative transformation policy:
source orientation preserved, no reflection, GPA center/scale/rotate. If exact
R-workflow reproduction fails, the model must remain `VALIDATION_FAILED` and the
diagnostic report should be stored in `validation_metrics_json`.

## Result reproducibility

Each analysis run stores the model ID used for the result. Existing runs remain
linked to their original model version when a newer model is activated.

## Artifact checksum validation

Model artifacts store SHA-256. Loading an active model verifies the checksum
before analysis. If the artifact bytes differ, analysis fails instead of using a
silent, unreproducible model.
