import os

from flask import Flask

from config import Config
from app.extensions import db, login_manager, csrf


def create_app(test_config=None):
    app = Flask(__name__)
    app.config.from_object(Config)
    if test_config:
        app.config.update(test_config)

    database_uri = app.config.get("SQLALCHEMY_DATABASE_URI", "")
    if database_uri.startswith("sqlite://") and database_uri not in {"sqlite://", "sqlite:///:memory:"}:
        if database_uri.startswith("sqlite:///"):
            db_path = database_uri.replace("sqlite:///", "", 1)
        elif database_uri.startswith("sqlite:////"):
            db_path = database_uri.replace("sqlite:////", "", 1)
        else:
            db_path = ""

        if db_path and not db_path.startswith(":memory:"):
            db_dir = os.path.dirname(db_path)
            if db_dir:
                os.makedirs(db_dir, exist_ok=True)

    db.init_app(app)
    login_manager.init_app(app)
    csrf.init_app(app)

    from app.models import User

    @login_manager.user_loader
    def load_user(user_id):
        try:
            return db.session.get(User, int(user_id))
        except (TypeError, ValueError):
            return None

    @app.template_filter("fromjson")
    def fromjson_filter(value):
        import json
        try:
            return json.loads(value or "[]")
        except (TypeError, ValueError):
            return []

    # Register blueprints
    from app.routes.auth import auth_bp
    from app.routes.dashboard import dashboard_bp
    from app.routes.career import career_bp
    from app.routes.profile import profile_bp
    from app.routes.roadmap import roadmap_bp
    from app.routes.assessment import assessment_bp
    from app.routes.learning import learning_bp

    app.register_blueprint(auth_bp)
    app.register_blueprint(dashboard_bp)
    app.register_blueprint(career_bp)
    app.register_blueprint(profile_bp)
    app.register_blueprint(roadmap_bp)
    app.register_blueprint(assessment_bp)
    app.register_blueprint(learning_bp)

    with app.app_context():
        os.makedirs(app.instance_path, exist_ok=True)
        db.create_all()
        _upgrade_sqlite_schema()

    return app


def _upgrade_sqlite_schema():
    """Lightweight additive migration for the bundled SQLite starter DB.
    Existing student data is preserved; missing columns are added safely.
    """
    from sqlalchemy import inspect, text
    if not str(db.engine.url).startswith("sqlite"):
        return
    additions = {
        "user_skills": {
            "source": "VARCHAR(30) DEFAULT 'self_reported'",
            "assessed_at": "DATETIME",
            "updated_at": "DATETIME",
        },
        "assessments": {
            "parent_assessment_id": "INTEGER",
            "assessment_type": "VARCHAR(30) DEFAULT 'initial'",
            "difficulty": "VARCHAR(30) DEFAULT 'Beginner'",
            "overall_skill_level": "VARCHAR(30)",
            "analysis_json": "TEXT",
        },
        "assessment_questions": {
            "explanation": "TEXT",
            "question_type": "VARCHAR(40) DEFAULT 'mcq'",
            "difficulty": "VARCHAR(30) DEFAULT 'Beginner'",
            "ai_generated": "BOOLEAN DEFAULT 0",
            "generation_metadata_json": "TEXT",
        },
        "roadmaps": {
            "title": "VARCHAR(200)",
            "summary": "TEXT",
            "analysis_json": "TEXT",
            "generated_by_ai": "BOOLEAN DEFAULT 0",
        },
        "roadmap_steps": {
            "project_id": "INTEGER",
            "provider": "VARCHAR(120)",
            "resource_url": "VARCHAR(500)",
            "estimated_weeks": "INTEGER",
            "completed_at": "DATETIME",
        },
        "courses": {
            "verified_url": "BOOLEAN DEFAULT 0",
            "source_type": "VARCHAR(40) DEFAULT 'catalog'",
        },
        "projects": {
            "career_id": "INTEGER",
            "generated_by_ai": "BOOLEAN DEFAULT 0",
            "requirements_json": "TEXT",
            "expected_outcomes": "TEXT",
        },
        "user_progress": {
            "progress_percent": "INTEGER DEFAULT 0",
            "started_at": "DATETIME",
            "completed_at": "DATETIME",
        },
    }
    inspector=inspect(db.engine)
    with db.engine.begin() as conn:
        for table, columns in additions.items():
            if table not in inspector.get_table_names():
                continue
            existing={c["name"] for c in inspector.get_columns(table)}
            for name, definition in columns.items():
                if name not in existing:
                    conn.execute(text(f'ALTER TABLE "{table}" ADD COLUMN "{name}" {definition}'))
