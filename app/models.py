from datetime import datetime, timezone

from flask_login import UserMixin
from sqlalchemy import UniqueConstraint
from werkzeug.security import generate_password_hash, check_password_hash

from app.extensions import db


def _utcnow():
    return datetime.now(timezone.utc).replace(tzinfo=None)


class User(UserMixin, db.Model):
    __tablename__ = "users"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), nullable=False)
    email = db.Column(db.String(150), unique=True, nullable=False, index=True)
    password_hash = db.Column(db.String(255), nullable=False)
    created_at = db.Column(db.DateTime, default=_utcnow, nullable=False)

    profile = db.relationship("Profile", backref="user", uselist=False, cascade="all, delete-orphan")
    user_skills = db.relationship("UserSkill", backref="user", cascade="all, delete-orphan")
    assessments = db.relationship("Assessment", backref="user", cascade="all, delete-orphan")
    roadmaps = db.relationship("Roadmap", backref="user", cascade="all, delete-orphan")
    progress = db.relationship("UserProgress", backref="user", cascade="all, delete-orphan")
    career_selections = db.relationship("UserCareer", backref="user", cascade="all, delete-orphan")

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)


class Profile(db.Model):
    __tablename__ = "profiles"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, unique=True)
    education = db.Column(db.String(200))
    experience_years = db.Column(db.Float, default=0)
    bio = db.Column(db.Text)
    goal_career = db.Column(db.String(150))
    updated_at = db.Column(db.DateTime, default=_utcnow, onupdate=_utcnow, nullable=False)


class Skill(db.Model):
    __tablename__ = "skills"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), unique=True, nullable=False, index=True)
    category = db.Column(db.String(80), index=True)

    career_requirements = db.relationship("CareerSkill", back_populates="skill", cascade="all, delete-orphan")
    user_skills = db.relationship("UserSkill", back_populates="skill", cascade="all, delete-orphan")
    courses = db.relationship("Course", back_populates="skill")
    projects = db.relationship("Project", back_populates="skill")


class UserSkill(db.Model):
    __tablename__ = "user_skills"
    __table_args__ = (UniqueConstraint("user_id", "skill_id", name="uq_user_skill"),)

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, index=True)
    skill_id = db.Column(db.Integer, db.ForeignKey("skills.id"), nullable=False, index=True)
    proficiency = db.Column(db.Integer, default=1, nullable=False)  # estimated 1-5 scale
    source = db.Column(db.String(30), default="self_reported", nullable=False)  # self_reported, assessment, reassessment, imported
    assessed_at = db.Column(db.DateTime)
    updated_at = db.Column(db.DateTime, default=_utcnow, onupdate=_utcnow, nullable=False)

    skill = db.relationship("Skill", back_populates="user_skills")


class Career(db.Model):
    __tablename__ = "careers"

    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(150), nullable=False, unique=True)
    description = db.Column(db.Text)
    avg_salary = db.Column(db.String(80))
    growth_outlook = db.Column(db.String(120))

    career_skills = db.relationship("CareerSkill", back_populates="career", cascade="all, delete-orphan")
    selected_by_users = db.relationship("UserCareer", back_populates="career", cascade="all, delete-orphan")
    assessments = db.relationship("Assessment", back_populates="career")
    roadmaps = db.relationship("Roadmap", back_populates="career")
    projects = db.relationship("Project", back_populates="career")


class UserCareer(db.Model):
    """Careers currently selected by a student; supports multiple target careers."""
    __tablename__ = "user_careers"
    __table_args__ = (UniqueConstraint("user_id", "career_id", name="uq_user_career"),)

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, index=True)
    career_id = db.Column(db.Integer, db.ForeignKey("careers.id"), nullable=False, index=True)
    is_primary = db.Column(db.Boolean, default=False, nullable=False)
    selected_at = db.Column(db.DateTime, default=_utcnow, nullable=False)

    career = db.relationship("Career", back_populates="selected_by_users")


class CareerSkill(db.Model):
    __tablename__ = "career_skills"
    __table_args__ = (UniqueConstraint("career_id", "skill_id", name="uq_career_skill"),)

    id = db.Column(db.Integer, primary_key=True)
    career_id = db.Column(db.Integer, db.ForeignKey("careers.id"), nullable=False, index=True)
    skill_id = db.Column(db.Integer, db.ForeignKey("skills.id"), nullable=False, index=True)
    importance = db.Column(db.Integer, default=3, nullable=False)  # 1-5 target level/importance

    career = db.relationship("Career", back_populates="career_skills")
    skill = db.relationship("Skill", back_populates="career_requirements")


class Assessment(db.Model):
    __tablename__ = "assessments"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, index=True)
    # Kept for backward compatibility with the existing single-career routes.
    career_id = db.Column(db.Integer, db.ForeignKey("careers.id"), nullable=True, index=True)
    parent_assessment_id = db.Column(db.Integer, db.ForeignKey("assessments.id"), nullable=True)
    assessment_type = db.Column(db.String(30), default="initial", nullable=False)  # initial, reassessment
    status = db.Column(db.String(30), default="in_progress", nullable=False)
    difficulty = db.Column(db.String(30), default="Beginner", nullable=False)
    score = db.Column(db.Float)
    overall_skill_level = db.Column(db.String(30))
    analysis_json = db.Column(db.Text)
    started_at = db.Column(db.DateTime, default=_utcnow, nullable=False)
    completed_at = db.Column(db.DateTime)

    questions = db.relationship("AssessmentQuestion", back_populates="assessment", cascade="all, delete-orphan", order_by="AssessmentQuestion.order_index")
    career = db.relationship("Career", back_populates="assessments")
    selected_careers = db.relationship("AssessmentCareer", back_populates="assessment", cascade="all, delete-orphan")
    parent_assessment = db.relationship("Assessment", remote_side=[id], backref="reassessments")


class AssessmentCareer(db.Model):
    """Careers covered by an assessment, allowing one assessment to span multiple careers."""
    __tablename__ = "assessment_careers"
    __table_args__ = (UniqueConstraint("assessment_id", "career_id", name="uq_assessment_career"),)

    id = db.Column(db.Integer, primary_key=True)
    assessment_id = db.Column(db.Integer, db.ForeignKey("assessments.id"), nullable=False, index=True)
    career_id = db.Column(db.Integer, db.ForeignKey("careers.id"), nullable=False, index=True)

    assessment = db.relationship("Assessment", back_populates="selected_careers")
    career = db.relationship("Career")


class AssessmentQuestion(db.Model):
    __tablename__ = "assessment_questions"

    id = db.Column(db.Integer, primary_key=True)
    assessment_id = db.Column(db.Integer, db.ForeignKey("assessments.id"), nullable=False, index=True)
    question_text = db.Column(db.Text, nullable=False)
    options_json = db.Column(db.Text)
    correct_option = db.Column(db.String(10))
    user_answer = db.Column(db.String(10))
    explanation = db.Column(db.Text)
    question_type = db.Column(db.String(40), default="mcq", nullable=False)
    difficulty = db.Column(db.String(30), default="Beginner", nullable=False)
    ai_generated = db.Column(db.Boolean, default=False, nullable=False)
    generation_metadata_json = db.Column(db.Text)
    skill_id = db.Column(db.Integer, db.ForeignKey("skills.id"), index=True)
    order_index = db.Column(db.Integer, default=0, nullable=False)

    assessment = db.relationship("Assessment", back_populates="questions")
    skill = db.relationship("Skill")


class Roadmap(db.Model):
    __tablename__ = "roadmaps"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, index=True)
    career_id = db.Column(db.Integer, db.ForeignKey("careers.id"), nullable=False, index=True)
    title = db.Column(db.String(200))
    summary = db.Column(db.Text)
    analysis_json = db.Column(db.Text)
    generated_by_ai = db.Column(db.Boolean, default=False, nullable=False)
    generated_at = db.Column(db.DateTime, default=_utcnow, nullable=False)

    steps = db.relationship("RoadmapStep", back_populates="roadmap", cascade="all, delete-orphan", order_by="RoadmapStep.order_index")
    career = db.relationship("Career", back_populates="roadmaps")


class RoadmapStep(db.Model):
    __tablename__ = "roadmap_steps"

    id = db.Column(db.Integer, primary_key=True)
    roadmap_id = db.Column(db.Integer, db.ForeignKey("roadmaps.id"), nullable=False, index=True)
    order_index = db.Column(db.Integer, default=0, nullable=False)
    title = db.Column(db.String(200), nullable=False)
    description = db.Column(db.Text)
    skill_id = db.Column(db.Integer, db.ForeignKey("skills.id"), index=True)
    course_id = db.Column(db.Integer, db.ForeignKey("courses.id"), index=True)
    project_id = db.Column(db.Integer, db.ForeignKey("projects.id"), index=True)
    provider = db.Column(db.String(120))
    resource_url = db.Column(db.String(500))
    estimated_weeks = db.Column(db.Integer)
    status = db.Column(db.String(30), default="not_started", nullable=False)
    completed_at = db.Column(db.DateTime)

    roadmap = db.relationship("Roadmap", back_populates="steps")
    skill = db.relationship("Skill")
    course = db.relationship("Course")
    project = db.relationship("Project")


class Course(db.Model):
    __tablename__ = "courses"

    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(200), nullable=False)
    provider = db.Column(db.String(120))
    url = db.Column(db.String(500))
    skill_id = db.Column(db.Integer, db.ForeignKey("skills.id"), index=True)
    level = db.Column(db.String(30))
    description = db.Column(db.Text)
    verified_url = db.Column(db.Boolean, default=False, nullable=False)
    source_type = db.Column(db.String(40), default="catalog", nullable=False)

    skill = db.relationship("Skill", back_populates="courses")


class Project(db.Model):
    __tablename__ = "projects"

    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(200), nullable=False)
    description = db.Column(db.Text)
    skill_id = db.Column(db.Integer, db.ForeignKey("skills.id"), index=True)
    career_id = db.Column(db.Integer, db.ForeignKey("careers.id"), index=True)
    difficulty = db.Column(db.String(30))
    generated_by_ai = db.Column(db.Boolean, default=False, nullable=False)
    requirements_json = db.Column(db.Text)
    expected_outcomes = db.Column(db.Text)

    skill = db.relationship("Skill", back_populates="projects")
    career = db.relationship("Career", back_populates="projects")


class UserProgress(db.Model):
    __tablename__ = "user_progress"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, index=True)
    roadmap_step_id = db.Column(db.Integer, db.ForeignKey("roadmap_steps.id"), index=True)
    course_id = db.Column(db.Integer, db.ForeignKey("courses.id"), index=True)
    project_id = db.Column(db.Integer, db.ForeignKey("projects.id"), index=True)
    status = db.Column(db.String(30), default="not_started", nullable=False)
    progress_percent = db.Column(db.Integer, default=0, nullable=False)
    started_at = db.Column(db.DateTime)
    completed_at = db.Column(db.DateTime)
    updated_at = db.Column(db.DateTime, default=_utcnow, onupdate=_utcnow, nullable=False)

    roadmap_step = db.relationship("RoadmapStep")
    course = db.relationship("Course")
    project = db.relationship("Project")
