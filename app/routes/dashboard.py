from flask import Blueprint, render_template
from flask_login import login_required, current_user

from app.models import Roadmap, Assessment, UserSkill

dashboard_bp = Blueprint("dashboard", __name__)


@dashboard_bp.route("/dashboard")
@login_required
def home():
    active_roadmap = (
        Roadmap.query.filter_by(user_id=current_user.id)
        .order_by(Roadmap.generated_at.desc())
        .first()
    )
    recent_assessments = (
        Assessment.query.filter_by(user_id=current_user.id)
        .order_by(Assessment.started_at.desc())
        .limit(5)
        .all()
    )
    completed_steps = sum(step.status == "completed" for step in active_roadmap.steps) if active_roadmap else 0
    skill_count = UserSkill.query.filter_by(user_id=current_user.id).count()
    return render_template(
        "dashboard/home.html",
        active_roadmap=active_roadmap,
        recent_assessments=recent_assessments,
        completed_steps=completed_steps,
        skill_count=skill_count,
    )
