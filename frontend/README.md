# Policy Copilot: web frontend

React + TypeScript + Vite + Tailwind CSS. A thin client over the FastAPI
backend in this repository: the API is the source of truth for
authentication, permissions, retrieval, answers and citations. The frontend
never filters, ranks or rewrites what the API returns.

## Run it locally

Prerequisites: Node 20+, the backend stack running, and Ollama with the model
pulled (see the root `docker-compose.yml`).

```bash
docker compose up -d              # from the repository root
cd frontend
npm install
npm run dev                       # http://localhost:5173
```

Create an account, then sign in with it (run from the repository root; the
password is asked for twice at a hidden prompt):

```bash
python -m app.cli.users create alice --roles employee manager
```

Other account commands: `set-password`, `set-roles`, `disable`, `enable`,
`delete`, `list` (see `app/cli/users.py`). Roles are `employee`, `manager`,
`hr`, `security` (document access) and `admin` (document upload only).

### Demo mode (for showing the project)

Set `POLICY_DEMO_MODE=true` in the root `.env` and restart the API
(`docker compose up -d api`). The sign-in page then offers one-click sample
accounts (Employee, Manager, HR, Security), each with the number of
policies it can read, so a visitor can see the same question answered from
different documents without a password. Each click creates a fresh private
identity (`demo-<role>-<random>`), so visitors never see each other's
conversations; real usernames can't start with `demo-`. Demo sign-ins are
rate-limited per address. Leave it off for anything but a showcase: anyone
who can reach the API can use it.

Sign-in calls `POST /auth/login`, which checks the Argon2id password hash and
returns the same bearer token every other endpoint already verifies.
Attempts are rate-limited per account and per client address. Tokens last
`POLICY_JWT_TTL_MINUTES` (60 by default); signing out discards the token in
the browser, and role changes apply at the next sign-in.

### Configuration

| Variable | Where | Default | Purpose |
|---|---|---|---|
| `VITE_API_BASE_URL` | build time, browser | `/api` | Base URL for API calls |
| `API_PROXY_TARGET` | dev server only | `http://127.0.0.1:8000` | Where `/api` is forwarded in `npm run dev` |

Copy `.env.example` to `.env.local` to override. Never put secrets in a
`VITE_` variable: they are compiled into the public bundle.

In development the browser talks only to Vite, which forwards `/api/*` to
FastAPI. Same origin, so the API needs no CORS configuration.

## Scripts

| Command | What it does |
|---|---|
| `npm run dev` | Dev server with hot reload |
| `npm run build` | Type-check, then build to `dist/` |
| `npm run typecheck` | TypeScript only |
| `npm test` | Unit tests (Vitest): stream parser, citations, token parsing, turn lifecycle |
| `npm run test:e2e` | End-to-end tests (Playwright) against the **real** stack |

`npm run test:e2e` needs the backend running and ready. It creates two
throwaway accounts with random passwords through `app.cli.users` (so it needs
the backend's Python environment and `.env`), signs in through the real form,
and deletes the accounts afterwards. It starts the dev server if needed and
runs serially because local Ollama answers one question at a time. Expect
about a minute. Run `npx playwright install chromium` once beforehand.

## How it works

```
src/
  api/            fetch wrapper, typed errors, SSE reader, endpoint functions
  auth/           token sign-in, session storage, route guard
  chat/           conversation view, composer, message rendering, turn store
  sources/        citation markers, sources strip, sources panel
  conversations/  sidebar list state, delete flow
  documents/      document library
  layout/         app shell, sidebar, header, service status banner
  ui/             buttons, icons, notices, dialog
```

### Streaming answers

`POST /conversations/{id}/messages/stream` is a POST with a bearer token, so
`EventSource` can't be used; `api/sse.ts` reads the same `text/event-stream`
format from `fetch`. Events arrive as `status → question → token… → answer →
citations → saved → done`, or `error` instead of `answer`.

- `token` text is shown as it arrives; the `answer` event is authoritative
  and replaces it (the server removes invalid citations).
- The server keeps a question only if its answer is saved. On any failure,
  including the user pressing Stop or the connection dropping, it deletes
  the question. The UI therefore shows a failed question as "not saved" with
  Retry, and after an interrupted stream asks the server whether the answer
  was stored before deciding.
- `chat/turns.ts` holds in-flight questions outside React views, one per
  conversation, so a stream continues while you open another conversation
  and a second send can't start a duplicate.

### Citations

`[Source N]` markers (the only form the backend validates) become buttons via
a small remark plugin that works on the parsed Markdown tree, so markers in
code stay literal. Source `N` is the N-th entry of the answer's citation list.
Live answers get the list from the `citations` event; saved answers from
`GET /conversations/{id}`. Passages are loaded on demand from
`GET /chunks/{chunk_id}`, which applies the same document permissions as
retrieval.

Generated text is set in Public Sans; anything quoted from or naming a
policy is set in Source Serif 4, so evidence is never mistaken for the
model's words.

### Sessions and security

- Wrong username, wrong password and disabled account all get the same
  "Incorrect username or password." The password field is cleared after a
  failed attempt; the form supports password managers (`autocomplete`).
- The token is kept in `sessionStorage` (this tab only, cleared on close)
  and sent only as an `Authorization` header, never in URLs or logs.
- Token claims are decoded only to show who is signed in and when the
  session ends. The API verifies every request; any 401 signs the user out.
- Behind a reverse proxy, run uvicorn with `--proxy-headers` (and trusted
  `--forwarded-allow-ips`) so the per-address sign-in limit sees real client
  addresses rather than the proxy's.
- Model output and policy text are rendered as Markdown with raw HTML
  disabled.

## Deploying

Build once (`npm run build`) and serve `dist/` from the same origin as the
API, so no CORS is needed and the bearer token never crosses origins. With
nginx in front of the API:

```nginx
server {
    listen 443 ssl;
    root /srv/policy-copilot/frontend/dist;

    location /api/ {
        proxy_pass http://127.0.0.1:8000/;   # trailing slash strips /api
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Request-ID $request_id;
        proxy_buffering off;                 # stream SSE tokens immediately
        proxy_read_timeout 300s;             # long answers
    }

    location /assets/ {
        add_header Cache-Control "public, max-age=31536000, immutable";
    }

    location / {
        try_files $uri /index.html;          # client-side routes
        add_header Cache-Control "no-cache";
    }
}
```

Build with `VITE_API_BASE_URL=/api` (the default). If the API must live on
another origin, set `VITE_API_BASE_URL` to its URL and add CORS to the API
for exactly that origin.

## Known limits

- The conversation list shows the 50 most recent conversations (an API
  limit); the document list isn't paginated.
- Answers loaded from history have no retrieval score (it isn't stored);
  the UI doesn't display scores anywhere.
