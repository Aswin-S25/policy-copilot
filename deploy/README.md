# Deploying Policy Copilot for free

A public demo at ₹0/month: no paid plans anywhere.

```
Browser ──HTTPS──▶ Vercel Hobby (static React build)
   └──HTTPS, bearer token, CORS limited to the Vercel origin──▶ Render Free (FastAPI, 1 instance)
                     ├─ embedding model via ONNX Runtime (in-process, no PyTorch)
                     ├──TLS──▶ Neon Free (PostgreSQL + pgvector)
                     └──HTTPS─▶ Groq free tier (OpenAI-compatible LLM API)
```

Not deployed: Redis and the Celery worker (document upload). The knowledge
base is copied from your local database instead (step 3), and rate limits
run in memory on the single API instance.

## What "free" costs you

| Service | Free allowance (Nov 2026; re-check on signup) | What visitors notice |
|---|---|---|
| Render Free | 512 MB RAM, sleeps after 15 min idle, 750 h/month | First visit after idle: "Waking up…" for up to a minute |
| Neon Free | 1 GB storage, 100 compute-hours/month, sleeps after 5 min idle | ~1 s extra on the first query after idle; never paused |
| Groq free tier | Per account, roughly 30 requests/min, 1,000/day, 8K tokens/min, 200K tokens/day | About 1–2 answers per minute across all visitors, ~40–50 per day; beyond that "temporarily unavailable, try again" |
| Vercel Hobby | Personal, non-commercial projects | Nothing |

The deployed model is Groq's `openai/gpt-oss-120b`, not the local Qwen3-8B,
so answers read differently. The citation rules are enforced by the API
either way: uncited answers are replaced by a refusal.

Measured on the deployment image capped at 512 MB: 275 MB at idle, 278 MB
peak while streaming answers. Embeddings from ONNX match the stored PyTorch
vectors (cosine similarity 1.000000 over all chunks), so the existing
vectors are reused as they are.

## Accounts you need

Sign up with your GitHub account where offered. Neon, Groq and Vercel need
no card. Render may ask for a card at signup; the free instance is never
billed while `render.yaml` says `plan: free`.

## Step 1: Groq API key

1. https://console.groq.com → API Keys → Create API key. Copy it once; it
   isn't shown again.
2. Check the model is offered to your account (PowerShell):
   ```powershell
   $secure = Read-Host "Groq key" -AsSecureString
   $key = [System.Net.NetworkCredential]::new("", $secure).Password
   (Invoke-RestMethod https://api.groq.com/openai/v1/models -Headers @{Authorization="Bearer $key"}).data.id | Select-String gpt-oss
   Remove-Variable key, secure
   ```
   If `openai/gpt-oss-120b` isn't listed, pick another listed model and use
   its id for `POLICY_LLM_MODEL` in step 4.

## Step 2: Neon database

1. https://console.neon.tech → New project. Region: **AWS Asia Pacific
   (Singapore)** (same region as the API). Postgres 16 or 17.
2. Dashboard → Connect → copy the connection string with **connection
   pooling turned off** (the host without `-pooler`). The app holds its own
   small pool, and Neon's pooler doesn't support psycopg's prepared
   statements. It looks like
   `postgresql://USER:PASSWORD@ep-xxxx.ap-southeast-1.aws.neon.tech/neondb?sslmode=require`.
   Keep it secret.

## Step 3: Schema and knowledge base (from your machine)

Run from the repository root with the local stack running
(`docker compose up -d`). Works in Windows PowerShell 5.1 and PowerShell 7:

```powershell
# Read the Neon URL once. Paste with Ctrl+V or right-click; it shows as *****.
$secure = Read-Host "Neon URL" -AsSecureString
$neon = [System.Net.NetworkCredential]::new("", $secure).Password

# Create the schema and pgvector in Neon. The output must include lines like
# "Running upgrade  -> f596eed3342c"; if it doesn't, it ran against your local database.
$env:POLICY_DATABASE_URL = $neon
alembic upgrade head
Remove-Item Env:POLICY_DATABASE_URL

# Copy the knowledge base: local database (source) -> Neon (target).
$env:SOURCE_DATABASE_URL = "postgresql://policy_user:policy_password@127.0.0.1:5433/policy_copilot"
$env:TARGET_DATABASE_URL = $neon
python deploy/copy_documents.py --dry-run # checks only
python deploy/copy_documents.py           # copies documents, sections, chunks, access rules

# Forget the secret in this window.
Remove-Item Env:TARGET_DATABASE_URL; Remove-Variable neon, secure
```

`copy_documents.py` copies only the policy knowledge base (no users, no
conversations), refuses if the schemas differ or the target already has
documents, and runs in one transaction. Your local database is only read.

## Step 4: API on Render

1. https://dashboard.render.com → New → **Blueprint** → connect this GitHub
   repository. Render reads `render.yaml` (branch `main`).
2. It asks for the secret values (`sync: false`):

   | Variable | Value |
   |---|---|
   | `POLICY_DATABASE_URL` | the Neon URL from step 2 (`postgresql://…` is fine) |
   | `POLICY_LLM_API_KEY` | the Groq key from step 1 |
   | `POLICY_CORS_ORIGINS` | leave as `https://example.invalid` for now; set in step 6 |

   Already set by the Blueprint: `POLICY_JWT_SECRET` (generated by Render),
   `POLICY_LLM_PROVIDER=openai`, `POLICY_LLM_BASE_URL`, `POLICY_LLM_MODEL`,
   `POLICY_LLM_REASONING_EFFORT=low`, `POLICY_LLM_MAX_CONCURRENCY=3`,
   `POLICY_DEMO_MODE=true`. Baked into the image: the ONNX embedding settings
   and `POLICY_RATE_LIMIT_BACKEND=memory`.
3. Apply. The first build takes several minutes. Then open
   `https://<service>.onrender.com/health/ready`: every critical check
   (`database`, `llm`, `embedding_model`) should be `true`. `redis` is
   `false` by design.

## Step 5: Frontend on Vercel

1. https://vercel.com/new → import this repository.
2. **Root Directory: `frontend`**. Framework: Vite (detected; `vercel.json`
   sets the build and the client-side routing rewrite).
3. Environment variable: `VITE_API_BASE_URL` = `https://<service>.onrender.com`
   (no trailing slash). It's public by design: only the API's address.
4. Deploy, and note the production URL (`https://<project>.vercel.app`).

## Step 6: Allow the frontend's origin

Render → the service → Environment → `POLICY_CORS_ORIGINS` =
`https://<project>.vercel.app` (exact origin, no trailing slash; several are
comma-separated). Saving redeploys the API.

## Keeping it safe

- Secrets live only in the Render and Neon dashboards. The frontend holds no
  keys; `VITE_` variables are public.
- Authorization is unchanged: every request is checked by the API, documents
  are filtered by role in SQL, demo visitors get fresh private identities.
- The policies are synthetic. Don't load real company documents into a
  public demo.
- No keep-alive pings: the API sleeps when nobody uses it, as the free plan
  intends. Visitors see "Waking up Policy Copilot…" and their request
  continues on its own.

## When something is wrong

| Symptom | Likely cause |
|---|---|
| `/health/ready` shows `llm: false` | Wrong Groq key, or the model id isn't offered (step 1) |
| Browser console: CORS error | `POLICY_CORS_ORIGINS` isn't exactly the Vercel origin |
| "The answer service is temporarily unavailable" | Groq free-tier rate limit; wait a minute |
| Every visit shows "Waking up…" | Expected after 15 min idle on Render Free |
| Render deploy fails with "out of memory" | The service isn't using `deploy/Dockerfile` |
