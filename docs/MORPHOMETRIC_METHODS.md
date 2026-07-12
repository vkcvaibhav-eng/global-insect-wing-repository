# Morphometric Methods

The implementation lives in `wing_repository/morphometrics/`.

## Coordinate validation

`validation.py` requires exactly 19 finite x,y coordinate pairs. Row order is
the landmark order; validation does not sort or relabel points.

18-point and 20-point configurations are rejected.

## Generalized Procrustes Analysis

`gpa.py` and `ordinary_procrustes.py` implement deterministic 2D geometric
morphometrics:

1. Center every configuration at its centroid.
2. Divide by centroid size.
3. Rotate to the current consensus.
4. Recompute consensus.
5. Iterate to convergence.

Reflection is not allowed by default. This is intentional because the published
workflow and coordinate structure must be inspected before any left/right
conversion is introduced.

Centroid size is retained as an analytical value in source-coordinate units. It
is not converted to millimetres unless a true calibration exists.

## Sample averaging

Individual aligned wings are grouped by sample/colony identifier. Mean shapes
are calculated at sample level for classification, preventing leakage of wings
from one colony/sample between training and validation.

## PCA

`pca.py` uses deterministic NumPy SVD. PCA scores are model-internal projection
coordinates only. They are never treated as permanent identifiers.

Saved query projection uses the existing PCA mean/loadings and does not rebuild
the reference GPA/PCA model.

## CVA/LDA-style probabilities

`cva.py` implements a deterministic pooled-covariance linear-discriminant
classifier with regularization. The output probabilities are finite, constrained
to `[0, 1]`, and tested to sum to approximately `1.0`.

Regional and lineage classifiers are trained from labelled sample mean shapes.
The lineage model requires A, C, M and O labels.

## Closest published shapes

`nearest_shapes.py` aligns a query to the saved reference consensus and returns
nearest external individual reference configurations by Procrustes distance.

The query is aligned to the saved consensus without rebuilding the model.

## Similarity percentile

`similarity_calibration.py` uses an empirical distribution of reference
distances. Smaller Procrustes distances produce higher similarity percentiles.

The implementation does not use:

`similarity = 100 × (1 − distance)`

## Outlier handling

`outlier_detection.py` compares the nearest distance to a saved empirical
distance threshold. If outside the validated reference distribution, the report
uses cautious wording and does not force a confident geographical assignment.

## Dependencies

The project declares SciPy, scikit-learn and joblib compatible ranges for
production scientific environments. The implemented core path uses deterministic
NumPy/SciPy-compatible operations and stores artifacts with checksum validation.
