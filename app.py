import json
import os
import re
import sys
import tempfile
import time
from collections import Counter
from datetime import datetime
from email.parser import BytesParser
from email.policy import default
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import unquote
from src.rag_chatbot import add_cv_to_vector_db, generate_chatbot_answer, list_indexed_cvs

BASE_DIR = Path(__file__).resolve().parent
LOCAL_SITE_PACKAGES = BASE_DIR / ".venv" / "Lib" / "site-packages"


def prefer_local_site_packages():
    local_path = str(LOCAL_SITE_PACKAGES)
    if LOCAL_SITE_PACKAGES.exists():
        sys.path[:] = [path for path in sys.path if path != local_path]
        sys.path.insert(0, local_path)


prefer_local_site_packages()

from src.ai_report import generate_report
from src.classifier import load_classifier, predict_candidate
from src.cleaner import clean_text
from src.extractor import extract_docx_text, extract_pdf_text
from src.matcher import compare_skills, load_model, semantic_similarity
from src.skills import extract_skills


UPLOAD_DIR = BASE_DIR / "data" / "cvs"
ALLOWED_EXTENSIONS = {".pdf", ".docx", ".txt"}

SECTION_PATTERNS = {
    "Profil": r"\b(profil|summary|resume|objectif|a propos)\b",
    "Experience": r"\b(experience|experiences|work history|emploi|stage)\b",
    "Formation": r"\b(formation|education|diplome|degree|universite)\b",
    "Competences": r"\b(competences|skills|technologies|outils)\b",
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
        level = "Intermediaire"
    elif detected_years >= 1:
        level = "Junior"
    else:
        level = "Non detecte"

    evidence = (
        f"{detected_years} an(s) d'experience estimee"
        if detected_years
        else "Aucune duree explicite detectee dans le CV"
    )
    return {"level": level, "years": detected_years, "evidence": evidence}


def build_ats_checks(word_count, sections_found, contacts, skill_count, extension):
    checks = [
        {
            "label": "Coordonnees",
            "status": "ok" if any(contacts.values()) else "warn",
            "detail": "Email, telephone ou profil professionnel detecte."
            if any(contacts.values())
            else "Ajoutez au moins un email ou un telephone visible.",
            "weight": 20,
        },
        {
            "label": "Sections cles",
            "status": "ok" if len(sections_found) >= 4 else "warn",
            "detail": f"{len(sections_found)} section(s) standard detectee(s).",
            "weight": 25,
        },
        {
            "label": "Longueur",
            "status": "ok" if 250 <= word_count <= 950 else "warn",
            "detail": f"{word_count} mots detectes.",
            "weight": 20,
        },
        {
            "label": "Competences",
            "status": "ok" if skill_count >= 6 else "warn",
            "detail": f"{skill_count} competence(s) reconnue(s).",
            "weight": 25,
        },
        {
            "label": "Format",
            "status": "ok" if extension in ALLOWED_EXTENSIONS else "warn",
            "detail": f"Format {extension.upper()} compatible avec l'analyse.",
            "weight": 10,
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
        questions.append(f"Pouvez-vous expliquer comment vous monteriez rapidement en competence sur {skill} ?")
    for skill in matched_skills[:2]:
        questions.append(f"Quel projet concret demontre votre niveau sur {skill} ?")
    if offer_keywords:
        questions.append(f"Comment adapteriez-vous votre experience aux priorites suivantes : {', '.join(offer_keywords[:3])} ?")
    questions.append("Quel resultat mesurable aimeriez-vous livrer pendant les 90 premiers jours ?")
    return questions[:6]


def build_rewrite_suggestions(missing_skills, keyword_gap, sections_missing, contacts):
    suggestions = []
    if missing_skills:
        suggestions.append("Ajouter une ligne Competences ciblee avec : " + ", ".join(missing_skills[:4]) + ".")
    if keyword_gap["missing"]:
        suggestions.append("Reprendre naturellement ces mots-cles de l'offre : " + ", ".join(keyword_gap["missing"][:5]) + ".")
    if sections_missing:
        suggestions.append("Ajouter ou renommer les sections manquantes : " + ", ".join(sections_missing[:3]) + ".")
    if not any(contacts.values()):
        suggestions.append("Rendre les coordonnees visibles en haut du CV.")
    suggestions.append("Transformer les missions principales en resultats chiffres quand c'est possible.")
    return suggestions[:5]


def verdict_for(score, threshold):
    if score >= threshold + 10:
        return "Excellent alignement"
    if score >= threshold:
        return "Profil shortlist"
    if score >= 50:
        return "A revoir"
    return "Faible alignement"


def build_actions(missing_skills, missing_sections, final_score, semantic_score):
    actions = []
    if missing_skills:
        actions.append("Ajouter ou clarifier ces competences : " + ", ".join(missing_skills[:5]) + ".")
    if missing_sections:
        actions.append("Renforcer les sections : " + ", ".join(missing_sections[:3]) + ".")
    if semantic_score < 55:
        actions.append("Adapter le vocabulaire du CV aux mots-cles de l'offre.")
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
        raise ValueError("Aucun texte lisible detecte dans le CV.")

    clean_cv = clean_text(cv_text)
    clean_offer = clean_text(offer_text)
    cv_skills = extract_skills(clean_cv)
    offer_skills = extract_skills(clean_offer)
    result = compare_skills(cv_skills, offer_skills)
    semantic_score = semantic_similarity(clean_cv[:6000], clean_offer[:6000])
    skill_score = result["score"]
    final_score = round(
        (skill_score * (skill_weight / 100))
        + (semantic_score * ((100 - skill_weight) / 100)),
        2,
    )

    prediction, probability = predict_candidate(
        skill_score,
        semantic_score,
        len(result["matched_skills"]),
        len(result["missing_skills"]),
    )
    contacts = extract_contact_details(cv_text)
    sections_found, sections_missing = detect_sections(cv_text)
    word_count = len(re.findall(r"\w+", cv_text))
    health_score = compute_cv_health(word_count, sections_found, contacts, len(cv_skills))
    ats_score, ats_checks = build_ats_checks(
        word_count,
        sections_found,
        contacts,
        len(cv_skills),
        file_path.suffix.lower(),
    )
    keyword_gap = keyword_coverage(offer_text, cv_text)
    experience = estimate_experience(cv_text)
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
    processing_time_ms = round((time.perf_counter() - started_at) * 1000)
    ai_engines = {
        "semantic": (
            "SentenceTransformer all-MiniLM-L6-v2"
            if semantic_model is not None
            else "Fallback lexical rapide"
        ),
        "classifier": (
            "Modele ML local RandomForest"
            if classifier_model is not None
            else "Regles de decision fallback"
        ),
        "semanticReady": semantic_model is not None,
        "classifierReady": classifier_model is not None,
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
        "probability": [float(probability[0]), float(probability[1])],
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


class ResumeAnalyzerHandler(BaseHTTPRequestHandler):
    server_version = "ResumeAnalyzer/1.0"

    def do_GET(self):
        path = unquote(self.path.split("?", 1)[0])
        if path == "/api/rag/cvs":
            self.send_json(list_indexed_cvs())
            return
        if path in {"/", "/index.html"}:
            self.send_static_file(BASE_DIR / "index.html", "text/html; charset=utf-8")
            return
        if path == "/styles.css":
            self.send_static_file(BASE_DIR / "styles.css", "text/css; charset=utf-8")
            return
        if path == "/script.js":
            self.send_static_file(BASE_DIR / "script.js", "application/javascript; charset=utf-8")
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
                analysis = analyze_resume(offer_text, temp_path, original_name, skill_weight, threshold)
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

    def log_message(self, format, *args):
        print(f"{self.address_string()} - {format % args}")


def run_server():
    port = int(os.environ.get("PORT", 8502))
    server = ThreadingHTTPServer(("127.0.0.1", port), ResumeAnalyzerHandler)
    print(" * Serving Resume Analyzer Pro")
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
