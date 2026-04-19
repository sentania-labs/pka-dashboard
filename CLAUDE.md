# CLAUDE.md — PKA Dashboard (Renarin)

Renarin is the web dashboard for Scott's Personal Knowledge Assistant. He renders what the PKA's agents write and supports a small set of targeted, mediated writes (toggling `reviewed`, editing todos/comments, saving per-item review responses) — no auth, no search. The observer who occasionally annotates.

## Project Overview

A lightweight, LAN-only FastAPI + htmx + Jinja2 web app served from a Docker container on `dashboard.example.internal:8443`. Renarin reads the PKA filesystem (bind-mounted into the container as `/data/pka`) and renders four views:

1. **Today** — today's daily briefing rendered as HTML
2. **Needs Attention** — live-computed list of unreviewed notes and stale drafts
3. **Drafts** — pending content drafts in `scott/inbox/content-drafts/`
4. **Archive** — browse `scott/inbox/briefing-archive/`

Views are primarily read-oriented. Targeted writes are allowed via mediated routes only (see Hard Rules and the `routes/edit_*.py` files): `reviewed` toggle, todo bracket edits, Scott's-comment block edits, and per-item `review_responses` writes. File moves and broader schema rewrites remain out of scope.

Canonical scope document: `../../agents/riker/status/pka-dashboard.md` (relative to this workspace). Don't duplicate requirements here — defer to that doc for decisions.

## Hard Rules

1. **Writes are mediated.** All filesystem writes go through `services/file_writer.py` only. Never write files directly from routes.
2. **No auth.** LAN trust perimeter. Single user. Do not add authentication layers.
3. **No CI.** No GitHub Actions, no workflow files, no runner configuration. Images are hand-built on the deploy host.
4. **No canonical remote by default.** GitHub may be added as a mirror when explicitly authorized by Scott. Treat local as canonical even with a remote configured — the Docker host's local working tree is the source of truth. Never `push` without explicit instruction.
5. **`PKA_ROOT` is always an env var.** Never hardcode `/path/to/pka` or `/data/pka` in the app code. Dev uses `PKA_ROOT=/path/to/pka`; container uses `PKA_ROOT=/data/pka`.
6. **TLS in production, HTTP in dev.** uvicorn serves HTTPS directly in the container (cert/key bind-mounted at `/certs/tls.key` and `/certs/tls.crt`). For local dev, run uvicorn on HTTP port 8000 — no certs needed.
7. **python-frontmatter for all YAML.** Never manually parse YAML frontmatter from markdown files. Use the `python-frontmatter` library.
8. **No database.** The PKA filesystem is the data source. No SQLite, no PostgreSQL, no ORM.

## Tech Stack

| Component | Choice |
|-----------|--------|
| Backend | FastAPI (Python 3.12+) |
| Frontend | Jinja2 templates + htmx |
| CSS | Pico CSS (minimal, no framework overhead) |
| Markdown rendering | mistune |
| Frontmatter parsing (read) | python-frontmatter |
| Frontmatter round-trip (write) | ruamel.yaml (preserves key order, quotes, block style) |
| Container | Single Docker container, no compose services |
| TLS | uvicorn `--ssl-keyfile` / `--ssl-certfile` (certs from your internal CA) |
| Port | 8443 (production) / 8000 (dev, HTTP) |

## PKA Filesystem Layout (read targets)

The app reads from `$PKA_ROOT`. In dev: `/path/to/pka`. In container: `/data/pka`.

```
$PKA_ROOT/
├── scott/
│   ├── inbox/
│   │   ├── YYYY-MM-DD-daily-briefing.md     ← Today view
│   │   ├── content-drafts/                  ← Drafts view
│   │   └── briefing-archive/                ← Archive view
│   └── ...
└── kb/                                      ← Needs Attention scan
    ├── work/
    ├── personal/
    ├── reference/
    └── Attachments/                         ← EXCLUDED from scans
```

**Needs Attention scan:** walk `kb/` (excluding `kb/Attachments/`), find notes where frontmatter has `needs_review: true` AND `reviewed` is absent or not `true`. Group by age bucket using the `date:` frontmatter field.

## Project Structure

```
pka-dashboard/
├── CLAUDE.md
├── Dockerfile
├── pyproject.toml
├── README.md
├── .gitignore
├── .pka/                    ← PKA workspace comms zone (updates land here)
│   └── updates/
│       └── archive/
└── app/
    ├── main.py              ← FastAPI app + route registration
    ├── config.py            ← PKA_ROOT and other env-driven settings
    ├── routes/
    │   ├── today.py         ← GET /
    │   ├── needs_attention.py  ← GET /needs-attention
    │   ├── drafts.py        ← GET /drafts
    │   ├── archive.py       ← GET /archive
    │   ├── edit_todo.py     ← PATCH /edit/todo (briefing todo brackets)
    │   ├── edit_comments.py ← PATCH /edit/comments (Scott's-comment blocks)
    │   ├── edit_review.py   ← POST /edit/reviewed (toggle reviewed=true)
    │   └── edit_review_response.py  ← PATCH /edit/review-response (per-item responses)
    ├── services/
    │   ├── notes.py         ← Frontmatter parsing, note loading, typed objects
    │   └── file_writer.py   ← Mediated write layer (ruamel.yaml round-trip, atomic + mtime-guarded)
    ├── templates/
    │   ├── base.html        ← Nav, page shell
    │   ├── today.html
    │   ├── needs_attention.html
    │   ├── drafts.html
    │   └── archive.html
    └── static/
        ├── htmx.min.js
        ├── todo.js          ← Inline editors for todos + comment blocks + toast wiring
        └── style.css
```

## Deploy Target

- **Host:** `dashboard.example.internal` (managed by your deploy host / lab toolkit)
- **Port:** 8443, HTTPS
- **TLS:** uvicorn `--ssl-keyfile /certs/tls.key --ssl-certfile /certs/tls.crt` — certs bind-mounted from the internal CA pattern used on `docker.example.internal`
- **Volume mount:** `~/pka/scott/` and `~/pka/kb/` → `/data/pka/scott/` and `/data/pka/kb/` (RW on the mount; app is RO in this phase)
- **No reverse proxy** in front. Single container, single port, direct TLS.
- **Image build:** `docker build` by hand on the deploy host. No CI, no registry push required.

## Not In Scope (MVP)

- Authentication of any kind
- Search (that's Jasnah's domain)
- Creating new notes from scratch, or file moves/renames
- Schema-wide frontmatter rewrites beyond the targeted edits listed above
- GitHub remote, CI/CD, GitHub Actions

## New frontmatter fields (Renarin-introduced)

- `review_responses: list[str]` — per-item responses to the `review_notes` questions raised by Shallan. Written by Renarin's Needs Attention editor. Index-aligned: `review_responses[N]` is the response to `review_notes[N]`. Missing trailing entries are treated as empty; writes extend the list with empty strings as needed. Shallan's agent def does not yet know about this field (as of 2026-04-17) — update separately before she next processes notes Scott has annotated.

## Development

```bash
# Install deps
pip install -e ".[dev]"

# Run locally (HTTP, port 8000)
PKA_ROOT=/path/to/pka uvicorn app.main:app --reload --port 8000

# Visit
open http://localhost:8000/

# Build container image
docker build -t pka-dashboard .

# Run container locally (HTTP mode for testing — no certs)
docker run -e PKA_ROOT=/data/pka \
  -v /path/to/pka/scott:/data/pka/scott:ro \
  -v /path/to/pka/kb:/data/pka/kb:ro \
  -p 8000:8000 pka-dashboard \
  uvicorn app.main:app --host 0.0.0.0 --port 8000
```
