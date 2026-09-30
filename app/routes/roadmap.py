import json
from flask import Blueprint, abort, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required
from app.extensions import db
from app.models import Career, Course, Project, Roadmap, RoadmapStep, UserSkill
from app.services import ai_service, question_bank

roadmap_bp=Blueprint("roadmap",__name__)
VALID_STATUSES={"not_started","in_progress","completed"}

@roadmap_bp.post("/careers/<int:career_id>/roadmap")
@login_required
def generate(career_id):
    career=db.get_or_404(Career,career_id)
    levels={u.skill_id:u.proficiency for u in UserSkill.query.filter_by(user_id=current_user.id).all()}
    gaps=[]
    for cs in career.career_skills:
        current=levels.get(cs.skill_id,0); target=cs.importance or 1
        if current<target:
            diff=target-current
            gaps.append({"skill":cs.skill.name,"current_level":current,"required_level":target,
                         "priority":"High" if diff>=3 else "Medium" if diff==2 else "Low"})
    try:
        ai=ai_service.generate_roadmap(career.title,gaps,[{"name":cs.skill.name,"proficiency":levels.get(cs.skill_id,0)} for cs in career.career_skills])
        if not isinstance(ai, dict) or not isinstance(ai.get("steps"), list):
            raise ValueError("AI returned an invalid roadmap.")
        steps=[]
        for item in ai["steps"]:
            if not isinstance(item, dict):
                continue
            try:
                weeks=max(1, int(item.get("estimated_weeks") or 1))
            except (TypeError, ValueError, OverflowError):
                weeks=1
            steps.append({
                "title": str(item.get("title") or "Learning step"),
                "description": str(item.get("description") or ""),
                "skill": str(item.get("skill") or ""),
                "estimated_weeks": weeks,
            })
        if not steps:
            raise ValueError("AI returned no roadmap steps.")
        title=str(ai.get("title") or f"{career.title} learning roadmap")
        summary=str(ai.get("summary") or "")
        generated=True
    except Exception:
        steps=[{"title":f"Build {g['skill']}","description":f"Move from {g['current_level']}/5 toward {g['required_level']}/5.","skill":g["skill"],"suggested_course_topic":g["skill"],"estimated_weeks":2} for g in gaps]
        if not steps: steps=[{"title":f"Build a {career.title} portfolio project","description":"Apply your skills in an end-to-end project.","skill":"","suggested_course_topic":"","estimated_weeks":3}]
        title=f"{career.title} learning roadmap"; summary="Deterministic fallback roadmap generated from your measured skill gaps."; generated=False
    roadmap=Roadmap(user_id=current_user.id,career_id=career.id,title=title,summary=summary,analysis_json=json.dumps({"gaps":gaps}),generated_by_ai=generated)
    db.session.add(roadmap); db.session.flush()
    skill_by_name={cs.skill.name.lower():cs.skill for cs in career.career_skills}
    for i,item in enumerate(steps,1):
        skill_name=str(item.get("skill","")).lower()
        skill=skill_by_name.get(skill_name) or next((v for k,v in skill_by_name.items() if k in skill_name or skill_name in k),None)
        course=None
        if skill: course=Course.query.filter_by(skill_id=skill.id).order_by(Course.id).first()
        # AI URLs are never trusted into the database; catalog URL is preferred.
        url=course.url if course and course.verified_url else ""
        db.session.add(RoadmapStep(roadmap_id=roadmap.id,order_index=i,title=str(item.get("title") or "Learning step"),description=str(item.get("description") or ""),skill_id=skill.id if skill else None,course_id=course.id if course else None,provider=course.provider if course else None,resource_url=url,estimated_weeks=int(item.get("estimated_weeks") or 1)))
    db.session.commit()
    flash("Your personalized roadmap is ready.","success")
    return redirect(url_for("roadmap.detail",roadmap_id=roadmap.id))

@roadmap_bp.get("/roadmaps/<int:roadmap_id>")
@login_required
def detail(roadmap_id):
    roadmap=db.get_or_404(Roadmap,roadmap_id)
    if roadmap.user_id!=current_user.id: abort(404)
    completed=sum(s.status=="completed" for s in roadmap.steps)
    return render_template("roadmap/detail.html",roadmap=roadmap,completed_steps=completed)

@roadmap_bp.post("/roadmaps/<int:roadmap_id>/steps/<int:step_id>")
@login_required
def update_step(roadmap_id,step_id):
    roadmap=db.get_or_404(Roadmap,roadmap_id)
    if roadmap.user_id!=current_user.id: abort(404)
    step=RoadmapStep.query.filter_by(id=step_id,roadmap_id=roadmap.id).first_or_404()
    status=request.form.get("status","")
    if status not in VALID_STATUSES: abort(400)
    step.status=status
    db.session.commit()
    flash("Roadmap progress updated.","success")
    return redirect(url_for("roadmap.detail",roadmap_id=roadmap.id))
