const page = document.body.dataset.page;
const els = {
  pageContent: document.querySelector("#pageContent"),
  pageMetric: document.querySelector("#pageMetric"),
  downloadMd: document.querySelector("#downloadMd"),
  downloadHtml: document.querySelector("#downloadHtml")
};

let latestAnalysis = null;

if (els.downloadMd) {
  els.downloadMd.addEventListener("click", () => {
    if (!latestAnalysis) return;
    downloadFile("rapport-cv.md", buildMarkdownReport(latestAnalysis), "text/markdown");
  });
}

if (els.downloadHtml) {
  els.downloadHtml.addEventListener("click", () => {
    if (!latestAnalysis) return;
    downloadFile("rapport-cv.html", buildHtmlDocument(latestAnalysis), "text/html");
  });
}

async function loadLatestAnalysis() {
  try {
    const response = await fetch("/api/analysis/latest");
    const payload = await readJson(response);
    if (!response.ok) {
      throw new Error(payload.error || "Analyse indisponible.");
    }
    if (!payload.analysis) {
      renderEmpty();
      return;
    }

    latestAnalysis = normalizeAnalysis(payload.analysis);
    renderPage(latestAnalysis);
  } catch (error) {
    renderError(error.message || "Impossible de charger la dernière analyse.");
  }
}

function normalizeAnalysis(item) {
  const summary = item.summary || {};
  const keywordCoverage = summary.keywordCoverage || {};
  const profileType = summary.profileType || {};
  const classification = summary.classification || buildFallbackClassification(item, keywordCoverage);
  const classificationPrediction = toNumber(classification.prediction, toNumber(summary.prediction));
  const isPositiveClassification = classification.label === "Bon profil"
    || (classification.label !== "Profil faible" && classificationPrediction === 1);
  return {
    id: item.id || "",
    createdAt: item.createdAt || "",
    fileName: item.fileName || "CV analyse",
    verdict: item.verdict || "Analyse terminee",
    finalScore: toNumber(item.finalScore),
    skillScore: toNumber(item.skillScore),
    semanticScore: toNumber(item.semanticScore),
    atsScore: toNumber(item.atsScore),
    keywordScore: toNumber(item.keywordScore),
    wordCount: toNumber(item.wordCount),
    matchedSkills: asArray(summary.matchedSkills),
    missingSkills: asArray(summary.missingSkills),
    actions: asArray(summary.actions),
    classification: {
      label: isPositiveClassification ? "Bon profil" : "Profil faible",
      score: toNumber(classification.score),
      tone: isPositiveClassification ? "good" : "bad",
      detail: classification.detail || "Classification binaire Random Forest.",
      prediction: classificationPrediction,
      positiveProbability: toNumber(classification.positiveProbability),
      negativeProbability: toNumber(classification.negativeProbability),
      model: classification.model || "RandomForestClassifier"
    },
    profileType: {
      label: profileType.label || item.profileType || "Profil generaliste",
      score: toNumber(profileType.score),
      confidence: profileType.confidence || "faible",
      signals: asArray(profileType.signals),
      alternatives: asArray(profileType.alternatives)
    },
    experience: summary.experience || { level: "Non détecté", years: 0, evidence: "Aucune durée explicite détectée." },
    sections: summary.sections || { found: [], missing: [] },
    documentCheck: summary.documentCheck || {
      isCv: true,
      score: 100,
      positiveSignals: [],
      negativeSignals: []
    },
    keywordCoverage: {
      score: toNumber(keywordCoverage.score, toNumber(item.keywordScore)),
      matched: asArray(keywordCoverage.matched),
      missing: asArray(keywordCoverage.missing),
      total: toNumber(keywordCoverage.total)
    },
    contacts: summary.contacts || {},
    atsChecks: asArray(summary.atsChecks),
    interviewQuestions: asArray(summary.interviewQuestions),
    rewriteSuggestions: asArray(summary.rewriteSuggestions),
    aiEngines: summary.aiEngines || {},
    processingTimeMs: toNumber(summary.processingTimeMs),
    threshold: toNumber(summary.threshold, 70),
    skillWeight: toNumber(summary.skillWeight, 60),
    reportMarkdown: item.reportMarkdown || ""
  };
}

function renderPage(analysis) {
  if (page === "skills") {
    renderSkills(analysis);
    return;
  }
  if (page === "insights") {
    renderInsights(analysis);
    return;
  }
  if (page === "diagnostic") {
    renderDiagnostic(analysis);
    return;
  }
  if (page === "report") {
    renderReport(analysis);
  }
}

function buildFallbackClassification(item) {
  const summary = item.summary || {};
  const probability = asArray(summary.probability).map((value) => toNumber(value));
  if (probability.length >= 2) {
    const prediction = toNumber(summary.prediction);
    const positiveProbability = round(probability[1] * 100);
    const negativeProbability = round(probability[0] * 100);
    const isPositive = prediction === 1;
    return {
      label: isPositive ? "Bon profil" : "Profil faible",
      score: isPositive ? positiveProbability : negativeProbability,
      tone: isPositive ? "good" : "bad",
      detail: `Classification binaire Random Forest (${positiveProbability}% positif / ${negativeProbability}% negatif).`,
      prediction,
      positiveProbability,
      negativeProbability,
      model: "RandomForestClassifier"
    };
  }

  const finalScore = toNumber(item.finalScore);
  const threshold = toNumber(summary.threshold, 65);
  const isPositive = finalScore >= threshold;
  const positiveProbability = round(finalScore);
  const negativeProbability = round(100 - finalScore);
  return {
    label: isPositive ? "Bon profil" : "Profil faible",
    score: isPositive ? positiveProbability : negativeProbability,
    tone: isPositive ? "good" : "bad",
    detail: "Estimation binaire de secours; relancez l'analyse pour utiliser Random Forest.",
    prediction: isPositive ? 1 : 0,
    positiveProbability,
    negativeProbability,
    model: "Fallback local"
  };
}

function renderSkills(analysis) {
  els.pageMetric.textContent = String(analysis.matchedSkills.length);
  els.pageContent.innerHTML = `
    <section class="two-column detached-grid">
      <article class="panel">
        <div class="panel-head">
          <div>
            <span class="section-kicker">Correspondances</span>
            <h2>Compétences validées</h2>
          </div>
          <span class="pill">${analysis.matchedSkills.length}</span>
        </div>
        <div class="chip-list">${chipHtml(analysis.matchedSkills, "good", "Aucune compétence commune détectée.")}</div>
      </article>
      <article class="panel">
        <div class="panel-head">
          <div>
            <span class="section-kicker">Ecarts</span>
            <h2>Compétences à renforcer</h2>
          </div>
          <span class="pill warn">${analysis.missingSkills.length}</span>
        </div>
        <div class="chip-list">${chipHtml(analysis.missingSkills, "warn", "Aucun écart majeur détecté.")}</div>
      </article>
    </section>
    <section class="results-grid detached-metrics">
      ${metricCard("Score compétences", `${analysis.skillScore}%`)}
      ${metricCard("Score semantique", `${analysis.semanticScore}%`)}
      ${metricCard("Mots-clés", `${analysis.keywordCoverage.score}%`)}
      ${metricCard("Mots détectés", analysis.wordCount)}
    </section>
  `;
}

function renderInsights(analysis) {
  els.pageMetric.textContent = `${analysis.keywordCoverage.score}%`;
  const alternatives = analysis.profileType.alternatives.map((item) => item.label).join(", ") || "Aucune";
  els.pageContent.innerHTML = `
    <section class="insights-grid detached-grid">
      <article class="panel insight-card classification-panel ${analysis.classification.tone}">
        <div>
          <span class="section-kicker">Classification</span>
          <h2>Niveau candidat</h2>
        </div>
        <div class="profile-summary">
          <strong>${escapeHtml(analysis.classification.label)}</strong>
          <span>${analysis.classification.score}%</span>
          <p>${escapeHtml(analysis.classification.detail)}</p>
        </div>
      </article>

      <article class="panel insight-card profile-type-card">
        <div class="panel-head">
          <div>
            <span class="section-kicker">Type détecté</span>
            <h2>Orientation profil</h2>
          </div>
          <span class="pill">${analysis.profileType.score}%</span>
        </div>
        <div class="profile-summary">
          <strong>${escapeHtml(analysis.profileType.label)}</strong>
          <span>Confiance ${escapeHtml(analysis.profileType.confidence)}</span>
          <p>Signaux : ${escapeHtml(analysis.profileType.signals.join(", ") || "Aucun signal fort détecté.")}</p>
          <p>Alternatives : ${escapeHtml(alternatives)}</p>
        </div>
      </article>

      <article class="panel insight-card">
        <div>
          <span class="section-kicker">Profil</span>
          <h2>Niveau estime</h2>
        </div>
        <div class="profile-summary">
          <strong>${escapeHtml(analysis.experience.level || "Non détecté")}</strong>
          <span>${toNumber(analysis.experience.years)} an(s)</span>
          <p>${escapeHtml(analysis.experience.evidence || "Aucune durée explicite détectée.")}</p>
        </div>
      </article>

      <article class="panel insight-card">
        <div class="panel-head">
          <div>
            <span class="section-kicker">Mots-clés</span>
            <h2>Couverture de l'offre</h2>
          </div>
          <span class="pill">${analysis.keywordCoverage.score}%</span>
        </div>
        <h3>Presents dans le CV</h3>
        <div class="chip-list compact">${chipHtml(analysis.keywordCoverage.matched, "good", "Aucun mot-clé prioritaire détecté.")}</div>
        <h3 class="stack-title">À intégrer</h3>
        <div class="chip-list compact">${chipHtml(analysis.keywordCoverage.missing, "warn", "Tous les mots-clés prioritaires sont couverts.")}</div>
      </article>

      <article class="panel insight-card">
        <div>
          <span class="section-kicker">Entretien</span>
          <h2>Questions suggerees</h2>
        </div>
        <ol class="insight-list">${listItems(analysis.interviewQuestions, "Aucune question disponible.")}</ol>
      </article>

      <article class="panel insight-card">
        <div>
          <span class="section-kicker">Reecriture</span>
          <h2>Ameliorations prioritaires</h2>
        </div>
        <ul class="insight-list">${listItems(analysis.rewriteSuggestions, "Aucune recommandation disponible.")}</ul>
      </article>

      <article class="panel insight-card ai-engine-card">
        <div>
          <span class="section-kicker">Transparence IA</span>
          <h2>Moteurs utilises</h2>
        </div>
        <div class="engine-list">
          <div><span>Sémantique</span><strong>${escapeHtml(analysis.aiEngines.semantic || "Non renseigné")}</strong></div>
          <div><span>Prédiction</span><strong>${escapeHtml(analysis.aiEngines.classifier || "Non renseigné")}</strong></div>
          <div><span>Duree reelle</span><strong>${analysis.processingTimeMs} ms</strong></div>
        </div>
      </article>
    </section>
  `;
}

function renderDiagnostic(analysis) {
  els.pageMetric.textContent = `${analysis.atsScore}%`;
  const contactEntries = Object.entries(analysis.contacts);
  els.pageContent.innerHTML = `
    <section class="panel">
      <div class="panel-head">
        <div>
          <span class="section-kicker">Diagnostic CV</span>
          <h2>Structure et informations</h2>
        </div>
        <span class="pill">${contactEntries.filter(([, value]) => Boolean(value)).length}/4 coordonnées</span>
      </div>
      <div class="diagnostic-grid">
        <div class="diagnostic-block">
          <h3>Sections présentes</h3>
          <div class="chip-list">${chipHtml(asArray(analysis.sections.found), "good", "Aucune section standard détectée.")}</div>
        </div>
        <div class="diagnostic-block">
          <h3>Sections à renforcer</h3>
          <div class="chip-list">${chipHtml(asArray(analysis.sections.missing), "warn", "Toutes les sections principales sont présentes.")}</div>
        </div>
        <div class="diagnostic-block">
          <h3>Coordonnées détectées</h3>
          <ul class="contact-list">${contactHtml(contactEntries)}</ul>
        </div>
        <div class="diagnostic-block">
          <h3>Checklist ATS</h3>
          <div class="check-list">${atsCheckHtml(analysis.atsChecks)}</div>
        </div>
        <div class="diagnostic-block">
          <h3>Controle document</h3>
          <div class="check-list">
            <div class="check-item ${analysis.documentCheck.isCv ? "good" : "warn"}">
              <span>${analysis.documentCheck.isCv ? "OK" : "A verifier"}</span>
              <div>
                <strong>${analysis.documentCheck.isCv ? "CV reconnu" : "Document non CV"}</strong>
                <p>${analysis.documentCheck.score}% de confiance - ${escapeHtml(asArray(analysis.documentCheck.positiveSignals).join(", ") || "signaux insuffisants")}</p>
              </div>
            </div>
          </div>
        </div>
      </div>
    </section>
  `;
}

function renderReport(analysis) {
  els.pageMetric.textContent = `${analysis.finalScore}%`;
  els.pageContent.innerHTML = buildReportMarkup(analysis);
  [els.downloadMd, els.downloadHtml].filter(Boolean).forEach((button) => {
    button.disabled = false;
  });
}

function buildReportMarkup(analysis) {
  return `
    <div class="report-title">
      <span class="section-kicker">Synthese</span>
      <h2>${escapeHtml(analysis.verdict)}</h2>
      <p><strong>${escapeHtml(analysis.fileName)}</strong> - ${analysis.wordCount} mots détectés - ${formatDateTime(analysis.createdAt)}</p>
    </div>

    <div class="report-summary-grid">
      ${reportMetric("Score final", `${analysis.finalScore}%`)}
      ${reportMetric("Type document", analysis.documentCheck.isCv ? `CV reconnu (${analysis.documentCheck.score}%)` : "Non CV")}
      ${reportMetric("Classification", analysis.classification.label)}
      ${reportMetric("Type profil", analysis.profileType.label)}
      ${reportMetric("Compétences", `${analysis.skillScore}%`)}
      ${reportMetric("Sémantique", `${analysis.semanticScore}%`)}
      ${reportMetric("ATS", `${analysis.atsScore}%`)}
      ${reportMetric("Mots-clés", `${analysis.keywordCoverage.score}%`)}
    </div>

    <div class="report-section">
      <h3>Controle du document</h3>
      <ul class="report-actions">
        <li>Statut : ${analysis.documentCheck.isCv ? "CV accepte" : "Document refuse"} (${analysis.documentCheck.score}%)</li>
        <li>Signaux : ${escapeHtml(asArray(analysis.documentCheck.positiveSignals).join(", ") || "Aucun signal detaille")}</li>
      </ul>
    </div>

    <div class="report-section">
      <h3>Classification candidat</h3>
      <ul class="report-actions">
        <li>Niveau : ${escapeHtml(analysis.classification.label)} (${analysis.classification.score}%)</li>
        <li>Lecture : ${escapeHtml(analysis.classification.detail)}</li>
      </ul>
    </div>

    <div class="report-section">
      <h3>Type de profil détecté</h3>
      <ul class="report-actions">
        <li>Orientation : ${escapeHtml(analysis.profileType.label)} (${analysis.profileType.score}% de confiance)</li>
        <li>Confiance : ${escapeHtml(analysis.profileType.confidence)}</li>
        <li>Signaux : ${escapeHtml(analysis.profileType.signals.join(", ") || "Aucun signal spécialisé fort détecté")}</li>
      </ul>
    </div>

    <div class="report-section">
      <h3>Compétences correspondantes</h3>
      <div class="report-tag-grid">${reportTags(analysis.matchedSkills, "good", "Aucune compétence commune détectée.")}</div>
    </div>

    <div class="report-section">
      <h3>Compétences à renforcer</h3>
      <div class="report-tag-grid">${reportTags(analysis.missingSkills, "warn", "Aucun écart majeur détecté.")}</div>
    </div>

    <div class="report-section">
      <h3>Plan d'action</h3>
      <ul class="report-actions">${listItems(analysis.actions, "Aucune action prioritaire disponible.")}</ul>
    </div>

    <div class="report-section">
      <h3>Questions d'entretien</h3>
      <ul class="report-actions">${listItems(analysis.interviewQuestions, "Aucune question disponible.")}</ul>
    </div>

    <div class="report-section">
      <h3>Ameliorations prioritaires</h3>
      <ul class="report-actions">${listItems(analysis.rewriteSuggestions, "Aucune recommandation disponible.")}</ul>
    </div>
  `;
}

function buildMarkdownReport(analysis) {
  return `# Rapport d'analyse du CV

## Decision
Verdict : ${analysis.verdict}
Fichier : ${analysis.fileName}
Controle document : ${analysis.documentCheck.isCv ? "CV reconnu" : "Non CV"} (${analysis.documentCheck.score}%)
Classification : ${analysis.classification.label} (${analysis.classification.score}%)
Type de profil : ${analysis.profileType.label}

## Scores
- Score final : ${analysis.finalScore}%
- Score compétences : ${analysis.skillScore}%
- Score semantique : ${analysis.semanticScore}%
- Score ATS : ${analysis.atsScore}%
- Couverture mots-clés : ${analysis.keywordCoverage.score}%

## Compétences
Correspondances : ${analysis.matchedSkills.join(", ") || "Aucune"}
Manquantes : ${analysis.missingSkills.join(", ") || "Aucune"}

## Plan d'action
${analysis.actions.map((item) => `- ${item}`).join("\n") || "- Aucune action prioritaire disponible."}
`;
}

function buildHtmlDocument(analysis) {
  return `<!doctype html>
<html lang="fr">
<head>
  <meta charset="utf-8">
  <title>Rapport CV</title>
  <style>
    body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; color: #111827; margin: 42px; background: #f4f6f8; }
    .sheet { max-width: 900px; margin: auto; }
    .report-title, .report-summary-grid, .report-section { background: #fff; border: 1px solid #e5e7eb; border-radius: 14px; padding: 20px; margin-bottom: 14px; }
    .report-summary-grid { display: grid; grid-template-columns: repeat(3, 1fr); gap: 12px; }
    .report-metric { background: #f8fafc; border-radius: 10px; padding: 14px; }
    .report-tag { display: inline-block; margin: 4px; padding: 6px 10px; border-radius: 10px; background: #f8fafc; border: 1px solid #e5e7eb; }
  </style>
</head>
<body><main class="sheet"><h1>Rapport d'analyse du CV</h1>${buildReportMarkup(analysis)}</main></body>
</html>`;
}

function renderEmpty() {
  els.pageMetric.textContent = page === "skills" ? "0" : "--";
  els.pageContent.innerHTML = `
    <div class="panel">
      <div class="history-empty">
        <strong>Aucune analyse sauvegardee</strong>
        <p>Lancez une analyse depuis la page principale pour alimenter cette page.</p>
        <a class="ghost-btn nav-action" href="/app?start=1#analyse">Nouvelle analyse</a>
      </div>
    </div>
  `;
}

function renderError(message) {
  els.pageMetric.textContent = "--";
  els.pageContent.innerHTML = `
    <div class="panel">
      <div class="history-empty">
        <strong>Chargement impossible</strong>
        <p>${escapeHtml(message)}</p>
      </div>
    </div>
  `;
}

function chipHtml(items, tone, emptyText) {
  const values = items.length ? items : [emptyText];
  return values.map((item) => `<span class="chip ${items.length ? tone : ""}">${escapeHtml(item)}</span>`).join("");
}

function reportTags(items, tone, emptyText) {
  const values = items.length ? items : [emptyText];
  return values.map((item) => `<span class="report-tag ${items.length ? tone : ""}">${escapeHtml(item)}</span>`).join("");
}

function listItems(items, emptyText) {
  const values = items.length ? items : [emptyText];
  return values.map((item) => `<li>${escapeHtml(item)}</li>`).join("");
}

function metricCard(label, value) {
  return `<article class="metric-card"><span>${escapeHtml(label)}</span><strong>${escapeHtml(value)}</strong></article>`;
}

function reportMetric(label, value) {
  return `<div class="report-metric"><span>${escapeHtml(label)}</span><strong>${escapeHtml(value)}</strong></div>`;
}

function contactHtml(entries) {
  if (!entries.length) return "<li>Aucune coordonnée détectée</li>";
  return entries.map(([label, value]) => `<li>${escapeHtml(label)}: ${escapeHtml(value || "Non détecté")}</li>`).join("");
}

function atsCheckHtml(checks) {
  if (!checks.length) {
    return `<div class="check-item warn"><span>A verifier</span><div><strong>Checklist ATS</strong><p>Aucune checklist disponible pour cette analyse.</p></div></div>`;
  }
  return checks.map((check) => `
    <div class="check-item ${check.status === "ok" ? "good" : "warn"}">
      <span>${check.status === "ok" ? "OK" : "A corriger"}</span>
      <div>
        <strong>${escapeHtml(check.label)}</strong>
        <p>${escapeHtml(check.detail)}</p>
      </div>
    </div>
  `).join("");
}

async function readJson(response) {
  const text = await response.text();
  if (!text) return {};
  try {
    return JSON.parse(text);
  } catch (error) {
    return { error: text.slice(0, 220) || "Reponse serveur invalide." };
  }
}

function downloadFile(fileName, content, type) {
  const blob = new Blob([content], { type });
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = fileName;
  document.body.appendChild(link);
  link.click();
  link.remove();
  URL.revokeObjectURL(url);
}

function escapeHtml(value) {
  return String(value)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#039;");
}

function asArray(value) {
  return Array.isArray(value) ? value : [];
}

function toNumber(value, fallback = 0) {
  const number = Number(value);
  return Number.isFinite(number) ? number : fallback;
}

function round(value) {
  return Math.round(value * 100) / 100;
}

function formatDateTime(value) {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "Date inconnue";
  return new Intl.DateTimeFormat("fr-FR", {
    day: "2-digit",
    month: "short",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit"
  }).format(date);
}

loadLatestAnalysis();
