(() => {
  const DEFAULT_RAG_SUGGESTIONS = [
    "Trouve le meilleur profil Python SQL Power BI",
    "Compare les candidats les plus proches du poste",
    "Quels CV manquent de machine learning ?"
  ];

  const WIDGET_HTML = `
    <button class="chatbot-launcher" id="chatbotToggle" type="button" aria-label="Ouvrir le chatbot RAG" aria-expanded="false" aria-controls="chatbotPanel">
      <img class="chatbot-logo" src="/assets/assistant-logo.svg" alt="" aria-hidden="true">
      <span class="chatbot-pulse" aria-hidden="true"></span>
    </button>

    <aside class="chatbot-popover" id="chatbotPanel" aria-label="Chatbot RAG">
      <div class="chatbot-header">
        <div class="chatbot-title">
          <img class="chatbot-header-logo" src="/assets/assistant-logo.svg" alt="" aria-hidden="true">
          <div>
            <span class="section-kicker">Assistant RAG</span>
            <h2>Recherche multi-CV</h2>
            <p class="chatbot-subtitle" id="ragMode">Base vectorielle prête</p>
          </div>
        </div>
        <div class="chatbot-header-actions">
          <span class="pill" id="ragCvCount">0 CV</span>
          <button class="chatbot-close" id="chatbotClose" type="button" aria-label="Fermer le chatbot">×</button>
        </div>
      </div>

      <div class="chatbot-body">
        <section class="chatbot-upload rag-library-panel" aria-label="CV indexés">
          <div class="rag-library" id="ragLibrary"></div>
          <p class="status" id="ragStatus">Les CV analysés apparaissent ici.</p>
        </section>

        <section class="chatbot-conversation" aria-label="Conversation avec le chatbot">
          <div class="rag-chat-head">
            <div>
              <span class="section-kicker">Conversation</span>
              <strong>Assistant de recherche</strong>
            </div>
            <span class="rag-live-dot" aria-hidden="true"></span>
          </div>
          <div class="chat-box" id="ragMessages">
            <div class="chat-message bot">
              <strong>Assistant RAG</strong>
              <p>Je peux rechercher dans les CV indexés et classer les meilleurs profils selon votre besoin.</p>
            </div>
          </div>

          <div class="rag-question-row">
            <textarea id="ragQuestion" rows="2" placeholder="Ex : candidats avec Python, SQL et Power BI"></textarea>
            <button class="primary-btn" id="ragAskBtn" type="button">Envoyer</button>
          </div>

          <div class="rag-suggestions" id="ragSuggestions"></div>
          <div class="rag-results" id="ragResults"></div>
        </section>
      </div>
    </aside>
  `;

  let els = {};
  let ragIndexedCount = 0;

  function initRagWidget() {
    if (!document.querySelector("#chatbotToggle")) {
      document.body.insertAdjacentHTML("beforeend", WIDGET_HTML);
    }

    els = {
      ragStatus: document.querySelector("#ragStatus"),
      ragMode: document.querySelector("#ragMode"),
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

    if (!els.chatbotToggle || !els.chatbotPanel) return;

    els.chatbotToggle.addEventListener("click", () => {
      const isOpen = els.chatbotPanel.classList.toggle("is-open");
      els.chatbotToggle.setAttribute("aria-expanded", String(isOpen));
      if (isOpen) {
        loadRagLibrary();
        window.setTimeout(() => els.ragQuestion?.focus(), 90);
      }
    });

    els.chatbotClose?.addEventListener("click", closeChatbot);

    document.addEventListener("keydown", (event) => {
      if (event.key === "Escape" && els.chatbotPanel.classList.contains("is-open")) {
        closeChatbot();
      }
    });

    els.ragAskBtn?.addEventListener("click", askRagBot);

    els.ragSuggestions?.addEventListener("click", async (event) => {
      const button = event.target.closest("button[data-question]");
      if (!button) return;
      els.ragQuestion.value = button.dataset.question;
      await askRagBot();
    });

    els.ragQuestion?.addEventListener("keydown", async (event) => {
      if (event.key === "Enter" && !event.shiftKey) {
        event.preventDefault();
        await askRagBot();
      }
    });

    renderRagSuggestions(DEFAULT_RAG_SUGGESTIONS);
    loadRagLibrary();
  }

  function closeChatbot() {
    els.chatbotPanel.classList.remove("is-open");
    els.chatbotToggle.setAttribute("aria-expanded", "false");
  }

  async function askRagBot() {
    const question = els.ragQuestion.value.trim();
    if (!question) {
      setRagStatus("Posez une question avant d'interroger le chatbot.", "error");
      els.ragQuestion.focus();
      return;
    }
    if (!ragIndexedCount) {
      const message = "Aucun CV n'est encore indexé. Analysez un CV depuis la page Analyse pour l'ajouter à la base RAG.";
      appendChatMessage("bot", "Assistant RAG", message);
      setRagStatus(message, "error");
      return;
    }

    try {
      appendChatMessage("user", "Vous", question);
      appendChatMessage("bot is-loading", "Assistant RAG", "Recherche dans la base vectorielle...");
      els.ragQuestion.value = "";
      setRagMode("Recherche en cours...");
      els.chatbotPanel.classList.add("is-busy");
      els.ragAskBtn.disabled = true;

      const response = await fetch("/api/rag/chat", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ question, topK: 5 })
      });
      const payload = await readJson(response);
      if (!response.ok) throw new Error(payload.error || "Chatbot RAG indisponible.");

      replaceLastBotMessage(payload.answer || "Je n'ai pas pu produire une réponse exploitable.");
      renderRagResults(payload.results || []);
      renderRagSuggestions(payload.suggestions || []);
      if (typeof payload.indexedCount === "number") {
        ragIndexedCount = payload.indexedCount;
        els.ragCvCount.textContent = `${payload.indexedCount} CV`;
      }
      setRagStatus(payload.indexedCount ? `Recherche terminée. ${formatEmbeddingEngine(payload.embedding)}` : "Analysez un CV pour activer la recherche.", payload.indexedCount ? "ok" : "");
    } catch (error) {
      replaceLastBotMessage(error.message || "Chatbot RAG indisponible.");
      setRagStatus(error.message || "Chatbot RAG indisponible.", "error");
    } finally {
      els.ragAskBtn.disabled = false;
      els.chatbotPanel.classList.remove("is-busy");
      setRagMode(ragIndexedCount ? "Recherche prête" : "Analysez un CV");
    }
  }

  async function loadRagLibrary() {
    try {
      const response = await fetch("/api/rag/cvs");
      if (!response.ok) return;
      renderRagLibrary(await readJson(response));
    } catch (error) {
      setRagStatus("Base RAG non chargée pour le moment.", "");
    }
  }

  function renderRagLibrary(library) {
    const cvs = library && Array.isArray(library.cvs) ? library.cvs : [];
    ragIndexedCount = cvs.length;
    els.ragCvCount.textContent = `${cvs.length} CV`;
    els.ragLibrary.innerHTML = "";
    setRagMode(cvs.length ? "Recherche prête" : "Analysez un CV");

    if (!cvs.length) {
      els.ragLibrary.innerHTML = `
        <div class="rag-empty-state">
          <strong>Base vide</strong>
          <p>Analysez un CV pour l'ajouter à la base vectorielle.</p>
        </div>
      `;
      renderRagSuggestions(DEFAULT_RAG_SUGGESTIONS);
      return;
    }

    cvs.slice(0, 6).forEach((cv) => {
      const card = document.createElement("div");
      card.className = "rag-library-item";
      const skills = Array.isArray(cv.skills) ? cv.skills : String(cv.skills || "").split(/\s+/).filter(Boolean);
      card.innerHTML = `
        <strong>${escapeHtml(cv.filename)}</strong>
        <span>${cv.wordCount || 0} mots</span>
        <p>${escapeHtml(skills.slice(0, 5).join(", ") || "Compétences non détectées")}</p>
      `;
      els.ragLibrary.appendChild(card);
    });
    if (cvs.length > 6) {
      const more = document.createElement("p");
      more.className = "empty-note";
      more.textContent = `+ ${cvs.length - 6} autre(s) CV indexé(s)`;
      els.ragLibrary.appendChild(more);
    }
    renderRagSuggestions(DEFAULT_RAG_SUGGESTIONS);
    setRagStatus(`${cvs.length} CV indexé(s). ${formatEmbeddingEngine(library && library.embedding)}`, (library && library.embedding && library.embedding.neural) ? "ok" : "");
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
    last.classList.remove("is-loading");
  }

  function renderRagResults(results) {
    els.ragResults.innerHTML = "";
    if (!results.length) {
      els.ragResults.innerHTML = `
        <div class="rag-empty-state">
          <strong>Aucune correspondance</strong>
          <p>Essayez une recherche avec un poste, des outils ou des compétences plus précises.</p>
        </div>
      `;
      return;
    }

    results.forEach((result, index) => {
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
            <strong><span class="rag-rank">#${index + 1}</span>${escapeHtml(result.filename)}</strong>
            <span>${escapeHtml(contactLine || "Coordonnées non détectées")}</span>
            <span class="rag-confidence">${escapeHtml(result.confidenceLabel || "Correspondance estimée")}</span>
          </div>
          <em>${toNumber(result.score).toFixed(1)}%</em>
        </div>
        <div class="rag-score-bar" style="--score: ${Math.max(0, Math.min(toNumber(result.score), 100))}%"></div>
        <div class="chip-list compact">
          ${chips.slice(0, 8).map((skill) => `<span class="chip good">${escapeHtml(skill)}</span>`).join("") || `<span class="chip">Similarité texte</span>`}
        </div>
        <p>${escapeHtml(snippet.slice(0, 360))}${snippet.length > 360 ? "..." : ""}</p>
      `;
      els.ragResults.appendChild(card);
    });
  }

  function renderRagSuggestions(suggestions) {
    els.ragSuggestions.innerHTML = "";
    const values = asArray(suggestions).length ? asArray(suggestions) : DEFAULT_RAG_SUGGESTIONS;
    values.slice(0, 4).forEach((suggestion) => {
      const button = document.createElement("button");
      button.type = "button";
      button.dataset.question = suggestion;
      button.textContent = suggestion;
      els.ragSuggestions.appendChild(button);
    });
  }

  function setRagStatus(message, tone) {
    if (!els.ragStatus) return;
    els.ragStatus.textContent = message;
    els.ragStatus.className = `status ${tone || ""}`;
  }

  function setRagMode(message) {
    if (els.ragMode) els.ragMode.textContent = message;
  }

  function formatEmbeddingEngine(embedding) {
    if (!embedding) return "Moteur : local.";
    if (embedding.neural) return "Moteur : MiniLM multilingue.";
    return "Moteur : fallback local.";
  }

  async function readJson(response) {
    const text = await response.text();
    if (!text) return {};
    const trimmed = text.trim();
    const lowerText = trimmed.toLowerCase();
    if (lowerText.startsWith("<!doctype") || lowerText.startsWith("<html")) {
      return {
        error: `Le serveur Python de l'application ne répond pas correctement sur cette adresse (${response.status}). Relancez l'application avec python app.py, puis rechargez la page.`
      };
    }
    try {
      return JSON.parse(text);
    } catch (error) {
      return { error: trimmed.slice(0, 220) || "Réponse serveur invalide." };
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

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", initRagWidget);
  } else {
    initRagWidget();
  }
})();
