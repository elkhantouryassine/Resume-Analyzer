import hashlib
import json
import math
import os
import re
import sqlite3
import tempfile
from datetime import datetime
from functools import lru_cache
from pathlib import Path

from src.cleaner import clean_text
from src.skills import extract_skills

try:
    from sentence_transformers import SentenceTransformer
except Exception:
    SentenceTransformer = None


BASE_DIR = Path(__file__).resolve().parents[1]


def runtime_data_dir():
    configured_dir = os.environ.get("ARCHITEO_DATA_DIR")
    if configured_dir:
        return Path(configured_dir)
    if os.environ.get("VERCEL"):
        return Path(tempfile.gettempdir()) / "architeo_recruit"
    return BASE_DIR / "data"


VECTOR_DIR = runtime_data_dir() / "vector_db"
DB_PATH = VECTOR_DIR / "rag_vectors.sqlite"
HASH_VECTOR_DIM = 512
HASH_ENGINE = "hashing-v1"
EMBEDDING_MODEL_NAME = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"

STOPWORDS = {
    "avec", "dans", "pour", "plus", "nous", "vous", "votre", "notre", "cette",
    "cela", "comme", "dune", "d'un", "d'une", "des", "les", "une", "sur",
    "de", "du", "la", "le", "un", "aux", "au", "en", "et", "ou", "je",
    "tu", "il", "elle", "ils", "elles", "mon", "ma", "mes", "ton", "ta",
    "qui", "que", "quoi", "quel", "quelle", "quels", "quelles", "cherche",
    "recherche", "profil", "candidat", "candidate", "cv", "experience",
    "competence", "competences", "poste", "emploi", "stage", "and", "the",
    "for", "with", "from", "that", "this", "who", "what", "which", "role",
}


def get_connection():
    VECTOR_DIR.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(DB_PATH)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    init_db(connection)
    return connection


def init_db(connection):
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS cvs (
            id TEXT PRIMARY KEY,
            filename TEXT NOT NULL,
            content_hash TEXT NOT NULL UNIQUE,
            text TEXT NOT NULL,
            skills TEXT NOT NULL,
            contacts TEXT NOT NULL,
            word_count INTEGER NOT NULL,
            created_at TEXT NOT NULL
        )
        """
    )
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS chunks (
            id TEXT PRIMARY KEY,
            cv_id TEXT NOT NULL,
            filename TEXT NOT NULL,
            chunk_index INTEGER NOT NULL,
            text TEXT NOT NULL,
            vector TEXT NOT NULL,
            vector_engine TEXT NOT NULL DEFAULT 'hashing-v1',
            vector_dim INTEGER NOT NULL DEFAULT 512,
            FOREIGN KEY(cv_id) REFERENCES cvs(id) ON DELETE CASCADE
        )
        """
    )
    ensure_chunk_columns(connection)
    connection.commit()


def ensure_chunk_columns(connection):
    columns = {row["name"] for row in connection.execute("PRAGMA table_info(chunks)").fetchall()}
    if "vector_engine" not in columns:
        connection.execute("ALTER TABLE chunks ADD COLUMN vector_engine TEXT NOT NULL DEFAULT 'hashing-v1'")
    if "vector_dim" not in columns:
        connection.execute("ALTER TABLE chunks ADD COLUMN vector_dim INTEGER NOT NULL DEFAULT 512")


def tokenize(text):
    normalized = clean_text(text).lower()
    tokens = re.findall(r"[a-zA-Z0-9+#.]{2,}", normalized)
    return [token for token in tokens if token not in STOPWORDS]


def stable_index(token):
    digest = hashlib.blake2b(token.encode("utf-8"), digest_size=4).digest()
    return int.from_bytes(digest, "big") % HASH_VECTOR_DIM


@lru_cache(maxsize=1)
def load_embedding_model():
    if SentenceTransformer is None:
        return None
    try:
        return SentenceTransformer(EMBEDDING_MODEL_NAME)
    except Exception:
        return None


def current_embedding_engine():
    return EMBEDDING_MODEL_NAME if load_embedding_model() is not None else HASH_ENGINE


def embedding_status():
    model = load_embedding_model()
    if model is not None:
        return {
            "engine": EMBEDDING_MODEL_NAME,
            "model": EMBEDDING_MODEL_NAME,
            "type": "sentence-transformers",
            "neural": True,
        }
    return {
        "engine": HASH_ENGINE,
        "model": HASH_ENGINE,
        "type": "hashing-local",
        "neural": False,
    }


def hash_embed_text(text):
    tokens = tokenize(text)
    vector = [0.0] * HASH_VECTOR_DIM

    for token in tokens:
        vector[stable_index(token)] += 1.0

    for left, right in zip(tokens, tokens[1:]):
        vector[stable_index(f"{left}_{right}")] += 0.55

    norm = math.sqrt(sum(value * value for value in vector))
    if not norm:
        return vector

    return [round(value / norm, 7) for value in vector]


def embed_text(text):
    model = load_embedding_model()
    if model is not None:
        vector = model.encode(text, normalize_embeddings=True)
        return [round(float(value), 7) for value in vector]
    return hash_embed_text(text)


def cosine_similarity(left, right):
    if len(left) != len(right):
        return 0
    return sum(a * b for a, b in zip(left, right))


def content_hash(text):
    return hashlib.sha256(text.encode("utf-8", errors="ignore")).hexdigest()


def split_text(text, chunk_size=1100, overlap=220):
    clean = re.sub(r"\s+", " ", text).strip()
    if not clean:
        return []

    chunks = []
    start = 0
    while start < len(clean):
        end = min(len(clean), start + chunk_size)
        chunk = clean[start:end].strip()
        if chunk:
            chunks.append(chunk)
        if end == len(clean):
            break
        start = max(0, end - overlap)

    return chunks


def extract_contacts(text):
    email = re.search(r"[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}", text, re.I)
    phone = re.search(r"(?:\+?\d[\s().-]?){8,16}", text)
    linkedin = re.search(r"(?:https?://)?(?:www\.)?linkedin\.com/[^\s)]+", text, re.I)
    github = re.search(r"(?:https?://)?(?:www\.)?github\.com/[^\s)]+", text, re.I)
    return {
        "email": email.group(0) if email else "",
        "phone": phone.group(0).strip() if phone else "",
        "linkedin": linkedin.group(0) if linkedin else "",
        "github": github.group(0) if github else "",
    }


def add_cv_to_vector_db(cv_text, filename):
    text = cv_text.strip()
    if not text:
        raise ValueError("CV vide ou illisible.")

    digest = content_hash(text)
    cv_id = digest[:18]
    skills = extract_skills(clean_text(text))
    contacts = extract_contacts(text)
    chunks = split_text(text)
    vector_engine = current_embedding_engine()
    if not chunks:
        raise ValueError("Impossible de creer des segments RAG pour ce CV.")

    with get_connection() as connection:
        existing = connection.execute(
            "SELECT id FROM cvs WHERE content_hash = ?",
            (digest,),
        ).fetchone()
        if existing:
            connection.execute("DELETE FROM cvs WHERE id = ?", (existing["id"],))

        connection.execute(
            """
            INSERT INTO cvs (id, filename, content_hash, text, skills, contacts, word_count, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                cv_id,
                filename,
                digest,
                text,
                json.dumps(skills, ensure_ascii=False),
                json.dumps(contacts, ensure_ascii=False),
                len(re.findall(r"\w+", text)),
                datetime.now().isoformat(timespec="seconds"),
            ),
        )

        insert_cv_chunks(connection, cv_id, filename, text, chunks, vector_engine)

        connection.commit()

    return {
        "id": cv_id,
        "filename": filename,
        "chunks": len(chunks),
        "skills": skills[:12],
        "wordCount": len(re.findall(r"\w+", text)),
        "embeddingEngine": vector_engine,
    }


def insert_cv_chunks(connection, cv_id, filename, text, chunks, vector_engine):
    for index, chunk in enumerate(chunks):
        chunk_id = f"{cv_id}_{index}"
        vector = embed_text(chunk)
        connection.execute(
            """
            INSERT INTO chunks (id, cv_id, filename, chunk_index, text, vector, vector_engine, vector_dim)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                chunk_id,
                cv_id,
                filename,
                index,
                chunk,
                json.dumps(vector),
                vector_engine,
                len(vector),
            ),
        )


def ensure_current_vector_engine(connection, vector_engine):
    rows = connection.execute(
        """
        SELECT id, filename, text
        FROM cvs
        WHERE NOT EXISTS (
            SELECT 1
            FROM chunks
            WHERE chunks.cv_id = cvs.id
              AND chunks.vector_engine = ?
        )
        """,
        (vector_engine,),
    ).fetchall()

    reindexed = 0
    for row in rows:
        chunks = split_text(row["text"])
        if not chunks:
            continue
        connection.execute("DELETE FROM chunks WHERE cv_id = ?", (row["id"],))
        insert_cv_chunks(connection, row["id"], row["filename"], row["text"], chunks, vector_engine)
        reindexed += 1

    if reindexed:
        connection.commit()

    return reindexed


def list_indexed_cvs():
    with get_connection() as connection:
        rows = connection.execute(
            """
            SELECT id, filename, skills, contacts, word_count, created_at
            FROM cvs
            ORDER BY created_at DESC
            """
        ).fetchall()

    cvs = []
    for row in rows:
        cvs.append(
            {
                "id": row["id"],
                "filename": row["filename"],
                "skills": json.loads(row["skills"]),
                "contacts": json.loads(row["contacts"]),
                "wordCount": row["word_count"],
                "createdAt": row["created_at"],
            }
        )

    return {"count": len(cvs), "cvs": cvs, "embedding": embedding_status()}


def keywords_for_question(question, limit=10):
    counts = {}
    for token in tokenize(question):
        counts[token] = counts.get(token, 0) + 1
    return [word for word, _ in sorted(counts.items(), key=lambda item: item[1], reverse=True)[:limit]]


def search_cvs(question, top_k=5):
    query = question.strip()
    if not query:
        return []

    vector_engine = current_embedding_engine()
    query_vector = embed_text(query)
    query_skills = set(extract_skills(clean_text(query)))
    query_keywords = set(keywords_for_question(query, limit=14))
    by_cv = {}

    with get_connection() as connection:
        ensure_current_vector_engine(connection, vector_engine)
        rows = connection.execute(
            """
            SELECT c.id AS cv_id, c.filename, c.skills, c.contacts, c.word_count,
                   ch.text AS chunk_text, ch.vector, ch.vector_engine, ch.vector_dim
            FROM chunks ch
            JOIN cvs c ON c.id = ch.cv_id
            WHERE ch.vector_engine = ?
            """
            ,
            (vector_engine,),
        ).fetchall()

    for row in rows:
        chunk_vector = json.loads(row["vector"])
        if row["vector_dim"] != len(query_vector):
            continue
        base_score = cosine_similarity(query_vector, chunk_vector)
        skills = json.loads(row["skills"])
        skill_overlap = sorted(query_skills & set(skills))
        keyword_hits = sorted(keyword for keyword in query_keywords if keyword in clean_text(row["chunk_text"]).lower())
        skill_bonus = (len(skill_overlap) / max(len(query_skills), 1)) * 0.18 if query_skills else 0
        keyword_bonus = min(len(keyword_hits) * 0.018, 0.14)
        score = min(base_score + skill_bonus + keyword_bonus, 1.0)

        current = by_cv.get(row["cv_id"])
        snippet = {
            "text": row["chunk_text"],
            "score": round(score * 100, 2),
            "keywordHits": keyword_hits[:8],
        }

        if current is None:
            by_cv[row["cv_id"]] = {
                "id": row["cv_id"],
                "filename": row["filename"],
                "score": round(score * 100, 2),
                "skills": skills,
                "matchedSkills": skill_overlap,
                "contacts": json.loads(row["contacts"]),
                "wordCount": row["word_count"],
                "snippets": [snippet],
            }
        else:
            current["score"] = max(current["score"], round(score * 100, 2))
            current["matchedSkills"] = sorted(set(current["matchedSkills"]) | set(skill_overlap))
            current["snippets"].append(snippet)

    results = sorted(by_cv.values(), key=lambda item: item["score"], reverse=True)
    for result in results:
        result["snippets"] = sorted(result["snippets"], key=lambda item: item["score"], reverse=True)[:2]
        result["confidenceLabel"] = confidence_label(result["score"])

    relevant_results = [
        result
        for result in results
        if result["score"] >= 20
        or result["matchedSkills"]
        or any(snippet.get("keywordHits") for snippet in result["snippets"])
    ]

    return relevant_results[:top_k]


def reason_for_result(result, question):
    reasons = []
    if result["matchedSkills"]:
        reasons.append("compétences détectées : " + ", ".join(result["matchedSkills"][:5]))
    top_keywords = result["snippets"][0].get("keywordHits", []) if result["snippets"] else []
    if top_keywords:
        reasons.append("mots proches de la recherche : " + ", ".join(top_keywords[:5]))
    if not reasons:
        reasons.append("similarite vectorielle avec la question")
    return "; ".join(reasons)


def confidence_label(score):
    if score >= 70:
        return "Tres forte correspondance"
    if score >= 45:
        return "Bonne correspondance"
    if score >= 20:
        return "Correspondance possible"
    return "Signal faible a verifier"


def contact_summary(contacts):
    values = [
        contacts.get("email", ""),
        contacts.get("phone", ""),
        contacts.get("linkedin", ""),
        contacts.get("github", ""),
    ]
    visible = [value for value in values if value]
    return " | ".join(visible) if visible else "coordonnées non détectées"


def suggested_questions(results):
    suggestions = [
        "Fais une shortlist de 3 candidats.",
        "Compare les meilleurs candidats.",
        "Qui manque de Docker ?",
        "Quels sont les 3 meilleurs profils pour ce besoin ?",
    ]
    if results:
        skills = []
        for result in results:
            skills.extend(result.get("skills", [])[:4])
        unique_skills = []
        for skill in skills:
            if skill not in unique_skills:
                unique_skills.append(skill)
        if unique_skills:
            suggestions.insert(0, "Qui combine " + ", ".join(unique_skills[:3]) + " ?")
    return suggestions[:3]


def detect_hr_intent(question):
    normalized = clean_text(question).lower()
    if re.search(r"\b(compare|comparaison|difference|differences|versus|vs)\b", normalized):
        return "compare"
    if re.search(r"\b(shortlist|top\s*\d*|meilleurs?|classe|classement|rank|trie|selectionne)\b", normalized):
        return "shortlist"
    if re.search(r"\b(resume|résume|synthèse|synthèse|profil de|decris|décris|description)\b", normalized):
        return "summary"
    if re.search(r"\b(manque|manquent|missing|sans|n'a pas|ne possede pas|ne possède pas|lacune)\b", normalized):
        return "missing_skill"
    return "search"


def requested_limit(question, default=3, maximum=8):
    normalized = clean_text(question).lower()
    if re.search(r"\b(tous|toutes|chaque|all|each)\b", normalized):
        return maximum
    match = re.search(r"\b(\d{1,2})\b", question)
    if not match:
        return default
    return max(1, min(int(match.group(1)), maximum))


def load_cv_records(include_text=False):
    selected_text = ", text" if include_text else ""
    with get_connection() as connection:
        rows = connection.execute(
            f"""
            SELECT id, filename, skills, contacts, word_count, created_at{selected_text}
            FROM cvs
            ORDER BY created_at DESC
            """
        ).fetchall()

    records = []
    for row in rows:
        item = {
            "id": row["id"],
            "filename": row["filename"],
            "skills": json.loads(row["skills"]),
            "contacts": json.loads(row["contacts"]),
            "wordCount": row["word_count"],
            "createdAt": row["created_at"],
        }
        if include_text:
            item["text"] = row["text"]
        records.append(item)
    return records


def requested_skills(question):
    skills = extract_skills(clean_text(question))
    if skills:
        return skills

    tokens = keywords_for_question(question, limit=6)
    ignored = {
        "manque", "manquent", "missing", "sans", "candidat", "candidats",
        "profil", "profils", "qui", "avec", "competence", "competences",
    }
    return [token for token in tokens if token not in ignored]


def strongest_skills(candidate, limit=6):
    return candidate.get("matchedSkills", [])[:limit] or candidate.get("skills", [])[:limit]


def missing_requested_skills(candidate, question):
    asked = requested_skills(question)
    candidate_skills = set(candidate.get("skills", []))
    return [skill for skill in asked if skill not in candidate_skills]


def missing_known_skills(candidate, question):
    asked = extract_skills(clean_text(question))
    candidate_skills = set(candidate.get("skills", []))
    return [skill for skill in asked if skill not in candidate_skills]


def candidate_quality_score(record):
    skills_count = len(record.get("skills", []))
    contacts = record.get("contacts", {})
    contact_score = sum(1 for value in contacts.values() if value) * 4
    length_score = min(record.get("wordCount", 0) / 18, 25)
    skills_score = min(skills_count * 1.35, 45)
    return round(min(95, 20 + skills_score + length_score + contact_score), 2)


def cv_records_as_results(limit=8):
    records = load_cv_records()
    results = []
    for record in records:
        score = candidate_quality_score(record)
        skills = record.get("skills", [])
        results.append(
            {
                **record,
                "score": score,
                "matchedSkills": skills[:8],
                "snippets": [
                    {
                        "text": "Profil indexé dans la base CV. Classement RH basé sur la richesse du CV, les compétences détectées et les coordonnées disponibles.",
                        "score": score,
                        "keywordHits": skills[:6],
                    }
                ],
                "confidenceLabel": confidence_label(score),
            }
        )
    return sorted(results, key=lambda item: item["score"], reverse=True)[:limit]


def summarize_candidate(candidate, question=""):
    strengths = strongest_skills(candidate, limit=5)
    missing = missing_known_skills(candidate, question) if question else []
    parts = [
        f"{candidate['filename']} : score {candidate.get('score', 0)}%",
        "points forts " + (", ".join(strengths) if strengths else "non détectés"),
    ]
    if missing:
        parts.append("a verifier/manquant " + ", ".join(missing[:4]))
    parts.append("contact " + contact_summary(candidate.get("contacts", {})))
    return "; ".join(parts) + "."


def build_shortlist_answer(results, library_count, question):
    limit = requested_limit(question, default=3)
    shortlist = results[:limit]
    lines = [
        f"Shortlist RH : {len(shortlist)} candidat(s) retenu(s) parmi {library_count} CV indexé(s).",
        "",
    ]
    for index, candidate in enumerate(shortlist, start=1):
        lines.append(f"{index}. {summarize_candidate(candidate, question)}")
    lines.append("")
    lines.append("Conseil RH : commencez par le premier profil, puis utilisez les autres comme alternatives si le besoin exige plus de couverture technique.")
    return "\n".join(lines)


def build_comparison_answer(results, library_count, question):
    compared = results[: min(4, len(results))]
    lines = [
        f"Comparaison RH des {len(compared)} meilleur(s) candidat(s) sur {library_count} CV.",
        "",
        "Candidat | Score | Forces | Points a verifier",
    ]
    for candidate in compared:
        strengths = ", ".join(strongest_skills(candidate, limit=4)) or "non détectées"
        missing = ", ".join(missing_known_skills(candidate, question)[:4]) or "selon entretien"
        lines.append(f"{candidate['filename']} | {candidate.get('score', 0)}% | {strengths} | {missing}")
    lines.append("")
    lines.append("Lecture : le score combine similarité sémantique, compétences détectées et mots proches de la demande.")
    return "\n".join(lines)


def build_summary_answer(results, library_count, question):
    summarized = results[: requested_limit(question, default=3)]
    lines = [f"Resume RH de {len(summarized)} profil(s) parmi {library_count} CV.", ""]
    for candidate in summarized:
        lines.append("- " + summarize_candidate(candidate, question))
    return "\n".join(lines)


def build_missing_skill_answer(question, library_count):
    asked = requested_skills(question)
    if not asked:
        return (
            "Je peux vérifier les lacunes, mais il faut préciser une compétence. "
            "Exemple : Qui manque de Docker ?"
        ), []

    records = load_cv_records()
    missing_rows = []
    matching_results = []
    for record in records:
        skills = set(record.get("skills", []))
        missing = [skill for skill in asked if skill not in skills]
        if missing:
            missing_rows.append((record, missing))
        else:
            matching_results.append(
                {
                    **record,
                    "score": 100,
                    "matchedSkills": asked,
                    "snippets": [{"text": "Toutes les compétences demandées sont détectées dans ce CV.", "score": 100, "keywordHits": asked}],
                    "confidenceLabel": "Compétences demandées détectées",
                }
            )

    lines = [
        f"Verification des lacunes sur {library_count} CV pour : {', '.join(asked)}.",
        "",
    ]
    if missing_rows:
        lines.append("CV avec compétence(s) manquante(s) :")
        for record, missing in missing_rows[:8]:
            lines.append(f"- {record['filename']} : manque {', '.join(missing)}.")
    else:
        lines.append("Aucun manque détecté : tous les CV indexé(s) couvrent ces compétences.")

    if matching_results:
        lines.append("")
        lines.append("CV qui couvrent la demande : " + ", ".join(result["filename"] for result in matching_results[:5]) + ".")

    return "\n".join(lines), matching_results


def build_search_answer(results, library_count, question):
    best = results[0]
    lines = [
        f"J'ai trouve {len(results)} CV pertinent(s) parmi {library_count} CV indexé(s).",
        f"Le meilleur profil est {best['filename']} ({best['score']}%, {best['confidenceLabel'].lower()}).",
        "",
        "Pourquoi : " + reason_for_result(best, question) + ".",
        "Contact : " + contact_summary(best["contacts"]) + ".",
    ]

    if len(results) > 1:
        lines.append("")
        lines.append("Classement rapide :")
        lines.append(f"1. {best['filename']} - {best['score']}% - {reason_for_result(best, question)}.")
        for position, result in enumerate(results[1:4], start=2):
            lines.append(f"{position}. {result['filename']} - {result['score']}% - {reason_for_result(result, question)}.")

    return "\n".join(lines)


def generate_chatbot_answer(question, top_k=5):
    intent = detect_hr_intent(question)
    search_limit = max(top_k, requested_limit(question, default=3, maximum=8))
    results = search_cvs(question, top_k=search_limit)
    library = list_indexed_cvs()
    embedding = embedding_status()

    if not library["count"]:
        return {
            "answer": "Aucun CV n'est encore indexé. Analysez un CV pour l'ajouter automatiquement à la base RAG avant de poser une question.",
            "results": [],
            "indexedCount": 0,
            "embedding": embedding,
            "assistantMode": intent,
            "suggestions": [
                "Analysez plusieurs CV puis demandez le meilleur profil pour un poste.",
                "Vous pouvez chercher par compétences, outils, diplôme ou expérience.",
            ],
        }

    if intent in {"shortlist", "compare", "summary"} and not results:
        results = cv_records_as_results(limit=search_limit)

    if intent == "missing_skill":
        answer, missing_results = build_missing_skill_answer(question, library["count"])
        return {
            "answer": answer,
            "results": missing_results,
            "indexedCount": library["count"],
            "embedding": embedding,
            "assistantMode": intent,
            "suggestions": suggested_questions(missing_results),
            "mode": embedding["engine"],
        }

    if not results:
        return {
            "answer": (
                "Je n'ai pas trouve de CV suffisamment proche de votre recherche. "
                "Essayez d'ajouter des compétences concrètes, un intitulé de poste ou des outils précis."
            ),
            "results": [],
            "indexedCount": library["count"],
            "embedding": embedding,
            "assistantMode": intent,
            "suggestions": suggested_questions([]),
        }

    if intent == "shortlist":
        answer = build_shortlist_answer(results, library["count"], question)
    elif intent == "compare":
        answer = build_comparison_answer(results, library["count"], question)
    elif intent == "summary":
        answer = build_summary_answer(results, library["count"], question)
    else:
        answer = build_search_answer(results, library["count"], question)

    return {
        "answer": answer,
        "results": results,
        "indexedCount": library["count"],
        "embedding": embedding,
        "assistantMode": intent,
        "suggestions": suggested_questions(results),
        "mode": embedding["engine"],
    }
