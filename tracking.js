const els = {
  trackingList: document.querySelector("#trackingList"),
  trackingTotal: document.querySelector("#trackingTotal"),
  trackingStageStats: document.querySelector("#trackingStageStats"),
  trackingStatus: document.querySelector("#trackingStatus"),
  refreshTrackingBtn: document.querySelector("#refreshTrackingBtn")
};

let trackingPayload = { stages: [], counts: {}, items: [] };

els.refreshTrackingBtn.addEventListener("click", async () => {
  await loadTracking();
});

els.trackingList.addEventListener("click", async (event) => {
  const button = event.target.closest("button[data-stage], button[data-save-note]");
  if (!button) return;

  const card = button.closest("[data-analysis-id]");
  if (!card) return;

  const analysisId = card.dataset.analysisId;
  const notesInput = card.querySelector("[data-tracking-notes]");
  const currentItem = trackingPayload.items.find((item) => item.id === analysisId) || {};
  const stage = button.dataset.stage || (currentItem.tracking && currentItem.tracking.stage) || "selection";
  const notes = notesInput ? notesInput.value : "";

  await saveTracking(analysisId, stage, notes, button);
});

async function loadTracking() {
  setTrackingStatus("Chargement du suivi...", "");
  try {
    els.refreshTrackingBtn.disabled = true;
    const response = await fetch("/api/tracking");
    const payload = await readJson(response);
    if (!response.ok) {
      throw new Error(payload.error || "Suivi indisponible.");
    }
    renderTracking(payload);
    setTrackingStatus(payload.items.length ? "Suivi à jour." : "Aucun bon CV à suivre pour le moment.", payload.items.length ? "ok" : "");
  } catch (error) {
    els.trackingTotal.textContent = "0";
    els.trackingStageStats.innerHTML = "";
    els.trackingList.innerHTML = `
      <div class="history-empty">
        <strong>Suivi indisponible</strong>
        <p>${escapeHtml(error.message || "Impossible de charger le suivi des candidats.")}</p>
      </div>
    `;
    setTrackingStatus(error.message || "Suivi indisponible.", "error");
  } finally {
    els.refreshTrackingBtn.disabled = false;
  }
}

async function saveTracking(analysisId, stage, notes, sourceButton) {
  setTrackingStatus("Mise à jour du suivi...", "");
  setCardBusy(sourceButton, true);
  try {
    const response = await fetch("/api/tracking", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ analysisId, stage, notes })
    });
    const payload = await readJson(response);
    if (!response.ok) {
      throw new Error(payload.error || "Mise à jour impossible.");
    }
    renderTracking(payload);
    setTrackingStatus("Étape candidat sauvegardée.", "ok");
  } catch (error) {
    setTrackingStatus(error.message || "Mise à jour impossible.", "error");
  } finally {
    setCardBusy(sourceButton, false);
  }
}

function renderTracking(payload) {
  trackingPayload = {
    stages: asArray(payload.stages),
    counts: payload.counts || {},
    items: asArray(payload.items)
  };

  els.trackingTotal.textContent = String(trackingPayload.items.length);
  renderStageStats();
  renderCandidateList();
}

function renderStageStats() {
  const stages = trackingPayload.stages;
  if (!stages.length) {
    els.trackingStageStats.innerHTML = "";
    return;
  }

  els.trackingStageStats.innerHTML = stages.map((stage) => `
    <div class="tracking-stat">
      <span>${escapeHtml(stage.label)}</span>
      <strong>${toNumber(trackingPayload.counts[stage.id]).toFixed(0)}</strong>
    </div>
  `).join("");
}

function renderCandidateList() {
  els.trackingList.innerHTML = "";

  if (!trackingPayload.items.length) {
    els.trackingList.innerHTML = `
      <div class="history-empty">
        <strong>Aucun candidat retenu</strong>
        <p>Lancez une analyse avec un bon CV pour alimenter le suivi.</p>
      </div>
    `;
    return;
  }

  trackingPayload.items.forEach((item) => {
    const summary = item.summary || {};
    const profile = summary.profileType || {};
    const classification = normalizeClassification(summary.classification || buildFallbackClassification(item));
    const matchedSkills = asArray(summary.matchedSkills).slice(0, 5);
    const tracking = item.tracking || { stage: "selection", notes: "" };
    const activeStage = tracking.stage || "selection";
    const progress = stageProgress(activeStage);
    const card = document.createElement("article");
    card.className = "tracking-item";
    card.dataset.analysisId = item.id;
    card.innerHTML = `
      <div class="tracking-main">
        <div>
          <span class="section-kicker">${escapeHtml(formatDateTime(item.createdAt))}</span>
          <h3>${escapeHtml(item.fileName)}</h3>
        </div>
        <p>${escapeHtml(item.verdict)} - ${escapeHtml(classification.label)} - ${escapeHtml(profile.label || item.profileType || "Profil généraliste")}</p>
        <div class="history-tags">
          <span class="chip classification-chip ${escapeHtml(classification.tone || "good")}">${escapeHtml(classification.label)}</span>
          ${matchedSkills.map((skill) => `<span class="chip good">${escapeHtml(skill)}</span>`).join("")}
        </div>
        <div class="tracking-progress" style="--progress: ${progress}%">
          <span></span>
        </div>
        <div class="tracking-stage-options" aria-label="Étapes de recrutement">
          ${trackingPayload.stages.map((stage) => `
            <button class="stage-option ${stage.id === activeStage ? "is-active" : ""}" type="button" data-stage="${escapeHtml(stage.id)}">
              ${escapeHtml(stage.label)}
            </button>
          `).join("")}
        </div>
        <label class="tracking-notes">
          <span>Note recruteur</span>
          <textarea data-tracking-notes maxlength="600" placeholder="Exemple : entretien RH planifié, test technique envoyé...">${escapeHtml(tracking.notes || "")}</textarea>
        </label>
        <button class="ghost-btn tracking-save-note" type="button" data-save-note="1">Enregistrer la note</button>
      </div>
      <div class="tracking-score">
        <strong>${toNumber(item.finalScore).toFixed(1)}%</strong>
        <span>score final</span>
        <em>${escapeHtml(stageLabel(activeStage))}</em>
      </div>
    `;
    els.trackingList.appendChild(card);
  });
}

function setCardBusy(button, isBusy) {
  if (!button) return;
  const card = button.closest("[data-analysis-id]");
  if (!card) return;
  card.querySelectorAll("button").forEach((item) => {
    item.disabled = isBusy;
  });
}

function stageLabel(stageId) {
  const stage = trackingPayload.stages.find((item) => item.id === stageId);
  return stage ? stage.label : "CV retenu";
}

function stageProgress(stageId) {
  const stages = trackingPayload.stages;
  const index = stages.findIndex((stage) => stage.id === stageId);
  if (index <= 0 || stages.length <= 1) return 0;
  return Math.round((index / (stages.length - 1)) * 100);
}

function normalizeClassification(classification) {
  const prediction = toNumber(classification.prediction);
  const isPositive = classification.label === "Bon profil"
    || (classification.label !== "Profil faible" && prediction === 1);
  return {
    ...classification,
    label: isPositive ? "Bon profil" : "Profil faible",
    tone: isPositive ? "good" : "bad"
  };
}

function buildFallbackClassification(item) {
  const summary = item.summary || {};
  const finalScore = toNumber(item.finalScore);
  const threshold = toNumber(summary.threshold, 70);
  const isPositive = finalScore >= threshold;
  return {
    label: isPositive ? "Bon profil" : "Profil faible",
    score: Math.round(finalScore * 100) / 100,
    tone: isPositive ? "good" : "bad"
  };
}

async function readJson(response) {
  const text = await response.text();
  if (!text) return {};
  try {
    return JSON.parse(text);
  } catch (error) {
    return { error: text.slice(0, 220) || "Réponse serveur invalide." };
  }
}

function setTrackingStatus(message, tone) {
  els.trackingStatus.textContent = message || "";
  els.trackingStatus.className = `status ${tone || ""}`.trim();
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

loadTracking();
