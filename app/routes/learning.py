from datetime import datetime, timezone

from flask import Blueprint, abort, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required
from app.extensions import db
from app.models import Course, Project, RoadmapStep, Skill, UserProgress
from app.services import ai_service

learning_bp=Blueprint("learning",__name__)
VALID_STATUSES={"not_started","in_progress","completed"}

@learning_bp.get("/learning/courses")
@login_required
def courses():
    items=Course.query.order_by(Course.title).all()
    progress={x.course_id:x.status for x in UserProgress.query.filter_by(user_id=current_user.id).filter(UserProgress.course_id.isnot(None)).all()}
    return render_template("learning/catalog.html",items=items,progress=progress,resource_type="course",heading="Courses")

@learning_bp.get("/learning/courses/<int:course_id>")
@login_required
def course_detail(course_id):
    course=db.get_or_404(Course,course_id)
    progress=UserProgress.query.filter_by(user_id=current_user.id,course_id=course.id,project_id=None).first()
    related_courses=[]
    if course.skill_id is not None:
        related_courses=Course.query.filter(
            Course.skill_id==course.skill_id,
            Course.id!=course.id,
        ).order_by(Course.title).all()
        if not related_courses and course.skill and course.skill.category:
            related_courses=Course.query.join(Skill).filter(
                Skill.category==course.skill.category,
                Course.id!=course.id,
            ).order_by(Course.title).all()
    if not related_courses:
        related_courses=Course.query.filter(
            Course.id!=course.id,
        ).order_by(Course.title).limit(3).all()
    return render_template(
        "learning/course_detail.html",
        course=course,
        progress=progress,
        related_courses=related_courses,
    )

@learning_bp.get("/learning/projects")
@login_required
def projects():
    items=Project.query.order_by(Project.title).all()
    progress={x.project_id:x.status for x in UserProgress.query.filter_by(user_id=current_user.id).filter(UserProgress.project_id.isnot(None)).all()}
    return render_template("learning/catalog.html",items=items,progress=progress,resource_type="project",heading="Projects")

@learning_bp.get("/projects/<int:project_id>")
@login_required
def project_detail(project_id):
    project=db.get_or_404(Project,project_id)
    return render_template("learning/project_detail.html",project=project)

@learning_bp.post("/learning/progress/<resource_type>/<int:resource_id>")
@login_required
def update_progress(resource_type,resource_id):
    if resource_type=="course":
        resource=db.get_or_404(Course,resource_id); lookup={"course_id":resource.id,"project_id":None}
    elif resource_type=="project":
        resource=db.get_or_404(Project,resource_id); lookup={"project_id":resource.id,"course_id":None}
    else: abort(404)
    status=request.form.get("status","")
    if status not in VALID_STATUSES: abort(400)
    progress=UserProgress.query.filter_by(user_id=current_user.id,**lookup).first()
    if progress is None: progress=UserProgress(user_id=current_user.id,**lookup); db.session.add(progress)
    progress.status=status
    progress.progress_percent=100 if status=="completed" else (50 if status=="in_progress" else 0)
    progress.completed_at=datetime.now(timezone.utc).replace(tzinfo=None) if status == "completed" else None

    # Keep a linked roadmap step in sync with course/project completion.
    linked_steps=RoadmapStep.query.filter_by(**lookup).all() if resource_type=="course" else []
    for step in linked_steps:
        step.status=status
        step.completed_at=progress.completed_at

    db.session.commit()
    # A completed roadmap step/course exposes reassessment from the UI.
    flash("Learning progress saved.","success")
    return redirect(url_for(f"learning.{resource_type}s"))
