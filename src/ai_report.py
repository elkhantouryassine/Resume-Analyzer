def _join_or_none(items):
    return ", ".join(items) if items else "Aucun"


def generate_report(result, semantic_score, final_score, insights=None):
    insights = insights or {}
    verdict = insights.get("verdict", "Non defini")
    threshold = insights.get("threshold", 70)
    skill_weight = insights.get("skill_weight", 60)
    semantic_weight = insights.get("semantic_weight", 40)
    cv_health = insights.get("cv_health", "Non calcule")
    word_count = insights.get("word_count", "Non calcule")
    contacts = insights.get("contacts", {})
    sections_found = insights.get("sections_found", [])
    sections_missing = insights.get("sections_missing", [])
    document_check = insights.get("document_check", {})
    classification = insights.get("classification", {})
    actions = insights.get("actions", [])

    if final_score >= threshold:
        recommendation = "Profil a conserver pour la suite du processus."
    elif final_score >= 50:
        recommendation = "Profil interessant, mais plusieurs points doivent etre clarifies."
    else:
        recommendation = "Profil peu aligne avec les criteres principaux de l'offre."

    action_lines = "\n".join(f"- {item}" for item in actions) if actions else "- Aucun plan d'action généré."
    contact_lines = "\n".join(
        f"- {label} : {value if value else 'Non détecté'}"
        for label, value in contacts.items()
    )

    return f"""# Rapport d'analyse du CV

## Decision
Verdict : {verdict}
Controle document : {"CV reconnu" if document_check.get("isCv", True) else "Document refuse"} ({document_check.get("score", 100)}%)
Classification binaire Random Forest : {classification.get("label", "Non calculee")} ({classification.get("score", 0)}%)
Modèle classification : {classification.get("model", "Non renseigné")}
Recommendation : {recommendation}
Seuil shortlist : {threshold}%

## Scores
- Score compétences : {result["score"]}%
- Score semantique : {semantic_score}%
- Score final : {final_score}%
- Santé du CV : {cv_health}%
- Pondération : {skill_weight}% compétences / {semantic_weight}% sémantique

## Compétences
Compétences correspondantes : {_join_or_none(result["matched_skills"])}
Compétences manquantes : {_join_or_none(result["missing_skills"])}

## Diagnostic du CV
- Nombre de mots détectés : {word_count}
- Sections présentes : {_join_or_none(sections_found)}
- Sections à renforcer : {_join_or_none(sections_missing)}

## Coordonnées détectées
{contact_lines if contact_lines else "- Aucune coordonnée détectée"}

## Plan d'action
{action_lines}
"""
