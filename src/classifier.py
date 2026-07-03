from functools import lru_cache


try:
    import joblib
except ImportError:
    joblib = None


@lru_cache(maxsize=1)
def load_classifier():
    if joblib is None:
        return None

    try:
        return joblib.load("model/recruitment_model.pkl")
    except Exception:
        return None


def predict_candidate(skill_score, semantic_score, matched_skills, missing_skills):
    model = load_classifier()

    if model is None:
        fallback_score = (skill_score * 0.6) + (semantic_score * 0.4)
        positive = max(0.05, min(fallback_score / 100, 0.95))
        prediction = 1 if fallback_score >= 65 else 0
        return prediction, [1 - positive, positive]

    features = [[skill_score, semantic_score, matched_skills, missing_skills]]
    prediction = model.predict(features)[0]
    probability = model.predict_proba(features)[0]

    return prediction, probability
