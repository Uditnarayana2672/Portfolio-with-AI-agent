"""Portfolio content document upgrades (domain layer).

The stored document is brought to the current shape on read, so old rows keep
working and the next save persists the new shape.
"""
from __future__ import annotations

import copy

PROJECT_COUNT_SOURCE = "published_projects"

DEFAULT_THROUGH_LINE = ["Listen", "Deliver", "Build"]
DEFAULT_EDUCATION_SECTION = {"title": "Learning the", "title_soft": "theory first."}
# What the page showed before education became editable.
DEFAULT_EDUCATION = [
    {
        "id": "ed-btech",
        "degree": "B.Tech — Computer Science & Engineering",
        "institution": "Specialization in Artificial Intelligence · First Class",
        "start_year": 2016,
        "end_year": 2020,
        "summary": (
            "Machine learning, distributed systems and human-computer interaction. "
            "Capstone: a neural retrieval engine for lecture archives."
        ),
        "highlights": [
            "Led the AI student chapter; ran weekly paper-reading circles",
            "Built the department’s first course-recommendation model",
        ],
    },
    {
        "id": "ed-deep-learning",
        "degree": "Deep Learning Specialization",
        "institution": "DeepLearning.AI · Coursera",
        "start_year": 2023,
        "end_year": 2023,
        "summary": "Sequence models, attention and transformers — the theory underneath the agents I build today.",
        "highlights": ["Completed all five courses with distinction"],
    },
]


def upgrade_document(content: dict) -> dict:
    """Current shape: no "currently building" card, a portrait slot, every stat
    naming its source, one category per tech, jobs with a logo and images, and
    editable education. The student-conversations stat becomes the live project
    count."""
    doc = copy.deepcopy(content)
    hero = doc.get("hero") or {}
    hero.pop("currently_building", None)
    hero.setdefault("portrait", None)
    for stat in (doc.get("about") or {}).get("stats") or []:
        if "source" in stat:
            continue
        if "student conversations" in (stat.get("label") or "").lower():
            stat.update(source=PROJECT_COUNT_SOURCE, value=None, suffix="+", label="scalable projects")
        else:
            stat["source"] = "manual"
    about = doc.get("about")
    if isinstance(about, dict):
        about.setdefault("through_line", list(DEFAULT_THROUGH_LINE))
    for tech in doc.get("tech") or []:
        categories = tech.pop("categories", None)
        if "category" not in tech and categories:
            tech["category"] = categories[0]  # one category only; the first one wins
    for job in doc.get("experience") or []:
        job.setdefault("logo", None)
        job.setdefault("images", [])
    doc.setdefault("education_section", copy.deepcopy(DEFAULT_EDUCATION_SECTION))
    doc.setdefault("education", copy.deepcopy(DEFAULT_EDUCATION))
    return doc


def resolve_stats(content: dict, published_projects: int) -> dict:
    """Public view: fill automatic stats in with their real values."""
    doc = copy.deepcopy(content)
    for stat in (doc.get("about") or {}).get("stats") or []:
        if stat.get("source") == PROJECT_COUNT_SOURCE:
            stat["value"] = str(published_projects)
    return doc
