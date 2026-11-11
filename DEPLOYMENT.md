# Deploying VidKit

| Part | Host | Why |
|---|---|---|
| Frontend (`vidkit-frontend`) | **Vercel** | Static Next.js build |
| API (`vidkit-backend`) | **Render free plan** (Docker web service) | Needs FFmpeg, LibreOffice, Ghostscript, Tesseract, Pandoc, a background job queue and local temp storage, none of which run on serverless |
| Database | **Neon** (recommended) or **Supabase** Postgres | Survives redeploys; no Render disk needed |

```
Browser ──> Vercel (Next.js) ──HTTPS──> Render (FastAPI + FFmpeg, 1 instance) ──> Neon Postgres
                                              └── /app/storage (temp files, deleted after 1h)
```

---

## Database choice

The API stores two kinds of data:

1. **Rows** (`jobs`, `job_files`, `short_urls`): need to survive deploys (short links last 30 days).
2. **Files** (uploads/outputs): temporary, deleted after `FILE_TTL_MINUTES` (30 on the free setup).

| Option | Rows survive deploys? | Cost | Verdict |
|---|---|---|---|
| SQLite, no disk | **No**. Wiped on every deploy/restart | Free | Only for a quick test |
| SQLite on a Render disk | Yes | Disk is paid; a service with a disk can't do zero-downtime deploys | Works, but more moving parts |
| **Neon / Supabase Postgres** | Yes | Free tier is enough | **Recommended** |

With Postgres the files can live on the container's ephemeral disk. A deploy only loses jobs that were in progress, and those expire within the hour anyway.

---

## Step 0: Put the code on GitHub

The project folder is not a git repository yet. From `vidkit/`:

```bash
git init
git add .
git status          # confirm NO .env, .env.local, vidkit.db or storage/ files are listed
git commit -m "Initial commit"
```

Create an empty **private** repo on GitHub, then:

```bash
git remote add origin https://github.com/<you>/vidkit.git
git branch -M main
git push -u origin main
```

Both `.gitignore` files already exclude `.env`, `.env.local`, `*.db` and `storage/`.

---

## Step 1: Create the database

### Option A: Neon (recommended)

1. Sign up at [neon.tech](https://neon.tech) → **New Project**.
   - Name: `vidkit`, Postgres version: latest.
   - **Region: AWS US West (Oregon)** to match the Render region in `render.yaml`. If you prefer Europe, pick Frankfurt on both.
2. On the project dashboard click **Connect**, keep **Connection pooling** on, and copy the URL:
   ```
   postgresql://neondb_owner:xxxx@ep-xxx-pooler.us-west-2.aws.neon.tech/neondb?sslmode=require
   ```
3. Keep it for Step 2. You don't need to create tables: the API runs migrations on startup.

The free tier suspends the database after ~5 minutes idle. The first request afterwards takes about half a second longer. The API reconnects automatically (`pool_pre_ping`).

### Option B: Supabase

1. [supabase.com](https://supabase.com) → **New project**, region close to Render (e.g. West US / Oregon).
2. **Connect** → **Session pooler** → copy the URI (port **5432**):
   ```
   postgresql://postgres.<ref>:<password>@aws-0-us-west-1.pooler.supabase.com:5432/postgres
   ```
   - Do **not** use the *Transaction pooler* (port 6543). It breaks psycopg's prepared statements.
   - Do **not** use the *Direct connection*. It is IPv6-only, and Render can't reach it.
3. Append `?sslmode=require` to the URL.
4. If the password has special characters (`@ : / ? #`), URL-encode them (e.g. `@` → `%40`).

No code change is needed for either option. `postgresql://` URLs are switched to the psycopg driver automatically.

---

## Step 2: Deploy the API on Render

### Free plan: what to expect

`render.yaml` uses Render's **free** plan ($0, no card required). It's good for going live and testing, with these limits:

| Limit | Effect | How the config handles it |
|---|---|---|
| 512 MB RAM, small shared CPU | Video processing is slow | `MAX_UPLOAD_MB=200`, `MAX_VIDEO_DURATION_MIN=15`, `MAX_CONCURRENT_JOBS=1` |
| Sleeps after 15 min without traffic | First request after that takes ~1 min; a job running at that moment is lost | Nothing to do: users retry. Open `/api/health` to wake it before testing |
| Not enough memory for Demucs | **Vocal remover is disabled** (returns `DEPENDENCY_MISSING`) | Image is built with `INSTALL_DEMUCS=false` (the Dockerfile default) |

Everything else works: video, image, PDF, audio, Markdown and URL shortener. Keep test videos short (a few minutes).

Moving later (Oracle or a paid plan) needs no code change: run the same Dockerfile with `--build-arg INSTALL_DEMUCS=true`, raise the limits, and update `NEXT_PUBLIC_API_BASE_URL` on Vercel.

### 2.1 Connect GitHub

[dashboard.render.com](https://dashboard.render.com) → sign in with GitHub → allow access to the `vidkit` repo.

### 2.2 Create the service from the Blueprint

1. **New** → **Blueprint** → select the `vidkit` repo, branch `main`.
2. Render reads [`render.yaml`](render.yaml) and shows one web service, `vidkit-api`.
3. It asks for the three secret values:

| Variable | Value now |
|---|---|
| `DATABASE_URL` | The Neon/Supabase URL from Step 1 |
| `PUBLIC_BASE_URL` | `https://vidkit-api.onrender.com` (Render gives `https://<service-name>.onrender.com`; if the name is taken it adds a suffix, so fix this after the first deploy if needed) |
| `CORS_ORIGINS` | `http://localhost:3000` for now. Replaced in Step 4 |

4. Click **Apply**. The first build takes **5–15 minutes** (system packages, LibreOffice). Later builds are faster.

#### Without the Blueprint (manual alternative)

**New** → **Web Service** → pick the repo, then:

- Language: **Docker**
- Root Directory: `vidkit-backend` (Render then finds `vidkit-backend/Dockerfile` itself)
- Region: same as your database
- Instance type: **Free**
- Health Check Path: `/api/health`
- Environment: add every variable in the table in Step 2.4

Leave the Start Command empty, since the Dockerfile's `CMD` runs migrations and then the server.

### 2.3 Watch the first deploy

In **Logs** you should see, in order:

```
INFO  [alembic.runtime.migration] Running upgrade  -> 001_initial
INFO  [alembic.runtime.migration] Running upgrade 001_initial -> 002_short_urls
{"env": "production", "event": "app_started", ...}
Uvicorn running on http://0.0.0.0:10000
```

Render injects `PORT=10000`, and the container listens on it automatically.

### 2.4 Full environment variable reference

| Variable | Production value | Required |
|---|---|---|
| `APP_ENV` | `production` | yes |
| `DATABASE_URL` | Neon/Supabase URL | yes |
| `CORS_ORIGINS` | `https://<your-app>.vercel.app` (comma-separate several; no trailing `/`) | yes |
| `PUBLIC_BASE_URL` | `https://vidkit-api.onrender.com` (or your API custom domain) | yes |
| `STORAGE_DIR` | `/app/storage` | set by Dockerfile |
| `MAX_UPLOAD_MB` | `200` (free plan) | recommended |
| `MAX_VIDEO_DURATION_MIN` | `15` (free plan) | recommended |
| `MAX_CONCURRENT_JOBS` | `1` (free plan) | recommended |
| `FILE_TTL_MINUTES` | `30` (free plan) | optional |
| `RATE_LIMIT_INFO` / `RATE_LIMIT_JOBS` | `10/minute` / `5/hour` | optional |
| `YTDLP_COOKIES_FILE` | `/etc/secrets/cookies.txt` (see Step 6) | optional |
| `PDF_CONVERT_TIMEOUT_SEC`, `AUDIO_SEPARATE_TIMEOUT_SEC`, `MARKDOWN_TIMEOUT_SEC`, `SHORT_URL_TTL_DAYS` | defaults | optional |

The binary paths (`FFMPEG_PATH`, `GS_PATH`, `LIBREOFFICE_PATH`, …) are **not** needed. The image puts everything on `PATH`.

The vocal remover is off because the Dockerfile builds with `INSTALL_DEMUCS=false` by default. Don't enable it on the free plan.

### 2.5 Verify the API

```bash
curl https://vidkit-api.onrender.com/api/health
```

You should get `"status": "ok"`, `"env": "production"`, and a non-null version for `ffmpeg`, `ffprobe`, `yt_dlp`, `ghostscript`, `libreoffice` and `tesseract`. A `null` means that tool is missing from the image. Also open `https://vidkit-api.onrender.com/docs`.

In Neon/Supabase → Tables you should now see `jobs`, `job_files`, `short_urls`, `users`, `alembic_version`.

---

## Step 3: Deploy the frontend on Vercel

1. [vercel.com](https://vercel.com) → **Add New** → **Project** → import the `vidkit` repo.
2. **Root Directory**: `vidkit-frontend` (click *Edit*). Framework preset: Next.js (auto). Leave build settings as default.
3. **Environment Variables**:

   | Name | Value |
   |---|---|
   | `NEXT_PUBLIC_API_BASE_URL` | `https://vidkit-api.onrender.com` (no trailing `/`) |

4. **Deploy**. You get `https://<project>.vercel.app`.

`NEXT_PUBLIC_API_BASE_URL` is baked in at build time. After changing it, use **Deployments → ⋯ → Redeploy**.

---

## Step 4: Connect the two (CORS)

In Render → `vidkit-api` → **Environment**, set:

```
CORS_ORIGINS=https://<project>.vercel.app
```

Add custom domains comma-separated, e.g. `https://<project>.vercel.app,https://vidkit.com,https://www.vidkit.com`. Saving triggers a redeploy.

Vercel **preview** deployments use per-branch URLs that aren't in this list, so their API calls fail with a CORS error. Test against the production URL.

---

## Step 5: Smoke test

On the Vercel site:

- [ ] Home page loads, theme toggle works
- [ ] **Image Compressor**: upload a JPG → download result
- [ ] **Video Compressor**: upload a short MP4 → progress bar moves → download
- [ ] **Video Splitter**: upload → parts list → *Download all (ZIP)*
- [ ] **Merge PDF**, **PDF to Word**, **PDF OCR**, **Compress PDF**: one of each
- [ ] **Audio Converter**: MP3 → WAV
- [ ] **Markdown Convert**: to HTML
- [ ] **URL Shortener**: create a link, open it (redirects via `PUBLIC_BASE_URL/r/<code>`)
- [ ] **Video Downloader**: a public YouTube link (see Step 6 if it fails)

In the browser devtools Network tab, every API call should go to `vidkit-api.onrender.com` with no CORS errors.

---

## Step 6 (optional): Cookies for the video downloader

YouTube, Instagram and Facebook often block datacenter IPs like Render's, returning *"Sign in to confirm you're not a bot"* or `PRIVATE_OR_LOGIN_REQUIRED`.

1. Export cookies from a logged-in browser in Netscape format (e.g. the "Get cookies.txt LOCALLY" extension). Use a throwaway account, not your personal one.
2. Render → `vidkit-api` → **Environment** → **Secret Files** → add a file named `cookies.txt` with that content.
3. Set `YTDLP_COOKIES_FILE=/etc/secrets/cookies.txt`.

Cookies expire, so repeat when downloads start failing again. If cookies aren't enough, the next step is a residential proxy; this needs a small code change to pass `proxy` to yt-dlp.

---

## Step 7 (optional): Custom domains

- **Frontend**: Vercel → Project → Settings → Domains → add `vidkit.com`, then follow the DNS instructions.
- **API**: Render → `vidkit-api` → Settings → Custom Domains → add `api.vidkit.com` (CNAME to `vidkit-api.onrender.com`). Then update:
  - Render: `PUBLIC_BASE_URL=https://api.vidkit.com`, `CORS_ORIGINS=https://vidkit.com,https://www.vidkit.com`
  - Vercel: `NEXT_PUBLIC_API_BASE_URL=https://api.vidkit.com` → redeploy

---

## Operations

| Task | How |
|---|---|
| Deploy a change | `git push` to `main`. Render rebuilds the API only when `vidkit-backend/**` changes; Vercel rebuilds the frontend |
| Update yt-dlp (extractors break) | Render → **Manual Deploy → Clear build cache & deploy** (reinstalls the newest release) |
| See logs | Render → Logs (JSON lines); Vercel → Deployments → Functions/Build logs |
| Run a migration | Automatic. `alembic upgrade head` runs on every container start |
| Roll back | Render → Events → pick a previous deploy → *Rollback*; Vercel → Deployments → *Promote* |

### Constraints to keep in mind

- **Keep exactly one API instance.** Jobs run inside the API process, and files live on that instance's disk. Scaling out needs Celery + Redis and object storage (S3/R2) first.
- A deploy or restart kills jobs that are running at that moment. They show as failed, and users just retry.
- Render's ephemeral disk is limited. Keep `MAX_UPLOAD_MB` and `FILE_TTL_MINUTES` modest.

---

## Troubleshooting

| Symptom | Cause / fix |
|---|---|
| Browser console: *blocked by CORS policy* | `CORS_ORIGINS` doesn't exactly match the site origin (scheme, no trailing slash). Fix and let Render redeploy |
| Frontend calls `localhost:8000` | `NEXT_PUBLIC_API_BASE_URL` wasn't set before the build. Set it and redeploy on Vercel |
| Deploy fails at `alembic upgrade head` | Wrong `DATABASE_URL`: check password encoding, `?sslmode=require`, and use the Supabase *Session pooler* |
| `prepared statement ... already exists` | Supabase transaction pooler (port 6543). Switch to the session pooler (5432) |
| Instance restarts with *Out of memory* | File too big for 512 MB: lower `MAX_UPLOAD_MB` / `MAX_VIDEO_DURATION_MIN`, keep `MAX_CONCURRENT_JOBS=1` |
| `DEPENDENCY_MISSING` on vocal remover | Expected on the free plan (Demucs not installed) |
| Site hangs ~1 min on first action | Free instance waking from sleep. Wait, or open `/api/health` first |
| Short links point to `localhost` | `PUBLIC_BASE_URL` not set to the public API URL |
| All users hit the rate limit together | Proxy headers not trusted. The Dockerfile `CMD` passes `--proxy-headers`, so don't override the Start Command |
| Video downloader: *Sign in to confirm you're not a bot* | Datacenter IP blocked. See Step 6 |
