# Piano Pedagogue

An intelligent piano pedagogue and repertoire companion. Progressive web app with a
Python backend, a relational database, and a HUD-style constellation map of your repertoire.

## What is built so far

The backend is complete: 41 tables, 70 HTTP endpoints plus a live-listening WebSocket,
and 50 tests. The frontend PWA covers auth, repertoire, the constellation map, the
progression engine, and the Observatory where XP and gold are spent. The catalog carries
written context for every piece: what it depicts, its history, its hardest passages by bar
number, and why any two pieces are connected.

| Area | Status |
|---|---|
| Database models, all 7 schema sections | done |
| Async engine and session factory | done |
| Alembic, wired for async and pgvector | done |
| Auth: register, login, bearer tokens | done |
| Onboarding: profile, tastes, techniques, top ten | done |
| Catalog search and seed data | done |
| Repertoire CRUD, filtering, stats | done |
| Submissions: text, PDF, audio with queued processing | done |
| Storage layer, local and S3-compatible | done |
| Analyzer pipeline and job queue | done |
| Progression engine, prerequisites and paths | done |
| Constellation map graph, including friends' | done |
| Practice sessions, load guard, live listening | done |
| Weakness forge, practice plans, sight-reading, polyrhythm | done |
| Performance readiness scoring | done |
| Frontend app shell, router, API client | done |
| PWA offline support via Workbox | done |
| Constellation rendering with filters | done |
| Prerequisite flowchart with one-click pathway adoption | done |
| XP, gold, levels, ledger and achievements | done |
| Observatory shop: star colours, glow, nebulas, connectors | done |
| Performance grading gate above difficulty 7.0 | done |
| Rich piece overviews: scene, history, techniques, metadata | done |
| Hardest sections marked by bar number with practice cues | done |
| Clickable constellation links with connection summaries | done |
| Analyzers: PDF via OMR, audio via transcription | next |
| Frontend: submissions, drills, plans, live listening | next |

## Setup

Run the backend first, then the frontend in a second terminal.

## Backend

### 1. Start the database

```bash
cd backend
docker compose up -d
```

This brings up PostgreSQL 16 with the pgvector extension, plus Redis for the
job queue you will need in a later phase.

### 2. Create the virtual environment

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

On Windows the activate line is `.venv\Scripts\activate`.

### 3. Configure

```bash
cp .env.example .env
```

Then edit `.env` and set `SECRET_KEY` to a long random string. Generate one with:

```bash
python -c "import secrets; print(secrets.token_urlsafe(48))"
```

### 4. Migrate

```bash
export PYTHONPATH=.
alembic revision --autogenerate -m "initial schema"
alembic upgrade head
```

Before running `upgrade`, open the generated file in `alembic/versions/` and add this
as the first line of `upgrade()`:

```python
op.execute("CREATE EXTENSION IF NOT EXISTS vector")
```

Alembic does not emit extension statements, and the `pieces` and `techniques` tables
both have `vector` columns.

If you already migrated an earlier version of this project, the economy tables
(`wallets`, `ledger_entries`, `achievements`, `user_achievements`, `cosmetics`,
`user_cosmetics`) are new, as is `piece_link_notes` and a set of new columns on `pieces`,
`composers`, `techniques` and `passages`. Generate a follow-up migration for them:

```bash
alembic revision --autogenerate -m "economy and cosmetics"
alembic upgrade head
```

### 5. Seed the catalog

```bash
python -m app.seed
```

Loads 6 eras, 11 genres, 17 techniques, 11 composers, and 25 pieces with technique
weights, plus the prerequisite graph, 14 achievements and 19 shop cosmetics. It then fills
in the catalog detail: scene, history and a fact for all 29 pieces and movements, 67 marked
sections with bar numbers and practice cues, mechanics and common faults for every
technique, biographies for every composer, and 8 curated link notes.

Running it twice is safe. The base catalog exits early if it is already present, but new
catalog pieces, composers and genres are added, and marked sections are updated in place
(matched on piece and label, so recorded assessments and drills keep their passage).
Achievements and cosmetics are matched on their `code` and updated in place, so if you
seeded before the economy existed, re-run this command to pick them up. Without it the
Observatory will be empty.

### 6. Run

```bash
fastapi dev app/main.py
```

Open http://localhost:8000/docs.

### 7. Test

```bash
pytest
```

## Frontend

```bash
cd frontend
npm install
cp .env.example .env
npm run dev
```

Open http://localhost:5173. Vite proxies `/api` to the backend on port 8000, so there is
no CORS to configure in development.

For the PWA and offline behaviour, build and preview instead — the service worker is
deliberately off in dev so you are never fighting a stale cache:

```bash
npm run build
npm run preview
```

See `frontend/README.md` for the router, the API client and the constellation renderer.

## Trying the API

Register at `/docs`, copy the `access_token` from the response, click Authorize, and
paste it. Then walk the onboarding flow in order:

1. `PUT /api/v1/onboarding/profile` with `years_playing`, `self_level`, `hand_span_cm`
2. `GET /api/v1/catalog/genres` and `PUT /api/v1/onboarding/genres`
3. `GET /api/v1/catalog/composers?q=chopin` and `PUT /api/v1/onboarding/composers`
4. `GET /api/v1/catalog/techniques` and `PUT /api/v1/onboarding/techniques`
5. `GET /api/v1/catalog/pieces?q=etude` and `PUT /api/v1/onboarding/top-ten`
6. `GET /api/v1/onboarding/summary` to see it all together

Then the repertoire and submission flow:

7. `POST /api/v1/repertoire` with a `piece_id`, or an inline `piece` object
8. `POST /api/v1/repertoire/{entry_id}/submissions/text` with practice notes
9. `GET /api/v1/submissions/{id}` to poll, then `/analyses` for the passages found

Then the coaching features:

10. `GET /api/v1/progression/pieces/{piece_id}/prerequisites?persist=true` on a hard piece
11. `GET /api/v1/progression/pieces/{piece_id}/path` for the stepping-stone chain
12. `GET /api/v1/progression/constellation` for the HUD map data
13. `POST /api/v1/practice/sessions`, add items, then close it
14. `GET /api/v1/practice/load` for the load guard verdict
15. `POST /api/v1/drills/forge` with `{"count": 3}` to mine your weak passages
16. `POST /api/v1/repertoire/{entry_id}/plans` on a multi-movement work
17. `POST /api/v1/performances`, set a program, then check `/readiness`

Two behaviours worth knowing:

- `PUT /top-ten` is a full replace. It clears existing top-ten flags and rewrites them,
  so send the whole list every time.
- A top-ten item takes either a `piece_id` from catalog search, or an inline `piece`
  object. The inline path creates the piece with `is_user_created=True` and resolves the
  composer by name, creating the composer if new.

## Layout

```
piano-pedagogue/
├── backend/
├── frontend/
└── README.md
```

```
backend/
├── alembic/
│   ├── versions/
│   ├── env.py
│   └── script.py.mako
├── alembic.ini
├── app/
│   ├── api/
│   │   ├── deps.py
│   │   └── v1/
│   │       ├── auth.py
│   │       ├── coach.py
│   │       ├── onboarding.py
│   │       ├── performance.py
│   │       ├── practice.py
│   │       ├── progression.py
│   │       ├── repertoire.py
│   │       ├── submissions.py
│   │       └── router.py
│   ├── core/
│   │   ├── config.py
│   │   ├── database.py
│   │   ├── security.py
│   │   └── storage.py
│   ├── models/
│   │   └── models.py
│   ├── schemas/
│   │   └── schemas.py
│   ├── services/
│   │   ├── analyzers.py
│   │   ├── catalog.py
│   │   ├── coach.py
│   │   ├── economy.py
│   │   ├── onboarding.py
│   │   ├── performance.py
│   │   ├── practice.py
│   │   ├── progression.py
│   │   └── repertoire.py
│   ├── workers/
│   │   └── queue.py
│   ├── main.py
│   ├── seed.py
│   └── seed_lore.py
├── tests/
│   ├── test_algorithms.py
│   ├── test_catalog_detail.py
│   ├── test_smoke.py
│   └── test_units.py
├── docker-compose.yml
└── requirements.txt
```

## Notes on the design

**Joined-table inheritance.** `Submission` is the base table with a
`submission_type` discriminator. `TextSubmission`, `PdfSubmission`, and
`AudioSubmission` each carry their own table keyed on `submission_id`, mapped to the
attribute `id` so `submission.id` reads the same across all three.

**Two database drivers.** `asyncpg` drives the application, `psycopg` drives Alembic.
Running migrations through an async driver invites event-loop problems for no gain.

**Eager loading is not optional.** `expire_on_commit=False` on the session factory, and
`selectinload` on every list query. A lazy relationship access after an async commit
raises `MissingGreenlet`.

**The submission handshake.** Uploads return `202 Accepted` with a `poll_url`, not the
finished analysis. The submission row is committed before the job is enqueued, so the
worker can never race ahead of the write. Status moves
`queued -> processing -> done`, or `failed` with the error recorded in the analysis row.
The client polls `poll_url` until it settles.

**Polymorphic loading is not optional.** Querying the `Submission` base class lazily
loads subclass columns such as `body` and `storage_key` on attribute access, which
raises `MissingGreenlet` under async. Every submission query carries
`selectin_polymorphic`.

**Swappable queue and storage.** `JobQueue` has three implementations: `InlineQueue`
for tests, `BackgroundQueue` using FastAPI background tasks (the current default), and
`RedisQueue` backed by arq for when OMR and transcription land. `Storage` has
`LocalStorage` and `S3Storage`; setting `STORAGE_ENDPOINT` switches to S3 automatically.

**Catalog context is data, not prose in a template.** Every piece carries `scene`,
`historical_note`, `fun_fact`, `mood` and `tempo_marking`; every technique carries a
`mechanic` and a `common_fault`; every composer carries a `bio`, a `fun_fact` and a
`signature_sound`. The hardest sections are ordinary `passages` rows with
`source='catalog'`, a `difficulty_score`, a bar range, a description and a
`practice_cue`, linked to techniques through `passage_techniques`. All of it lives in
`app/seed_lore.py` and is applied by `seed_catalog_detail()`, which matches on title and
overwrites in place, so re-seeding never duplicates anything.

**Link summaries are generated, then overridden.** `LinkExplainer` composes an
explanation from real data: the techniques the two pieces actually share, each one's
weight in each piece, the mechanic behind it, and the marked passages where it shows up.
A `piece_link_notes` row keyed on the ordered pair plus link type replaces that generated
text with a hand-written one, and the response says which you got via `curated`. So every
edge in the constellation is explainable, and the ones worth writing about by hand are.

**Analyzers are real, their heavy lifting is not yet.** `TextAnalyzer` genuinely parses
practice notes: it extracts measure references, creates `passages`, tags them with
techniques, and writes `passage_assessments`. `ScoreAnalyzer` and `AudioAnalyzer` ingest
and validate files and count PDF pages, but stop short of OMR and transcription. Those
are the next phase, and they slot in behind the same interface.

**Explainable recommendations.** Technique weights and difficulty scores live in
ordinary columns, so the progression engine computes overlap deterministically. Every
recommendation carries a `rationale` naming the shared techniques, the difficulty gap,
and any technique the pianist rated a struggle. No LLM is required to rank; one can sit
on top later for prose and drill design.

## How the engines work

**Prerequisite ranking.** Each piece is a sparse technique vector of `{technique_id:
weight}`. A candidate scores on three parts: `0.60 x (0.7 cosine + 0.3 coverage)` for
technique similarity, `0.25 x gap_fit` where `gap_fit` is a Gaussian peaking at a
1.5-point difficulty drop, and `0.15 x weakness_bonus` for candidates that drill what
the pianist rated a struggle. Anything at or above the target's difficulty scores zero
and is dropped. Ask for Feux Follets and Chopin's double-thirds etude surfaces near the
top, because the shared double-thirds weight dominates the cosine.

**Stepping stones.** `PathPlanner` walks down from the target, taking the best
prerequisite the pianist does not already own, until it reaches their comfort ceiling
(the hardest piece they have retired or marked performance ready). The chain comes back
in ascending order, so it reads as a route rather than a regression.

**Load guard.** Each session item's load is minutes times a technique-weighted factor,
so 30 minutes of double thirds costs more than 30 minutes of scales. The weekly total is
compared against a chronic baseline: the average of the previous four active weeks times
1.3, floored at 120. Crossing 1.2 is caution, 1.5 is rest. Changing severity clears a
previous acknowledgement so a worsening week is not silently dismissed.

**Movement ordering.** `PlanBuilder` sorts movements by `difficulty + duration/600` and
opens with the gentlest. For Rachmaninoff's Second Concerto that puts the Adagio first,
which is the advice a teacher would give and exactly the behaviour the brief asked for.

**Readiness.** `15 + 55 x accuracy + 30 x tempo stability`, minus 6 per restart and 12
per memory slip, clamped to 0 to 100. A piece is only stage ready at 85 or above with a
genuinely clean run, and an entry that clears that bar is promoted to
`performance_ready` automatically. A program's verdict follows its weakest link, not its
average.
