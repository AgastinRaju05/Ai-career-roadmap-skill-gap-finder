"""LLM integration for Career Roadmap AI.

The LLM generates content and analysis. Scoring, adaptation, validation,
persistence, and fallbacks remain deterministic in the Flask application.
"""
import json
import re
import warnings

from flask import current_app

# Groq's bundled pydantic dependency is incompatible with Python 3.14+, but
# the app still works in fallback mode when the API key is absent.
# We suppress only the warning that is irrelevant to functionality.
warnings.filterwarnings("ignore", message=".*Core Pydantic V1 functionality.*", category=UserWarning)

try:
    from groq import Groq
except Exception:  # pragma: no cover - fallback if Groq isn't available
    Groq = None


def _client():
    api_key = current_app.config.get("GROQ_API_KEY", "")
    if not api_key:
        raise RuntimeError("GROQ_API_KEY is not configured.")
    if Groq is None:
        raise RuntimeError("groq package is not available.")
    return Groq(api_key=api_key)

def _chat(system_prompt, user_prompt, temperature=0.35):
    response = _client().chat.completions.create(
        model=current_app.config.get("GROQ_MODEL", "llama-3.3-70b-versatile"),
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        temperature=temperature,
        response_format={"type": "json_object"},
    )
    content = response.choices[0].message.content or ""
    try:
        return json.loads(content)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", content, re.S)
        if match:
            return json.loads(match.group(0))
        raise ValueError("AI returned invalid JSON.")

def _normalize_question(text):
    """Normalize question text for reliable duplicate detection."""
    text = str(text or "").lower()
    text = re.sub(r"```[\s\S]*?```", " ", text)
    text = re.sub(r"[^a-z0-9]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def _is_duplicate_question(candidate, previous_questions, accepted_questions):
    """Return True for exact or near-identical questions."""
    from difflib import SequenceMatcher

    candidate_key = _normalize_question(candidate)
    if not candidate_key:
        return True

    for old in list(previous_questions or []) + list(accepted_questions or []):
        old_key = _normalize_question(old)
        if not old_key:
            continue
        if candidate_key == old_key:
            return True
        if SequenceMatcher(None, candidate_key, old_key).ratio() >= 0.90:
            return True
    return False


def _validate_questions(payload, allowed_skills, difficulty="Beginner",
                        previous_questions=None, accepted_questions=None):
    """Validate one AI response and remove duplicate/invalid questions."""
    if not isinstance(payload, dict) or not isinstance(payload.get("questions"), list):
        raise ValueError("AI returned an invalid question payload.")

    previous_questions = previous_questions or []
    accepted_questions = accepted_questions or []
    allowed = {s.strip().lower(): s for s in allowed_skills}
    output = []

    for item in payload["questions"]:
        if not isinstance(item, dict):
            continue

        text = str(item.get("question", "")).strip()
        options = item.get("options")
        correct = str(item.get("correct_option", "")).strip().upper()
        skill = str(item.get("skill", "")).strip()

        if not text or not isinstance(options, dict):
            continue
        if correct not in {"A", "B", "C", "D"}:
            continue
        if any(k not in options for k in ("A", "B", "C", "D")):
            continue
        if any(not str(options[k]).strip() for k in ("A", "B", "C", "D")):
            continue

        # Map small AI variations back to the real career skill name.
        skill_name = allowed.get(skill.lower())
        if not skill_name:
            skill_name = next(
                (real for key, real in allowed.items()
                 if key in skill.lower() or skill.lower() in key),
                None,
            )
        if not skill_name:
            continue

        if _is_duplicate_question(text, previous_questions, accepted_questions + [q["question"] for q in output]):
            continue

        output.append({
            "question": text,
            "skill": skill_name,
            "options": {k: str(options[k]).strip() for k in ("A", "B", "C", "D")},
            "correct_option": correct,
            "question_type": str(item.get("question_type", "mcq")).strip() or "mcq",
            # Never trust the LLM's difficulty label. The backend owns it.
            "difficulty": difficulty,
            "explanation": str(item.get("explanation", "")).strip(),
        })

    return output


def generate_assessment_questions(skill_names, num_questions=10, difficulty="Beginner",
                                  current_levels=None, previous_performance=None,
                                  previous_questions=None, reassessment=False):
    """Generate a fresh adaptive question set with duplicate protection."""
    current_levels = current_levels or {}
    previous_performance = previous_performance or {}
    previous_questions = list(previous_questions or [])
    difficulty = str(difficulty or "Beginner").strip().title()
    if difficulty not in {"Beginner", "Intermediate", "Advanced"}:
        difficulty = "Beginner"

    rules = {
        "Beginner": "Test fundamentals, basic syntax, simple concepts and straightforward output.",
        "Intermediate": "Require application, multi-step reasoning, debugging, practical scenarios and non-trivial code/data problems. Avoid simple definitions.",
        "Advanced": "Require deep reasoning, edge cases, debugging, optimization, trade-offs and realistic technical scenarios. Avoid simple definitions and one-step questions.",
    }

    system = f"""You are an expert adaptive technical assessment generator.
Generate NEW, objectively gradeable A/B/C/D questions.

Requested level: {difficulty}
Difficulty rule: {rules[difficulty]}

STRICT RULES:
- Generate genuinely new underlying problems.
- Never repeat or paraphrase a previous question.
- Never repeat a question within the same response.
- Exactly four options: A, B, C, D.
- Exactly one correct option.
- Use only the supplied skills.
- Match the requested difficulty in the actual problem complexity, not merely the label.
- Mix conceptual, output, debugging, correct-code and scenario questions when appropriate.
- Return only JSON.

JSON format:
{{"questions":[{{"question":"...","skill":"...","options":{{"A":"...","B":"...","C":"...","D":"..."}},"correct_option":"A","question_type":"mcq","difficulty":"{difficulty}","explanation":"..."}}]}}"""

    accepted = []
    # Multiple smaller requests are much more reliable than demanding a huge
    # perfect response from the model in one call.
    remaining = num_questions

    for attempt in range(4):
        if remaining <= 0:
            break

        already_seen = previous_questions + [q["question"] for q in accepted]
        prompt = {
            "skills": skill_names,
            "difficulty": difficulty,
            "num_questions": remaining,
            "current_levels": current_levels,
            "previous_performance": previous_performance,
            "previous_questions": already_seen[-60:],
            "reassessment": reassessment,
            "instruction": (
                f"Generate exactly {remaining} additional questions. "
                "Every one must be different from previous_questions and from the other questions."
            ),
        }

        if attempt:
            prompt["instruction"] += (
                " The earlier response did not provide enough usable unique questions. "
                "Generate completely different replacement questions now."
            )

        try:
            payload = _chat(system, json.dumps(prompt), 0.55 + attempt * 0.05)
            fresh = _validate_questions(
                payload,
                skill_names,
                difficulty=difficulty,
                previous_questions=previous_questions,
                accepted_questions=[q["question"] for q in accepted],
            )
            accepted.extend(fresh)
            remaining = num_questions - len(accepted)
        except Exception:
            # Retry with a fresh request. Do not expose a transient AI error
            # as "no questions" when another generation attempt can succeed.
            continue

    if not accepted:
        raise RuntimeError("AI could not generate any valid unique questions.")

    # Return whatever unique AI questions were successfully generated. The
    # route will safely top-up from unused local questions if necessary.
    return {"questions": accepted[:num_questions]}

def analyze_assessment(career_title, skill_results, overall_score, gaps):
    system="""Analyze an adaptive career assessment. Do not change the score.
Return JSON:
{"summary":str,"strengths":[str],"weaknesses":[str],"learning_priorities":[str],
"next_steps":[str]}"""
    return _chat(system,json.dumps({
        "career":career_title,"overall_score":overall_score,
        "skill_results":skill_results,"skill_gaps":gaps,
    }))

def analyze_skill_gap(user_skills, career_title, required_skills):
    system="""Compare current estimated skill levels to career requirements.
Return JSON {"gaps":[{"skill":str,"current_level":int,"required_level":int,
"priority":"High|Medium|Low","note":str}]}.
Do not invent skills outside the required list."""
    return _chat(system,json.dumps({"career":career_title,"current_skills":user_skills,
                                    "required_skills":required_skills}))

def generate_roadmap(career_title, skill_gaps, current_skills=None):
    system="""Create a practical learning roadmap for a student. Return JSON:
{"title":str,"summary":str,"steps":[{"title":str,"description":str,"skill":str,
"suggested_course_topic":str,"provider":str,"resource_url":str,
"estimated_weeks":int}]}.
Do not fabricate URLs. Leave resource_url empty unless the supplied catalog
already provides a URL. Providers may be named without URLs."""
    return _chat(system,json.dumps({"career":career_title,"skill_gaps":skill_gaps,
                                    "current_skills":current_skills or []}),0.45)

def generate_project(career_title, skill_name, level="Advanced"):
    system="""Design one realistic portfolio project for a college student who
has reached Advanced skill level. Return JSON:
{"title":str,"description":str,"objective":str,"technology_stack":[str],
"features":[str],"requirements":[str],"expected_outcomes":[str],
"difficulty":"Advanced"}"""
    return _chat(system,json.dumps({"career":career_title,"skill":skill_name,"level":level}),0.5)

def match_careers(user_skills, goal_career=None):
    system="""Recommend career matches from a provided catalog only. Return
JSON {"matches":[{"career":str,"match_percent":int,"reason":str}]}."""
    return _chat(system,json.dumps({"current_skills":user_skills,"goal_career_hint":goal_career}))

def local_analysis(skill_results, gaps):
    return {
        "summary":"Your assessment shows measurable strengths and skill gaps. Follow the roadmap and reassess after completing a learning phase.",
        "strengths":[r["skill"] for r in skill_results if r["proficiency"] >= 4],
        "weaknesses":[r["skill"] for r in skill_results if r["proficiency"] <= 2],
        "learning_priorities":[g["skill"] for g in gaps],
        "next_steps":["Start the highest-priority skill","Complete the recommended learning phase","Reassess the skill"],
    }
