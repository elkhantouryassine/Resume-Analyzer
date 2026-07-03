import math
from collections import Counter
from functools import lru_cache


try:
    from sentence_transformers import SentenceTransformer, util
except Exception:
    SentenceTransformer = None
    util = None


@lru_cache(maxsize=1)
def load_model():
    if SentenceTransformer is None:
        return None
    try:
        return SentenceTransformer("all-MiniLM-L6-v2")
    except Exception:
        return None


def compare_skills(cv_skills, offer_skills):
    cv_set = set(cv_skills)
    matched = [skill for skill in offer_skills if skill in cv_set]
    missing = [skill for skill in offer_skills if skill not in cv_set]

    score = (len(matched) / len(offer_skills)) * 100 if offer_skills else 0

    return {
        "matched_skills": matched,
        "missing_skills": missing,
        "score": round(score, 2),
    }


def lexical_similarity(cv_text, offer_text):
    cv_words = Counter(cv_text.split())
    offer_words = Counter(offer_text.split())
    common_words = set(cv_words) & set(offer_words)

    numerator = sum(cv_words[word] * offer_words[word] for word in common_words)
    cv_norm = math.sqrt(sum(count * count for count in cv_words.values()))
    offer_norm = math.sqrt(sum(count * count for count in offer_words.values()))

    if not cv_norm or not offer_norm:
        return 0

    return round((numerator / (cv_norm * offer_norm)) * 100, 2)


def semantic_similarity(cv_text, offer_text):
    model = load_model()

    if model is None:
        return lexical_similarity(cv_text, offer_text)

    cv_emb = model.encode(cv_text, convert_to_tensor=True)
    offer_emb = model.encode(offer_text, convert_to_tensor=True)

    similarity = util.cos_sim(cv_emb, offer_emb)

    return round(float(similarity[0][0]) * 100, 2)


def final_score(skill_score, semantic_score):
    return round((skill_score * 0.6) + (semantic_score * 0.4), 2)
