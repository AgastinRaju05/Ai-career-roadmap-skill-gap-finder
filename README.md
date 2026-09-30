# CareerPath AI

A Flask app for exploring career paths, tracking your skills, creating a personalized learning roadmap, and tracking course and project progress. Career matching and roadmaps work locally without an AI API key. Groq credentials are optional and are not required by the default workflow.

## Quick start (Windows PowerShell)

From this folder:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
Copy-Item .env.example .env
```

Set `SECRET_KEY` in `.env` to a private random value before deploying. A Groq key is optional; leave `GROQ_API_KEY` blank to use the built-in local matching and roadmap generation.

Initialize the sample career and learning catalog, then start the server:

```powershell
.\.venv\Scripts\python.exe seed.py
.\.venv\Scripts\python.exe run.py
```

Open http://127.0.0.1:5000, register, add skills in **Profile**, take a skill check, and build a roadmap from a career page. The SQLite database is created under `instance/` and is ignored by Git.

## Features

- Account registration, login/logout, password hashing, same-site post-login redirects, and CSRF protection.
- Profile, education, career goal, and per-skill proficiency tracking.
- Career discovery ranked by the weighted overlap between user skill levels and career requirements.
- Career-specific self-assessment that updates the user's skill profile.
- Persistent roadmaps with ordered skill-building tasks and step status tracking.
- Course and project catalogs with per-user progress tracking.
- Repeatable seed script that creates or repairs sample career relationships and resources.

## Configuration

Configuration is loaded from environment variables or a local `.env` file. `DATABASE_URL` defaults to an SQLite database under `instance/`; `SECRET_KEY` must be set explicitly for any deployment — `run.py` and `wsgi.py` both refuse to start without one unless `FLASK_DEBUG=1`. Set `FLASK_DEBUG=1` only for local development. The Groq integration in `app/services/ai_service.py` is optional and is not used by core routes.

## Security notes

- **Never commit `.env`** (it's git-ignored). `.env.example` must only ever contain placeholder values — if a real secret is ever committed to a repo (even briefly), treat it as compromised and rotate it immediately, since it must be assumed to have been scraped by bots the moment it was pushed.
- The bundled `instance/` database is git-ignored on purpose; it can contain real user emails and password hashes once people register. Don't ship or share the `.db` file, and don't commit it.
- Generate a real `SECRET_KEY` with `python -c "import secrets; print(secrets.token_hex(32))"` and store it as an environment variable / platform secret, not in source control.
- When deploying behind HTTPS, set `SESSION_COOKIE_SECURE=true` in the environment.

## Deployment

The app ships with a `wsgi.py` entry point, a `Procfile`, and a `Dockerfile`, so it can be deployed to most PaaS providers (Render, Railway, Fly.io, Heroku-style platforms) or as a container.

**Required environment variables in production:**
- `SECRET_KEY` — long random value (see above). The app will not start without it outside `FLASK_DEBUG` mode.
- `DATABASE_URL` — e.g. a managed Postgres URL for real deployments. SQLite works but doesn't survive redeploys on most PaaS platforms with ephemeral filesystems.
- `GROQ_API_KEY` — optional; leave unset to use the deterministic local fallback.
- `SESSION_COOKIE_SECURE=true` — once served over HTTPS.

**Platform-as-a-service (Procfile-based):**
```bash
pip install -r requirements.txt
# set SECRET_KEY, DATABASE_URL, etc. as platform environment variables/secrets
python seed.py   # one-off, populates sample careers/skills/courses
gunicorn wsgi:app
```
The `Procfile`'s `web` line (`gunicorn wsgi:app`) is what most platforms auto-detect and run.

**Docker:**
```bash
docker build -t career-roadmap .
docker run -p 8000:8000 \
  -e SECRET_KEY=$(python -c "import secrets; print(secrets.token_hex(32))") \
  -e DATABASE_URL=sqlite:////app/instance/career_roadmap.db \
  -v career-roadmap-data:/app/instance \
  career-roadmap
```
Run `python seed.py` once (e.g. `docker exec` into the container) to populate the sample catalog.

`runtime.txt` pins Python 3.12: the `groq` package's bundled Pydantic v1 compatibility layer breaks on Python 3.14+, so deploy on 3.11–3.13 rather than the very latest interpreter.

## Tests

Install the requirements and run:

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

`db.create_all()` bootstraps a new local database; use a migration tool before making schema changes to an existing deployment database.

## Adaptive AI workflow

The current implementation uses an LLM through Groq for question generation, assessment analysis, personalized roadmaps, reassessments, and Advanced project briefs. The backend remains deterministic for scoring, the 50%/70% adaptive difficulty policy, skill-level estimation, validation, persistence, and fallback behavior.

Run:

```bash
pip install -r requirements.txt
copy .env.example .env
# Add GROQ_API_KEY to .env for live AI. The app still works with the local fallback bank without a key.
python seed.py
python run.py
```

Flow: Login → select one or more careers → adaptive AI MCQ → result/skill web → AI roadmap → learning progress → reassessment → Advanced → practical project.
