"""
Local fallback content for the skill-assessment feature.

The AI service (app/services/ai_service.py) already exposes
`generate_assessment_questions()` and `analyze_skill_gap()`, but both
depend on GROQ_API_KEY being configured and the API being reachable.
This module provides a small, deterministic fallback so the MCQ
assessment and skill-gap analysis still work out of the box (no key,
offline demo, API error, etc.). Routes should try the AI service first
and fall back to these helpers on failure.
"""

# A modest hand-written MCQ bank, keyed by skill name (case-insensitive).
# Each question: text, options A-D, and the correct option letter.
QUESTION_BANK = {
    "python": [
        {
            "question": "What does the following return? len([1, 2, 3])",
            "options": {"A": "2", "B": "3", "C": "Error", "D": "None"},
            "correct_option": "B",
        },
        {
            "question": "Which keyword defines a function in Python?",
            "options": {"A": "func", "B": "def", "C": "function", "D": "lambda only"},
            "correct_option": "B",
        },
        {
            "question": "Which data type is immutable in Python?",
            "options": {"A": "list", "B": "dict", "C": "tuple", "D": "set"},
            "correct_option": "C",
        },
    ],
    "javascript": [
        {
            "question": "Which keyword declares a block-scoped variable in modern JavaScript?",
            "options": {"A": "var", "B": "let", "C": "define", "D": "int"},
            "correct_option": "B",
        },
        {
            "question": "What does `===` check in JavaScript?",
            "options": {
                "A": "Value only",
                "B": "Type only",
                "C": "Value and type",
                "D": "Reference only",
            },
            "correct_option": "C",
        },
    ],
    "sql": [
        {
            "question": "Which SQL clause filters rows before grouping?",
            "options": {"A": "HAVING", "B": "WHERE", "C": "GROUP BY", "D": "ORDER BY"},
            "correct_option": "B",
        },
        {
            "question": "Which JOIN returns only matching rows from both tables?",
            "options": {"A": "LEFT JOIN", "B": "RIGHT JOIN", "C": "INNER JOIN", "D": "FULL OUTER JOIN"},
            "correct_option": "C",
        },
    ],
    "html/css": [
        {
            "question": "Which CSS property controls spacing outside an element's border?",
            "options": {"A": "padding", "B": "margin", "C": "border-spacing", "D": "gap"},
            "correct_option": "B",
        },
        {
            "question": "Which HTML tag is used for the largest heading?",
            "options": {"A": "<h6>", "B": "<heading>", "C": "<h1>", "D": "<head>"},
            "correct_option": "C",
        },
    ],
    "data structures & algorithms": [
        {
            "question": "What is the average time complexity of binary search?",
            "options": {"A": "O(n)", "B": "O(log n)", "C": "O(n^2)", "D": "O(1)"},
            "correct_option": "B",
        },
        {
            "question": "Which data structure uses LIFO ordering?",
            "options": {"A": "Queue", "B": "Stack", "C": "Linked list", "D": "Graph"},
            "correct_option": "B",
        },
    ],
    "machine learning": [
        {
            "question": "Which of these is an example of supervised learning?",
            "options": {
                "A": "Clustering unlabeled data",
                "B": "Predicting house prices from labeled examples",
                "C": "Reducing dimensionality",
                "D": "Random exploration with no reward",
            },
            "correct_option": "B",
        },
        {
            "question": "What does 'overfitting' mean?",
            "options": {
                "A": "The model performs well on both training and unseen data",
                "B": "The model is too simple to learn patterns",
                "C": "The model memorizes training data but generalizes poorly",
                "D": "The model has no parameters",
            },
            "correct_option": "C",
        },
    ],
    "statistics": [
        {
            "question": "What does the standard deviation measure?",
            "options": {
                "A": "The middle value of a dataset",
                "B": "The spread of values around the mean",
                "C": "The most frequent value",
                "D": "The total sum of values",
            },
            "correct_option": "B",
        },
        {
            "question": "A p-value below the significance threshold typically suggests:",
            "options": {
                "A": "The null hypothesis is likely true",
                "B": "Strong evidence against the null hypothesis",
                "C": "The sample size was too small",
                "D": "No conclusion can be drawn",
            },
            "correct_option": "B",
        },
    ],
    "data visualization": [
        {
            "question": "Which chart type best shows change over time?",
            "options": {"A": "Pie chart", "B": "Line chart", "C": "Scatter plot", "D": "Heatmap"},
            "correct_option": "B",
        },
    ],
    "cloud computing (aws/gcp)": [
        {
            "question": "Which service model provides raw virtual machines you manage yourself?",
            "options": {"A": "SaaS", "B": "PaaS", "C": "IaaS", "D": "FaaS"},
            "correct_option": "C",
        },
        {
            "question": "What is the main benefit of auto-scaling in the cloud?",
            "options": {
                "A": "It permanently lowers storage cost",
                "B": "It adjusts compute capacity automatically with demand",
                "C": "It replaces the need for monitoring",
                "D": "It encrypts data at rest",
            },
            "correct_option": "B",
        },
    ],
    "git & version control": [
        {
            "question": "Which command creates a new branch in Git?",
            "options": {"A": "git branch <name>", "B": "git new <name>", "C": "git create <name>", "D": "git init <name>"},
            "correct_option": "A",
        },
        {
            "question": "What does `git merge` do?",
            "options": {
                "A": "Deletes a branch",
                "B": "Combines changes from one branch into another",
                "C": "Reverts the last commit",
                "D": "Renames a repository",
            },
            "correct_option": "B",
        },
    ],
    "rest apis": [
        {
            "question": "Which HTTP method is typically used to update an existing resource?",
            "options": {"A": "GET", "B": "POST", "C": "PUT", "D": "OPTIONS"},
            "correct_option": "C",
        },
        {
            "question": "Which HTTP status code means 'Not Found'?",
            "options": {"A": "200", "B": "301", "C": "404", "D": "500"},
            "correct_option": "C",
        },
    ],
    "system design": [
        {
            "question": "What is the main purpose of a load balancer?",
            "options": {
                "A": "Store data permanently",
                "B": "Distribute incoming traffic across multiple servers",
                "C": "Encrypt database records",
                "D": "Compile application code",
            },
            "correct_option": "B",
        },
    ],
    "ui/ux design": [
        {
            "question": "What is the primary goal of a usability test?",
            "options": {
                "A": "To check the code for bugs",
                "B": "To see how real users interact with a design and find friction points",
                "C": "To measure server response time",
                "D": "To finalize the color palette",
            },
            "correct_option": "B",
        },
    ],
    "communication": [
        {
            "question": "When giving constructive feedback, it is generally best to:",
            "options": {
                "A": "Focus only on what went wrong",
                "B": "Be specific, focus on behavior, and suggest a way forward",
                "C": "Avoid giving feedback to prevent conflict",
                "D": "Give feedback publicly to save time",
            },
            "correct_option": "B",
        },
    ],
    "project management": [
        {
            "question": "In Agile, a 'sprint' typically refers to:",
            "options": {
                "A": "A one-time final release",
                "B": "A fixed, short time-boxed period to complete a set of work",
                "C": "An unplanned meeting",
                "D": "A budgeting document",
            },
            "correct_option": "B",
        },
    ],
}


def _generic_questions(skill_name):
    """Last-resort question for a skill with no dedicated bank entry."""
    return [
        {
            "question": f"Which statement best describes a solid working knowledge of {skill_name}?",
            "options": {
                "A": f"I can independently apply {skill_name} to solve a real task and explain my choices",
                "B": f"I have only heard the term {skill_name} before",
                "C": f"I have never encountered {skill_name}",
                "D": f"{skill_name} is unrelated to my field",
            },
            "correct_option": "A",
        }
    ]


def get_questions(skill_names, per_skill=2):
    """
    Build a flat list of MCQ dicts covering the given skill names, e.g.:
    [{"question": str, "skill": str, "options": {...}, "correct_option": "A"}, ...]
    Pulls from QUESTION_BANK when available, otherwise uses a generic
    self-check question so every requested skill is still covered.
    """
    questions = []
    for name in skill_names:
        bank_entries = QUESTION_BANK.get(name.strip().lower())
        entries = bank_entries[:per_skill] if bank_entries else _generic_questions(name)
        for entry in entries:
            questions.append({
                "question": entry["question"],
                "skill": name,
                "options": entry["options"],
                "correct_option": entry["correct_option"],
            })
    return questions


def local_skill_gap(current_levels_by_name, required_skills):
    """
    Fallback skill-gap analysis (no AI call).
    required_skills: list of {"name": str, "importance": int(1-5)}
    Returns the same shape as ai_service.analyze_skill_gap():
    {"gaps": [{"skill", "current_level", "required_level", "priority", "note"}]}
    """
    gaps = []
    for item in required_skills:
        name = item["name"]
        required_level = item["importance"]
        current_level = current_levels_by_name.get(name, 0)
        if current_level < required_level:
            diff = required_level - current_level
            if diff >= 3:
                priority = "High"
            elif diff == 2:
                priority = "Medium"
            else:
                priority = "Low"
            gaps.append({
                "skill": name,
                "current_level": current_level,
                "required_level": required_level,
                "priority": priority,
                "note": (
                    f"Your assessed level is {current_level}/5, below the {required_level}/5 "
                    f"typically expected for this role. Focus practice here."
                ),
            })
    gaps.sort(key=lambda g: {"High": 0, "Medium": 1, "Low": 2}[g["priority"]])
    return {"gaps": gaps}
