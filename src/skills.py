import re


SKILL_CATEGORIES = {
    "Langages": [
        "python",
        "java",
        "c++",
        "c#",
        "php",
        "javascript",
        "sql",
        "typescript",
        "r",
    ],
    "Data et IA": [
        "pandas",
        "numpy",
        "matplotlib",
        "scikit learn",
        "machine learning",
        "deep learning",
        "data science",
        "nlp",
        "power bi",
        "tableau",
        "excel",
    ],
    "Web et API": [
        "django",
        "laravel",
        "node.js",
        ".net",
        "react",
        "react native",
        "fastapi",
        "bootstrap",
    ],
    "Bases de donnees": [
        "mysql",
        "sqlite",
        "oracle database",
        "postgresql",
        "mongodb",
        "neo4j",
        "cassandra",
    ],
    "Outils et methodes": [
        "docker",
        "git",
        "github",
        "jupyter",
        "merise",
        "uml",
        "agile",
        "scrum",
        "ci/cd",
    ],
}

SKILLS = sorted({skill for skills in SKILL_CATEGORIES.values() for skill in skills})


def _skill_pattern(skill):
    escaped = re.escape(skill).replace(r"\ ", r"\s+")
    return re.compile(rf"(?<![\w+#.]){escaped}(?![\w+#.])", re.IGNORECASE)


def extract_skills(text):
    found_skills = []

    for skill in SKILLS:
        if _skill_pattern(skill).search(text):
            found_skills.append(skill)

    return found_skills
