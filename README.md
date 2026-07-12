# Global Insect Wing Repository

Version 0.1 is a functional, local-first Streamlit milestone for manual
digitization and expert curation of **Hymenopteran right forewings**. It stores
immutable original uploads, ordered landmark coordinates in original pixels and
normalized units, optional image-level millimeter calibration, version-specific
reviews, and approved repository accessions.

This is intentionally not the complete worldwide platform. It contains no
machine learning, WingSearch, PCA identifiers, automated landmarking, or
cross-template morphometric comparison.

## Implemented workflow

1. The first institutional administrator is bootstrapped from environment
   secrets. Students and expert reviewers then request accounts from the login
   page using their own email addresses and passwords. Each account remains
   inactive until an administrator approves it.
2. An administrator assigns each approved student to one genus and one exact
   landmark template version.
3. The student records required specimen metadata and uploads a right-forewing
   image. Required fields include species identification, identification
   method, sex, collection date, country, locality, collector, locality sample
   code, planned locality sample count, and the specimen number within that
   1..N locality set. Notes remain optional.
4. The student calibrates image scale from a visible reference length, such as
   a 1 mm scale bar, then places the template's numbered landmarks with the
   zoomed digitization view.
5. If a student submits by mistake before expert review, they may withdraw the
   submission from the review queue, create an editable replacement revision,
   or delete the withdrawn item from their active workspace. Deletion is a
   soft-delete/discard state; the withdrawn coordinate set remains preserved
   internally.
6. An expert approves it or returns it with comments. Returned work is cloned
   into a new editable revision; the reviewed coordinates remain preserved.
7. Approval atomically creates a permanent accession such as
   `WBR-HYM-APIS-000001`.
8. Repository and export pages expose approved records only. CSV and TPS export
   always target one exact template version.

See [the architecture](docs/ARCHITECTURE.md) and
[the Version 0.1 assumptions](docs/ASSUMPTIONS.md) before using the data model.

## Requirements

- Python 3.11 or newer
- SQLite for local single-user development
- PostgreSQL for production/concurrent use
- Cloudflare R2 or another durable object store for hosted original images

## Install

Create and activate a virtual environment, then install the package and test
dependencies:

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -e ".[dev]"
```

Copy `.env.example` to `.env` and configure a real administrator account.
`.env` is ignored by Git. On PowerShell, environment variables can instead be
set for the current process:

```powershell
$env:DATABASE_URL = "sqlite:///data/wing_repository.db"
$env:WBR_DATA_DIR = "data"
$env:WBR_BOOTSTRAP_ADMIN_EMAIL = "curator@institute.edu"
$env:WBR_BOOTSTRAP_ADMIN_FULL_NAME = "Institute Curator"
$env:WBR_BOOTSTRAP_ADMIN_PASSWORD = "choose-a-long-admin-password"
```

Create/upgrade the schema, then create/update the institutional administrator
and bundled Apis template:

```powershell
alembic upgrade head
python scripts/bootstrap_institution.py
```

Students and expert reviewers may request accounts from the first page of the
app using their own Gmail or institutional email addresses. Version 0.1 does
not implement Google OAuth or email verification; administrator approval is
required before a requested account can sign in.

If a newly provisioned hosted database has no published landmark templates, the
administrator page offers a **Load bundled Apis 19-landmark template** action.
This imports `repository_assets/templates/apis_standard_19_v2.json` so approved
students can be assigned without shell access to the hosted database.

## Run

From the repository root:

```powershell
streamlit run app.py
```

The default local address is `http://localhost:8501`.

## Test

```powershell
pytest
```

The default suite uses temporary SQLite databases and includes an Alembic
upgrade smoke test. SQLite foreign-key enforcement is enabled on every
connection. Concurrency and row-lock behavior must additionally be tested
against PostgreSQL before production deployment.

## Persistent Streamlit Cloud deployment

For a persistent hosted repository, keep Streamlit Cloud for the app but move
state out of Streamlit's ephemeral filesystem:

1. Create a Neon or Supabase PostgreSQL database.
2. Create a Cloudflare R2 bucket for original wing-image uploads.
3. Add R2 API credentials with object read/write access to that bucket.
4. Configure Streamlit Cloud secrets with a PostgreSQL `DATABASE_URL` and
   `WBR_STORAGE_BACKEND = "r2"`.

Example local PowerShell configuration:

```powershell
$env:DATABASE_URL = "postgresql+psycopg://wbr:secret@db.example.org/wbr?sslmode=require"
$env:WBR_STORAGE_BACKEND = "r2"
$env:WBR_R2_ENDPOINT_URL = "https://<account-id>.r2.cloudflarestorage.com"
$env:WBR_R2_BUCKET_NAME = "wing-originals"
$env:WBR_R2_ACCESS_KEY_ID = "<r2-access-key-id>"
$env:WBR_R2_SECRET_ACCESS_KEY = "<r2-secret-access-key>"
$env:WBR_R2_KEY_PREFIX = "originals/"
alembic upgrade head
streamlit run app.py
```

When an existing database was created through Alembic, the app applies pending
schema migrations on startup. For the first empty hosted database, configure
`WBR_BOOTSTRAP_ADMIN_EMAIL` and `WBR_BOOTSTRAP_ADMIN_PASSWORD`; startup creates
that real administrator account and imports the bundled Apis 19-landmark
template. It does not create example students, example reviewers, synthetic
specimens, or synthetic annotations. If the first administrator password needs
correction, temporarily set `WBR_BOOTSTRAP_ADMIN_RESET_PASSWORD = "true"` and
reboot once, then set it back to `"false"`.

The database and R2 bucket must be backed up together. Production users and
expert templates should be provisioned through reviewed administrative
procedures.

## Landmark template JSON

The bundled active template is at
`repository_assets/templates/apis_standard_19_v2.json`:

- `Apis right forewing standard 19-landmark template`
- version `2`
- right forewing only
- 19 fixed landmarks
- status `published`
- optional visual guide image:
  `repository_assets/reference_guides/apis_standard_19_v2_landmark_guide.png`

Each template fixes a genus, version, wing side/type, point count, ordinal
sequence, labels, and descriptions. Once a template is used by an annotation it
is treated as immutable; corrections are new template versions. The old bundled
10-landmark Apis teaching template has been retired and removed from new
assignments to avoid confusion.

Administrators can set the template's locality sampling policy. The default
policy is minimum 10 right forewings from one locality and advisable 15. The
student metadata form enforces that minimum for new records.

The guide image is displayed only to help human landmark placement; the app
does not extract coordinates from it, does not save its pixels with specimen
records, and does not mix it with uploaded-wing coordinates. Replace the
bundled user-provided guide with a licensed and cited image before production
publication if its reuse rights are uncertain.

## Published Apis Reference Analysis

The optional `Published Apis Reference Analysis` page is restricted to
preliminary single-wing **Apis mellifera** worker right-forewing shape analysis.
It is not species identification and does not make molecular/genomic lineage
claims. Hindwings are not supported.

External reference records are stored separately from native repository
specimens and never receive `WBR-HYM-*` accessions. The module expects local
copies of the published datasets; it does not download research data during
Streamlit startup.

The code is updated, but the analysis is not yet automatically active. It still
requires:

1. Downloading the Oleksa, Nawrocka and WorkflowHub reference files.
2. Running the database migration.
3. Importing the coordinates.
4. Validating the imported data.
5. Confirming the bundled 19-landmark template is published.
6. Building and activating the models.

Configure local source directories and an artifact directory:

```powershell
$env:WBR_OLEKSA_REFERENCE_DIR = "C:\reference-data\oleksa-zenodo-7244070"
$env:WBR_NAWROCKA_REFERENCE_DIR = "C:\reference-data\nawrocka-zenodo-7567336"
$env:WBR_APIS_WORKFLOW_DIR = "C:\reference-data\workflowhub-422"
$env:WBR_ANALYSIS_ARTIFACT_DIR = "data\analysis-artifacts"
```

Inspect and import:

```powershell
python -m wing_repository.reference_data inspect-oleksa
python -m wing_repository.reference_data import-oleksa
python -m wing_repository.reference_data inspect-nawrocka
python -m wing_repository.reference_data import-nawrocka
python -m wing_repository.reference_data validate-import
```

Build and activate models after the bundled 19-landmark template and external
reference imports are ready:

```powershell
python -m wing_repository.reference_data ensure-apis-template
python -m wing_repository.reference_data build-analysis-models --model-version 1
python -m wing_repository.reference_data activate-models --model-version 1
```

See:

- `docs/PUBLISHED_APIS_REFERENCE_ANALYSIS.md`
- `docs/EXTERNAL_REFERENCE_DATA.md`
- `docs/MORPHOMETRIC_METHODS.md`
- `docs/MODEL_VALIDATION.md`

## Digitizer capabilities and boundary

The current digitizer supports per-image scale calibration, selectable zoom,
viewport move controls, numbered sequential placement, immediate coordinate
persistence, undo-last, explicit deletion/replacement, and a server-rendered
landmark overlay. Templates may also declare an optional visual reference guide
image, which is shown above the uploaded specimen image when available. At
higher zoom levels, the app renders a cropped movable viewport and maps each
click back to the stored original specimen-raster dimensions. Pixel and
normalized coordinates are preserved; calibrated millimeter coordinates are
derived when a saved image scale is available.

Smooth mouse-drag pan, direct point dragging, hit-testing, keyboard nudging,
high-resolution tiles, and touch/pen interactions still require a purpose-built
Streamlit TypeScript component. The required event contract and coordinate
transform safeguards are documented in `docs/ARCHITECTURE.md`.

## Configuration

| Variable | Purpose | Default |
|---|---|---|
| `DATABASE_URL` | SQLAlchemy database URL | `sqlite:///data/wing_repository.db` |
| `WBR_STORAGE_BACKEND` | Original-image store: `local` or `r2` | `local` |
| `WBR_DATA_DIR` | Immutable image storage root | `data` |
| `WBR_MAX_UPLOAD_MB` | Maximum original upload size | `25` |
| `WBR_BOOTSTRAP_ADMIN_EMAIL` | First real administrator email for empty hosted databases | none |
| `WBR_BOOTSTRAP_ADMIN_FULL_NAME` | First administrator display name | `Repository Administrator` |
| `WBR_BOOTSTRAP_ADMIN_PASSWORD` | First administrator password; required when creating/resetting the bootstrap admin | none |
| `WBR_BOOTSTRAP_ADMIN_RESET_PASSWORD` | Reset bootstrap admin password from env on next startup | `false` |
| `WBR_R2_ENDPOINT_URL` | Cloudflare R2 S3 endpoint URL | none |
| `WBR_R2_BUCKET_NAME` | Cloudflare R2 bucket for original images | none |
| `WBR_R2_ACCESS_KEY_ID` | R2 access key ID | none |
| `WBR_R2_SECRET_ACCESS_KEY` | R2 secret access key | none |
| `WBR_R2_KEY_PREFIX` | Prefix for newly uploaded R2 objects | `originals/` |
| `WBR_OLEKSA_REFERENCE_DIR` | Local Oleksa/Zenodo 7244070 source directory | none |
| `WBR_NAWROCKA_REFERENCE_DIR` | Local Nawrocka/Zenodo 7567336 source directory | none |
| `WBR_APIS_WORKFLOW_DIR` | Local WorkflowHub 422 workflow directory | none |
| `WBR_ANALYSIS_ARTIFACT_DIR` | Versioned model artifact directory | `data/analysis-artifacts` |

Passwords are salted and hashed before storage. The local authentication layer
is for this milestone; production still requires HTTPS, hardened sessions,
account lifecycle management, audit logging, rate limiting, and a security
review.

## Streamlit Community Cloud repository deployment

For a persistent Streamlit Cloud repository, use root-level secrets like:

```toml
DATABASE_URL = "postgresql+psycopg://user:password@host/database?sslmode=require"
WBR_STORAGE_BACKEND = "r2"
WBR_R2_ENDPOINT_URL = "https://<account-id>.r2.cloudflarestorage.com"
WBR_R2_BUCKET_NAME = "wing-originals"
WBR_R2_ACCESS_KEY_ID = "<r2-access-key-id>"
WBR_R2_SECRET_ACCESS_KEY = "<r2-secret-access-key>"
WBR_R2_KEY_PREFIX = "originals/"
WBR_BOOTSTRAP_ADMIN_EMAIL = "curator@institute.edu"
WBR_BOOTSTRAP_ADMIN_FULL_NAME = "Institute Curator"
WBR_BOOTSTRAP_ADMIN_PASSWORD = "choose-a-distinct-long-password"
WBR_BOOTSTRAP_ADMIN_RESET_PASSWORD = "false"
```

Keep GitHub for source code only; do not push SQLite databases or uploaded wing
images into the repository.

## Repository layout

```text
app.py                         Streamlit entry point
wing_repository/               Models, services, and UI
alembic/                       Versioned database migrations
repository_assets/templates/   Bundled versioned template JSON
repository_assets/reference_guides/  Optional visual-only landmark guide images
scripts/bootstrap_institution.py  First-admin/template bootstrap helper
docs/ARCHITECTURE.md           Boundaries and data-integrity design
docs/ASSUMPTIONS.md            Explicit Version 0.1 assumptions
tests/                         Automated workflow and migration tests
```

## Scientific safeguards

- Original bytes, SHA-256, dimensions, and original-pixel coordinates are
  retained.
- `x_normalized = x_pixel / image_width` and
  `y_normalized = y_pixel / image_height` are saved for each point.
- Approved accessions refer to one exact immutable annotation revision and
  template version.
- Locality sample codes and sample numbers preserve 1..N collection grouping;
  Version 0.1 does not yet issue one shared accession to a multi-wing batch.
- Different template versions are never combined automatically.
- PCA scores are neither calculated nor used as identifiers.
