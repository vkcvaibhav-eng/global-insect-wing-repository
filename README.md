# Global Insect Wing Repository

Version 0.1 is a functional, local-first Streamlit milestone for manual
digitization and expert curation of **Hymenopteran right forewings**. It stores
immutable original uploads, ordered landmark coordinates in original pixels and
normalized units, version-specific reviews, and approved repository accessions.

This is intentionally not the complete worldwide platform. It contains no
machine learning, WingSearch, PCA identifiers, automated landmarking, or
cross-template morphometric comparison.

## Implemented workflow

1. An administrator assigns a student to one genus and one exact landmark
   template version.
2. The student records specimen metadata and uploads a right-forewing image.
3. The student places the template's numbered landmarks and submits a complete
   immutable annotation revision.
4. An expert approves it or returns it with comments. Returned work is cloned
   into a new editable revision; the reviewed coordinates remain preserved.
5. Approval atomically creates a permanent accession such as
   `WBR-HYM-APIS-000001`.
6. Repository and export pages expose approved records only. CSV and TPS export
   always target one exact template version.

See [the architecture](docs/ARCHITECTURE.md) and
[the Version 0.1 assumptions](docs/ASSUMPTIONS.md) before using the data model.

## Requirements

- Python 3.11 or newer
- SQLite for the single-user local demonstration
- PostgreSQL for production/concurrent use

## Install

Create and activate a virtual environment, then install the package and test
dependencies:

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -e ".[dev]"
```

Copy `.env.example` to `.env` and replace all three demo passwords. `.env` is
ignored by Git. On PowerShell, environment variables can instead be set for the
current process:

```powershell
$env:DATABASE_URL = "sqlite:///data/wing_repository.db"
$env:WBR_DATA_DIR = "data"
$env:WBR_DEMO_ADMIN_PASSWORD = "choose-a-long-admin-password"
$env:WBR_DEMO_STUDENT_PASSWORD = "choose-a-long-student-password"
$env:WBR_DEMO_REVIEWER_PASSWORD = "choose-a-long-reviewer-password"
```

Create/upgrade the schema, then seed synthetic demonstration data:

```powershell
alembic upgrade head
python scripts/seed_demo.py
```

The seed is idempotent. It creates these local demonstration identities, using
the passwords supplied through environment variables:

| Role | Login |
|---|---|
| Administrator | `admin@example.test` |
| Student | `student@example.test` |
| Expert reviewer | `reviewer@example.test` |

The demonstration image is a generated schematic and is not a taxonomic
reference specimen.

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

## PostgreSQL deployment

Install the project as above and set a PostgreSQL SQLAlchemy URL, for example:

```powershell
$env:DATABASE_URL = "postgresql+psycopg://wbr:secret@db.example.org/wbr"
alembic upgrade head
streamlit run app.py
```

`WBR_DATA_DIR` must be a durable, backed-up volume. The database and original
image store must be backed up together. Run the seed command only for an
explicit demonstration environment; production users and expert templates
should be provisioned through reviewed administrative procedures.

## Landmark template JSON

The illustrative, versioned template is at
`demo_data/templates/apis_v1.json`. Each template fixes a genus, version, wing
side/type, point count, ordinal sequence, labels, and descriptions. Once a
template is used by an annotation it is treated as immutable; corrections are
new template versions.

## Digitizer capabilities and boundary

The current digitizer supports numbered sequential placement, immediate
coordinate persistence, undo-last, explicit deletion/replacement, and a
server-rendered landmark overlay. Every click is mapped from the component's
actual rendered dimensions to the stored original raster dimensions.

Smooth zoom/pan, direct point dragging, hit-testing, keyboard nudging,
high-resolution tiles, and touch/pen interactions require a purpose-built
Streamlit TypeScript component. The required event contract and coordinate
transform safeguards are documented in `docs/ARCHITECTURE.md`. The milestone
does not pretend that browser-level image scaling provides scientific zoom.

## Configuration

| Variable | Purpose | Default |
|---|---|---|
| `DATABASE_URL` | SQLAlchemy database URL | `sqlite:///data/wing_repository.db` |
| `WBR_DATA_DIR` | Immutable image storage root | `data` |
| `WBR_MAX_UPLOAD_MB` | Maximum original upload size | `25` |
| `WBR_AUTO_BOOTSTRAP_DEMO` | Auto-migrate/seed disposable hosted demo | `false` |
| `WBR_DEMO_ADMIN_PASSWORD` | Seed-only administrator password | none |
| `WBR_DEMO_STUDENT_PASSWORD` | Seed-only student password | none |
| `WBR_DEMO_REVIEWER_PASSWORD` | Seed-only reviewer password | none |

Passwords are salted and hashed before storage. The local authentication layer
is for this milestone; production still requires HTTPS, hardened sessions,
account lifecycle management, audit logging, rate limiting, and a security
review.

## Streamlit Community Cloud demonstration

For a disposable demonstration deployment, configure these root-level secrets
in Streamlit Community Cloud before starting the app:

```toml
DATABASE_URL = "sqlite:///data/wing_repository.db"
WBR_DATA_DIR = "data"
WBR_AUTO_BOOTSTRAP_DEMO = "true"
WBR_DEMO_ADMIN_PASSWORD = "choose-a-distinct-long-password"
WBR_DEMO_STUDENT_PASSWORD = "choose-another-distinct-long-password"
WBR_DEMO_REVIEWER_PASSWORD = "choose-a-third-distinct-long-password"
```

This mode applies Alembic migrations and creates the synthetic approved sample
on first startup. Community Cloud's local filesystem is not durable: uploaded
images and SQLite changes can disappear on restart or redeploy. Use PostgreSQL
and durable original-image storage for any production or real-data deployment.

## Repository layout

```text
app.py                         Streamlit entry point
wing_repository/               Models, services, and UI
alembic/                       Versioned database migrations
demo_data/templates/           Sample versioned template JSON
scripts/seed_demo.py           Idempotent synthetic demo seed
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
- Different template versions are never combined automatically.
- PCA scores are neither calculated nor used as identifiers.
