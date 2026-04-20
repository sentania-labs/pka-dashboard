# Renarin — PKA Dashboard

A LAN-only, single-user web dashboard over Scott's Personal Knowledge Assistant filesystem. FastAPI + Jinja2 + htmx + Pico CSS. No database, no auth, no search. Primarily read-oriented with a small set of mediated writes (toggle `reviewed`, edit briefing todos/comments, save per-item review responses) — all writes flow through `services/file_writer.py`.

Four views:

- **Today** — renders `scott/inbox/YYYY-MM-DD-daily-briefing.md`
- **Needs Attention** — unreviewed notes under `kb/` grouped by age bucket
- **Drafts** — pending items in `scott/inbox/content-drafts/`
- **Archive** — browse `scott/inbox/briefing-archive/`

Installs as a PWA on mobile — service worker caches GETs, writes are never cached or replayed.

## Local development

```bash
pip install -e ".[dev]"

# Substitute /path/to/pka with your own PKA root path
PKA_ROOT=/path/to/pka uvicorn app.main:app --reload --port 8000
# open http://localhost:8000/
```

`PKA_ROOT` is required. No default — the app fails at import if it is unset.

Optional env vars:

| Var | Default | Purpose |
|---|---|---|
| `RENARIN_TZ` | `America/Chicago` | zoneinfo key used for "today" date math |
| `RENARIN_IDLE_LOCK_SECONDS` | `900` | Frontend idle-lock overlay (screen-privacy shim, NOT auth). `0` disables. |

## Docker

```bash
# Build
docker build -t pka-dashboard .

# Dev (HTTP, no certs) — substitute /path/to/pka with your own PKA root
docker run --rm -p 8000:8000 \
  -e PKA_ROOT=/data/pka \
  -v /path/to/pka/scott:/data/pka/scott:ro \
  -v /path/to/pka/kb:/data/pka/kb:ro \
  pka-dashboard \
  uvicorn app.main:app --host 0.0.0.0 --port 8000

# Prod (HTTPS, certs provided at /certs/) — substitute /path/to/pka with your own PKA root
docker run -d -p 8443:8443 \
  -e PKA_ROOT=/data/pka \
  -v /path/to/pka/scott:/data/pka/scott:ro \
  -v /path/to/pka/kb:/data/pka/kb:ro \
  -v /path/to/certs:/certs:ro \
  pka-dashboard
```

TLS certs (`/certs/tls.key`, `/certs/tls.crt`) are bind-mounted in production by your deploy host / lab toolkit from the internal-CA pattern already in use on `docker.example.internal`. Renarin does not generate or manage certificates.

## Endpoints

| Path | Purpose |
|---|---|
| `/` | Today's briefing |
| `/needs-attention` | Unreviewed notes grouped by age |
| `/drafts` | Pending content drafts |
| `/archive` | Archive index |
| `/archive/{filename}` | Render a single archived briefing |
| `/partials/today-body` | htmx partial refresh of the Today body |
| `/healthz` | `{"status":"ok"}` |

Mediated-write routes (CSRF-guarded, called by htmx from the views above): `POST /edit/reviewed`, `POST /edit/reviewed-undo`, `PATCH /edit/todo`, `PATCH /edit/comments`, `PATCH|POST /edit/review-response`. Every successful write triggers an auto-commit in the PKA repo (insurance snapshot) and a JSONL audit-log entry at `scott/inbox/_renarin-audit-log.jsonl`.

## Hard rules

Read `CLAUDE.md` — scope, hard rules (read-only, no auth, no CI), and the canonical scope doc are all linked there.
