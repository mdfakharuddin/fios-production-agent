const API_BASE = "http://127.0.0.1:8000";
const ENDPOINTS = {
  EXECUTE: `${API_BASE}/brain/execute`,
  INGEST: `${API_BASE}/api/v1/ingest`,
  INGEST_CONVERSATION: `${API_BASE}/api/v1/ingest/conversation`,
  HEALTH: `${API_BASE}/health`
};

let activePane = "pane-overview";

function safeJsonParse(text) {
  try {
    return JSON.parse(text);
  } catch (_) {
    return null;
  }
}

function normalizeOutput(result) {
  if (!result) return "";
  if (typeof result.output === "string") return result.output;
  if (typeof result.response === "string") return result.response;
  if (typeof result === "string") return result;
  return JSON.stringify(result, null, 2);
}

function splitList(text) {
  return String(text || "")
    .split(/\n{2,}|\n\s*(?:\d+\.|-|•)\s*/g)
    .map((line) => line.trim())
    .filter(Boolean);
}

function renderList(containerId, text) {
  const container = document.getElementById(containerId);
  if (!container) return;

  const items = splitList(text);
  if (items.length === 0) {
    container.innerHTML = '<div class="empty">No data available.</div>';
    return;
  }

  container.innerHTML = items
    .slice(0, 12)
    .map((item) => `<div class="list-item">${item.replace(/</g, "&lt;").replace(/>/g, "&gt;")}</div>`)
    .join("");
}

function extractMetric(text, patterns, fallback = "--") {
  for (const pattern of patterns) {
    const match = String(text || "").match(pattern);
    if (match && match[1]) return match[1].trim();
  }
  return fallback;
}

function tabsQuery(queryInfo) {
  return new Promise((resolve, reject) => {
    chrome.tabs.query(queryInfo, (tabs) => {
      if (chrome.runtime.lastError) {
        reject(new Error(chrome.runtime.lastError.message));
        return;
      }
      resolve(tabs || []);
    });
  });
}

function sendMessageToTab(tabId, message) {
  return new Promise((resolve) => {
    chrome.tabs.sendMessage(tabId, message, (response) => {
      if (chrome.runtime.lastError) {
        resolve(null);
        return;
      }
      resolve(response || null);
    });
  });
}

async function getActiveTabContext() {
  const tabs = await tabsQuery({ active: true, currentWindow: true });
  const tab = tabs[0] || {};

  if (!tab.id) {
    return {
      url: "",
      full_html: "",
      page_text: "",
      page_data: {}
    };
  }

  const pageData = await sendMessageToTab(tab.id, { action: "EXTRACT_PAGE_CONTENT" });

  return {
    url: tab.url || "",
    full_html: pageData?.raw_html || pageData?.html || "",
    page_text: pageData?.raw_text || pageData?.text || "",
    page_data: pageData || {}
  };
}

async function executePrompt(input, extraContext = {}) {
  const pageContext = await getActiveTabContext();

  const roomId = pageContext.page_data?.room_id || `popup_${Date.now()}`;
  const payload = {
    event_type: "free_chat",
    query: input,
    source: "upie_extension",
    conversation_id: roomId,
    room_id: roomId,
    data: {
      room_id: roomId,
      url: pageContext.url,
      page_type: "popup_control_center",
      full_html: pageContext.full_html,
      page_text: pageContext.page_text,
      page_data: pageContext.page_data,
      timestamp: Date.now(),
      ...extraContext
    }
  };

  const response = await fetch(ENDPOINTS.EXECUTE, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload)
  });

  if (!response.ok) {
    const text = await response.text();
    throw new Error(`HTTP ${response.status}: ${text.slice(0, 240)}`);
  }

  return response.json();
}

async function loadOverview() {
  const summaryEl = document.getElementById("overview-summary");
  summaryEl.textContent = "Loading profile summary from Brain...";

  try {
    const result = await executePrompt("Summarize my freelancer intelligence profile.", {
      full_html: document.body.outerHTML
    });

    const output = normalizeOutput(result);
    summaryEl.textContent = output || "No summary returned.";

    const metricsResult = await executePrompt(
      "Return JSON only with keys conversations_tracked, winning_proposals, success_rate, intelligence_level based on my archive memory."
    );
    const metricsRaw = normalizeOutput(metricsResult);

    let metrics = safeJsonParse(metricsRaw);
    if (!metrics && metricsRaw.includes("{")) {
      const jsonSlice = metricsRaw.slice(metricsRaw.indexOf("{"), metricsRaw.lastIndexOf("}") + 1);
      metrics = safeJsonParse(jsonSlice);
    }

    const convos = metrics?.conversations_tracked || extractMetric(output, [/conversations?\s*tracked\s*[:\-]\s*([^\n]+)/i, /conversations?\s*[:\-]\s*([^\n]+)/i]);
    const props = metrics?.winning_proposals || extractMetric(output, [/winning\s*proposals?\s*[:\-]\s*([^\n]+)/i, /proposals?\s*[:\-]\s*([^\n]+)/i]);
    const success = metrics?.success_rate || extractMetric(output, [/success\s*rate\s*[:\-]\s*([^\n]+)/i, /(\d+%)/]);
    const level = metrics?.intelligence_level || extractMetric(output, [/intelligence\s*level\s*[:\-]\s*([^\n]+)/i], "Active");

    document.getElementById("stat-convos").innerText = convos || "--";
    document.getElementById("stat-props").innerText = props || "--";
    document.getElementById("stat-success").innerText = success || "--";
    document.getElementById("stat-level").innerText = level || "--";

    renderList("activity-list", output);
  } catch (error) {
    summaryEl.textContent = `Failed to load overview: ${error.message || "Unknown error"}`;
  }
}

async function loadOpportunities() {
  const listId = "opps-list";
  document.getElementById(listId).innerHTML = '<div class="empty">Loading opportunities...</div>';

  try {
    const result = await executePrompt("List my highest-priority active opportunities from memory with win rationale.");
    renderList(listId, normalizeOutput(result));
  } catch (error) {
    document.getElementById(listId).innerHTML = `<div class="empty">Failed to load opportunities: ${error.message}</div>`;
  }
}

async function loadConversations() {
  const listId = "convos-list";
  document.getElementById(listId).innerHTML = '<div class="empty">Loading conversations...</div>';

  try {
    const result = await executePrompt("List my recent client conversations with status and recommended next action.");
    renderList(listId, normalizeOutput(result));
  } catch (error) {
    document.getElementById(listId).innerHTML = `<div class="empty">Failed to load conversations: ${error.message}</div>`;
  }
}

async function loadProposals() {
  const listId = "props-list";
  document.getElementById(listId).innerHTML = '<div class="empty">Loading proposals...</div>';

  try {
    const result = await executePrompt("List my proposal history with performance signals and improvement notes.");
    renderList(listId, normalizeOutput(result));
  } catch (error) {
    document.getElementById(listId).innerHTML = `<div class="empty">Failed to load proposals: ${error.message}</div>`;
  }
}

async function loadClients() {
  const listId = "clients-list";
  document.getElementById(listId).innerHTML = '<div class="empty">Loading client intelligence...</div>';

  try {
    const result = await executePrompt("Summarize my client intelligence profile: best clients, risk flags, and communication style guidance.");
    renderList(listId, normalizeOutput(result));
  } catch (error) {
    document.getElementById(listId).innerHTML = `<div class="empty">Failed to load clients: ${error.message}</div>`;
  }
}

async function loadMemorySummary() {
  const listId = "memory-list";
  document.getElementById(listId).innerHTML = '<div class="empty">Loading memory store summary...</div>';

  try {
    const result = await executePrompt("Summarize what you have learned about my freelancer voice, strengths, and archive memory.");
    renderList(listId, normalizeOutput(result));
  } catch (error) {
    document.getElementById(listId).innerHTML = `<div class="empty">Failed to load memory summary: ${error.message}</div>`;
  }
}

async function activatePane(paneId) {
  activePane = paneId;

  switch (paneId) {
    case "pane-overview":
      await loadOverview();
      break;
    case "pane-opps":
      await loadOpportunities();
      break;
    case "pane-convos":
      await loadConversations();
      break;
    case "pane-props":
      await loadProposals();
      break;
    case "pane-clients":
      await loadClients();
      break;
    case "pane-memory":
      await loadMemorySummary();
      break;
    default:
      break;
  }
}

document.addEventListener("DOMContentLoaded", () => {
  const navItems = document.querySelectorAll(".nav-item");
  const panes = document.querySelectorAll(".pane");

  navItems.forEach((item) => {
    item.addEventListener("click", async () => {
      const targetPane = item.dataset.pane;
      if (!targetPane) return;

      navItems.forEach((i) => i.classList.remove("active"));
      item.classList.add("active");

      panes.forEach((pane) => pane.classList.remove("active"));
      document.getElementById(targetPane)?.classList.add("active");

      await activatePane(targetPane);
    });
  });

  const btnRebuild = document.getElementById("btn-rebuild");
  const rebuildStatus = document.getElementById("rebuild-status");

  if (btnRebuild) {
    btnRebuild.addEventListener("click", async () => {
      btnRebuild.disabled = true;
      btnRebuild.textContent = "Rebuilding...";
      rebuildStatus.textContent = "Requesting rebuild from production Brain...";

      try {
        const result = await executePrompt("Force rebuild brain intelligence and confirm completion in one concise sentence.");
        rebuildStatus.textContent = normalizeOutput(result) || "Rebuild request completed.";
      } catch (error) {
        rebuildStatus.textContent = `Rebuild failed: ${error.message || "Unknown error"}`;
      } finally {
        btnRebuild.disabled = false;
        btnRebuild.textContent = "Force Rebuild Brain Intelligence";
      }
    });
  }

  activatePane(activePane);
});
