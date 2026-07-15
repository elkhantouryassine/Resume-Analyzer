from functools import lru_cache
import warnings


try:
    import joblib
except ImportError:
    joblib = None

try:
    import pandas as pd
except ImportError:
    pd = None


CLASSIFIER_FEATURES = [
    "skill_score",
    "semantic_score",
    "matched_skills",
    "missing_skills",
]


@lru_cache(maxsize=1)
def load_classifier():
    if joblib is None:
        return None

    try:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            return joblib.load("model/recruitment_model.pkl")
    except Exception:
        return None


def _clean_class_label(value):
    try:
        return int(value)
    except (TypeError, ValueError):
        return str(value)


def _classifier_metadata(model, ready):
    classes = getattr(model, "classes_", [0, 1]) if model is not None else [0, 1]
    features = getattr(model, "feature_names_in_", CLASSIFIER_FEATURES) if model is not None else CLASSIFIER_FEATURES
    return {
        "ready": ready,
        "engine": "Random Forest" if ready else "Fallback local",
        "model": type(model).__name__ if model is not None else "FallbackScore",
        "classes": [_clean_class_label(item) for item in classes],
        "features": [str(item) for item in features],
    }


def _build_feature_input(model, skill_score, semantic_score, matched_skills, missing_skills):
    values = {
        "skill_score": float(skill_score),
        "semantic_score": float(semantic_score),
        "matched_skills": int(matched_skills),
        "missing_skills": int(missing_skills),
    }
    feature_names = list(getattr(model, "feature_names_in_", CLASSIFIER_FEATURES))
    row = [values.get(name, 0) for name in feature_names]

    if pd is not None and getattr(model, "feature_names_in_", None) is not None:
        return pd.DataFrame([row], columns=feature_names)

    return [row]


def predict_candidate(skill_score, semantic_score, matched_skills, missing_skills):
    model = load_classifier()

    if model is None:
        fallback_score = (skill_score * 0.6) + (semantic_score * 0.4)
        positive = max(0.05, min(fallback_score / 100, 0.95))
        prediction = 1 if fallback_score >= 65 else 0
        return prediction, [1 - positive, positive], _classifier_metadata(None, False)

    features = _build_feature_input(model, skill_score, semantic_score, matched_skills, missing_skills)
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        prediction = model.predict(features)[0]
        probability = [float(value) for value in model.predict_proba(features)[0]]

    return int(prediction), probability, _classifier_metadata(model, True)
