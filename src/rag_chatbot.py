import hashlib
import json
import math
import re
import sqlite3
from datetime import datetime
from pathlib import Path

from src.cleaner import clean_text
from src.skills import extract_skills


BASE_DIR = Path(__file__).resolve().parents[1]
VECTOR_DIR = BASE_DIR / "data" / "vector_db"
DB_PATH = VECTOR_DIR / "rag_vectors.sqlite"
VECTOR_DIM = 512

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
            FOREIGN KEY(cv_id) REFERENCES cvs(id) ON DELETE CASCADE
        )
        """
    )
    connection.commit()


def tokenize(text):
    normalized = clean_text(text).lower()
    tokens = re.findall(r"[a-zA-Z0-9+#.]{2,}", normalized)
    return [token for token in tokens if token not in STOPWORDS]


def stable_index(token):
    digest = hashlib.blake2b(token.encode("utf-8"), digest_size=4).digest()
    return int.from_bytes(digest, "big") % VECTOR_DIM


def embed_text(text):
    tokens = tokenize(text)
    vector = [0.0] * VECTOR_DIM

    for token in tokens:
        vector[stable_index(token)] += 1.0

    for left, right in zip(tokens, tokens[1:]):
        vector[stable_index(f"{left}_{right}")] += 0.55

    norm = math.sqrt(sum(value * value for value in vector))
    if not norm:
        return vector

    return [round(value / norm, 7) for value in vector]


def cosine_similarity(left, right):
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

        for index, chunk in enumerate(chunks):
            chunk_id = f"{cv_id}_{index}"
            connection.execute(
                """
                INSERT INTO chunks (id, cv_id, filename, chunk_index, text, vector)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    chunk_id,
                    cv_id,
                    filename,
                    index,
                    chunk,
                    json.dumps(embed_text(chunk)),
                ),
            )

        connection.commit()

    return {
        "id": cv_id,
        "filename": filename,
        "chunks": len(chunks),
        "skills": skills[:12],
        "wordCount": len(re.findall(r"\w+", text)),
    }


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

    return {"count": len(cvs), "cvs": cvs}


def keywords_for_question(question, limit=10):
    counts = {}
    for token in tokenize(question):
        counts[token] = counts.get(token, 0) + 1
    return [word for word, _ in sorted(counts.items(), key=lambda item: item[1], reverse=True)[:limit]]


def search_cvs(question, top_k=5):
    query = question.strip()
    if not query:
        return []

    query_vector = embed_text(query)
    query_skills = set(extract_skills(clean_text(query)))
    query_keywords = set(keywords_for_question(query, limit=14))
    by_cv = {}

    with get_connection() as connection:
        rows = connection.execute(
            """
            SELECT c.id AS cv_id, c.filename, c.skills, c.contacts, c.word_count,
                   ch.text AS chunk_text, ch.vector
            FROM chunks ch
            JOIN cvs c ON c.id = ch.cv_id
            """
        ).fetchall()

    for row in rows:
        chunk_vector = json.loads(row["vector"])
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
        reasons.append("competences detectees : " + ", ".join(result["matchedSkills"][:5]))
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
    return " | ".join(visible) if visible else "coordonnees non detectees"


def suggested_questions(results):
    suggestions = [
        "Quels sont les 3 meilleurs profils pour ce besoin ?",
        "Quels candidats ont les competences les plus proches ?",
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


def generate_chatbot_answer(question, top_k=5):
    results = search_cvs(question, top_k=top_k)
    library = list_indexed_cvs()

    if not library["count"]:
        return {
            "answer": "Aucun CV n'est encore indexe. Importez plusieurs CV dans la base RAG avant de poser une question.",
            "results": [],
            "indexedCount": 0,
            "suggestions": [
                "Ajoutez 3 a 10 CV puis demandez le meilleur profil pour un poste.",
                "Vous pouvez chercher par competences, outils, diplome ou experience.",
            ],
        }

    if not results:
        return {
            "answer": (
                "Je n'ai pas trouve de CV suffisamment proche de votre recherche. "
                "Essayez d'ajouter des competences concretes, un intitule de poste ou des outils precis."
            ),
            "results": [],
            "indexedCount": library["count"],
            "suggestions": suggested_questions([]),
        }

    best = results[0]
    lines = [
        f"J'ai trouve {len(results)} CV pertinent(s) parmi {library['count']} CV indexe(s).",
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

    return {
        "answer": "\n".join(lines),
        "results": results,
        "indexedCount": library["count"],
        "suggestions": suggested_questions(results),
        "mode": "rag_sqlite_vectoriel_local",
    }
