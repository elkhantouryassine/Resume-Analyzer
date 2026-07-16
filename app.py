import json
import os
import re
import sqlite3
import sys
import tempfile
import time
import unicodedata
import uuid
from collections import Counter
from datetime import datetime
from email.parser import BytesParser
from email.policy import default
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlsplit
from src.rag_chatbot import add_cv_to_vector_db, generate_chatbot_answer, list_indexed_cvs
from src.ai_report import generate_report
from src.classifier import load_classifier, predict_candidate
from src.cleaner import clean_text
from src.extractor import extract_docx_text, extract_pdf_text
from src.matcher import compare_skills, load_model, semantic_similarity
from src.skills import extract_skills

BASE_DIR = Path(__file__).resolve().parent
LOCAL_SITE_PACKAGES = BASE_DIR / ".venv" / "Lib" / "site-packages"


def prefer_local_site_packages():
    local_path = str(LOCAL_SITE_PACKAGES)
    if LOCAL_SITE_PACKAGES.exists():
        sys.path[:] = [path for path in sys.path if path != local_path]
        sys.path.insert(0, local_path)


prefer_local_site_packages()



UPLOAD_DIR = BASE_DIR / "data" / "cvs"
HISTORY_DIR = BASE_DIR / "data" / "history"
HISTORY_DB = HISTORY_DIR / "analysis_history.sqlite"

TRACKING_STAGES = [
    {"id": "selection", "label": "CV retenu"},
    {"id": "rh", "label": "Entretien RH"},
    {"id": "technical", "label": "Entretien technique"},
    {"id": "procedure", "label": "Suite de procedure"},
]
TRACKING_STAGE_IDS = {stage["id"] for stage in TRACKING_STAGES}
ALLOWED_EXTENSIONS = {".pdf", ".docx", ".txt"}

SECTION_PATTERNS = {
    "Profil": r"\b(profil|summary|resume|objectif|a propos)\b",
    "Experience": r"\b(experience|experiences|work history|emploi|stage)\b",
    "Formation": r"\b(formation|education|diplôme|degree|universite)\b",
    "Compétences": r"\b(competences|skills|technologies|outils)\b",
    "Projets": r"\b(projets|projects|realisations)\b",
    "Langues": r"\b(langues|languages)\b",
}

KEYWORD_STOPWORDS = {
    "avec", "dans", "pour", "plus", "nous", "vous", "votre", "notre", "cette",
    "poste", "profil", "offre", "emploi", "recherche", "recherchons", "capable",
    "competence", "competences", "attendues", "attendu", "bonne", "bonnes",
    "bases", "plus", "and", "the", "for", "with", "from", "that", "this",
    "candidate", "role", "job", "work", "team", "teams", "skills", "skill",
}

PROFILE_TYPES = {
    "Data Analyst": {
        "skills": ["python", "sql", "pandas", "numpy", "excel", "power bi", "tableau", "matplotlib"],
        "keywords": [
            "data analyst", "analyse de donnees", "dashboard", "tableau de bord",
            "reporting", "kpi", "visualisation", "statistique", "metier",
        ],
    },
    "Data Scientist": {
        "skills": ["python", "pandas", "numpy", "scikit learn", "machine learning", "deep learning", "nlp"],
        "keywords": [
            "data scientist", "modele", "prediction", "classification", "regression",
            "intelligence artificielle", "feature engineering", "ml", "ia",
        ],
    },
    "Developpeur BI": {
        "skills": ["sql", "power bi", "tableau", "excel", "mysql", "postgresql", "oracle database"],
        "keywords": [
            "bi", "business intelligence", "etl", "data warehouse", "dwh",
            "dax", "reporting", "cube", "decisionnel",
        ],
    },
    "Developpeur Backend": {
        "skills": ["python", "java", "php", "django", "laravel", "fastapi", "node.js", ".net", "sql", "postgresql", "mongodb"],
        "keywords": [
            "backend", "back end", "api", "rest", "microservice", "authentification",
            "serveur", "endpoint", "architecture",
        ],
    },
    "Developpeur Frontend": {
        "skills": ["javascript", "typescript", "react", "bootstrap"],
        "keywords": [
            "frontend", "front end", "interface", "ui", "ux", "html", "css",
            "responsive", "web app",
        ],
    },
    "Developpeur Full Stack": {
        "skills": ["javascript", "typescript", "react", "node.js", "django", "laravel", "fastapi", "sql", "mongodb"],
        "keywords": [
            "full stack", "fullstack", "frontend", "backend", "api", "application web",
            "interface", "base de donnees",
        ],
    },
    "Developpeur Mobile": {
        "skills": ["react native", "java"],
        "keywords": [
            "mobile", "android", "ios", "flutter", "kotlin", "swift", "application mobile",
        ],
    },
    "DevOps / Cloud": {
        "skills": ["docker", "git", "github", "ci/cd"],
        "keywords": [
            "devops", "cloud", "kubernetes", "aws", "azure", "gcp", "linux",
            "deploiement", "pipeline", "infrastructure",
        ],
    },
    "Database / ETL": {
        "skills": ["sql", "mysql", "sqlite", "oracle database", "postgresql", "mongodb", "merise"],
        "keywords": [
            "base de donnees", "database", "etl", "modelisation", "schema",
            "requete", "data warehouse", "migration",
        ],
    },
    "Ingenieur Logiciel": {
        "skills": ["python", "java", "c++", "c#", "git", "uml", "agile", "scrum"],
        "keywords": [
            "software engineer", "ingenieur logiciel", "conception", "poo",
            "architecture", "tests", "qualite", "maintenance",
        ],
    },
}

CV_DOCUMENT_TERMS = [
    "curriculum vitae", "resume", "cv", "profil", "profile", "experience",
    "experiences", "formation", "education", "competences", "skills",
    "projets", "projects", "certifications", "certificats", "langues",
    "languages", "stage", "internship", "mission", "missions", "emploi",
    "work experience", "professional experience", "technologies", "outils",
]

NON_CV_DOCUMENT_TERMS = [
    "facture", "invoice", "bon de commande", "purchase order", "devis",
    "contrat de vente", "conditions generales", "proces verbal",
    "compte rendu", "rapport annuel", "article scientifique", "abstract",
    "chapitre", "table des matieres", "sommaire", "bibliographie",
    "recu", "receipt", "attestation", "certificat medical", "syllabus",
    "powerpoint", "presentation powerpoint", "support de presentation",
    "diapositive", "diapositives", "slide", "slides", "support de cours",
    "cours magistral", "plan du cours", "objectifs du cours",
    "objectif pedagogique", "objectifs pedagogiques", "travaux diriges",
    "travaux pratiques", "exercice", "exercices", "corrige", "corriges",
    "controle continu", "examen final", "module", "enseignant",
    "professeur", "semestre", "seance", "support pedagogique",
]

STRICT_NON_CV_DOCUMENT_TERMS = [
    "powerpoint", "presentation powerpoint", "support de presentation",
    "diapositive", "diapositives", "slide", "slides", "support de cours",
    "cours magistral", "plan du cours", "objectifs du cours",
    "objectif pedagogique", "objectifs pedagogiques", "travaux diriges",
    "travaux pratiques", "support pedagogique", "syllabus",
]

MIN_CV_DOCUMENT_SCORE = 68


def extract_contact_details(text):
    email = re.search(r"[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}", text, re.I)
    phone = re.search(r"(?:\+?\d[\s().-]?){8,16}", text)
    linkedin = re.search(r"(?:https?://)?(?:www\.)?linkedin\.com/[^\s)]+", text, re.I)
    github = re.search(r"(?:https?://)?(?:www\.)?github\.com/[^\s)]+", text, re.I)

    return {
        "Email": email.group(0) if email else "",
        "Telephone": phone.group(0).strip() if phone else "",
        "LinkedIn": linkedin.group(0) if linkedin else "",
        "GitHub": github.group(0) if github else "",
    }


def detect_sections(text):
    normalized = clean_text(text)
    found = []
    missing = []

    for label, pattern in SECTION_PATTERNS.items():
        if re.search(pattern, normalized, re.I):
            found.append(label)
        else:
            missing.append(label)

    return found, missing


def compute_cv_health(word_count, sections_found, contacts, skill_count):
    score = 0
    if word_count >= 250:
        score += 25
    elif word_count >= 120:
        score += 15

    score += min(len(sections_found) * 9, 36)
    score += 18 if any(contacts.values()) else 0
    score += min(skill_count * 3, 21)
    return min(score, 100)


def extract_keywords(text, limit=18):
    words = re.findall(r"[a-zA-Z0-9+#.]{3,}", clean_text(text).lower())
    filtered = [
        word for word in words
        if word not in KEYWORD_STOPWORDS and not word.isdigit()
    ]
    return [word for word, _ in Counter(filtered).most_common(limit)]


def keyword_coverage(offer_text, cv_text):
    offer_keywords = extract_keywords(offer_text)
    clean_cv = clean_text(cv_text).lower()
    matched = [keyword for keyword in offer_keywords if keyword in clean_cv]
    missing = [keyword for keyword in offer_keywords if keyword not in clean_cv]
    score = round((len(matched) / len(offer_keywords)) * 100, 2) if offer_keywords else 0
    return {
        "score": score,
        "matched": matched,
        "missing": missing,
        "total": len(offer_keywords),
    }


def normalize_profile_text(text):
    normalized = unicodedata.normalize("NFKD", (text or "").lower())
    ascii_text = normalized.encode("ascii", "ignore").decode("ascii")
    return re.sub(r"[^a-z0-9+#. ]+", " ", ascii_text)


def unique_limited(items, limit=6):
    unique_items = []
    seen = set()
    for item in items:
        key = item.lower()
        if key in seen:
            continue
        seen.add(key)
        unique_items.append(item)
        if len(unique_items) >= limit:
            break
    return unique_items


def has_normalized_phrase(normalized_text, phrase):
    normalized_phrase = normalize_profile_text(phrase).strip()
    return bool(normalized_phrase and normalized_phrase in normalized_text)


def evaluate_cv_document(text, filename="", cv_skills=None, contacts=None, sections_found=None):
    normalized_text = normalize_profile_text(text)
    normalized_filename = normalize_profile_text(filename)
    combined_text = f"{normalized_filename} {normalized_text}".strip()
    words = re.findall(r"\b[a-z0-9+#.]{2,}\b", normalized_text)
    word_count = len(words)
    contacts = contacts if contacts is not None else extract_contact_details(text)
    sections_found = sections_found if sections_found is not None else detect_sections(text)[0]
    cv_skills = cv_skills if cv_skills is not None else extract_skills(clean_text(text))
    contact_count = sum(1 for value in contacts.values() if value)
    skill_count = len(cv_skills)
    score = 0
    positive_signals = []

    if word_count >= 80:
        score += 12
        positive_signals.append("Longueur compatible CV")
    elif word_count >= 40:
        score += 6
        positive_signals.append("Texte court mais exploitable")

    if contact_count:
        score += 20
        positive_signals.append("Coordonnées détectées")

    if sections_found:
        score += min(len(sections_found) * 10, 45)
        positive_signals.extend([f"Section {section}" for section in sections_found[:4]])

    if skill_count >= 6:
        score += 25
        positive_signals.append("Compétences techniques détectées")
    elif skill_count >= 3:
        score += 16
        positive_signals.append("Plusieurs compétences détectées")
    elif skill_count:
        score += 6
        positive_signals.append("Compétence détectée")

    professional_hits = [
        term for term in CV_DOCUMENT_TERMS
        if has_normalized_phrase(combined_text, term)
    ]
    score += min(len(professional_hits) * 3, 18)
    positive_signals.extend(professional_hits[:5])

    filename_denies_cv = re.search(r"\b(non|not|pas)\s+cv\b", normalized_filename)
    if re.search(r"\b(cv|resume|curriculum)\b", normalized_filename) and not filename_denies_cv:
        score += 8
        positive_signals.append("Nom de fichier oriente CV")

    negative_signals = [
        term for term in NON_CV_DOCUMENT_TERMS
        if has_normalized_phrase(combined_text, term)
    ]
    strict_negative_signals = [
        term for term in STRICT_NON_CV_DOCUMENT_TERMS
        if has_normalized_phrase(combined_text, term)
    ]
    score -= min(len(negative_signals) * 12, 36)
    score -= min(len(strict_negative_signals) * 18, 45)

    if word_count < 35:
        score -= 18
    if not sections_found and contact_count == 0 and skill_count < 2:
        score -= 20

    has_experience_signal = bool(re.search(r"\b(experience|experiences|work history|emploi|mission|missions|stage|stages)\b", normalized_text))
    has_education_signal = bool(re.search(r"\b(formation|education|diplome|degree|universite|ecole|master|licence|bachelor)\b", normalized_text))
    has_skills_signal = bool(re.search(r"\b(competence|competences|skills|technologies|outils|langages|languages)\b", normalized_text)) or skill_count >= 4
    has_contact_signal = contact_count > 0
    has_cv_title_signal = bool(re.search(r"\b(curriculum vitae|resume|cv)\b", combined_text))
    core_section_count = sum([has_experience_signal, has_education_signal, has_skills_signal])
    strict_requirements = {
        "contact": has_contact_signal,
        "experienceOrEducation": has_experience_signal or has_education_signal,
        "skills": has_skills_signal,
        "cvStructure": core_section_count >= 2,
        "minimumLength": word_count >= 80,
    }
    missing_requirements = [
        label for label, passed in {
            "coordonnees visibles": strict_requirements["contact"],
            "experience ou formation": strict_requirements["experienceOrEducation"],
            "competences": strict_requirements["skills"],
            "structure CV": strict_requirements["cvStructure"],
            "contenu suffisant": strict_requirements["minimumLength"],
        }.items()
        if not passed
    ]

    strong_non_cv_context = bool(strict_negative_signals)
    if len(negative_signals) >= 3:
        strong_non_cv_context = True
    if strict_negative_signals:
        score = min(score, 42)

    score = round(max(0, min(score, 100)), 2)
    passes_strict_cv_rules = all(strict_requirements.values()) or (
        has_cv_title_signal
        and has_contact_signal
        and core_section_count >= 2
        and skill_count >= 3
    )
    is_cv = score >= MIN_CV_DOCUMENT_SCORE and passes_strict_cv_rules and not strong_non_cv_context

    return {
        "isCv": is_cv,
        "score": score,
        "threshold": MIN_CV_DOCUMENT_SCORE,
        "wordCount": word_count,
        "sectionsFound": sections_found,
        "contactCount": contact_count,
        "skillCount": skill_count,
        "positiveSignals": unique_limited(positive_signals, 8),
        "negativeSignals": unique_limited(negative_signals, 6),
        "strictNegativeSignals": unique_limited(strict_negative_signals, 6),
        "strictRequirements": strict_requirements,
        "missingRequirements": missing_requirements,
        "documentTypeBlocked": strong_non_cv_context,
    }


def build_cv_rejection_message(document_check):
    signals = document_check.get("positiveSignals", [])
    signal_text = ", ".join(signals[:3]) if signals else "signaux CV insuffisants"
    negative_signals = document_check.get("strictNegativeSignals") or document_check.get("negativeSignals", [])
    missing = document_check.get("missingRequirements", [])
    negative_text = ", ".join(negative_signals[:3])
    missing_text = ", ".join(missing[:4])
    details = []
    if negative_text:
        details.append(f"signaux non-CV detectes : {negative_text}")
    if missing_text:
        details.append(f"elements CV manquants : {missing_text}")
    details.append(f"signaux CV detectes : {signal_text}")
    return (
        "Document refuse : seuls les CV sont acceptes. "
        "Les presentations PowerPoint, supports de cours, rapports, attestations "
        "et documents generiques sont bloques. "
        "Le fichier importe ne ressemble pas assez a un CV "
        f"(confiance {document_check.get('score', 0)}%). "
        "Importez un CV contenant des coordonnees visibles, une experience ou formation "
        "et des competences. "
        + " ; ".join(details)
        + "."
    )
    return (
        "Document refuse : le fichier importe ne semble pas etre un CV "
        f"(confiance {document_check.get('score', 0)}%). "
        "Importez uniquement un CV contenant au minimum des coordonnées, "
        "une expérience/formation et des compétences. "
        f"Signaux détectés : {signal_text}."
    )


def detect_profile_type(cv_text, cv_skills, sections_found):
    normalized_text = normalize_profile_text(cv_text)
    skill_set = {skill.lower() for skill in cv_skills}
    scored_profiles = []

    for label, config in PROFILE_TYPES.items():
        score = 0
        signals = []

        for skill in config["skills"]:
            if skill.lower() in skill_set:
                score += 10
                signals.append(skill)

        for keyword in config["keywords"]:
            keyword_key = normalize_profile_text(keyword).strip()
            if keyword_key and keyword_key in normalized_text:
                score += 4
                signals.append(keyword)

        if "Projets" in sections_found:
            score += 2
        if "Experience" in sections_found:
            score += 2

        confidence_score = min(100, round(score * 2.4, 2))
        scored_profiles.append(
            {
                "label": label,
                "score": confidence_score,
                "rawScore": score,
                "signals": unique_limited(signals),
            }
        )

    scored_profiles.sort(key=lambda item: item["rawScore"], reverse=True)
    best = scored_profiles[0] if scored_profiles else {"rawScore": 0, "score": 0}

    if best["rawScore"] <= 0:
        return {
            "label": "Profil generaliste",
            "score": 0,
            "confidence": "faible",
            "signals": [],
            "alternatives": [],
        }

    confidence = "elevee" if best["rawScore"] >= 35 else "moyenne" if best["rawScore"] >= 18 else "faible"
    alternatives = [
        {
            "label": item["label"],
            "score": item["score"],
            "signals": item["signals"],
        }
        for item in scored_profiles[1:4]
        if item["rawScore"] > 0
    ]

    return {
        "label": best["label"],
        "score": best["score"],
        "confidence": confidence,
        "signals": best["signals"],
        "alternatives": alternatives,
    }


def estimate_experience(text):
    current_year = datetime.now().year
    normalized = clean_text(text).lower()
    years = []

    for match in re.findall(r"(\d{1,2})\s*\+?\s*(?:ans|annees|years?)\s+(?:d experience|experience)", normalized):
        years.append(int(match))

    range_pattern = r"\b(19\d{2}|20\d{2})\s*(?:-|a|to)\s*(19\d{2}|20\d{2}|present|actuel|aujourd hui)\b"
    for start, end in re.findall(range_pattern, normalized):
        start_year = int(start)
        end_year = current_year if not end[:4].isdigit() else int(end[:4])
        if start_year <= end_year <= current_year:
            years.append(min(end_year - start_year, 20))

    detected_years = max(years) if years else 0
    if detected_years >= 6:
        level = "Senior"
    elif detected_years >= 3:
        level = "Intermédiaire"
    elif detected_years >= 1:
        level = "Junior"
    else:
        level = "Non détecté"

    evidence = (
        f"{detected_years} an(s) d'expérience estimée"
        if detected_years
        else "Aucune durée explicite détectée dans le CV"
    )
    return {"level": level, "years": detected_years, "evidence": evidence}


def build_ats_checks(word_count, sections_found, contacts, skill_count, extension, document_check=None):
    document_check = document_check or {}
    checks = [
        {
            "label": "Type de document",
            "status": "ok" if document_check.get("isCv", True) else "warn",
            "detail": (
                f"CV reconnu avec {document_check.get('score', 100)}% de confiance."
                if document_check.get("isCv", True)
                else "Le fichier ne ressemble pas assez a un CV."
            ),
            "weight": 15,
        },
        {
            "label": "Coordonnées",
            "status": "ok" if any(contacts.values()) else "warn",
            "detail": "Email, téléphone ou profil professionnel détecté."
            if any(contacts.values())
            else "Ajoutez au moins un email ou un téléphone visible.",
            "weight": 18,
        },
        {
            "label": "Sections clés",
            "status": "ok" if len(sections_found) >= 4 else "warn",
            "detail": f"{len(sections_found)} section(s) standard détectée(s).",
            "weight": 22,
        },
        {
            "label": "Longueur",
            "status": "ok" if 250 <= word_count <= 950 else "warn",
            "detail": f"{word_count} mots détectés.",
            "weight": 18,
        },
        {
            "label": "Compétences",
            "status": "ok" if skill_count >= 6 else "warn",
            "detail": f"{skill_count} compétence(s) reconnue(s).",
            "weight": 20,
        },
        {
            "label": "Format",
            "status": "ok" if extension in ALLOWED_EXTENSIONS else "warn",
            "detail": f"Format {extension.upper()} compatible avec l'analyse.",
            "weight": 7,
        },
    ]
    total = sum(item["weight"] for item in checks)
    achieved = sum(item["weight"] for item in checks if item["status"] == "ok")
    for item in checks:
        item.pop("weight", None)
    return round((achieved / total) * 100, 2), checks


def build_interview_questions(missing_skills, matched_skills, offer_keywords):
    questions = []
    for skill in missing_skills[:3]:
        questions.append(f"Pouvez-vous expliquer comment vous monteriez rapidement en compétence sur {skill} ?")
    for skill in matched_skills[:2]:
        questions.append(f"Quel projet concret démontre votre niveau sur {skill} ?")
    if offer_keywords:
        questions.append(f"Comment adapteriez-vous votre expérience aux priorités suivantes : {', '.join(offer_keywords[:3])} ?")
    questions.append("Quel résultat mesurable aimeriez-vous livrer pendant les 90 premiers jours ?")
    return questions[:6]


def build_rewrite_suggestions(missing_skills, keyword_gap, sections_missing, contacts):
    suggestions = []
    if missing_skills:
        suggestions.append("Ajouter une ligne Compétences ciblée avec : " + ", ".join(missing_skills[:4]) + ".")
    if keyword_gap["missing"]:
        suggestions.append("Reprendre naturellement ces mots-clés de l'offre : " + ", ".join(keyword_gap["missing"][:5]) + ".")
    if sections_missing:
        suggestions.append("Ajouter ou renommer les sections manquantes : " + ", ".join(sections_missing[:3]) + ".")
    if not any(contacts.values()):
        suggestions.append("Rendre les coordonnées visibles en haut du CV.")
    suggestions.append("Transformer les missions principales en résultats chiffrés quand c'est possible.")
    return suggestions[:5]


def verdict_for(score, threshold):
    if score >= threshold + 10:
        return "Excellent alignement"
    if score >= threshold:
        return "Profil shortlist"
    if score >= 50:
        return "A revoir"
    return "Faible alignement"


def probability_for_class(probability, classes, expected_class):
    for index, class_value in enumerate(classes):
        if str(class_value) == str(expected_class) and index < len(probability):
            return float(probability[index])
    fallback_index = int(expected_class) if str(expected_class).isdigit() else 0
    if fallback_index < len(probability):
        return float(probability[fallback_index])
    return 0.0


def classify_candidate(prediction, probability, classifier_details):
    classes = classifier_details.get("classes") or [0, 1]
    positive_probability = probability_for_class(probability, classes, 1)
    negative_probability = probability_for_class(probability, classes, 0)
    prediction_value = int(prediction)
    is_positive = prediction_value == 1
    confidence = positive_probability if is_positive else negative_probability
    confidence_percent = round(max(0, min(confidence * 100, 100)), 2)
    positive_percent = round(max(0, min(positive_probability * 100, 100)), 2)
    negative_percent = round(max(0, min(negative_probability * 100, 100)), 2)

    if is_positive:
        label = "Bon profil"
        tone = "good"
        decision = "positive"
    else:
        label = "Profil faible"
        tone = "bad"
        decision = "negative"

    if classifier_details.get("ready"):
        detail = (
            f"Décision binaire {decision} par Random Forest "
            f"avec {confidence_percent}% de confiance."
        )
    else:
        detail = (
            "Modèle Random Forest indisponible, decision binaire produite par "
            "un fallback local."
        )

    return {
        "label": label,
        "score": confidence_percent,
        "tone": tone,
        "detail": detail,
        "prediction": prediction_value,
        "positiveProbability": positive_percent,
        "negativeProbability": negative_percent,
        "model": classifier_details.get("model", "RandomForestClassifier"),
        "engine": classifier_details.get("engine", "Random Forest"),
        "classes": classes,
    }


def build_actions(missing_skills, missing_sections, final_score, semantic_score):
    actions = []
    if missing_skills:
        actions.append("Ajouter ou clarifier ces compétences : " + ", ".join(missing_skills[:5]) + ".")
    if missing_sections:
        actions.append("Renforcer les sections : " + ", ".join(missing_sections[:3]) + ".")
    if semantic_score < 55:
        actions.append("Adapter le vocabulaire du CV aux mots-clés de l'offre.")
    if final_score < 70:
        actions.append("Quantifier les realisations avec contexte, action et resultat.")
    actions.append("Ajouter un titre de CV aligne avec le poste vise.")
    return actions[:5]


def extract_text(file_path):
    extension = file_path.suffix.lower()
    if extension == ".pdf":
        return extract_pdf_text(str(file_path))
    if extension == ".docx":
        return extract_docx_text(str(file_path))
    if extension == ".txt":
        return file_path.read_text(encoding="utf-8", errors="ignore")
    raise ValueError("Format non supporte. Utilisez PDF, DOCX ou TXT.")


def analyze_resume(offer_text, file_path, original_name, skill_weight, threshold):
    started_at = time.perf_counter()
    cv_text = extract_text(file_path)
    if not cv_text.strip():
        raise ValueError("Aucun texte lisible détecté dans le CV.")

    clean_cv = clean_text(cv_text)
    clean_offer = clean_text(offer_text)
    cv_skills = extract_skills(clean_cv)
    contacts = extract_contact_details(cv_text)
    sections_found, sections_missing = detect_sections(cv_text)
    document_check = evaluate_cv_document(
        cv_text,
        original_name,
        cv_skills=cv_skills,
        contacts=contacts,
        sections_found=sections_found,
    )
    if not document_check["isCv"]:
        raise ValueError(build_cv_rejection_message(document_check))

    offer_skills = extract_skills(clean_offer)
    result = compare_skills(cv_skills, offer_skills)
    semantic_score = semantic_similarity(clean_cv[:6000], clean_offer[:6000])
    skill_score = result["score"]
    final_score = round(
        (skill_score * (skill_weight / 100))
        + (semantic_score * ((100 - skill_weight) / 100)),
        2,
    )

    prediction, probability, classifier_details = predict_candidate(
        skill_score,
        semantic_score,
        len(result["matched_skills"]),
        len(result["missing_skills"]),
    )
    profile_type = detect_profile_type(cv_text, cv_skills, sections_found)
    word_count = len(re.findall(r"\w+", cv_text))
    health_score = compute_cv_health(word_count, sections_found, contacts, len(cv_skills))
    ats_score, ats_checks = build_ats_checks(
        word_count,
        sections_found,
        contacts,
        len(cv_skills),
        file_path.suffix.lower(),
        document_check,
    )
    keyword_gap = keyword_coverage(offer_text, cv_text)
    experience = estimate_experience(cv_text)
    classification = classify_candidate(prediction, probability, classifier_details)
    verdict = verdict_for(final_score, threshold)
    actions = build_actions(result["missing_skills"], sections_missing, final_score, semantic_score)
    interview_questions = build_interview_questions(
        result["missing_skills"],
        result["matched_skills"],
        keyword_gap["matched"] or keyword_gap["missing"],
    )
    rewrite_suggestions = build_rewrite_suggestions(
        result["missing_skills"],
        keyword_gap,
        sections_missing,
        contacts,
    )

    insights = {
        "verdict": verdict,
        "threshold": threshold,
        "skill_weight": skill_weight,
        "semantic_weight": 100 - skill_weight,
        "cv_health": health_score,
        "word_count": word_count,
        "contacts": contacts,
        "sections_found": sections_found,
        "sections_missing": sections_missing,
        "profile_type": profile_type,
        "document_check": document_check,
        "classification": classification,
        "actions": actions,
        "ats_score": ats_score,
        "keyword_coverage": keyword_gap,
        "experience": experience,
        "interview_questions": interview_questions,
        "rewrite_suggestions": rewrite_suggestions,
        "uploaded_name": original_name,
    }
    report = generate_report(result, semantic_score, final_score, insights)
    semantic_model = load_model()
    classifier_model = load_classifier()
    classifier_ready = bool(classifier_details.get("ready")) and classifier_model is not None
    processing_time_ms = round((time.perf_counter() - started_at) * 1000)
    ai_engines = {
        "semantic": (
            "SentenceTransformer all-MiniLM-L6-v2"
            if semantic_model is not None
            else "Fallback lexical rapide"
        ),
        "classifier": (
            "RandomForestClassifier local"
            if classifier_ready
            else "Fallback local sans modele Random Forest"
        ),
        "semanticReady": semantic_model is not None,
        "classifierReady": classifier_ready,
    }

    return {
        "fileName": original_name,
        "cvText": cv_text,
        "offerSkills": offer_skills,
        "cvSkills": cv_skills,
        "matchedSkills": result["matched_skills"],
        "missingSkills": result["missing_skills"],
        "skillScore": skill_score,
        "semanticScore": semantic_score,
        "skillWeight": skill_weight,
        "threshold": threshold,
        "finalScore": final_score,
        "contacts": contacts,
        "sections": {"found": sections_found, "missing": sections_missing},
        "profileType": profile_type,
        "documentCheck": document_check,
        "classification": classification,
        "wordCount": word_count,
        "healthScore": health_score,
        "atsScore": ats_score,
        "atsChecks": ats_checks,
        "keywordCoverage": keyword_gap,
        "experience": experience,
        "interviewQuestions": interview_questions,
        "rewriteSuggestions": rewrite_suggestions,
        "verdict": verdict,
        "actions": actions,
        "prediction": int(prediction),
        "probability": [float(value) for value in probability],
        "classifierDetails": classifier_details,
        "aiEngines": ai_engines,
        "processingTimeMs": processing_time_ms,
        "report": report,
    }


def secure_filename(filename):
    clean_name = Path(filename or "cv").name
    clean_name = re.sub(r"[^A-Za-z0-9_.-]+", "_", clean_name).strip("._")
    return clean_name[:140] or "cv"


def parse_int(value, default):
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def parse_multipart_form(headers, body):
    content_type = headers.get("Content-Type", "")
    if "multipart/form-data" not in content_type:
        raise ValueError("Requete multipart/form-data attendue.")

    raw_message = (
        f"Content-Type: {content_type}\r\nMIME-Version: 1.0\r\n\r\n".encode("utf-8")
        + body
    )
    message = BytesParser(policy=default).parsebytes(raw_message)
    if not message.is_multipart():
        raise ValueError("Formulaire invalide.")

    fields = {}
    files = {}
    for part in message.iter_parts():
        if part.get_content_disposition() != "form-data":
            continue

        name = part.get_param("name", header="content-disposition")
        if not name:
            continue

        payload = part.get_payload(decode=True) or b""
        filename = part.get_filename()
        if filename:
            entry = {"filename": filename, "content": payload}
            if name in files:
                if isinstance(files[name], list):
                    files[name].append(entry)
                else:
                    files[name] = [files[name], entry]
            else:
                files[name] = entry
            continue

        charset = part.get_content_charset() or "utf-8"
        fields[name] = payload.decode(charset, errors="ignore")

    return fields, files


def collect_uploaded_files(files, *field_names):
    collected = []
    for field_name in field_names:
        value = files.get(field_name)
        if not value:
            continue
        if isinstance(value, list):
            collected.extend(value)
        else:
            collected.append(value)
    return collected


def connect_history_db():
    HISTORY_DIR.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(HISTORY_DB)
    connection.row_factory = sqlite3.Row
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS analyses (
            id TEXT PRIMARY KEY,
            created_at TEXT NOT NULL,
            cv_filename TEXT NOT NULL,
            profile_type TEXT NOT NULL,
            verdict TEXT NOT NULL,
            final_score REAL NOT NULL,
            skill_score REAL NOT NULL,
            semantic_score REAL NOT NULL,
            ats_score REAL NOT NULL,
            keyword_score REAL NOT NULL,
            word_count INTEGER NOT NULL,
            summary_json TEXT NOT NULL,
            report_markdown TEXT NOT NULL
        )
        """
    )
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS candidate_tracking (
            analysis_id TEXT PRIMARY KEY,
            stage TEXT NOT NULL DEFAULT 'selection',
            notes TEXT NOT NULL DEFAULT '',
            updated_at TEXT NOT NULL,
            FOREIGN KEY(analysis_id) REFERENCES analyses(id) ON DELETE CASCADE
        )
        """
    )
    return connection


def save_analysis_history(analysis):
    history_id = f"{datetime.now().strftime('%Y%m%d%H%M%S')}-{uuid.uuid4().hex[:8]}"
    created_at = datetime.now().isoformat(timespec="seconds")
    profile_type = analysis.get("profileType") or {}
    keyword_coverage_data = analysis.get("keywordCoverage") or {}
    summary = {
        "matchedSkills": analysis.get("matchedSkills", [])[:12],
        "missingSkills": analysis.get("missingSkills", [])[:12],
        "actions": analysis.get("actions", [])[:5],
        "profileType": profile_type,
        "documentCheck": analysis.get("documentCheck", {}),
        "classification": analysis.get("classification", {}),
        "prediction": analysis.get("prediction", 0),
        "probability": analysis.get("probability", []),
        "classifierDetails": analysis.get("classifierDetails", {}),
        "experience": analysis.get("experience", {}),
        "sections": analysis.get("sections", {}),
        "keywordCoverage": keyword_coverage_data,
        "contacts": analysis.get("contacts", {}),
        "atsChecks": analysis.get("atsChecks", []),
        "interviewQuestions": analysis.get("interviewQuestions", []),
        "rewriteSuggestions": analysis.get("rewriteSuggestions", []),
        "aiEngines": analysis.get("aiEngines", {}),
        "processingTimeMs": analysis.get("processingTimeMs", 0),
        "cvSkills": analysis.get("cvSkills", [])[:24],
        "offerSkills": analysis.get("offerSkills", [])[:24],
        "threshold": analysis.get("threshold", 70),
        "skillWeight": analysis.get("skillWeight", 60),
    }

    connection = connect_history_db()
    try:
        connection.execute(
            """
            INSERT INTO analyses (
                id, created_at, cv_filename, profile_type, verdict, final_score,
                skill_score, semantic_score, ats_score, keyword_score, word_count,
                summary_json, report_markdown
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                history_id,
                created_at,
                analysis.get("fileName", "CV analyse"),
                profile_type.get("label", "Profil generaliste"),
                analysis.get("verdict", "Analyse terminee"),
                float(analysis.get("finalScore", 0)),
                float(analysis.get("skillScore", 0)),
                float(analysis.get("semanticScore", 0)),
                float(analysis.get("atsScore", 0)),
                float(keyword_coverage_data.get("score", 0)),
                int(analysis.get("wordCount", 0)),
                json.dumps(summary, ensure_ascii=False),
                analysis.get("report", ""),
            ),
        )
        connection.commit()
    finally:
        connection.close()

    analysis["historyId"] = history_id
    analysis["createdAt"] = created_at
    return history_id


def list_analysis_history(limit=30, include_report=False):
    connection = connect_history_db()
    try:
        report_column = ", report_markdown" if include_report else ""
        rows = connection.execute(
            f"""
            SELECT id, created_at, cv_filename, profile_type, verdict, final_score,
                   skill_score, semantic_score, ats_score, keyword_score, word_count,
                   summary_json{report_column}
            FROM analyses
            ORDER BY datetime(created_at) DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()
    finally:
        connection.close()

    items = []
    for row in rows:
        try:
            summary = json.loads(row["summary_json"] or "{}")
        except json.JSONDecodeError:
            summary = {}
        items.append(
            {
                "id": row["id"],
                "createdAt": row["created_at"],
                "fileName": row["cv_filename"],
                "profileType": row["profile_type"],
                "verdict": row["verdict"],
                "finalScore": row["final_score"],
                "skillScore": row["skill_score"],
                "semanticScore": row["semantic_score"],
                "atsScore": row["ats_score"],
                "keywordScore": row["keyword_score"],
                "wordCount": row["word_count"],
                "summary": summary,
            }
        )
        if include_report:
            items[-1]["reportMarkdown"] = row["report_markdown"]
    return items


def get_latest_analysis():
    items = list_analysis_history(limit=1, include_report=True)
    return items[0] if items else None


def normalize_tracking_stage(stage):
    stage = str(stage or "selection").strip().lower()
    return stage if stage in TRACKING_STAGE_IDS else "selection"


def is_tracking_candidate(item):
    summary = item.get("summary") or {}
    classification = summary.get("classification") or {}
    label = str(classification.get("label", "")).strip().lower()
    if label == "bon profil":
        return True

    prediction = classification.get("prediction", summary.get("prediction"))
    try:
        if int(prediction) == 1:
            return True
    except (TypeError, ValueError):
        pass

    try:
        final_score = float(item.get("finalScore", 0))
        threshold = float(summary.get("threshold", 70))
        return final_score >= threshold
    except (TypeError, ValueError):
        return False


def fetch_tracking_rows(analysis_ids):
    if not analysis_ids:
        return {}

    placeholders = ", ".join("?" for _ in analysis_ids)
    connection = connect_history_db()
    try:
        rows = connection.execute(
            f"""
            SELECT analysis_id, stage, notes, updated_at
            FROM candidate_tracking
            WHERE analysis_id IN ({placeholders})
            """,
            analysis_ids,
        ).fetchall()
    finally:
        connection.close()

    return {
        row["analysis_id"]: {
            "stage": normalize_tracking_stage(row["stage"]),
            "notes": row["notes"] or "",
            "updatedAt": row["updated_at"],
        }
        for row in rows
    }


def list_candidate_tracking(limit=80):
    history_items = [item for item in list_analysis_history(limit=limit) if is_tracking_candidate(item)]
    tracking_rows = fetch_tracking_rows([item["id"] for item in history_items])
    stage_counts = {stage["id"]: 0 for stage in TRACKING_STAGES}

    items = []
    for item in history_items:
        tracking = tracking_rows.get(
            item["id"],
            {"stage": "selection", "notes": "", "updatedAt": item["createdAt"]},
        )
        tracking["stage"] = normalize_tracking_stage(tracking.get("stage"))
        stage_counts[tracking["stage"]] = stage_counts.get(tracking["stage"], 0) + 1
        item["tracking"] = tracking
        items.append(item)

    return {
        "stages": TRACKING_STAGES,
        "counts": stage_counts,
        "items": items,
    }


def update_candidate_tracking(analysis_id, stage, notes):
    analysis_id = str(analysis_id or "").strip()
    if not analysis_id:
        return None

    connection = connect_history_db()
    try:
        row = connection.execute(
            "SELECT id FROM analyses WHERE id = ?",
            (analysis_id,),
        ).fetchone()
        if row is None:
            return None

        updated_at = datetime.now().isoformat(timespec="seconds")
        connection.execute(
            """
            INSERT INTO candidate_tracking (analysis_id, stage, notes, updated_at)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(analysis_id) DO UPDATE SET
                stage = excluded.stage,
                notes = excluded.notes,
                updated_at = excluded.updated_at
            """,
            (analysis_id, normalize_tracking_stage(stage), str(notes or "")[:600], updated_at),
        )
        connection.commit()
    finally:
        connection.close()

    return list_candidate_tracking()


class ResumeAnalyzerHandler(BaseHTTPRequestHandler):
    server_version = "ArchiteoRecruit/1.0"

    def do_GET(self):
        parsed_url = urlsplit(self.path)
        path = unquote(parsed_url.path)
        query = parse_qs(parsed_url.query)
        if path == "/api/history":
            self.send_json({"items": list_analysis_history()})
            return
        if path == "/api/tracking":
            self.send_json(list_candidate_tracking())
            return
        if path == "/api/analysis/latest":
            self.send_json({"analysis": get_latest_analysis()})
            return
        if path == "/api/rag/cvs":
            self.send_json(list_indexed_cvs())
            return
        if path in {"/", "/index.html"}:
            self.send_static_file(BASE_DIR / "index.html", "text/html; charset=utf-8")
            return
        if path in {"/app", "/app.html"}:
            if query.get("start", ["0"])[0] != "1":
                self.send_redirect("/")
                return
            self.send_static_file(BASE_DIR / "app.html", "text/html; charset=utf-8")
            return
        if path in {"/history", "/history.html"}:
            self.send_static_file(BASE_DIR / "history.html", "text/html; charset=utf-8")
            return
        if path in {"/tracking", "/tracking.html"}:
            self.send_static_file(BASE_DIR / "tracking.html", "text/html; charset=utf-8")
            return
        if path in {"/skills", "/skills.html"}:
            self.send_static_file(BASE_DIR / "skills.html", "text/html; charset=utf-8")
            return
        if path in {"/insights", "/insights.html"}:
            self.send_static_file(BASE_DIR / "insights.html", "text/html; charset=utf-8")
            return
        if path in {"/diagnostic", "/diagnostic.html"}:
            self.send_static_file(BASE_DIR / "diagnostic.html", "text/html; charset=utf-8")
            return
        if path in {"/report", "/report.html"}:
            self.send_static_file(BASE_DIR / "report.html", "text/html; charset=utf-8")
            return
        if path == "/styles.css":
            self.send_static_file(BASE_DIR / "styles.css", "text/css; charset=utf-8")
            return
        if path == "/script.js":
            self.send_static_file(BASE_DIR / "script.js", "application/javascript; charset=utf-8")
            return
        if path == "/history.js":
            self.send_static_file(BASE_DIR / "history.js", "application/javascript; charset=utf-8")
            return
        if path == "/theme-toggle.js":
            self.send_static_file(BASE_DIR / "theme-toggle.js", "application/javascript; charset=utf-8")
            return
        if path == "/tracking.js":
            self.send_static_file(BASE_DIR / "tracking.js", "application/javascript; charset=utf-8")
            return
        if path == "/analysis-pages.js":
            self.send_static_file(BASE_DIR / "analysis-pages.js", "application/javascript; charset=utf-8")
            return
        if path == "/rag-widget.js":
            self.send_static_file(BASE_DIR / "rag-widget.js", "application/javascript; charset=utf-8")
            return
        if path.startswith("/assets/"):
            asset_path = (BASE_DIR / path.lstrip("/")).resolve()
            assets_root = (BASE_DIR / "assets").resolve()
            asset_types = {
                ".svg": "image/svg+xml; charset=utf-8",
                ".jpg": "image/jpeg",
                ".jpeg": "image/jpeg",
                ".png": "image/png",
                ".webp": "image/webp",
            }
            content_type = asset_types.get(asset_path.suffix.lower())
            if assets_root in asset_path.parents and content_type:
                self.send_static_file(asset_path, content_type)
                return
        self.send_json({"error": "Not found"}, HTTPStatus.NOT_FOUND)

    def do_POST(self):
        path = unquote(self.path.split("?", 1)[0])
        if path == "/api/analyze":
            self.handle_analyze()
            return
        if path == "/api/rag/upload":
            self.handle_rag_upload()
            return
        if path == "/api/rag/chat":
            self.handle_rag_chat()
            return
        if path == "/api/tracking":
            self.handle_tracking_update()
            return
        self.send_json({"error": "Not found"}, HTTPStatus.NOT_FOUND)

    def send_static_file(self, file_path, content_type):
        if not file_path.exists():
            self.send_json({"error": "Not found"}, HTTPStatus.NOT_FOUND)
            return

        content = file_path.read_bytes()
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(content)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(content)

    def send_redirect(self, location):
        self.send_response(HTTPStatus.FOUND)
        self.send_header("Location", location)
        self.send_header("Cache-Control", "no-store")
        self.end_headers()

    def send_json(self, payload, status=HTTPStatus.OK):
        content = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(content)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(content)

    def handle_analyze(self):
        content_length = parse_int(self.headers.get("Content-Length"), 0)
        if content_length <= 0:
            self.send_json({"error": "Requete vide."}, HTTPStatus.BAD_REQUEST)
            return

        try:
            body = self.rfile.read(content_length)
            fields, files = parse_multipart_form(self.headers, body)
            offer_text = fields.get("offer_text", "").strip()
            if not offer_text:
                self.send_json({"error": "Veuillez coller une offre d'emploi."}, HTTPStatus.BAD_REQUEST)
                return

            uploaded_items = collect_uploaded_files(files, "cv_file")
            uploaded = uploaded_items[0] if uploaded_items else None
            if not uploaded or not uploaded["filename"]:
                self.send_json({"error": "Veuillez importer un CV PDF, DOCX ou TXT."}, HTTPStatus.BAD_REQUEST)
                return

            skill_weight = parse_int(fields.get("skill_weight"), 60)
            threshold = parse_int(fields.get("threshold"), 70)
            original_name = secure_filename(uploaded["filename"])
            extension = Path(original_name).suffix.lower()
            if extension not in ALLOWED_EXTENSIONS:
                self.send_json({"error": "Format non supporte. Utilisez PDF, DOCX ou TXT."}, HTTPStatus.BAD_REQUEST)
                return

            UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
            with tempfile.NamedTemporaryFile(delete=False, suffix=extension, dir=UPLOAD_DIR) as temp_file:
                temp_path = Path(temp_file.name)
                temp_file.write(uploaded["content"])

            try:
                try:
                    analysis = analyze_resume(offer_text, temp_path, original_name, skill_weight, threshold)
                except ValueError as validation_exc:
                    self.send_json({"error": str(validation_exc)}, HTTPStatus.BAD_REQUEST)
                    return
                try:
                    indexed_cv = add_cv_to_vector_db(analysis["cvText"], original_name)
                    analysis["ragIndex"] = {
                        "indexed": True,
                        "item": indexed_cv,
                        "library": list_indexed_cvs(),
                    }
                except Exception as rag_exc:
                    analysis["ragIndex"] = {
                        "indexed": False,
                        "error": str(rag_exc),
                        "library": list_indexed_cvs(),
                    }
                try:
                    save_analysis_history(analysis)
                except Exception as history_exc:
                    analysis["historyError"] = str(history_exc)
                self.send_json(analysis)
            finally:
                try:
                    temp_path.unlink(missing_ok=True)
                except OSError:
                    pass
        except Exception as exc:
            self.send_json({"error": f"Analyse impossible : {exc}"}, HTTPStatus.INTERNAL_SERVER_ERROR)

    def handle_rag_upload(self):
        content_length = parse_int(self.headers.get("Content-Length"), 0)
        if content_length <= 0:
            self.send_json({"error": "Requete vide."}, HTTPStatus.BAD_REQUEST)
            return

        try:
            body = self.rfile.read(content_length)
            _, files = parse_multipart_form(self.headers, body)
            uploaded_files = collect_uploaded_files(files, "cv_files", "cv_files[]", "rag_files", "cv_file")
            if not uploaded_files:
                self.send_json({"error": "Importez au moins un CV PDF, DOCX ou TXT."}, HTTPStatus.BAD_REQUEST)
                return

            indexed = []
            errors = []
            UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

            for uploaded in uploaded_files:
                original_name = secure_filename(uploaded["filename"])
                extension = Path(original_name).suffix.lower()
                if extension not in ALLOWED_EXTENSIONS:
                    errors.append({"filename": original_name, "error": "Format non supporte."})
                    continue

                with tempfile.NamedTemporaryFile(delete=False, suffix=extension, dir=UPLOAD_DIR) as temp_file:
                    temp_path = Path(temp_file.name)
                    temp_file.write(uploaded["content"])

                try:
                    cv_text = extract_text(temp_path)
                    document_check = evaluate_cv_document(cv_text, original_name)
                    if not document_check["isCv"]:
                        errors.append(
                            {
                                "filename": original_name,
                                "error": build_cv_rejection_message(document_check),
                                "documentCheck": document_check,
                            }
                        )
                        continue
                    indexed.append(add_cv_to_vector_db(cv_text, original_name))
                except Exception as exc:
                    errors.append({"filename": original_name, "error": str(exc)})
                finally:
                    try:
                        temp_path.unlink(missing_ok=True)
                    except OSError:
                        pass

            self.send_json(
                {
                    "indexed": indexed,
                    "errors": errors,
                    "library": list_indexed_cvs(),
                },
                HTTPStatus.OK if indexed else HTTPStatus.BAD_REQUEST,
            )
        except Exception as exc:
            self.send_json({"error": f"Indexation RAG impossible : {exc}"}, HTTPStatus.INTERNAL_SERVER_ERROR)

    def handle_rag_chat(self):
        content_length = parse_int(self.headers.get("Content-Length"), 0)
        if content_length <= 0:
            self.send_json({"error": "Question vide."}, HTTPStatus.BAD_REQUEST)
            return

        try:
            body = self.rfile.read(content_length)
            payload = json.loads(body.decode("utf-8"))
            question = payload.get("question", "").strip()
            top_k = parse_int(payload.get("topK"), 5)
            if not question:
                self.send_json({"error": "Posez une question au chatbot."}, HTTPStatus.BAD_REQUEST)
                return

            self.send_json(generate_chatbot_answer(question, top_k=top_k))
        except json.JSONDecodeError:
            self.send_json({"error": "JSON invalide."}, HTTPStatus.BAD_REQUEST)
        except Exception as exc:
            self.send_json({"error": f"Chatbot RAG indisponible : {exc}"}, HTTPStatus.INTERNAL_SERVER_ERROR)

    def handle_tracking_update(self):
        content_length = parse_int(self.headers.get("Content-Length"), 0)
        if content_length <= 0:
            self.send_json({"error": "Requete vide."}, HTTPStatus.BAD_REQUEST)
            return

        try:
            body = self.rfile.read(content_length)
            payload = json.loads(body.decode("utf-8"))
            analysis_id = payload.get("analysisId") or payload.get("id")
            stage = str(payload.get("stage", "")).strip().lower()
            notes = str(payload.get("notes", "")).strip()

            if stage not in TRACKING_STAGE_IDS:
                self.send_json({"error": "Etape de suivi invalide."}, HTTPStatus.BAD_REQUEST)
                return

            tracking = update_candidate_tracking(analysis_id, stage, notes)
            if tracking is None:
                self.send_json({"error": "Analyse introuvable."}, HTTPStatus.NOT_FOUND)
                return

            self.send_json(tracking)
        except json.JSONDecodeError:
            self.send_json({"error": "JSON invalide."}, HTTPStatus.BAD_REQUEST)
        except Exception as exc:
            self.send_json({"error": f"Suivi indisponible : {exc}"}, HTTPStatus.INTERNAL_SERVER_ERROR)

    def log_message(self, format, *args):
        print(f"{self.address_string()} - {format % args}")


def wsgi_status_line(status):
    status_code = int(status)
    try:
        phrase = HTTPStatus(status_code).phrase
    except ValueError:
        phrase = "OK"
    return f"{status_code} {phrase}"


def wsgi_send(start_response, content, status=HTTPStatus.OK, content_type="text/plain; charset=utf-8", headers=None):
    body = content.encode("utf-8") if isinstance(content, str) else content
    response_headers = [
        ("Content-Type", content_type),
        ("Content-Length", str(len(body))),
        ("Cache-Control", "no-store"),
    ]
    if headers:
        response_headers.extend(headers)
    start_response(wsgi_status_line(status), response_headers)
    return [body]


def wsgi_json(start_response, payload, status=HTTPStatus.OK):
    content = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    return wsgi_send(start_response, content, status, "application/json; charset=utf-8")


def wsgi_static(start_response, file_path, content_type):
    if not file_path.exists():
        return wsgi_json(start_response, {"error": "Not found"}, HTTPStatus.NOT_FOUND)
    return wsgi_send(start_response, file_path.read_bytes(), HTTPStatus.OK, content_type)


def wsgi_redirect(start_response, location):
    return wsgi_send(
        start_response,
        b"",
        HTTPStatus.FOUND,
        "text/plain; charset=utf-8",
        [("Location", location)],
    )


def wsgi_headers(environ):
    headers = {}
    if environ.get("CONTENT_TYPE"):
        headers["Content-Type"] = environ["CONTENT_TYPE"]
    if environ.get("CONTENT_LENGTH"):
        headers["Content-Length"] = environ["CONTENT_LENGTH"]
    return headers


def wsgi_body(environ):
    content_length = parse_int(environ.get("CONTENT_LENGTH"), 0)
    if content_length <= 0:
        return content_length, b""
    return content_length, environ["wsgi.input"].read(content_length)


class ResumeAnalyzerWSGIApp:
    def __call__(self, environ, start_response):
        method = environ.get("REQUEST_METHOD", "GET").upper()
        path = unquote(environ.get("PATH_INFO") or "/")
        query = parse_qs(environ.get("QUERY_STRING", ""))

        try:
            if method == "GET":
                return self.handle_get(path, query, start_response)
            if method == "POST":
                return self.handle_post(path, environ, start_response)
            return wsgi_json(start_response, {"error": "Method not allowed"}, HTTPStatus.METHOD_NOT_ALLOWED)
        except Exception as exc:
            return wsgi_json(start_response, {"error": f"Erreur serveur : {exc}"}, HTTPStatus.INTERNAL_SERVER_ERROR)

    def handle_get(self, path, query, start_response):
        if path == "/api/history":
            return wsgi_json(start_response, {"items": list_analysis_history()})
        if path == "/api/tracking":
            return wsgi_json(start_response, list_candidate_tracking())
        if path == "/api/analysis/latest":
            return wsgi_json(start_response, {"analysis": get_latest_analysis()})
        if path == "/api/rag/cvs":
            return wsgi_json(start_response, list_indexed_cvs())
        if path in {"/", "/index.html"}:
            return wsgi_static(start_response, BASE_DIR / "index.html", "text/html; charset=utf-8")
        if path in {"/app", "/app.html"}:
            if query.get("start", ["0"])[0] != "1":
                return wsgi_redirect(start_response, "/")
            return wsgi_static(start_response, BASE_DIR / "app.html", "text/html; charset=utf-8")
        if path in {"/history", "/history.html"}:
            return wsgi_static(start_response, BASE_DIR / "history.html", "text/html; charset=utf-8")
        if path in {"/tracking", "/tracking.html"}:
            return wsgi_static(start_response, BASE_DIR / "tracking.html", "text/html; charset=utf-8")
        if path in {"/skills", "/skills.html"}:
            return wsgi_static(start_response, BASE_DIR / "skills.html", "text/html; charset=utf-8")
        if path in {"/insights", "/insights.html"}:
            return wsgi_static(start_response, BASE_DIR / "insights.html", "text/html; charset=utf-8")
        if path in {"/diagnostic", "/diagnostic.html"}:
            return wsgi_static(start_response, BASE_DIR / "diagnostic.html", "text/html; charset=utf-8")
        if path in {"/report", "/report.html"}:
            return wsgi_static(start_response, BASE_DIR / "report.html", "text/html; charset=utf-8")
        if path == "/styles.css":
            return wsgi_static(start_response, BASE_DIR / "styles.css", "text/css; charset=utf-8")
        if path == "/script.js":
            return wsgi_static(start_response, BASE_DIR / "script.js", "application/javascript; charset=utf-8")
        if path == "/history.js":
            return wsgi_static(start_response, BASE_DIR / "history.js", "application/javascript; charset=utf-8")
        if path == "/theme-toggle.js":
            return wsgi_static(start_response, BASE_DIR / "theme-toggle.js", "application/javascript; charset=utf-8")
        if path == "/tracking.js":
            return wsgi_static(start_response, BASE_DIR / "tracking.js", "application/javascript; charset=utf-8")
        if path == "/analysis-pages.js":
            return wsgi_static(start_response, BASE_DIR / "analysis-pages.js", "application/javascript; charset=utf-8")
        if path == "/rag-widget.js":
            return wsgi_static(start_response, BASE_DIR / "rag-widget.js", "application/javascript; charset=utf-8")
        if path.startswith("/assets/"):
            asset_path = (BASE_DIR / path.lstrip("/")).resolve()
            assets_root = (BASE_DIR / "assets").resolve()
            asset_types = {
                ".svg": "image/svg+xml; charset=utf-8",
                ".jpg": "image/jpeg",
                ".jpeg": "image/jpeg",
                ".png": "image/png",
                ".webp": "image/webp",
            }
            content_type = asset_types.get(asset_path.suffix.lower())
            if assets_root in asset_path.parents and content_type:
                return wsgi_static(start_response, asset_path, content_type)
        return wsgi_json(start_response, {"error": "Not found"}, HTTPStatus.NOT_FOUND)

    def handle_post(self, path, environ, start_response):
        if path == "/api/analyze":
            return self.handle_analyze(environ, start_response)
        if path == "/api/rag/upload":
            return self.handle_rag_upload(environ, start_response)
        if path == "/api/rag/chat":
            return self.handle_rag_chat(environ, start_response)
        if path == "/api/tracking":
            return self.handle_tracking_update(environ, start_response)
        return wsgi_json(start_response, {"error": "Not found"}, HTTPStatus.NOT_FOUND)

    def handle_analyze(self, environ, start_response):
        content_length, body = wsgi_body(environ)
        if content_length <= 0:
            return wsgi_json(start_response, {"error": "Requete vide."}, HTTPStatus.BAD_REQUEST)

        temp_path = None
        try:
            fields, files = parse_multipart_form(wsgi_headers(environ), body)
            offer_text = fields.get("offer_text", "").strip()
            if not offer_text:
                return wsgi_json(start_response, {"error": "Veuillez coller une offre d'emploi."}, HTTPStatus.BAD_REQUEST)

            uploaded_items = collect_uploaded_files(files, "cv_file")
            uploaded = uploaded_items[0] if uploaded_items else None
            if not uploaded or not uploaded["filename"]:
                return wsgi_json(start_response, {"error": "Veuillez importer un CV PDF, DOCX ou TXT."}, HTTPStatus.BAD_REQUEST)

            skill_weight = parse_int(fields.get("skill_weight"), 60)
            threshold = parse_int(fields.get("threshold"), 70)
            original_name = secure_filename(uploaded["filename"])
            extension = Path(original_name).suffix.lower()
            if extension not in ALLOWED_EXTENSIONS:
                return wsgi_json(start_response, {"error": "Format non supporte. Utilisez PDF, DOCX ou TXT."}, HTTPStatus.BAD_REQUEST)

            UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
            with tempfile.NamedTemporaryFile(delete=False, suffix=extension, dir=UPLOAD_DIR) as temp_file:
                temp_path = Path(temp_file.name)
                temp_file.write(uploaded["content"])

            try:
                analysis = analyze_resume(offer_text, temp_path, original_name, skill_weight, threshold)
            except ValueError as validation_exc:
                return wsgi_json(start_response, {"error": str(validation_exc)}, HTTPStatus.BAD_REQUEST)

            try:
                indexed_cv = add_cv_to_vector_db(analysis["cvText"], original_name)
                analysis["ragIndex"] = {
                    "indexed": True,
                    "item": indexed_cv,
                    "library": list_indexed_cvs(),
                }
            except Exception as rag_exc:
                analysis["ragIndex"] = {
                    "indexed": False,
                    "error": str(rag_exc),
                    "library": list_indexed_cvs(),
                }
            try:
                save_analysis_history(analysis)
            except Exception as history_exc:
                analysis["historyError"] = str(history_exc)
            return wsgi_json(start_response, analysis)
        except Exception as exc:
            return wsgi_json(start_response, {"error": f"Analyse impossible : {exc}"}, HTTPStatus.INTERNAL_SERVER_ERROR)
        finally:
            if temp_path is not None:
                try:
                    temp_path.unlink(missing_ok=True)
                except OSError:
                    pass

    def handle_rag_upload(self, environ, start_response):
        content_length, body = wsgi_body(environ)
        if content_length <= 0:
            return wsgi_json(start_response, {"error": "Requete vide."}, HTTPStatus.BAD_REQUEST)

        try:
            _, files = parse_multipart_form(wsgi_headers(environ), body)
            uploaded_files = collect_uploaded_files(files, "cv_files", "cv_files[]", "rag_files", "cv_file")
            if not uploaded_files:
                return wsgi_json(start_response, {"error": "Importez au moins un CV PDF, DOCX ou TXT."}, HTTPStatus.BAD_REQUEST)

            indexed = []
            errors = []
            UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

            for uploaded in uploaded_files:
                temp_path = None
                original_name = secure_filename(uploaded["filename"])
                extension = Path(original_name).suffix.lower()
                if extension not in ALLOWED_EXTENSIONS:
                    errors.append({"filename": original_name, "error": "Format non supporte."})
                    continue

                try:
                    with tempfile.NamedTemporaryFile(delete=False, suffix=extension, dir=UPLOAD_DIR) as temp_file:
                        temp_path = Path(temp_file.name)
                        temp_file.write(uploaded["content"])

                    cv_text = extract_text(temp_path)
                    document_check = evaluate_cv_document(cv_text, original_name)
                    if not document_check["isCv"]:
                        errors.append(
                            {
                                "filename": original_name,
                                "error": build_cv_rejection_message(document_check),
                                "documentCheck": document_check,
                            }
                        )
                        continue
                    indexed.append(add_cv_to_vector_db(cv_text, original_name))
                except Exception as exc:
                    errors.append({"filename": original_name, "error": str(exc)})
                finally:
                    if temp_path is not None:
                        try:
                            temp_path.unlink(missing_ok=True)
                        except OSError:
                            pass

            return wsgi_json(
                start_response,
                {
                    "indexed": indexed,
                    "errors": errors,
                    "library": list_indexed_cvs(),
                },
                HTTPStatus.OK if indexed else HTTPStatus.BAD_REQUEST,
            )
        except Exception as exc:
            return wsgi_json(start_response, {"error": f"Indexation RAG impossible : {exc}"}, HTTPStatus.INTERNAL_SERVER_ERROR)

    def handle_rag_chat(self, environ, start_response):
        content_length, body = wsgi_body(environ)
        if content_length <= 0:
            return wsgi_json(start_response, {"error": "Question vide."}, HTTPStatus.BAD_REQUEST)

        try:
            payload = json.loads(body.decode("utf-8"))
            question = payload.get("question", "").strip()
            top_k = parse_int(payload.get("topK"), 5)
            if not question:
                return wsgi_json(start_response, {"error": "Posez une question au chatbot."}, HTTPStatus.BAD_REQUEST)

            return wsgi_json(start_response, generate_chatbot_answer(question, top_k=top_k))
        except json.JSONDecodeError:
            return wsgi_json(start_response, {"error": "JSON invalide."}, HTTPStatus.BAD_REQUEST)
        except Exception as exc:
            return wsgi_json(start_response, {"error": f"Chatbot RAG indisponible : {exc}"}, HTTPStatus.INTERNAL_SERVER_ERROR)

    def handle_tracking_update(self, environ, start_response):
        content_length, body = wsgi_body(environ)
        if content_length <= 0:
            return wsgi_json(start_response, {"error": "Requete vide."}, HTTPStatus.BAD_REQUEST)

        try:
            payload = json.loads(body.decode("utf-8"))
            analysis_id = payload.get("analysisId") or payload.get("id")
            stage = str(payload.get("stage", "")).strip().lower()
            notes = str(payload.get("notes", "")).strip()

            if stage not in TRACKING_STAGE_IDS:
                return wsgi_json(start_response, {"error": "Etape de suivi invalide."}, HTTPStatus.BAD_REQUEST)

            tracking = update_candidate_tracking(analysis_id, stage, notes)
            if tracking is None:
                return wsgi_json(start_response, {"error": "Analyse introuvable."}, HTTPStatus.NOT_FOUND)

            return wsgi_json(start_response, tracking)
        except json.JSONDecodeError:
            return wsgi_json(start_response, {"error": "JSON invalide."}, HTTPStatus.BAD_REQUEST)
        except Exception as exc:
            return wsgi_json(start_response, {"error": f"Suivi indisponible : {exc}"}, HTTPStatus.INTERNAL_SERVER_ERROR)


app = ResumeAnalyzerWSGIApp()
application = app
handler = app


def run_server():
    port = int(os.environ.get("PORT", 8502))
    server = ThreadingHTTPServer(("127.0.0.1", port), ResumeAnalyzerHandler)
    print(" * Serving Architeo Recruit")
    print(f" * Running on http://127.0.0.1:{port}")
    print("Press CTRL+C to quit")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    run_server()
