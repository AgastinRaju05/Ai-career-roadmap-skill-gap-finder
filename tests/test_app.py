import unittest
from unittest.mock import patch

from app import create_app
from app.extensions import db
from app.models import Assessment, AssessmentQuestion, Career, CareerSkill, Course, Project, Roadmap, Skill, User
from app.services.adaptive import next_difficulty, proficiency_from_score


class CareerRoadmapAppTests(unittest.TestCase):
    def setUp(self):
        self.app = create_app({
            "TESTING": True,
            "SECRET_KEY": "test-secret",
            "SQLALCHEMY_DATABASE_URI": "sqlite://",
            "WTF_CSRF_ENABLED": False,
        })
        self.client = self.app.test_client()
        with self.app.app_context():
            self.skill = Skill(name="Python", category="Programming")
            self.career = Career(title="Data Scientist", description="Analyze data")
            db.session.add_all([self.skill, self.career])
            db.session.flush()
            db.session.add(CareerSkill(career_id=self.career.id, skill_id=self.skill.id, importance=4))
            db.session.add_all([
                Course(title="Python basics", skill_id=self.skill.id),
                Course(title="Advanced Python", skill_id=self.skill.id),
            ])
            db.session.add(Project(title="Python portfolio", skill_id=self.skill.id))
            self.user = User(name="Test User", email="test@example.com")
            self.user.set_password("password123")
            db.session.add(self.user)
            db.session.commit()
            self.skill_id = self.skill.id
            self.course_id = Course.query.filter_by(title="Python basics").one().id
            self.career_id = self.career.id
            self.user_id = self.user.id

    def tearDown(self):
        with self.app.app_context():
            db.session.remove()
            db.drop_all()
            db.engine.dispose()

    def login(self):
        return self.client.post("/login", data={
            "email": "test@example.com",
            "password": "password123",
        }, follow_redirects=True)

    def test_profile_updates_skill_ratings_and_career_discovery(self):
        self.login()
        response = self.client.post("/profile", data={
            "education": "Computer Science",
            "experience_years": "2",
            "goal_career": "Data Scientist",
            f"skill_{self.skill_id}": "4",
        }, follow_redirects=True)
        self.assertEqual(response.status_code, 200)
        discovery = self.client.get("/careers")
        self.assertEqual(discovery.status_code, 200)
        self.assertIn(b"80% skill match", discovery.data)

    def test_mcq_options_render_as_separate_letter_and_answer(self):
        self.login()
        with self.app.app_context():
            assessment = Assessment(user_id=self.user_id, career_id=self.career_id)
            db.session.add(assessment)
            db.session.flush()
            question = AssessmentQuestion(
                assessment_id=assessment.id,
                question_text="What does len([1, 2, 3]) return?",
                options_json='{"A": "2", "B": "3", "C": "Error", "D": "None"}',
                correct_option="B",
                skill_id=self.skill_id,
                order_index=1,
            )
            db.session.add(question)
            db.session.commit()
            assessment_id = assessment.id

        response = self.client.get(
            f"/careers/{self.career_id}/assessment/mcq?assessment_id={assessment_id}"
        )
        self.assertEqual(response.status_code, 200)
        self.assertIn(b'class="quiz-option-letter">A</span>', response.data)
        self.assertIn(b'class="quiz-option-text">2</span>', response.data)

    def test_assessment_generates_roadmap_and_step_progress(self):
        self.login()
        assessment = self.client.post(f"/careers/{self.career_id}/assessment", data={
            f"skill_{self.skill_id}": "3",
        }, follow_redirects=True)
        self.assertEqual(assessment.status_code, 200)
        self.assertIn(b"Skill check complete", assessment.data)

        roadmap_response = self.client.post(f"/careers/{self.career_id}/roadmap", follow_redirects=True)
        self.assertEqual(roadmap_response.status_code, 200)
        self.assertIn(f'/learning/courses/{self.course_id}'.encode(), roadmap_response.data)
        with self.app.app_context():
            roadmap = Roadmap.query.filter_by(user_id=self.user_id).one()
            step_id = roadmap.steps[0].id
            roadmap_id = roadmap.id
        update = self.client.post(f"/roadmaps/{roadmap_id}/steps/{step_id}", data={"status": "completed"}, follow_redirects=True)
        self.assertEqual(update.status_code, 200)
        self.assertIn(b"1 of 1 steps complete", update.data)

    def test_roadmap_handles_empty_steps_and_invalid_duration_from_ai(self):
        self.login()
        responses = [
            {"steps": []},
            {"steps": [{"title": "Study Python", "estimated_weeks": "unknown"}]},
        ]
        with patch("app.routes.roadmap.ai_service.generate_roadmap", side_effect=responses):
            fallback_response = self.client.post(
                f"/careers/{self.career_id}/roadmap", follow_redirects=True
            )
            normalized_response = self.client.post(
                f"/careers/{self.career_id}/roadmap", follow_redirects=True
            )

        self.assertEqual(fallback_response.status_code, 200)
        self.assertEqual(normalized_response.status_code, 200)
        with self.app.app_context():
            roadmaps = Roadmap.query.filter_by(user_id=self.user_id).order_by(Roadmap.id).all()
            self.assertEqual(len(roadmaps), 2)
            self.assertFalse(roadmaps[0].generated_by_ai)
            self.assertEqual(len(roadmaps[0].steps), 1)
            self.assertTrue(roadmaps[1].generated_by_ai)
            self.assertEqual(roadmaps[1].steps[0].estimated_weeks, 1)

    def test_learning_progress_and_foreign_roadmap_are_protected(self):
        self.login()
        catalog = self.client.get("/learning/courses")
        self.assertEqual(catalog.status_code, 200)
        with self.app.app_context():
            course_id = Course.query.first().id
        self.assertIn(f'/learning/courses/{course_id}'.encode(), catalog.data)
        course_detail = self.client.get(f"/learning/courses/{course_id}")
        self.assertEqual(course_detail.status_code, 200)
        self.assertIn(b"Python basics", course_detail.data)
        self.assertIn(b"Related courses for Python", course_detail.data)
        self.assertIn(b"Advanced Python", course_detail.data)
        update = self.client.post(f"/learning/progress/course/{course_id}", data={"status": "completed"}, follow_redirects=True)
        self.assertEqual(update.status_code, 200)

        other = User(name="Other User", email="other@example.com")
        other.set_password("password123")
        with self.app.app_context():
            db.session.add(other)
            db.session.commit()
        self.client.post("/logout")
        self.client.post("/login", data={"email": "other@example.com", "password": "password123"})
        with self.app.app_context():
            roadmap = Roadmap(user_id=self.user_id, career_id=self.career_id)
            db.session.add(roadmap)
            db.session.commit()
            roadmap_id = roadmap.id
        self.assertEqual(self.client.get(f"/roadmaps/{roadmap_id}").status_code, 404)

    def test_course_detail_shows_category_related_links_without_skill_siblings(self):
        self.login()
        with self.app.app_context():
            java_skill = Skill(name="Java", category="Programming")
            db.session.add(java_skill)
            db.session.flush()
            java_course = Course(title="Java foundations", skill_id=java_skill.id)
            db.session.add(java_course)
            db.session.commit()
            java_course_id = java_course.id

        response = self.client.get(f"/learning/courses/{java_course_id}")
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"Related courses for Java", response.data)
        self.assertIn(b"Python basics", response.data)
        self.assertIn(f'href="/learning/courses/{self.course_id}"'.encode(), response.data)
        self.assertIn(
            b'href="https://www.coursera.org/search?query=Python"', response.data
        )
        self.assertIn(b"Find Python courses", response.data)

    def test_adaptive_rules(self):
        self.assertEqual(next_difficulty("Beginner", 80), "Intermediate")
        self.assertEqual(next_difficulty("Intermediate", 80), "Advanced")
        self.assertEqual(next_difficulty("Advanced", 40), "Intermediate")
        self.assertEqual(next_difficulty("Beginner", 40), "Beginner")
        self.assertEqual(next_difficulty("Intermediate", 60), "Intermediate")

    def test_proficiency_mapping(self):
        self.assertEqual(proficiency_from_score(10), 1)
        self.assertEqual(proficiency_from_score(45), 3)
        self.assertEqual(proficiency_from_score(85), 5)


if __name__ == "__main__":
    unittest.main()