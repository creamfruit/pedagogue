# Deploying Pedagogue

This guide puts the backend, its database, Redis and a background worker on
[Render](https://render.com), stores uploads in an S3-compatible bucket
(Cloudflare R2 is used below; AWS S3 or Backblaze B2 work the same way), and
serves the website as a Render static site. Everything is described in
[`render.yaml`](render.yaml), so most of the work is filling in a few values.

The iOS and Android apps use the same backend. See
[`MOBILE_RELEASE.md`](MOBILE_RELEASE.md) for the store side.

## What gets created

| Render resource | Kind | What it does |
|---|---|---|
| `pedagogue-db` | Postgres 16 | All app data. The first migration enables `pgvector`. |
| `pedagogue-redis` | Key Value (Redis compatible) | Job queue for uploads, coach feedback and the daily/weekly schedules. |
| `pedagogue-api` | Docker web service | The FastAPI app. Before each deploy it runs `scripts/release.sh`: `alembic upgrade head`, then `python -m app.seed`. |
| `pedagogue-backup` | Docker cron job | Every night at 03:00 UTC, dumps the database with `pg_dump` and uploads it to the backup bucket. See "Backups and restoring" below. |
| `pedagogue-worker` | Docker background worker | Runs `arq app.workers.queue.WorkerSettings`: processes uploads, writes coach feedback, and runs the midnight roulette snippet and Friday meteor shower. |
| `pedagogue-web` | Static site | The Vite build of `frontend/`, with every path rewritten to `index.html`. |

Pre-deploy commands need a paid instance type, which is why the API and worker
use the `starter` plan. On a free instance, set `RUN_RELEASE_ON_START=true` on
`pedagogue-api` and the same migrations and seed run each time the container
starts.

The seed is safe to run on every deploy: it only adds what is missing and
updates marked passages, achievements and cosmetics in place.

## 1. Create the upload bucket (Cloudflare R2)

1. Sign in at <https://dash.cloudflare.com>, open **R2 Object Storage**, and
   add a payment method if asked (the free tier covers 10 GB).
2. **Create bucket**. Name it `pedagogue-uploads`, location Automatic. Leave
   public access off: the API reads and writes files itself and never hands
   out bucket URLs.
3. Back on the R2 overview page, choose **Manage R2 API Tokens**, then
   **Create API token**. Permission: **Object Read & Write**, restricted to
   `pedagogue-uploads`. Create it.
4. Copy three values from the result page. They are shown once:
   - **Access Key ID** becomes `STORAGE_ACCESS_KEY`
   - **Secret Access Key** becomes `STORAGE_SECRET_KEY`
   - the **S3 endpoint** (`https://<account id>.r2.cloudflarestorage.com`)
     becomes `STORAGE_ENDPOINT`

When `STORAGE_ENDPOINT` is set, the backend uses `S3Storage`. When it is empty
it falls back to the container's local disk, which Render wipes on every
deploy, so do not skip this step.

For AWS S3 instead: create a private bucket, an IAM user with
`s3:GetObject`, `s3:PutObject` and `s3:DeleteObject` on it, and set
`STORAGE_ENDPOINT=https://s3.<region>.amazonaws.com`.

## 2. Push the code

Render deploys from GitHub. Merge (or push) the branch you want live, for
example `main`, to `https://github.com/creamfruit/pedagogue`.

## 3. Create the Blueprint

1. Sign in at <https://dashboard.render.com> with GitHub and give Render
   access to the `pedagogue` repository.
2. **New > Blueprint**. Pick the repository and the branch. Render reads
   `render.yaml` and lists the five resources above.
3. Render asks for every variable marked `sync: false`. Fill them in now (the
   website URL is not known yet, so use the placeholder shown and change it in
   step 5):

   | Service | Variable | Value |
   |---|---|---|
   | pedagogue-api | `WEBSITE_URL` | `https://pedagogue-web.onrender.com` for now |
   | pedagogue-api | `CORS_ORIGINS` | the same URL; add any other site origins, comma separated |
   | pedagogue-api | `STORAGE_ENDPOINT` | R2 S3 endpoint from step 1 |
   | pedagogue-api | `STORAGE_BUCKET` | `pedagogue-uploads` |
   | pedagogue-api | `STORAGE_ACCESS_KEY` | R2 access key ID |
   | pedagogue-api | `STORAGE_SECRET_KEY` | R2 secret access key |
   | pedagogue-api | `ANTHROPIC_API_KEY` | your Anthropic key, or leave blank to turn AI features off |
   | pedagogue-api | `ADMIN_EMAILS` | your own sign-in email, for the admin endpoints |
   | pedagogue-web | `VITE_API_URL` | `https://pedagogue-api.onrender.com` (no trailing slash) |

4. **Apply**. Render creates the database and Redis first, builds the Docker
   image, runs the migrations and seed, then starts the API and worker. The
   first build takes about five minutes.
5. Open the `pedagogue-web` service and copy its URL. If it differs from the
   placeholder, set `WEBSITE_URL` and `CORS_ORIGINS` on `pedagogue-api` to
   it, then **Manual Deploy > Deploy latest commit** on the API.

The worker copies `SECRET_KEY`, the storage values and `ANTHROPIC_API_KEY`
from the API service, so you only enter them once. `SECRET_KEY` is generated
by Render. Never change it after launch: every signed-in user would be signed
out.

## 4. Check it works

1. `https://pedagogue-api.onrender.com/health` returns 200 with
   `{"status": "ok", ..., "checks": {"database": {"ok": true, ...}, "redis": {"ok": true, ...}}}`.
2. `https://pedagogue-api.onrender.com/docs` lists the endpoints.
3. Open the website, register, finish onboarding, open a piece and upload a
   PDF score. Its status should move from queued to done within a minute; if
   it stays queued, check the `pedagogue-worker` logs.

## 5. Custom domains (optional, needed before store submission)

The store listings and the privacy policy link should use your own domain.

1. On `pedagogue-web`, **Settings > Custom Domains > Add**, for example
   `pedagogue.app` and `www.pedagogue.app`. Create the DNS records Render
   shows you at your domain registrar. Render issues HTTPS certificates
   automatically.
2. On `pedagogue-api`, add `api.pedagogue.app` the same way.
3. Update the variables and redeploy:
   - `pedagogue-api`: `WEBSITE_URL=https://pedagogue.app`,
     `CORS_ORIGINS=https://pedagogue.app,https://www.pedagogue.app`
   - `pedagogue-web`: `VITE_API_URL=https://api.pedagogue.app`
4. Rebuild the mobile apps with the same `VITE_API_URL` (see
   `MOBILE_RELEASE.md`). The apps' own origins (`capacitor://localhost`,
   `http://localhost`, `https://localhost`) are always allowed by the API, so
   they need no CORS entry. Set `ALLOW_CAPACITOR_ORIGINS=false` only if you
   ever stop shipping the apps.

## Environment variable reference

### Backend (`pedagogue-api`, `pedagogue-worker`)

| Variable | Required | Default | Notes |
|---|---|---|---|
| `DATABASE_URL` | yes | local dev DB | Render's `postgres://` or `postgresql://` URL is accepted as is; the driver is added automatically. |
| `ALEMBIC_DATABASE_URL` | no | derived from `DATABASE_URL` | Only set it to migrate through a different connection. |
| `SECRET_KEY` | yes | `change_me` | Long random string. Generated by Render. |
| `ENVIRONMENT` | yes | `local` | `production` |
| `DEBUG` | yes | `true` | `false` |
| `WEBSITE_URL` | yes | none | The website origin. Always added to the CORS list. |
| `CORS_ORIGINS` | no | `http://localhost:5173,http://localhost:4173` | Extra allowed origins, comma separated. |
| `ALLOW_CAPACITOR_ORIGINS` | no | `true` | Allows `capacitor://localhost`, `http://localhost` and `https://localhost` for the apps. |
| `REDIS_URL` | yes with the worker | `redis://localhost:6379/0` | From the Key Value service. |
| `JOB_QUEUE` | yes | `background` | `redis` when the worker runs; `background` runs jobs inside the API process instead. |
| `STORAGE_ENDPOINT` | yes | none | S3 endpoint. Empty means local disk, which is lost on redeploy. |
| `STORAGE_BUCKET` | yes | `piano-pedagogue` | Bucket name. |
| `STORAGE_ACCESS_KEY` | yes | none | |
| `STORAGE_SECRET_KEY` | yes | none | |
| `ANTHROPIC_API_KEY` | no | none | Enables AI coach feedback, piece metadata and roulette snippets. |
| `ANTHROPIC_MODEL` | no | `claude-opus-5` | |
| `ANTHROPIC_EFFORT` | no | `medium` | |
| `ADMIN_EMAILS` | no | none | Comma separated. |
| `MAX_UPLOAD_MB` | no | `50` | Largest single upload. |
| `UPLOAD_QUOTA_MB` | no | `500` | Total stored uploads per user, measured from the bucket. An upload that would pass it is refused with a 413. |
| `RATE_LIMIT_ENABLED` | no | `true` | `false` turns every limit below off. |
| `RATE_LIMIT_STORAGE` | no | `memory` | `redis` counts in `REDIS_URL`, so limits hold across API instances and restarts. The blueprint sets `redis`. If Redis is unreachable the API counts in memory instead. |
| `RATE_LIMIT_SIGN_IN` | no | `10/minute` | Sign-in attempts per email address. Limits read `count/period`, where the period is `second`, `minute`, `hour` or `day`, optionally with a multiple (`5/15minutes`). |
| `RATE_LIMIT_SIGN_IN_IP` | no | `50/minute` | Sign-in attempts per client IP. |
| `RATE_LIMIT_REGISTER` | no | `20/hour` | New accounts per client IP. |
| `RATE_LIMIT_UPLOAD` | no | `30/hour` | Score and recording uploads per user. |
| `RATE_LIMIT_PDF_ANALYSIS` | no | `20/hour` | PDF scores sent to be read per user, counting uploads and retries. |
| `RATE_LIMIT_KEYBOARD_ATTEMPT` | no | `120/hour` | Keyboard runs saved per user. |
| `BACKUP_BUCKET` | yes for backups | `STORAGE_BUCKET` | Bucket the nightly dump goes to. Use its own bucket. |
| `BACKUP_RETENTION_DAYS` | no | `30` | Dumps older than this are deleted, but the newest `BACKUP_KEEP_MIN` (7) are always kept. |
| `SENTRY_DSN` | no | empty | Error reports from the API and worker. Empty turns reporting off. See "Error reporting" below. |
| `SENTRY_ENVIRONMENT` | no | `ENVIRONMENT` | Environment name on reports. |
| `SENTRY_TRACES_SAMPLE_RATE` | no | `0` | Share of requests sent as performance traces, 0 to 1. |
| `MUSICBRAINZ_CONTACT` | no | repo URL | Sent in the MusicBrainz user agent. |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | no | `10080` | Seven days. |
| `RUN_RELEASE_ON_START` | no | `false` | `true` runs migrations and seed on container start (free plans). |

### Website and apps (`pedagogue-web`, mobile builds)

| Variable | Required | Notes |
|---|---|---|
| `VITE_API_URL` | yes | Absolute backend origin, no trailing slash, no `/api/v1`. `npm run build` stops with an error without it. |
| `VITE_API_PREFIX` | no | Defaults to `/api/v1`. |
| `NODE_VERSION` | yes on Render | `22`. |
| `VITE_SENTRY_DSN` | no | Error reports from the website and apps. Empty turns reporting off, and the privacy policy then says no crash reporting is used. |
| `VITE_RELEASE` | no | Version tag on frontend error reports. |

## Backups and restoring

### What runs

`pedagogue-backup` is a Render cron job built from the same image as the API. Every night at 03:00
UTC it runs `python -m app.ops.backup run`, which:
- runs `pg_dump --format=custom --no-owner --no-privileges` against `DATABASE_URL`
- uploads the dump to `BACKUP_BUCKET` as `backups/pedagogue-YYYYMMDDTHHMMSSZ.dump`
- deletes dumps older than `BACKUP_RETENTION_DAYS`, always keeping the newest seven

A failed or empty dump fails the job. Render then marks the run as failed, and, with `SENTRY_DSN`
set, the error is reported. To change the time, edit `schedule` in `render.yaml` (cron syntax, UTC).

Render's paid Postgres plans also keep their own point-in-time recovery. The nightly dump is a
second copy outside Render, and one you can restore anywhere.

### Set it up

1. In Cloudflare R2, create a bucket just for backups (for example `pedagogue-backups`). Give the
   API token from step 1 read and write access to it, or create a separate token and set the
   storage keys on the cron job by hand.
2. Set `BACKUP_BUCKET` on `pedagogue-api` (the cron job copies it from there). The job reuses the
   API's `STORAGE_ENDPOINT` and keys.
3. In the Render dashboard, open `pedagogue-backup` and press **Trigger Run**. Check the logs for
   `uploaded backups/pedagogue-....dump`.

### Restore

Restore into a new, empty database first, check it, and only then point the app at it. This leaves
the current database untouched if something goes wrong.

1. **Find the dump.** Open the **Shell** tab of `pedagogue-api` and list the backups, newest first:

   ```bash
   python -m app.ops.backup list
   python -m app.ops.backup download backups/pedagogue-20261019T030000Z.dump /tmp/restore.dump
   ```

2. **Create the target.** In Render, create a new Postgres 16 database (for example
   `pedagogue-db-restore`) in the same region. Copy its **Internal Database URL**.
3. **Restore into it** from the same shell (the image ships `pg_restore` 17):

   ```bash
   export RESTORE_URL='postgresql://...internal URL of the new database...'
   pg_restore --no-owner --no-privileges --exit-on-error --dbname="$RESTORE_URL" /tmp/restore.dump
   ```

   The dump creates the `vector` extension itself, so the new database needs no setup.
4. **Check it**:

   ```bash
   psql "$RESTORE_URL" -c "select count(*) from users;" -c "select max(started_at) from practice_sessions;"
   psql "$RESTORE_URL" -c "select version_num from alembic_version;"
   ```

   The counts should match what you expect, and the latest session should be just before the dump.
5. **Switch over.** Suspend `pedagogue-worker` and `pedagogue-backup`. Then change `DATABASE_URL` on
   `pedagogue-api`, `pedagogue-worker` and `pedagogue-backup` to the new database. In the
   blueprint, rename `fromDatabase.name`, or set the URL by hand. Redeploy the API: its pre-deploy
   step runs `alembic upgrade head`, which brings an older dump up to the current schema. Resume
   the worker and the backup job.
6. Keep the old database until you are sure, then delete it.

**Restoring in place** overwrites the live database, so only do it when the database itself is
lost or unusable. Suspend the worker and the API first, then:

```bash
pg_restore --clean --if-exists --no-owner --no-privileges --single-transaction --exit-on-error \
  --dbname="$DATABASE_URL" /tmp/restore.dump
```

`--single-transaction` rolls everything back if any step fails. Everything written since the dump
is lost.

**Practise a restore** into a scratch database once a month, so you know the dumps work before you
need one.

Uploaded files live in the uploads bucket, not in the database, so they are not in these dumps.
Turn on R2 object versioning for that bucket if you want to recover deleted files.

## Error reporting

Errors from the API, the worker, the website and the apps go to Sentry when a DSN is set. Leave
`SENTRY_DSN` and `VITE_SENTRY_DSN` empty and nothing is sent.

1. In Sentry, create two projects: **Python (FastAPI)** for the backend and **Browser JavaScript**
   for the website and apps.
2. In each project, open **Settings > Security & Privacy** and turn on **Prevent Storing of IP
   Addresses** and **Data Scrubber**. The privacy policy promises the first.
3. Set the backend DSN as `SENTRY_DSN` on `pedagogue-api` (the worker copies it), and the browser
   DSN as `VITE_SENTRY_DSN` on `pedagogue-web` and in the mobile build environment. Redeploy, and
   rebuild the apps.

Before anything is sent, both sides strip personal data:
- **The user:** only the account ID is kept.
- **The request:** bodies, cookies, query strings and the `Authorization`, cookie and forwarding
  headers are dropped.
- **Everything else:** email addresses and bearer tokens are masked, and any field named like a
  password, token, secret or email is replaced.

Stack-frame variables are not collected. The backend scrubbing is in
`backend/app/core/monitoring.py`, the frontend's in `frontend/src/lib/monitoring.js`, and both are
covered by tests.

If an app build sets `VITE_SENTRY_DSN`, declare crash data in the store privacy forms
(`MOBILE_RELEASE.md`, section 8).

## Running the production image yourself

```bash
cd backend
docker build -t pedagogue-api .
docker run --rm -p 8000:8000 \
  -e DATABASE_URL=postgresql://piano:piano@host.docker.internal:5432/piano \
  -e SECRET_KEY=dev-only-secret \
  -e RUN_RELEASE_ON_START=true \
  pedagogue-api
```

Start the worker from the same image with `docker run ... pedagogue-api scripts/worker.sh`, and
take a backup with `docker run ... pedagogue-api scripts/backup.sh`.

## Health check

`GET /health` checks that the API can reach its dependencies:
- **Database:** runs `SELECT 1`.
- **Redis:** sends `PING`. This check runs only when something uses Redis (`JOB_QUEUE=redis` or
  `RATE_LIMIT_STORAGE=redis`, as in the blueprint). Otherwise it is reported as skipped.

Each check has a three-second timeout. The endpoint returns **200** with `"status": "ok"` when
every check that runs passes. Otherwise it returns **503** with `"status": "unavailable"`, plus
which check failed and how long each took. Error details go to the log, not the response.

The blueprint sets it as `healthCheckPath` on `pedagogue-api`. Render holds a new deploy back
until `/health` returns 200, so a release that cannot reach Postgres or Redis never takes traffic
and the previous version keeps serving. Once live, an instance that keeps failing the check is
restarted. On other hosts, point the platform's HTTP health check at `/health`.

## Other hosts

Nothing in the image is Render specific. On Fly.io, Railway or a VPS: build
`backend/Dockerfile`, run `scripts/release.sh` once per release, run
`scripts/start.sh` for the API (it listens on `$PORT`) and `scripts/worker.sh`
for the worker, and provide Postgres 16 with the `vector` extension available
plus any Redis 6 or newer. Use `/health` as the HTTP health check, and run `scripts/backup.sh`
nightly from the host's scheduler.
