import os
import secrets
import warnings
from pathlib import Path
from dotenv import load_dotenv

basedir = os.path.abspath(os.path.dirname(__file__))
load_dotenv(os.path.join(basedir, ".env"))

_DEBUG = os.environ.get("FLASK_DEBUG", "").lower() in {"1", "true", "yes"}
_SECRET_KEY = os.environ.get("SECRET_KEY")

if not _SECRET_KEY:
    # A random key is fine for local/dev/test runs, but it is generated fresh
    # every time the process starts. In production that silently logs out
    # every user on each restart/deploy, and every gunicorn worker would get
    # a *different* key, breaking sessions and CSRF at random. run.py/wsgi.py
    # refuse to start outside debug mode without a real SECRET_KEY, so this
    # fallback only ever applies to local development and the test suite.
    _SECRET_KEY = secrets.token_hex(32)
    if not _DEBUG:
        warnings.warn(
            "SECRET_KEY is not set; using a temporary key for this process only. "
            "Set a persistent SECRET_KEY before deploying.",
            RuntimeWarning,
        )


def _env_bool(name, default):
    value = os.environ.get(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes"}


class Config:
    SECRET_KEY = _SECRET_KEY
    SQLALCHEMY_DATABASE_URI = os.environ.get(
        "DATABASE_URL",
        "sqlite:///" + (Path(basedir) / "instance" / "career_roadmap.db").as_posix(),
    )
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    WTF_CSRF_ENABLED = True
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = "Lax"
    # Off by default so local http development and the test client keep
    # working. Set SESSION_COOKIE_SECURE=true in production (the app is
    # served over HTTPS there); see README.
    SESSION_COOKIE_SECURE = _env_bool("SESSION_COOKIE_SECURE", False)

    GROQ_API_KEY = os.environ.get("GROQ_API_KEY", "")
    GROQ_MODEL = os.environ.get("GROQ_MODEL", "llama-3.3-70b-versatile")
    GROQ_TIMEOUT = int(os.environ.get("GROQ_TIMEOUT", "45"))
