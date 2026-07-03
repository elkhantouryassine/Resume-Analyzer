const SAMPLE_OFFER = `Data Analyst - CDI

Nous recherchons un profil capable de construire des tableaux de bord, automatiser des analyses et travailler avec les équipes métier.

Compétences attendues :
- Python, SQL, pandas, numpy
- Data visualisation avec matplotlib ou Power BI
- Machine learning, statistiques et analyse exploratoire
- Bonnes bases en communication, documentation et présentation des résultats
- Docker ou FastAPI est un plus`;

const els = {
  offerInput: document.querySelector("#offerInput"),
  cvFile: document.querySelector("#cvFile"),
  uploadZone: document.querySelector("#uploadZone"),
  uploadTitle: document.querySelector("#uploadTitle"),
  uploadHint: document.querySelector("#uploadHint"),
  sampleOfferBtn: document.querySelector("#sampleOfferBtn"),
  analyzeBtn: document.querySelector("#analyzeBtn"),
  statusBox: document.querySelector("#statusBox"),
  skillWeight: document.querySelector("#skillWeight"),
  skillWeightValue: document.querySelector("#skillWeightValue"),
  threshold: document.querySelector("#threshold"),
  thresholdValue: document.querySelector("#thresholdValue"),
  heroScore: document.querySelector("#heroScore"),
  scoreRing: document.querySelector("#scoreRing"),
  scoreValue: document.querySelector("#scoreValue"),
  verdictText: document.querySelector("#verdictText"),
  scoreCopy: document.querySelector("#scoreCopy"),
  skillScore: document.querySelector("#skillScore"),
  semanticScore: document.querySelector("#semanticScore"),
  healthScore: document.querySelector("#healthScore"),
  atsScore: document.querySelector("#atsScore"),
  keywordScore: document.querySelector("#keywordScore"),
  wordCount: document.querySelector("#wordCount"),
  matchedCount: document.querySelector("#matchedCount"),
  missingCount: document.querySelector("#missingCount"),
  matchedSkills: document.querySelector("#matchedSkills"),
  missingSkills: document.querySelector("#missingSkills"),
  profileLevel: document.querySelector("#profileLevel"),
  profileYears: document.querySelector("#profileYears"),
  profileEvidence: document.querySelector("#profileEvidence"),
  keywordCoverageLabel: document.querySelector("#keywordCoverageLabel"),
  keywordMatched: document.querySelector("#keywordMatched"),
  keywordMissing: document.querySelector("#keywordMissing"),
  interviewQuestions: document.querySelector("#interviewQuestions"),
  rewriteSuggestions: document.querySelector("#rewriteSuggestions"),
  semanticEngine: document.querySelector("#semanticEngine"),
  classifierEngine: document.querySelector("#classifierEngine"),
  processingTime: document.querySelector("#processingTime"),
  sectionsFound: document.querySelector("#sectionsFound"),
  sectionsMissing: document.querySelector("#sectionsMissing"),
  contactsList: document.querySelector("#contactsList"),
  contactStatus: document.querySelector("#contactStatus"),
  atsChecks: document.querySelector("#atsChecks"),
  reportSheet: document.querySelector("#reportSheet"),
  downloadMd: document.querySelector("#downloadMd"),
  downloadHtml: document.querySelector("#downloadHtml"),
  downloadTxt: document.querySelector("#downloadTxt"),
  ragFiles: document.querySelector("#ragFiles"),
  ragUploadZone: document.querySelector("#ragUploadZone"),
  ragUploadTitle: document.querySelector("#ragUploadTitle"),
  ragUploadHint: document.querySelector("#ragUploadHint"),
  ragIndexBtn: document.querySelector("#ragIndexBtn"),
  ragStatus: document.querySelector("#ragStatus"),
  ragCvCount: document.querySelector("#ragCvCount"),
  ragLibrary: document.querySelector("#ragLibrary"),
  ragQuestion: document.querySelector("#ragQuestion"),
  ragAskBtn: document.querySelector("#ragAskBtn"),
  ragMessages: document.querySelector("#ragMessages"),
  ragSuggestions: document.querySelector("#ragSuggestions"),
  ragResults: document.querySelector("#ragResults"),
  chatbotToggle: document.querySelector("#chatbotToggle"),
  chatbotPanel: document.querySelector("#chatbotPanel"),
  chatbotClose: document.querySelector("#chatbotClose")
};

let uploadedFile = null;
let lastAnalysis = null;
let ragSelectedFiles = [];

document.querySelectorAll(".nav-tab").forEach((button) => {
  button.addEventListener("click", () => {
    document.querySelectorAll(".nav-tab").forEach((tab) => tab.classList.remove("is-active"));
    button.classList.add("is-active");
    document.querySelector(`#${button.dataset.target}`).scrollIntoView({ behavior: "smooth", block: "start" });
  });
});

els.chatbotToggle.addEventListener("click", () => {
  const isOpen = els.chatbotPanel.classList.toggle("is-open");
  els.chatbotToggle.setAttribute("aria-expanded", String(isOpen));
  if (isOpen) {
    loadRagLibrary();
    window.setTimeout(() => els.ragQuestion.focus(), 90);
  }
});

els.chatbotClose.addEventListener("click", () => {
  closeChatbot();
});

document.addEventListener("keydown", (event) => {
  if (event.key === "Escape" && els.chatbotPanel.classList.contains("is-open")) {
    closeChatbot();
  }
});

els.sampleOfferBtn.addEventListener("click", () => {
  els.offerInput.value = SAMPLE_OFFER;
});

els.skillWeight.addEventListener("input", () => {
  els.skillWeightValue.textContent = `${els.skillWeight.value}%`;
});

els.threshold.addEventListener("input", () => {
  els.thresholdValue.textContent = `${els.threshold.value}%`;
});

els.cvFile.addEventListener("change", () => {
  setUploadedFile(els.cvFile.files[0]);
});

["dragenter", "dragover"].forEach((eventName) => {
  els.uploadZone.addEventListener(eventName, (event) => {
    event.preventDefault();
    els.uploadZone.classList.add("is-dragging");
  });
});

["dragleave", "drop"].forEach((eventName) => {
  els.uploadZone.addEventListener(eventName, (event) => {
    event.preventDefault();
    els.uploadZone.classList.remove("is-dragging");
  });
});

els.uploadZone.addEventListener("drop", (event) => {
  const file = event.dataTransfer.files[0];
  if (file) {
    els.cvFile.files = event.dataTransfer.files;
    setUploadedFile(file);
  }
});

els.analyzeBtn.addEventListener("click", async () => {
  await analyze();
});

els.downloadMd.addEventListener("click", () => {
  if (lastAnalysis) downloadFile("rapport-cv.md", buildMarkdownReport(lastAnalysis), "text/markdown");
});

els.downloadHtml.addEventListener("click", () => {
  if (lastAnalysis) downloadFile("rapport-cv.html", buildHtmlDocument(lastAnalysis), "text/html");
});

els.downloadTxt.addEventListener("click", () => {
  if (lastAnalysis) downloadFile("cv-extrait.txt", lastAnalysis.cvText, "text/plain");
});

els.ragFiles.addEventListener("change", () => {
  setRagFiles(Array.from(els.ragFiles.files || []));
});

["dragenter", "dragover"].forEach((eventName) => {
  els.ragUploadZone.addEventListener(eventName, (event) => {
    event.preventDefault();
    els.ragUploadZone.classList.add("is-dragging");
  });
});

["dragleave", "drop"].forEach((eventName) => {
  els.ragUploadZone.addEventListener(eventName, (event) => {
    event.preventDefault();
    els.ragUploadZone.classList.remove("is-dragging");
  });
});

els.ragUploadZone.addEventListener("drop", (event) => {
  const files = Array.from(event.dataTransfer.files || []);
  if (files.length) {
    setRagFiles(files);
  }
});

els.ragIndexBtn.addEventListener("click", async () => {
  await indexRagFiles();
});

els.ragAskBtn.addEventListener("click", async () => {
  await askRagBot();
});

els.ragSuggestions.addEventListener("click", async (event) => {
  const button = event.target.closest("button[data-question]");
  if (!button) return;
  els.ragQuestion.value = button.dataset.question;
  await askRagBot();
});

els.ragQuestion.addEventListener("keydown", async (event) => {
  if (event.key === "Enter" && !event.shiftKey) {
    event.preventDefault();
    await askRagBot();
  }
});

function closeChatbot() {
  els.chatbotPanel.classList.remove("is-open");
  els.chatbotToggle.setAttribute("aria-expanded", "false");
}

function setUploadedFile(file) {
  uploadedFile = file || null;
  if (!uploadedFile) return;
  els.uploadTitle.textContent = uploadedFile.name;
  els.uploadHint.textContent = `${formatBytes(uploadedFile.size)} chargé`;
  setStatus("Fichier prêt pour analyse.", "ok");
}

function setRagFiles(files) {
  ragSelectedFiles = files.filter((file) => /\.(pdf|docx|txt)$/i.test(file.name));
  if (!ragSelectedFiles.length) {
    els.ragUploadTitle.textContent = "Importer des CV";
    els.ragUploadHint.textContent = "Formats acceptes : PDF, DOCX ou TXT";
    setRagStatus("Aucun fichier compatible selectionne.", "error");
    return;
  }

  els.ragUploadTitle.textContent = `${ragSelectedFiles.length} CV selectionne(s)`;
  els.ragUploadHint.textContent = ragSelectedFiles.map((file) => file.name).slice(0, 3).join(", ");
  setRagStatus("CV prets pour indexation vectorielle.", "ok");
}

async function indexRagFiles() {
  if (!ragSelectedFiles.length) {
    setRagStatus("Selectionnez plusieurs CV avant d'indexer.", "error");
    return;
  }

  try {
    setRagStatus("Indexation RAG en cours...", "");
    els.ragIndexBtn.disabled = true;
    const formData = new FormData();
    ragSelectedFiles.forEach((file) => {
      formData.append("cv_files", file);
    });

    const response = await fetch("/api/rag/upload", {
      method: "POST",
      body: formData
    });
    const payload = await readJson(response);
    if (!response.ok) {
      const details = asArray(payload.errors).map((item) => `${item.filename}: ${item.error}`).join(" | ");
      throw new Error(payload.error || details || "Indexation impossible.");
    }

    renderRagLibrary(payload.library);
    const indexedCount = payload.indexed ? payload.indexed.length : 0;
    const errorCount = payload.errors ? payload.errors.length : 0;
    setRagStatus(`${indexedCount} CV indexe(s) dans la base vectorielle${errorCount ? `, ${errorCount} erreur(s)` : ""}.`, "ok");
    ragSelectedFiles = [];
    els.ragFiles.value = "";
    els.ragUploadTitle.textContent = "Ajouter des CV";
    els.ragUploadHint.textContent = "PDF, DOCX ou TXT";
  } catch (error) {
    setRagStatus(error.message || "Indexation impossible.", "error");
  } finally {
    els.ragIndexBtn.disabled = false;
  }
}

async function askRagBot() {
  const question = els.ragQuestion.value.trim();
  if (!question) {
    setRagStatus("Posez une question avant d'interroger le chatbot.", "error");
    return;
  }

  try {
    appendChatMessage("user", "Vous", question);
    appendChatMessage("bot", "Assistant RAG", "Recherche dans la base vectorielle...");
    els.ragQuestion.value = "";
    els.ragAskBtn.disabled = true;

    const response = await fetch("/api/rag/chat", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ question, topK: 5 })
    });
    const payload = await readJson(response);
    if (!response.ok) {
      throw new Error(payload.error || "Chatbot RAG indisponible.");
    }

    replaceLastBotMessage(payload.answer || "Je n'ai pas pu produire une reponse exploitable.");
    renderRagResults(payload.results || []);
    renderRagSuggestions(payload.suggestions || []);
    if (typeof payload.indexedCount === "number") {
      els.ragCvCount.textContent = `${payload.indexedCount} CV`;
    }
    setRagStatus(payload.indexedCount ? "Recherche terminee." : "Importez des CV pour activer la recherche.", payload.indexedCount ? "ok" : "");
  } catch (error) {
    replaceLastBotMessage(error.message || "Chatbot RAG indisponible.");
    setRagStatus(error.message || "Chatbot RAG indisponible.", "error");
  } finally {
    els.ragAskBtn.disabled = false;
  }
}

async function loadRagLibrary() {
  try {
    const response = await fetch("/api/rag/cvs");
    if (!response.ok) return;
    renderRagLibrary(await readJson(response));
  } catch (error) {
    setRagStatus("Base RAG non chargee pour le moment.", "");
  }
}

function renderRagLibrary(library) {
  const cvs = library && Array.isArray(library.cvs) ? library.cvs : [];
  els.ragCvCount.textContent = `${cvs.length} CV`;
  els.ragLibrary.innerHTML = "";

  if (!cvs.length) {
    els.ragLibrary.innerHTML = `<p class="empty-note">Aucun CV indexe dans la base vectorielle.</p>`;
    return;
  }

  cvs.slice(0, 6).forEach((cv) => {
    const card = document.createElement("div");
    card.className = "rag-library-item";
    card.innerHTML = `
      <strong>${escapeHtml(cv.filename)}</strong>
      <span>${cv.wordCount || 0} mots</span>
      <p>${escapeHtml((cv.skills || []).slice(0, 5).join(", ") || "Competences non detectees")}</p>
    `;
    els.ragLibrary.appendChild(card);
  });
}

function appendChatMessage(type, author, text) {
  const message = document.createElement("div");
  message.className = `chat-message ${type}`;
  message.innerHTML = `
    <strong>${escapeHtml(author)}</strong>
    <p>${escapeHtml(text).replace(/\n/g, "<br>")}</p>
  `;
  els.ragMessages.appendChild(message);
  els.ragMessages.scrollTop = els.ragMessages.scrollHeight;
}

function replaceLastBotMessage(text) {
  const messages = Array.from(els.ragMessages.querySelectorAll(".chat-message.bot"));
  const last = messages[messages.length - 1];
  if (!last) {
    appendChatMessage("bot", "Assistant RAG", text);
    return;
  }
  const paragraph = last.querySelector("p");
  paragraph.innerHTML = escapeHtml(text).replace(/\n/g, "<br>");
}

function renderRagResults(results) {
  els.ragResults.innerHTML = "";
  if (!results.length) {
    els.ragResults.innerHTML = `<p class="empty-note">Aucun CV correspondant trouve.</p>`;
    return;
  }

  results.forEach((result) => {
    const card = document.createElement("article");
    card.className = "rag-result-card";
    const snippet = result.snippets && result.snippets.length ? result.snippets[0].text : "";
    const keywords = result.snippets && result.snippets.length ? asArray(result.snippets[0].keywordHits) : [];
    const chips = asArray(result.matchedSkills).length ? asArray(result.matchedSkills) : keywords;
    const contacts = result.contacts || {};
    const contactLine = [contacts.email, contacts.phone, contacts.linkedin, contacts.github].filter(Boolean).join(" | ");
    card.innerHTML = `
      <div class="rag-result-head">
        <div>
          <strong>${escapeHtml(result.filename)}</strong>
          <span>${escapeHtml(contactLine || "Coordonnees non detectees")}</span>
          <span class="rag-confidence">${escapeHtml(result.confidenceLabel || "Correspondance estimee")}</span>
        </div>
        <em>${toNumber(result.score).toFixed(1)}%</em>
      </div>
      <div class="chip-list compact">
        ${chips.slice(0, 8).map((skill) => `<span class="chip good">${escapeHtml(skill)}</span>`).join("") || `<span class="chip">Similarite texte</span>`}
      </div>
      <p>${escapeHtml(snippet.slice(0, 360))}${snippet.length > 360 ? "..." : ""}</p>
    `;
    els.ragResults.appendChild(card);
  });
}

function renderRagSuggestions(suggestions) {
  els.ragSuggestions.innerHTML = "";
  asArray(suggestions).slice(0, 3).forEach((suggestion) => {
    const button = document.createElement("button");
    button.type = "button";
    button.dataset.question = suggestion;
    button.textContent = suggestion;
    els.ragSuggestions.appendChild(button);
  });
}

async function analyze() {
  const offerText = els.offerInput.value.trim();
  if (!offerText) {
    setStatus("Veuillez coller une offre d'emploi.", "error");
    return;
  }
  if (!uploadedFile) {
    setStatus("Veuillez importer un CV PDF, DOCX ou TXT.", "error");
    return;
  }

  try {
    setStatus("Analyse Python en cours...", "");
    const formData = new FormData();
    formData.append("offer_text", offerText);
    formData.append("cv_file", uploadedFile);
    formData.append("skill_weight", els.skillWeight.value);
    formData.append("threshold", els.threshold.value);

    const response = await fetch("/api/analyze", {
      method: "POST",
      body: formData
    });
    const payload = await response.json();
    if (!response.ok) {
      throw new Error(payload.error || "Analyse impossible.");
    }

    const analysis = normalizeAnalysis(payload);
    lastAnalysis = analysis;
    renderAnalysis(analysis);
    setStatus(`Analyse terminée pour ${uploadedFile.name}.`, "ok");
  } catch (error) {
    setStatus(error.message || "Analyse impossible.", "error");
  }
}

function normalizeAnalysis(payload) {
  const matchedSkills = asArray(payload.matchedSkills);
  const missingSkills = asArray(payload.missingSkills);
  const offerSkills = asArray(payload.offerSkills);
  const cvSkills = asArray(payload.cvSkills);
  const sections = payload.sections || {};
  const contacts = payload.contacts || {};
  const keywordCoverage = payload.keywordCoverage || buildKeywordCoverage(matchedSkills, missingSkills, offerSkills);
  const actions = asArray(payload.actions);

  return {
    fileName: payload.fileName || "CV analyse",
    cvText: payload.cvText || "",
    offerSkills,
    cvSkills,
    matchedSkills,
    missingSkills,
    skillScore: toNumber(payload.skillScore),
    semanticScore: toNumber(payload.semanticScore),
    skillWeight: toNumber(payload.skillWeight, Number(els.skillWeight.value || 60)),
    threshold: toNumber(payload.threshold, Number(els.threshold.value || 70)),
    finalScore: toNumber(payload.finalScore),
    contacts,
    sections: {
      found: asArray(sections.found),
      missing: asArray(sections.missing)
    },
    wordCount: toNumber(payload.wordCount),
    healthScore: toNumber(payload.healthScore),
    atsScore: toNumber(payload.atsScore, toNumber(payload.healthScore)),
    atsChecks: asArray(payload.atsChecks).length ? asArray(payload.atsChecks) : buildFallbackAtsChecks(payload),
    keywordCoverage,
    experience: payload.experience || {
      level: "Non detecte",
      years: 0,
      evidence: "Aucune duree explicite detectee dans le CV."
    },
    interviewQuestions: asArray(payload.interviewQuestions).length
      ? asArray(payload.interviewQuestions)
      : buildFallbackQuestions(matchedSkills, missingSkills),
    rewriteSuggestions: asArray(payload.rewriteSuggestions).length
      ? asArray(payload.rewriteSuggestions)
      : (actions.length ? actions : ["Ajouter les competences manquantes avec des exemples concrets."]),
    verdict: payload.verdict || "Analyse terminee",
    actions,
    prediction: toNumber(payload.prediction),
    probability: asArray(payload.probability),
    aiEngines: payload.aiEngines || {
      semantic: "Moteur de similarite disponible",
      classifier: payload.probability ? "Modele ML local" : "Non renseigne",
      semanticReady: Boolean(payload.semanticScore),
      classifierReady: Boolean(payload.probability)
    },
    processingTimeMs: toNumber(payload.processingTimeMs),
    report: payload.report || ""
  };
}

function buildKeywordCoverage(matchedSkills, missingSkills, offerSkills) {
  const matched = matchedSkills.length ? matchedSkills : offerSkills.filter((skill) => !missingSkills.includes(skill));
  const missing = missingSkills;
  const total = matched.length + missing.length;
  return {
    score: total ? round((matched.length / total) * 100) : 0,
    matched,
    missing,
    total
  };
}

function buildFallbackAtsChecks(payload) {
  const sections = payload.sections || {};
  const contacts = payload.contacts || {};
  const foundSections = asArray(sections.found);
  const cvSkills = asArray(payload.cvSkills);
  return [
    {
      label: "Coordonnees",
      status: Object.values(contacts).some(Boolean) ? "ok" : "warn",
      detail: Object.values(contacts).some(Boolean) ? "Coordonnees detectees." : "Coordonnees non detectees."
    },
    {
      label: "Sections cles",
      status: foundSections.length >= 4 ? "ok" : "warn",
      detail: `${foundSections.length} section(s) standard detectee(s).`
    },
    {
      label: "Competences",
      status: cvSkills.length >= 6 ? "ok" : "warn",
      detail: `${cvSkills.length} competence(s) reconnue(s).`
    }
  ];
}

function buildFallbackQuestions(matchedSkills, missingSkills) {
  const questions = missingSkills.slice(0, 3).map((skill) => (
    `Comment le candidat peut-il demontrer ou acquerir rapidement la competence ${skill} ?`
  ));
  matchedSkills.slice(0, 2).forEach((skill) => {
    questions.push(`Quel projet concret prouve le niveau du candidat sur ${skill} ?`);
  });
  return questions.length ? questions : ["Quel resultat mesurable le candidat peut-il livrer pendant les 90 premiers jours ?"];
}

function renderAnalysis(analysis) {
  const degree = Math.max(0, Math.min(analysis.finalScore, 100)) * 3.6;
  const ringColor = analysis.finalScore >= analysis.threshold ? "var(--green)" : analysis.finalScore >= 50 ? "var(--amber)" : "var(--red)";
  els.heroScore.textContent = `${analysis.finalScore}%`;
  els.scoreValue.textContent = `${analysis.finalScore}%`;
  els.scoreRing.style.background = `conic-gradient(${ringColor} ${degree}deg, #e5e7eb 0deg)`;
  els.verdictText.textContent = analysis.verdict;
  els.scoreCopy.textContent = `Score combiné : ${analysis.skillWeight}% compétences et ${100 - analysis.skillWeight}% proximité sémantique.`;
  els.skillScore.textContent = `${analysis.skillScore}%`;
  els.semanticScore.textContent = `${analysis.semanticScore}%`;
  els.healthScore.textContent = `${analysis.healthScore}%`;
  els.atsScore.textContent = `${analysis.atsScore}%`;
  els.keywordScore.textContent = `${analysis.keywordCoverage.score}%`;
  els.wordCount.textContent = analysis.wordCount;
  els.matchedCount.textContent = analysis.matchedSkills.length;
  els.missingCount.textContent = analysis.missingSkills.length;
  renderChips(els.matchedSkills, analysis.matchedSkills, "good", "Aucune compétence commune détectée.");
  renderChips(els.missingSkills, analysis.missingSkills, "warn", "Aucun écart majeur détecté.");
  renderChips(els.sectionsFound, analysis.sections.found, "good", "Aucune section standard détectée.");
  renderChips(els.sectionsMissing, analysis.sections.missing, "warn", "Toutes les sections principales sont présentes.");
  renderProfile(analysis.experience);
  renderChips(els.keywordMatched, analysis.keywordCoverage.matched, "good", "Aucun mot-clé prioritaire détecté.");
  renderChips(els.keywordMissing, analysis.keywordCoverage.missing, "warn", "Tous les mots-clés prioritaires sont couverts.");
  els.keywordCoverageLabel.textContent = `${analysis.keywordCoverage.score}%`;
  renderList(els.interviewQuestions, analysis.interviewQuestions, true);
  renderList(els.rewriteSuggestions, analysis.rewriteSuggestions, false);
  renderAiEngines(analysis.aiEngines, analysis.processingTimeMs);
  renderContacts(analysis.contacts);
  renderAtsChecks(analysis.atsChecks);
  els.reportSheet.innerHTML = buildReportMarkup(analysis);
  [els.downloadMd, els.downloadHtml, els.downloadTxt].forEach((button) => { button.disabled = false; });
}

function renderChips(container, items, tone, emptyText) {
  container.innerHTML = "";
  const values = items.length ? items : [emptyText];
  values.forEach((item) => {
    const chip = document.createElement("span");
    chip.className = `chip ${items.length ? tone : ""}`;
    chip.textContent = item;
    container.appendChild(chip);
  });
}

function renderContacts(contacts) {
  els.contactsList.innerHTML = "";
  let count = 0;
  Object.entries(contacts).forEach(([label, value]) => {
    const item = document.createElement("li");
    item.textContent = `${label}: ${value || "Non détecté"}`;
    if (value) count += 1;
    els.contactsList.appendChild(item);
  });
  els.contactStatus.textContent = `${count}/4 détectées`;
}

function renderProfile(experience) {
  els.profileLevel.textContent = experience.level;
  els.profileYears.textContent = `${experience.years} an(s)`;
  els.profileEvidence.textContent = experience.evidence;
}

function renderList(container, items, ordered) {
  container.innerHTML = "";
  const values = items.length ? items : ["Aucune recommandation disponible."];
  values.forEach((value) => {
    const item = document.createElement("li");
    item.textContent = value;
    container.appendChild(item);
  });
  container.classList.toggle("is-ordered", Boolean(ordered));
}

function renderAtsChecks(checks) {
  els.atsChecks.innerHTML = "";
  checks.forEach((check) => {
    const item = document.createElement("div");
    item.className = `check-item ${check.status === "ok" ? "good" : "warn"}`;
    item.innerHTML = `
      <span>${check.status === "ok" ? "OK" : "À corriger"}</span>
      <div>
        <strong>${escapeHtml(check.label)}</strong>
        <p>${escapeHtml(check.detail)}</p>
      </div>
    `;
    els.atsChecks.appendChild(item);
  });
}

function renderAiEngines(engines, processingTimeMs) {
  els.semanticEngine.textContent = engines.semantic;
  els.classifierEngine.textContent = engines.classifier;
  els.processingTime.textContent = `${processingTimeMs} ms`;
  els.semanticEngine.className = engines.semanticReady ? "engine-ok" : "engine-warn";
  els.classifierEngine.className = engines.classifierReady ? "engine-ok" : "engine-warn";
}

function buildReportMarkup(analysis) {
  return `
    <div class="report-title">
      <span class="section-kicker">Synthèse</span>
      <h2>${escapeHtml(analysis.verdict)}</h2>
      <p><strong>${escapeHtml(analysis.fileName)}</strong> · ${analysis.wordCount} mots détectés · seuil ${analysis.threshold}%</p>
    </div>

    <div class="report-summary-grid">
      ${reportMetric("Score final", `${analysis.finalScore}%`)}
      ${reportMetric("Compétences", `${analysis.skillScore}%`)}
      ${reportMetric("Sémantique", `${analysis.semanticScore}%`)}
      ${reportMetric("Santé du CV", `${analysis.healthScore}%`)}
      ${reportMetric("ATS", `${analysis.atsScore}%`)}
      ${reportMetric("Mots-clés", `${analysis.keywordCoverage.score}%`)}
      ${reportMetric("Durée", `${analysis.processingTimeMs} ms`)}
    </div>

    <div class="report-section">
      <h3>Compétences correspondantes</h3>
      <div class="report-tag-grid">
        ${buildReportTags(analysis.matchedSkills, "good", "Aucune compétence commune détectée.")}
      </div>
    </div>

    <div class="report-section">
      <h3>Compétences à renforcer</h3>
      <div class="report-tag-grid">
        ${buildReportTags(analysis.missingSkills, "warn", "Aucun écart majeur détecté.")}
      </div>
    </div>

    <div class="report-section">
      <h3>Plan d'action</h3>
      <ul class="report-actions">${analysis.actions.map((item) => `<li>${escapeHtml(item)}</li>`).join("")}</ul>
    </div>

    <div class="report-section">
      <h3>Questions d'entretien suggérées</h3>
      <ul class="report-actions">${analysis.interviewQuestions.map((item) => `<li>${escapeHtml(item)}</li>`).join("")}</ul>
    </div>

    <div class="report-section">
      <h3>Améliorations prioritaires</h3>
      <ul class="report-actions">${analysis.rewriteSuggestions.map((item) => `<li>${escapeHtml(item)}</li>`).join("")}</ul>
    </div>

    <div class="report-section">
      <h3>Transparence IA</h3>
      <ul class="report-actions">
        <li>Sémantique : ${escapeHtml(analysis.aiEngines.semantic)}</li>
        <li>Prédiction : ${escapeHtml(analysis.aiEngines.classifier)}</li>
        <li>Durée réelle : ${analysis.processingTimeMs} ms</li>
      </ul>
    </div>
  `;
}

function reportMetric(label, value) {
  return `
    <div class="report-metric">
      <span>${escapeHtml(label)}</span>
      <strong>${escapeHtml(value)}</strong>
    </div>
  `;
}

function buildReportTags(items, tone, emptyText) {
  const values = items.length ? items : [emptyText];
  return values
    .map((item) => `<span class="report-tag ${items.length ? tone : ""}">${escapeHtml(item)}</span>`)
    .join("");
}

function buildMarkdownReport(analysis) {
  return `# Rapport d'analyse du CV

## Décision
Verdict : ${analysis.verdict}
Fichier : ${analysis.fileName}
Seuil shortlist : ${analysis.threshold}%

## Scores
- Score final : ${analysis.finalScore}%
- Score compétences : ${analysis.skillScore}%
- Score sémantique : ${analysis.semanticScore}%
- Santé du CV : ${analysis.healthScore}%
- Score ATS : ${analysis.atsScore}%
- Couverture mots-clés : ${analysis.keywordCoverage.score}%
- Mots détectés : ${analysis.wordCount}
- Durée réelle : ${analysis.processingTimeMs} ms

## Compétences
Correspondances : ${analysis.matchedSkills.join(", ") || "Aucune"}
Manquantes : ${analysis.missingSkills.join(", ") || "Aucune"}

## Diagnostic
Sections présentes : ${analysis.sections.found.join(", ") || "Aucune"}
Sections à renforcer : ${analysis.sections.missing.join(", ") || "Aucune"}
Niveau estimé : ${analysis.experience.level} (${analysis.experience.years} an(s))

## Mots-clés
Présents : ${analysis.keywordCoverage.matched.join(", ") || "Aucun"}
À intégrer : ${analysis.keywordCoverage.missing.join(", ") || "Aucun"}

## Plan d'action
${analysis.actions.map((item) => `- ${item}`).join("\n")}

## Questions d'entretien
${analysis.interviewQuestions.map((item) => `- ${item}`).join("\n")}

## Améliorations prioritaires
${analysis.rewriteSuggestions.map((item) => `- ${item}`).join("\n")}

## Transparence IA
- Sémantique : ${analysis.aiEngines.semantic}
- Prédiction : ${analysis.aiEngines.classifier}
- Durée réelle : ${analysis.processingTimeMs} ms
`;
}

function buildHtmlDocument(analysis) {
  return `<!doctype html>
<html lang="fr">
<head>
  <meta charset="utf-8">
  <title>Rapport CV</title>
  <style>
    body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; color: #111827; margin: 48px; line-height: 1.55; background: #f4f6f8; }
    .sheet { max-width: 860px; margin: auto; }
    h1 { font-size: 42px; }
    h2 { margin-top: 0; }
    .report-title, .report-summary-grid, .report-section { background: #fff; border: 1px solid #e8edf3; border-radius: 14px; padding: 20px; margin-bottom: 16px; }
    .report-summary-grid { display: grid; grid-template-columns: repeat(4, 1fr); gap: 12px; }
    .report-metric { background: #f8fafc; border-radius: 10px; padding: 14px; }
    .report-metric span { display: block; color: #667085; font-size: 13px; }
    .report-metric strong { display: block; margin-top: 8px; font-size: 24px; }
    .report-tag-grid { display: flex; flex-wrap: wrap; gap: 8px; }
    .report-tag { padding: 7px 10px; border-radius: 999px; background: #f8fafc; border: 1px solid #e8edf3; }
    .report-tag.good { color: #12805c; background: rgba(18, 128, 92, .1); }
    .report-tag.warn { color: #a15c07; background: rgba(161, 92, 7, .1); }
  </style>
</head>
<body><main class="sheet"><h1>Rapport d'analyse du CV</h1>${buildReportMarkup(analysis)}</main></body>
</html>`;
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

function setStatus(message, tone) {
  els.statusBox.textContent = message;
  els.statusBox.className = `status ${tone || ""}`;
}

function setRagStatus(message, tone) {
  els.ragStatus.textContent = message;
  els.ragStatus.className = `status ${tone || ""}`;
}

async function readJson(response) {
  const text = await response.text();
  if (!text) return {};
  const trimmed = text.trim();
  const lowerText = trimmed.toLowerCase();
  if (lowerText.startsWith("<!doctype") || lowerText.startsWith("<html")) {
    return {
      error: `Le serveur Python de l'application ne repond pas correctement sur cette adresse (${response.status}). Relancez l'application avec python app.py, puis rechargez la page.`
    };
  }
  try {
    return JSON.parse(text);
  } catch (error) {
    return { error: trimmed.slice(0, 220) || "Reponse serveur invalide." };
  }
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

function formatBytes(bytes) {
  if (!bytes) return "0 B";
  const units = ["B", "KB", "MB", "GB"];
  const index = Math.min(Math.floor(Math.log(bytes) / Math.log(1024)), units.length - 1);
  return `${(bytes / 1024 ** index).toFixed(index ? 1 : 0)} ${units[index]}`;
}

loadRagLibrary();
