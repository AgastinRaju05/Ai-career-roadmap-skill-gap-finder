"""Deterministic adaptive assessment rules.

AI generates questions; this module decides difficulty transitions and
proficiency levels. Thresholds are project policy, not a scientific claim.
"""
LEVELS = ("Beginner", "Intermediate", "Advanced")
DIFFICULTY_SCORE = {"Beginner": 1, "Intermediate": 2, "Advanced": 3}

def normalize_level(level):
    if not level:
        return "Beginner"
    value = str(level).strip().title()
    return value if value in LEVELS else "Beginner"

def next_difficulty(current, score_percent):
    current = normalize_level(current)
    score = float(score_percent or 0)
    index = LEVELS.index(current)
    if score > 70 and index < len(LEVELS)-1:
        index += 1
    elif score < 50 and index > 0:
        index -= 1
    return LEVELS[index]

def proficiency_from_score(score_percent):
    score = max(0.0, min(100.0, float(score_percent or 0)))
    # 1..5 estimated proficiency, deliberately deterministic.
    if score < 20: return 1
    if score < 40: return 2
    if score < 60: return 3
    if score < 80: return 4
    return 5

def difficulty_for_skill(current_level, score_percent=None):
    if score_percent is None:
        return normalize_level(current_level)
    return next_difficulty(current_level, score_percent)
