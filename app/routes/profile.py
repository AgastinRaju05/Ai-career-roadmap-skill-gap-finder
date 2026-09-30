from flask import Blueprint, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required

from app.extensions import db
from app.models import Profile, Skill, UserSkill

profile_bp = Blueprint("profile", __name__)


@profile_bp.route("/profile", methods=["GET", "POST"])
@login_required
def edit():
    profile = Profile.query.filter_by(user_id=current_user.id).first()
    skills = Skill.query.order_by(Skill.category, Skill.name).all()
    user_skills = {
        item.skill_id: item.proficiency
        for item in UserSkill.query.filter_by(user_id=current_user.id).all()
    }

    if request.method == "POST":
        try:
            experience = float(request.form.get("experience_years", "0") or 0)
        except ValueError:
            experience = -1
        if experience < 0 or experience > 80:
            flash("Experience must be between 0 and 80 years.", "error")
            return render_template("profile/edit.html", profile=profile, skills=skills, user_skills=user_skills)

        if profile is None:
            profile = Profile(user_id=current_user.id)
            db.session.add(profile)
        profile.education = request.form.get("education", "").strip()[:200]
        profile.experience_years = experience
        profile.bio = request.form.get("bio", "").strip()[:2000]
        profile.goal_career = request.form.get("goal_career", "").strip()[:150]

        known_skill_ids = {skill.id for skill in skills}
        for skill_id in known_skill_ids:
            raw_level = request.form.get(f"skill_{skill_id}", "").strip()
            existing = UserSkill.query.filter_by(user_id=current_user.id, skill_id=skill_id).first()
            if not raw_level:
                if existing:
                    db.session.delete(existing)
                continue
            try:
                level = int(raw_level)
            except ValueError:
                level = 0
            if level not in range(1, 6):
                flash("Choose a proficiency from 1 to 5 for each selected skill.", "error")
                db.session.rollback()
                return render_template("profile/edit.html", profile=profile, skills=skills, user_skills=user_skills)
            if existing:
                existing.proficiency = level
            else:
                db.session.add(UserSkill(user_id=current_user.id, skill_id=skill_id, proficiency=level))

        db.session.commit()
        flash("Your profile and skills have been saved.", "success")
        return redirect(url_for("profile.edit"))

    return render_template("profile/edit.html", profile=profile, skills=skills, user_skills=user_skills)