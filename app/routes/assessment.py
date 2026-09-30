import json
from datetime import datetime, timezone

from flask import (
    Blueprint,
    abort,
    flash,
    redirect,
    render_template,
    request,
    url_for,
)
from flask_login import current_user, login_required

from app.extensions import db
from app.models import (
    Assessment,
    AssessmentCareer,
    AssessmentQuestion,
    Career,
    Course,
    Project,
    Skill,
    UserSkill,
)
from app.services import ai_service, question_bank
from app.services.adaptive import proficiency_from_score


assessment_bp = Blueprint("assessment", __name__)


# ============================================================
# BASIC HELPERS
# ============================================================

def _now():
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _career_skills(career_ids):
    """
    Get careers and merge their required skills.

    If multiple careers share the same skill, that skill is
    assessed only once.
    """
    careers = [
        db.session.get(Career, cid)
        for cid in career_ids
    ]

    careers = [c for c in careers if c]

    merged = {}

    for career in careers:
        for career_skill in career.career_skills:
            merged.setdefault(
                career_skill.skill_id,
                career_skill
            )

    return careers, list(merged.values())


def _question_key(text):
    """
    Normalize question text so duplicate questions can be detected.
    """
    import re

    text = str(text or "").lower()
    text = re.sub(r"[^a-z0-9]+", " ", text)

    return re.sub(r"\s+", " ", text).strip()


def _current_skill_levels(user, requirements):
    """
    Return current UserSkill proficiency for every required skill.

    Example:
        {
            "Python": 4,
            "SQL": 3,
            "Git": 2
        }

    If a skill has never been assessed, it defaults to 1.
    """
    stored_levels = {
        user_skill.skill_id: user_skill.proficiency
        for user_skill in UserSkill.query.filter_by(
            user_id=user.id
        ).all()
    }

    result = {}

    for requirement in requirements:
        result[requirement.skill.name] = stored_levels.get(
            requirement.skill_id,
            1
        )

    return result


def _determine_assessment_difficulty(user, requirements):
    """
    Determine ONE difficulty level for the assessment.

    IMPORTANT:
    This difficulty is selected before the assessment starts.

    It NEVER changes while the assessment is being taken.

    Current proficiency scale:
        1-2 -> Beginner
        3-4 -> Intermediate
        5   -> Advanced

    For multiple skills, the average current proficiency is used.
    """

    levels = _current_skill_levels(user, requirements)

    if not levels:
        return "Beginner"

    values = []

    for value in levels.values():
        try:
            value = float(value)
        except (TypeError, ValueError):
            value = 1

        values.append(value)

    average_level = sum(values) / len(values)

    if average_level >= 4.5:
        return "Advanced"

    if average_level >= 2.5:
        return "Intermediate"

    return "Beginner"


# ============================================================
# QUESTION GENERATION
# ============================================================

def _build_questions(
    user,
    careers,
    requirements,
    difficulty,
    count,
    assessment,
    reassessment=False,
):
    """
    Generate ONE fixed-difficulty assessment.

    There are NO adaptive rounds here.

    The difficulty passed into this function remains fixed for
    every question in this assessment.
    """

    skill_names = [
        requirement.skill.name
        for requirement in requirements
    ]

    level_by_name = _current_skill_levels(
        user,
        requirements
    )

    # --------------------------------------------------------
    # Get ALL previous questions belonging to this user.
    # This prevents repeated questions across assessments and
    # reassessments.
    # --------------------------------------------------------

    history_rows = (
        AssessmentQuestion.query
        .join(
            Assessment,
            AssessmentQuestion.assessment_id == Assessment.id
        )
        .filter(
            Assessment.user_id == user.id
        )
        .all()
    )

    previous_questions = []
    previous_keys = set()

    for row in history_rows:
        text = str(row.question_text or "").strip()
        key = _question_key(text)

        if key and key not in previous_keys:
            previous_keys.add(key)
            previous_questions.append(text)

    # Also protect against duplicate questions already created
    # in the current assessment.
    for row in assessment.questions:
        text = str(row.question_text or "").strip()
        key = _question_key(text)

        if key and key not in previous_keys:
            previous_keys.add(key)
            previous_questions.append(text)

    # --------------------------------------------------------
    # AI GENERATION
    # --------------------------------------------------------

    ai_generated = False
    clean = []

    try:
        payload = ai_service.generate_assessment_questions(
            skill_names,
            num_questions=count,
            difficulty=difficulty,
            current_levels=level_by_name,
            previous_performance={},
            previous_questions=previous_questions,
            reassessment=reassessment,
        )

        raw = payload.get("questions", [])

        if isinstance(raw, list):
            ai_generated = True
        else:
            raw = []

    except Exception:
        raw = []
        ai_generated = False

    # --------------------------------------------------------
    # Clean AI questions and remove duplicates.
    # --------------------------------------------------------

    used_keys = set(previous_keys)

    for item in raw:

        if not isinstance(item, dict):
            continue

        text = str(
            item.get("question", "")
        ).strip()

        key = _question_key(text)

        if not text:
            continue

        if key in used_keys:
            continue

        options = item.get("options")

        if not isinstance(options, (list, dict)):
            continue

        correct_option = str(
            item.get("correct_option", "")
        ).strip().upper()

        if correct_option not in ("A", "B", "C", "D"):
            continue

        used_keys.add(key)
        clean.append(item)

        if len(clean) >= count:
            break

    # --------------------------------------------------------
    # Second AI request only for missing questions.
    #
    # This is NOT another assessment round.
    # It is simply question generation.
    # --------------------------------------------------------

    if len(clean) < count and ai_generated:

        remaining = count - len(clean)

        try:
            extra = ai_service.generate_assessment_questions(
                skill_names,
                num_questions=remaining,
                difficulty=difficulty,
                current_levels=level_by_name,
                previous_performance={},
                previous_questions=(
                    previous_questions
                    + [
                        item["question"]
                        for item in clean
                    ]
                ),
                reassessment=reassessment,
            )

            extra_questions = extra.get(
                "questions",
                []
            )

            if isinstance(extra_questions, list):

                for item in extra_questions:

                    if not isinstance(item, dict):
                        continue

                    text = str(
                        item.get("question", "")
                    ).strip()

                    key = _question_key(text)

                    if not text or key in used_keys:
                        continue

                    options = item.get("options")

                    if not isinstance(
                        options,
                        (list, dict)
                    ):
                        continue

                    correct_option = str(
                        item.get(
                            "correct_option",
                            ""
                        )
                    ).strip().upper()

                    if correct_option not in (
                        "A",
                        "B",
                        "C",
                        "D",
                    ):
                        continue

                    used_keys.add(key)
                    clean.append(item)

                    if len(clean) >= count:
                        break

        except Exception:
            pass

    # --------------------------------------------------------
    # OFFLINE FALLBACK
    # --------------------------------------------------------

    if len(clean) < count:

        try:
            bank = question_bank.get_questions(
                skill_names,
                per_skill=max(
                    2,
                    count // max(
                        1,
                        len(skill_names)
                    ) + 1,
                ),
            )
        except Exception:
            bank = []

        for item in bank:

            if not isinstance(item, dict):
                continue

            text = str(
                item.get("question", "")
            ).strip()

            key = _question_key(text)

            if not text or key in used_keys:
                continue

            options = item.get("options")

            if not isinstance(
                options,
                (list, dict)
            ):
                continue

            correct_option = str(
                item.get(
                    "correct_option",
                    ""
                )
            ).strip().upper()

            if correct_option not in (
                "A",
                "B",
                "C",
                "D",
            ):
                continue

            used_keys.add(key)
            clean.append(item)

            if len(clean) >= count:
                break

    # --------------------------------------------------------
    # LAST RESORT: the local question bank is small and fixed,
    # so a returning user can legitimately run out of brand-new
    # fallback questions once every bank entry for a skill has
    # already been asked in an earlier assessment. That is not a
    # real generation failure, so re-show already-seen bank
    # questions rather than blocking the assessment entirely.
    # Duplicates are still avoided *within this one assessment*.
    # --------------------------------------------------------

    if len(clean) < count:

        try:
            bank = question_bank.get_questions(
                skill_names,
                per_skill=max(
                    2,
                    count // max(
                        1,
                        len(skill_names)
                    ) + 1,
                ),
            )
        except Exception:
            bank = []

        seen_this_assessment = {
            _question_key(item.get("question", ""))
            for item in clean
        }

        for item in bank:

            if not isinstance(item, dict):
                continue

            text = str(
                item.get("question", "")
            ).strip()

            key = _question_key(text)

            if not text or key in seen_this_assessment:
                continue

            options = item.get("options")

            if not isinstance(
                options,
                (list, dict)
            ):
                continue

            correct_option = str(
                item.get(
                    "correct_option",
                    ""
                )
            ).strip().upper()

            if correct_option not in (
                "A",
                "B",
                "C",
                "D",
            ):
                continue

            seen_this_assessment.add(key)
            clean.append(item)

            if len(clean) >= count:
                break

    # --------------------------------------------------------
    # No questions at all = actual generation failure.
    # --------------------------------------------------------

    if not clean:
        raise RuntimeError(
            "No new questions could be generated "
            "for this assessment."
        )

    # --------------------------------------------------------
    # Map skill names to Skill objects.
    # --------------------------------------------------------

    skill_map = {
        requirement.skill.name.lower():
            requirement.skill
        for requirement in requirements
    }

    # --------------------------------------------------------
    # Store questions.
    # --------------------------------------------------------

    for index, item in enumerate(
        clean[:count],
        1
    ):

        name = str(
            item.get("skill", "")
        ).lower()

        skill = skill_map.get(name)

        if skill is None:
            skill = next(
                (
                    skill_obj
                    for skill_name, skill_obj
                    in skill_map.items()
                    if (
                        skill_name in name
                        or name in skill_name
                    )
                ),
                None,
            )

        question = AssessmentQuestion(
            assessment_id=assessment.id,
            question_text=item["question"],
            options_json=json.dumps(
                item["options"]
            ),
            correct_option=str(
                item["correct_option"]
            ).strip().upper(),
            explanation=item.get(
                "explanation"
            ),
            question_type=item.get(
                "question_type",
                "mcq"
            ),
            # IMPORTANT:
            # This difficulty NEVER changes during
            # the assessment.
            difficulty=difficulty,
            ai_generated=ai_generated,
            generation_metadata_json=json.dumps(
                {
                    "reassessment": reassessment,
                    "requested_difficulty": difficulty,
                    "fixed_assessment_difficulty": True,
                    "unique_against_user_history": True,
                }
            ),
            skill_id=(
                skill.id
                if skill
                else None
            ),
            order_index=index,
        )

        db.session.add(question)

    assessment.difficulty = difficulty

    return ai_generated


# ============================================================
# CAREER SELECTION
# ============================================================

@assessment_bp.get("/careers/select")
@login_required
def select():
    careers = Career.query.order_by(
        Career.title
    ).all()

    return render_template(
        "career/select.html",
        careers=careers,
    )


@assessment_bp.post("/careers/select")
@login_required
def select_post():

    ids = [
        int(x)
        for x in request.form.getlist(
            "career_ids"
        )
        if str(x).isdigit()
    ]

    ids = list(dict.fromkeys(ids))

    if not ids:
        flash(
            "Select at least one career.",
            "error",
        )

        return redirect(
            url_for("assessment.select")
        )

    return redirect(
        url_for(
            "assessment.start_multi",
            career_ids=",".join(
                map(str, ids)
            ),
        )
    )


# ============================================================
# START ASSESSMENT
# ============================================================

@assessment_bp.get(
    "/careers/<int:career_id>/assessment/start"
)
@login_required
def start(career_id):

    return redirect(
        url_for(
            "assessment.start_multi",
            career_ids=str(career_id),
        )
    )


@assessment_bp.get(
    "/assessments/start/<career_ids>"
)
@login_required
def start_multi(career_ids):

    try:
        ids = [
            int(x)
            for x in career_ids.split(",")
            if x
        ]
    except ValueError:
        abort(400)

    careers, requirements = _career_skills(ids)

    if not careers or not requirements:

        flash(
            "No skills configured for those careers.",
            "error",
        )

        return redirect(
            url_for("career.discovery")
        )

    # ========================================================
    # IMPORTANT:
    # Determine difficulty ONCE from CURRENT SKILL.
    #
    # There is no next_difficulty() here.
    # There will be no difficulty movement later.
    # ========================================================

    difficulty = _determine_assessment_difficulty(
        current_user,
        requirements,
    )

    question_count = min(
        max(
            6,
            len(requirements) * 2
        ),
        15,
    )

    assessment = Assessment(
        user_id=current_user.id,
        career_id=careers[0].id,
        status="in_progress",
        difficulty=difficulty,
        assessment_type="initial",
        started_at=_now(),
    )

    db.session.add(assessment)
    db.session.flush()

    # Store all selected careers.
    for career in careers:
        db.session.add(
            AssessmentCareer(
                assessment_id=assessment.id,
                career_id=career.id,
            )
        )

    # Generate ONE fixed assessment.
    try:
        _build_questions(
            current_user,
            careers,
            requirements,
            difficulty,
            question_count,
            assessment,
            reassessment=False,
        )
    except Exception:
        db.session.rollback()
        flash(
            "We couldn't prepare an assessment right now. Please try again.",
            "error",
        )
        return redirect(
            url_for("career.discovery")
        )

    db.session.commit()

    return redirect(
        url_for(
            "assessment.mcq_take",
            career_id=careers[0].id,
            assessment_id=assessment.id,
        )
    )


# ============================================================
# MCQ ASSESSMENT
# ============================================================

@assessment_bp.route(
    "/careers/<int:career_id>/assessment/mcq",
    methods=["GET", "POST"],
)
@login_required
def mcq_take(career_id):

    career = db.get_or_404(
        Career,
        career_id,
    )

    assessment_id = (
        request.args.get(
            "assessment_id",
            type=int,
        )
        or request.form.get(
            "assessment_id",
            type=int,
        )
    )

    if request.method == "GET" and not assessment_id:

        return redirect(
            url_for(
                "assessment.start",
                career_id=career.id,
            )
        )

    assessment = db.get_or_404(
        Assessment,
        assessment_id,
    )

    if (
        assessment.user_id
        != current_user.id
        or assessment.career_id
        != career.id
    ):
        abort(404)

    # Do not allow an already completed assessment
    # to be submitted again.
    if (
        request.method == "POST"
        and assessment.status == "completed"
    ):
        return redirect(
            url_for(
                "assessment.mcq_result",
                assessment_id=assessment.id,
            )
        )

    # ========================================================
    # SUBMIT THE SINGLE ASSESSMENT
    # ========================================================

    if request.method == "POST":

        questions = sorted(
            list(assessment.questions),
            key=lambda q: q.order_index,
        )

        if not questions:

            flash(
                "No questions are available for this assessment.",
                "error",
            )

            return redirect(
                url_for(
                    "assessment.start",
                    career_id=career.id,
                )
            )

        missing = False

        for question in questions:

            answer = request.form.get(
                f"q_{question.id}",
                "",
            )

            if answer not in (
                "A",
                "B",
                "C",
                "D",
            ):
                missing = True
                question.user_answer = None
            else:
                question.user_answer = answer

        # ----------------------------------------------------
        # Require every question to be answered.
        # ----------------------------------------------------

        if missing:

            flash(
                "Answer every question before submitting the assessment.",
                "error",
            )

            prepared = [
                (
                    question,
                    json.loads(
                        question.options_json
                        or "{}"
                    ),
                )
                for question in questions
            ]

            return render_template(
                "assessment/mcq_take.html",
                career=career,
                assessment=assessment,
                questions=questions,
                prepared=prepared,
            )

        # ----------------------------------------------------
        # Calculate final score.
        # ----------------------------------------------------

        total = len(questions)

        correct = sum(
            question.user_answer
            == question.correct_option
            for question in questions
        )

        score = (
            round(
                correct / total * 100,
                1,
            )
            if total
            else 0
        )

        # ====================================================
        # NO NEXT ROUND.
        # NO next_difficulty().
        # NO difficulty change.
        #
        # The assessment difficulty remains exactly the
        # difficulty selected when the assessment started.
        # ====================================================

        assessment.score = score

        assessment.status = "completed"

        assessment.completed_at = _now()

        # Overall skill level is based on the final score.
        if score >= 80:
            overall_level = "Advanced"
        elif score >= 50:
            overall_level = "Intermediate"
        else:
            overall_level = "Beginner"

        assessment.overall_skill_level = overall_level

        # ----------------------------------------------------
        # Update each individual skill.
        # ----------------------------------------------------

        skill_groups = _group_by_skill(
            questions
        )

        for skill_id, skill_questions in skill_groups.items():

            if not skill_id:
                continue

            answered = [
                question
                for question in skill_questions
                if question.user_answer
            ]

            if not answered:
                continue

            skill_correct = sum(
                question.user_answer
                == question.correct_option
                for question in answered
            )

            skill_score = (
                skill_correct
                / len(answered)
                * 100
            )

            skill_level = proficiency_from_score(
                skill_score
            )

            user_skill = UserSkill.query.filter_by(
                user_id=current_user.id,
                skill_id=skill_id,
            ).first()

            source = (
                "reassessment"
                if assessment.assessment_type
                == "reassessment"
                else "assessment"
            )

            if user_skill:

                user_skill.proficiency = skill_level
                user_skill.source = source
                user_skill.assessed_at = _now()

            else:

                db.session.add(
                    UserSkill(
                        user_id=current_user.id,
                        skill_id=skill_id,
                        proficiency=skill_level,
                        source=source,
                        assessed_at=_now(),
                    )
                )

        # ----------------------------------------------------
        # Store assessment metadata.
        # ----------------------------------------------------

        meta = {}

        try:
            meta = json.loads(
                assessment.analysis_json
                or "{}"
            )
        except Exception:
            meta = {}

        meta["assessment_score"] = score

        meta["correct_answers"] = correct

        meta["total_questions"] = total

        meta["assessment_difficulty"] = (
            assessment.difficulty
        )

        meta["difficulty_fixed"] = True

        meta["overall_skill_level"] = (
            overall_level
        )

        assessment.analysis_json = json.dumps(
            meta
        )

        db.session.commit()

        return redirect(
            url_for(
                "assessment.mcq_result",
                assessment_id=assessment.id,
            )
        )

    # ========================================================
    # GET ASSESSMENT
    # ========================================================

    questions = sorted(
        [
            question
            for question in assessment.questions
            if question.user_answer is None
        ],
        key=lambda q: q.order_index,
    )

    prepared = [
        (
            question,
            json.loads(
                question.options_json
                or "{}"
            ),
        )
        for question in questions
    ]

    return render_template(
        "assessment/mcq_take.html",
        career=career,
        assessment=assessment,
        questions=questions,
        prepared=prepared,
    )


# ============================================================
# GROUP QUESTIONS BY SKILL
# ============================================================

def _group_by_skill(questions):

    grouped = {}

    for question in questions:

        grouped.setdefault(
            question.skill_id,
            [],
        ).append(question)

    return grouped


# ============================================================
# MCQ RESULT
# ============================================================

@assessment_bp.get(
    "/assessments/<int:assessment_id>/mcq-result"
)
@login_required
def mcq_result(assessment_id):

    assessment = db.get_or_404(
        Assessment,
        assessment_id,
    )

    if assessment.user_id != current_user.id:
        abort(404)

    if assessment.status != "completed":

        return redirect(
            url_for(
                "assessment.mcq_take",
                career_id=assessment.career_id,
                assessment_id=assessment.id,
            )
        )

    career = assessment.career

    breakdown = []
    current = {}

    # --------------------------------------------------------
    # Calculate skill-wise result.
    # --------------------------------------------------------

    for skill_id, questions in _group_by_skill(
        assessment.questions
    ).items():

        skill = (
            db.session.get(
                Skill,
                skill_id,
            )
            if skill_id
            else None
        )

        total = len(questions)

        correct = sum(
            question.user_answer
            == question.correct_option
            for question in questions
        )

        skill_score = (
            correct / total * 100
            if total
            else 0
        )

        level = proficiency_from_score(
            skill_score
        )

        name = (
            skill.name
            if skill
            else "General"
        )

        current[name] = level

        breakdown.append(
            {
                "skill": name,
                "correct": correct,
                "total": total,
                "score": round(
                    skill_score,
                    1,
                ),
                "proficiency": level,
            }
        )

    # --------------------------------------------------------
    # Required career skills.
    # --------------------------------------------------------

    required = []

    if career:

        required = [
            {
                "name": career_skill.skill.name,
                "importance": (
                    career_skill.importance
                    or 1
                ),
            }
            for career_skill
            in career.career_skills
        ]

    # --------------------------------------------------------
    # AI skill-gap analysis.
    # --------------------------------------------------------

    try:

        gaps = ai_service.analyze_skill_gap(
            [
                {
                    "name": name,
                    "proficiency": level,
                }
                for name, level
                in current.items()
            ],
            career.title,
            required,
        ).get(
            "gaps",
            [],
        )

    except Exception:

        gaps = question_bank.local_skill_gap(
            current,
            required,
        ).get(
            "gaps",
            [],
        )

    # --------------------------------------------------------
    # AI assessment analysis.
    # --------------------------------------------------------

    results = [
        {
            "skill": item["skill"],
            "proficiency": item["proficiency"],
        }
        for item in breakdown
    ]

    try:

        analysis = ai_service.analyze_assessment(
            career.title,
            results,
            assessment.score,
            gaps,
        )

    except Exception:

        analysis = ai_service.local_analysis(
            results,
            gaps,
        )

    # Preserve the assessment metadata generated during
    # submission while adding the AI analysis.
    existing_meta = {}

    try:
        existing_meta = json.loads(
            assessment.analysis_json
            or "{}"
        )
    except Exception:
        existing_meta = {}

    if isinstance(analysis, dict):

        existing_meta["analysis"] = analysis

        assessment.analysis_json = json.dumps(
            existing_meta
        )

    db.session.commit()

    # --------------------------------------------------------
    # Advanced skills eligible for project generation.
    # --------------------------------------------------------

    advanced_items = []

    for item in breakdown:

        if item["proficiency"] >= 5:

            skill_id = next(
                (
                    career_skill.skill_id
                    for career_skill
                    in career.career_skills
                    if career_skill.skill.name
                    == item["skill"]
                ),
                None,
            )

            advanced_items.append(
                {
                    "skill": item["skill"],
                    "skill_id": skill_id,
                }
            )

    return render_template(
        "assessment/mcq_result.html",
        assessment=assessment,
        career=career,
        breakdown=breakdown,
        gaps=gaps,
        analysis=analysis,
        advanced_items=advanced_items,
    )


# ============================================================
# REASSESSMENT
# ============================================================

@assessment_bp.post(
    "/assessments/<int:assessment_id>/reassess"
)
@login_required
def reassess(assessment_id):

    previous = db.get_or_404(
        Assessment,
        assessment_id,
    )

    if (
        previous.user_id != current_user.id
        or previous.status != "completed"
    ):
        abort(404)

    career = previous.career

    selected_careers = [
        assessment_career.career
        for assessment_career
        in previous.selected_careers
        if assessment_career.career
    ]

    if not selected_careers and career:
        selected_careers = [career]

    if not selected_careers:
        abort(400)

    _, requirements = _career_skills(
        [
            career_item.id
            for career_item
            in selected_careers
        ]
    )

    # ========================================================
    # IMPORTANT:
    # Reassessment difficulty is determined from the user's
    # CURRENT UserSkill values.
    #
    # It does NOT use:
    #
    # next_difficulty()
    #
    # previous score does NOT push the difficulty up/down.
    # ========================================================

    difficulty = _determine_assessment_difficulty(
        current_user,
        requirements,
    )

    question_count = min(
        max(
            6,
            len(requirements) * 2
        ),
        15,
    )

    assessment = Assessment(
        user_id=current_user.id,
        career_id=selected_careers[0].id,
        status="in_progress",
        difficulty=difficulty,
        assessment_type="reassessment",
        parent_assessment_id=previous.id,
        started_at=_now(),
    )

    db.session.add(assessment)
    db.session.flush()

    for selected_career in selected_careers:

        db.session.add(
            AssessmentCareer(
                assessment_id=assessment.id,
                career_id=selected_career.id,
            )
        )

    # Generate ONE fixed-difficulty reassessment.
    try:
        _build_questions(
            current_user,
            selected_careers,
            requirements,
            difficulty,
            question_count,
            assessment,
            reassessment=True,
        )
    except Exception:
        db.session.rollback()
        flash(
            "We couldn't prepare a reassessment right now. Please try again.",
            "error",
        )
        return redirect(
            url_for(
                "assessment.mcq_result",
                assessment_id=previous.id,
            )
        )

    db.session.commit()

    flash(
        f"Reassessment generated at {difficulty} level.",
        "success",
    )

    return redirect(
        url_for(
            "assessment.mcq_take",
            career_id=career.id,
            assessment_id=assessment.id,
        )
    )


# ============================================================
# ADVANCED PROJECT GENERATION
# ============================================================

@assessment_bp.post(
    "/assessments/<int:assessment_id>/projects/<int:skill_id>"
)
@login_required
def generate_project(
    assessment_id,
    skill_id,
):

    assessment = db.get_or_404(
        Assessment,
        assessment_id,
    )

    if (
        assessment.user_id != current_user.id
        or assessment.status != "completed"
    ):
        abort(404)

    skill = db.get_or_404(
        Skill,
        skill_id,
    )

    user_skill = UserSkill.query.filter_by(
        user_id=current_user.id,
        skill_id=skill.id,
    ).first()

    if (
        not user_skill
        or user_skill.proficiency < 5
    ):

        flash(
            "Reach Advanced (5/5) in this skill before generating the project.",
            "error",
        )

        return redirect(
            url_for(
                "assessment.mcq_result",
                assessment_id=assessment.id,
            )
        )

    career = assessment.career

    try:

        data = ai_service.generate_project(
            career.title,
            skill.name,
            "Advanced",
        )

        project = Project(
            title=(
                data.get("title")
                or f"{skill.name} Advanced Portfolio Project"
            ),
            description=(
                data.get("objective")
                or ""
            )
            + "\n\n"
            + (
                data.get("description")
                or ""
            ),
            skill_id=skill.id,
            career_id=career.id,
            difficulty="Advanced",
            generated_by_ai=True,
            requirements_json=json.dumps(
                data.get("requirements")
                or data.get("features")
                or []
            ),
            expected_outcomes="\n".join(
                data.get(
                    "expected_outcomes"
                )
                or []
            ),
        )

    except Exception:

        project = Project(
            title=(
                f"{career.title} — "
                f"{skill.name} Advanced Portfolio Project"
            ),
            description=(
                "Build an end-to-end project "
                "demonstrating advanced "
                f"{skill.name} skills in a realistic "
                f"{career.title} scenario."
            ),
            skill_id=skill.id,
            career_id=career.id,
            difficulty="Advanced",
            generated_by_ai=False,
            requirements_json=json.dumps(
                [
                    "Define the problem and requirements",
                    "Implement the core solution",
                    "Add testing and documentation",
                    "Publish a clear README and demo",
                ]
            ),
            expected_outcomes=(
                "A working portfolio project with "
                "documented design decisions and "
                "measurable results."
            ),
        )

    db.session.add(project)
    db.session.commit()

    flash(
        "Your Advanced-level practical project is ready.",
        "success",
    )

    return redirect(
        url_for(
            "learning.project_detail",
            project_id=project.id,
        )
    )


# ============================================================
# BACKWARD-COMPATIBLE SELF-RATING
# ============================================================

@assessment_bp.route(
    "/careers/<int:career_id>/assessment",
    methods=["GET", "POST"],
)
@login_required
def take(career_id):

    career = db.get_or_404(
        Career,
        career_id,
    )

    requirements = career.career_skills

    if request.method == "POST":

        ratings = {}

        for requirement in requirements:

            try:
                value = int(
                    request.form.get(
                        f"skill_{requirement.skill_id}",
                        "0",
                    )
                )

            except ValueError:
                value = 0

            if value not in range(1, 6):

                flash(
                    "Rate every skill from 1 to 5.",
                    "error",
                )

                return render_template(
                    "assessment/take.html",
                    career=career,
                    requirements=requirements,
                    current_levels={},
                )

            ratings[
                requirement.skill_id
            ] = value

        assessment = Assessment(
            user_id=current_user.id,
            career_id=career.id,
            status="completed",
            score=(
                sum(ratings.values())
                / len(ratings)
            ),
            overall_skill_level="Self-reported",
            started_at=_now(),
            completed_at=_now(),
        )

        db.session.add(assessment)
        db.session.flush()

        for requirement in requirements:

            db.session.add(
                AssessmentQuestion(
                    assessment_id=assessment.id,
                    question_text=(
                        "Self-rated proficiency in "
                        f"{requirement.skill.name}"
                    ),
                    options_json='["1","2","3","4","5"]',
                    user_answer=str(
                        ratings[
                            requirement.skill_id
                        ]
                    ),
                    skill_id=requirement.skill_id,
                    order_index=requirement.id,
                )
            )

            user_skill = UserSkill.query.filter_by(
                user_id=current_user.id,
                skill_id=requirement.skill_id,
            ).first()

            if user_skill:

                user_skill.proficiency = ratings[
                    requirement.skill_id
                ]

                user_skill.source = "self_reported"

                user_skill.assessed_at = _now()

            else:

                db.session.add(
                    UserSkill(
                        user_id=current_user.id,
                        skill_id=requirement.skill_id,
                        proficiency=ratings[
                            requirement.skill_id
                        ],
                        source="self_reported",
                        assessed_at=_now(),
                    )
                )

        db.session.commit()

        return redirect(
            url_for(
                "assessment.result",
                assessment_id=assessment.id,
            )
        )

    levels = {
        user_skill.skill_id:
            user_skill.proficiency
        for user_skill
        in UserSkill.query.filter_by(
            user_id=current_user.id
        ).all()
    }

    return render_template(
        "assessment/take.html",
        career=career,
        requirements=requirements,
        current_levels=levels,
    )


# ============================================================
# LEGACY RESULT ROUTE
# ============================================================

@assessment_bp.get(
    "/assessments/<int:assessment_id>"
)
@login_required
def result(assessment_id):

    assessment = db.get_or_404(
        Assessment,
        assessment_id,
    )

    if assessment.user_id != current_user.id:
        abort(404)

    return render_template(
        "assessment/result.html",
        assessment=assessment,
    )