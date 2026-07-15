const els = {
  historyList: document.querySelector("#historyList"),
  refreshHistoryBtn: document.querySelector("#refreshHistoryBtn"),
  historyTotal: document.querySelector("#historyTotal")
};

els.refreshHistoryBtn.addEventListener("click", async () => {
  await loadHistory();
});

async function loadHistory() {
  try {
    els.refreshHistoryBtn.disabled = true;
    const response = await fetch("/api/history");
    const payload = await readJson(response);
    if (!response.ok) {
      throw new Error(payload.error || "Historique indisponible.");
    }
    renderHistory(asArray(payload.items));
  } catch (error) {
    els.historyTotal.textContent = "0";
    els.historyList.innerHTML = `
      <div class="history-empty">
        <strong>Historique indisponible</strong>
        <p>${escapeHtml(error.message || "Impossible de charger les analyses sauvegardées.")}</p>
      </div>
    `;
  } finally {
    els.refreshHistoryBtn.disabled = false;
  }
}

function renderHistory(items) {
  els.historyTotal.textContent = String(items.length);
  els.historyList.innerHTML = "";

  if (!items.length) {
    els.historyList.innerHTML = `
      <div class="history-empty">
        <strong>Aucune analyse sauvegardee</strong>
        <p>L'historique se remplira automatiquement après la premiere analyse.</p>
      </div>
    `;
    return;
  }

  items.forEach((item) => {
    const summary = item.summary || {};
    const profile = summary.profileType || {};
    const classification = normalizeClassification(
      summary.classification || buildFallbackClassification(item, summary.keywordCoverage || {})
    );
    const matchedSkills = asArray(summary.matchedSkills).slice(0, 6);
    const missingSkills = asArray(summary.missingSkills).slice(0, 4);
    const actions = asArray(summary.actions).slice(0, 2);
    const card = document.createElement("article");
    card.className = "history-item";
    card.innerHTML = `
      <div class="history-main">
        <div>
          <span class="section-kicker">${escapeHtml(formatDateTime(item.createdAt))}</span>
          <h3>${escapeHtml(item.fileName)}</h3>
        </div>
        <p>${escapeHtml(item.verdict)} - ${escapeHtml(classification.label)} - ${escapeHtml(profile.label || item.profileType || "Profil generaliste")}</p>
        <div class="history-tags">
          <span class="chip classification-chip ${escapeHtml(classification.tone || "warn")}">${escapeHtml(classification.label)}</span>
          ${matchedSkills.map((skill) => `<span class="chip good">${escapeHtml(skill)}</span>`).join("")}
          ${missingSkills.map((skill) => `<span class="chip warn">${escapeHtml(skill)}</span>`).join("")}
        </div>
        ${actions.length ? `<ul class="history-actions">${actions.map((action) => `<li>${escapeHtml(action)}</li>`).join("")}</ul>` : ""}
      </div>
      <div class="history-score">
        <strong>${toNumber(item.finalScore).toFixed(1)}%</strong>
        <span>score final</span>
        <em>ATS ${toNumber(item.atsScore).toFixed(0)}%</em>
      </div>
    `;
    els.historyList.appendChild(card);
  });
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
  const probability = asArray(summary.probability).map((value) => toNumber(value));
  if (probability.length >= 2) {
    const prediction = toNumber(summary.prediction);
    const positiveProbability = Math.round(probability[1] * 10000) / 100;
    const negativeProbability = Math.round(probability[0] * 10000) / 100;
    const isPositive = prediction === 1;
    return {
      label: isPositive ? "Bon profil" : "Profil faible",
      score: isPositive ? positiveProbability : negativeProbability,
      tone: isPositive ? "good" : "bad"
    };
  }

  const finalScore = toNumber(item.finalScore);
  const threshold = toNumber(summary.threshold, 65);
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
    return { error: text.slice(0, 220) || "Reponse serveur invalide." };
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

loadHistory();
