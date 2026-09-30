from flask import Blueprint, render_template
from flask_login import current_user, login_required

from app.extensions import db
from app.models import Career, UserSkill

career_bp = Blueprint("career", __name__)


@career_bp.route("/careers")
@login_required
def discovery():
    user_levels = {
        item.skill_id: item.proficiency
        for item in UserSkill.query.filter_by(user_id=current_user.id).all()
    }
    ranked_careers = []
    for career in Career.query.order_by(Career.title).all():
        requirements = career.career_skills
        possible = sum(max(1, item.importance or 1) for item in requirements)
        achieved = sum(
            max(1, item.importance or 1) * min(user_levels.get(item.skill_id, 0), 5) / 5
            for item in requirements
        )
        match_percent = round(achieved / possible * 100) if possible else 0
        ranked_careers.append((career, match_percent))
    ranked_careers.sort(key=lambda entry: (-entry[1], entry[0].title))
    return render_template("career/discovery.html", ranked_careers=ranked_careers)


@career_bp.route("/careers/<int:career_id>")
@login_required
def detail(career_id):
    career = db.get_or_404(Career, career_id)
    user_levels = {
        item.skill_id: item.proficiency
        for item in UserSkill.query.filter_by(user_id=current_user.id).all()
    }
    return render_template("career/detail.html", career=career, user_levels=user_levels)
