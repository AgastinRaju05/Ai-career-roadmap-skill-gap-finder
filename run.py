import os
import sys

from app import create_app

debug = os.environ.get("FLASK_DEBUG", "").lower() in {"1", "true", "yes"}

if not debug and not os.environ.get("SECRET_KEY"):
    sys.exit(
        "SECRET_KEY environment variable is not set.\n"
        "Generate one with:\n"
        '  python -c "import secrets; print(secrets.token_hex(32))"\n'
        "and set it in your environment (or .env for local runs) before "
        "starting the app outside FLASK_DEBUG mode."
    )

app = create_app()

if __name__ == "__main__":
    app.run(debug=debug)
