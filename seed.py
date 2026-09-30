"""
Run once to populate sample skills and careers so Career Discovery isn't empty.
Usage: python seed.py
"""
from urllib.parse import urlencode

from app import create_app
from app.extensions import db
from app.models import Skill, Career, CareerSkill, Course, Project

app = create_app()

SKILLS = [
    "Python", "JavaScript", "SQL", "HTML/CSS", "Data Structures & Algorithms",
    "Machine Learning", "Statistics", "Data Visualization", "Cloud Computing (AWS/GCP)",
    "Git & Version Control", "REST APIs", "System Design", "UI/UX Design",
    "Communication", "Project Management",
]

SKILL_CATEGORIES = {
    "Python": "Programming", "JavaScript": "Programming", "SQL": "Data",
    "HTML/CSS": "Web development", "Data Structures & Algorithms": "Computer science",
    "Machine Learning": "Data", "Statistics": "Data", "Data Visualization": "Data",
    "Cloud Computing (AWS/GCP)": "Cloud", "Git & Version Control": "Tools",
    "REST APIs": "Web development", "System Design": "Engineering",
    "UI/UX Design": "Design", "Communication": "Professional skills",
    "Project Management": "Professional skills",
}

CAREERS = [
    {
        "title": "Data Scientist",
        "description": "Analyzes large datasets to extract insights and build predictive models for business decisions.",
        "growth_outlook": "High demand, 20%+ projected growth",
        "skills": [("Python", 5), ("Statistics", 5), ("Machine Learning", 5), ("SQL", 4), ("Data Visualization", 4)],
    },
    {
        "title": "Full-Stack Web Developer",
        "description": "Builds both the frontend and backend of web applications end-to-end.",
        "growth_outlook": "Steady demand across industries",
        "skills": [("JavaScript", 5), ("HTML/CSS", 5), ("REST APIs", 4), ("SQL", 3), ("Git & Version Control", 4)],
    },
    {
        "title": "Cloud/DevOps Engineer",
        "description": "Manages cloud infrastructure, deployment pipelines, and system reliability.",
        "growth_outlook": "Very high demand",
        "skills": [("Cloud Computing (AWS/GCP)", 5), ("System Design", 4), ("Git & Version Control", 4), ("Python", 3)],
    },
    {
        "title": "UI/UX Designer",
        "description": "Designs intuitive, user-centered interfaces and experiences for digital products.",
        "growth_outlook": "Growing demand as products scale",
        "skills": [("UI/UX Design", 5), ("Communication", 4), ("HTML/CSS", 3)],
    },
    {
        "title": "Machine Learning Engineer",
        "description": "Builds, deploys, and maintains ML models in production systems.",
        "growth_outlook": "Very high demand, fast-growing field",
        "skills": [("Machine Learning", 5), ("Python", 5), ("System Design", 4), ("Statistics", 4), ("Cloud Computing (AWS/GCP)", 3)],
    },
]

with app.app_context():
    skill_map = {}
    for name in SKILLS:
        skill = Skill.query.filter_by(name=name).first()
        if not skill:
            skill = Skill(name=name, category=SKILL_CATEGORIES.get(name))
            db.session.add(skill)
            db.session.flush()
        else:
            skill.category = SKILL_CATEGORIES.get(name)
        skill_map[name] = skill

    for c in CAREERS:
        career = Career.query.filter_by(title=c["title"]).first()
        if not career:
            career = Career(
                title=c["title"],
                description=c["description"],
                growth_outlook=c["growth_outlook"],
            )
            db.session.add(career)
            db.session.flush()
        else:
            career.description = c["description"]
            career.growth_outlook = c["growth_outlook"]

        for skill_name, importance in c["skills"]:
            career_skill = CareerSkill.query.filter_by(
                career_id=career.id, skill_id=skill_map[skill_name].id
            ).first()
            if career_skill:
                career_skill.importance = importance
            else:
                db.session.add(CareerSkill(
                    career_id=career.id,
                    skill_id=skill_map[skill_name].id,
                    importance=importance,
                ))

    for skill in skill_map.values():
        course_title = f"{skill.name}: guided foundations"
        course = Course.query.filter_by(title=course_title).first()
        if not course:
            course = Course(title=course_title)
            db.session.add(course)
        course.provider = "Coursera course search"
        course.url = f"https://www.coursera.org/search?{urlencode({'query': skill.name})}"
        course.skill_id = skill.id
        course.level = "Beginner"
        course.description = (
            f"Learn the core concepts of {skill.name}, then practice them with a small, reviewable exercise."
        )
        project_title = f"Build a portfolio piece with {skill.name}"
        if not Project.query.filter_by(title=project_title).first():
            db.session.add(Project(
                title=project_title,
                description=f"Create a focused project that demonstrates practical use of {skill.name}. Write a short README describing your choices and what you learned.",
                skill_id=skill.id,
                difficulty="Beginner",
            ))

    db.session.commit()
    print(f"Seeded or updated {len(SKILLS)} skills, {len(CAREERS)} careers, and learning resources.")
