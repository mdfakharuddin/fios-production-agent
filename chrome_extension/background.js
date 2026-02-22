// Upie Background Router
// Routes extension actions to production Brain + archive ingestion endpoints.

importScripts("shadow_tabs.js");
importScripts("opportunity_store.js");

const API_BASE = "http://127.0.0.1:8000";
const ENDPOINTS = {
  EXECUTE: `${API_BASE}/brain/execute`,
  INGEST: `${API_BASE}/api/v1/ingest`,
  INGEST_CONVERSATION: `${API_BASE}/api/v1/ingest/conversation`,
  HEALTH: `${API_BASE}/health`
};

async function postJson(url, body) {
  const res = await fetch(url, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body || {})
  });

  if (!res.ok) {
    const text = await res.text();
    throw new Error(`HTTP ${res.status}: ${text.slice(0, 240)}`);
  }

  return res.json();
}

function buildExecutePayload(input, context = {}, conversationId = "ext_global_session") {
  const roomId = context.room_id || conversationId;
  return {
    event_type: context.event_type || "free_chat",
    query: input || "",
    source: "upie_extension",
    conversation_id: roomId,
    room_id: roomId,
    data: {
      room_id: roomId,
      url: context.url || "",
      page_type: context.page_type || "background_router",
      full_html: context.full_html || "",
      page_text: context.page_text || "",
      job: context.job || null,
      client: context.client || null,
      conversation: context.conversation || null,
      timestamp: Date.now(),
      ...context
    }
  };
}

function normalizeIngestPayload(payload, sender) {
  const data = payload?.data || {};
  const fallbackUrl = payload?.url || sender?.tab?.url || "";

  return {
    url: fallbackUrl,
    html: data.html || data.raw_html || "",
    text: data.text || data.page_text || data.raw_text || "",
    page_type: payload?.type || data.page_type || "generic",
    job: data.job || null,
    client: data.client || null,
    conversation: data.conversation || null,
    payload,
    timestamp: Date.now()
  };
}

function waitForTabComplete(tabId, timeoutMs = 20000) {
  return new Promise((resolve) => {
    const timer = setTimeout(() => {
      chrome.tabs.onUpdated.removeListener(onUpdated);
      resolve(false);
    }, timeoutMs);

    function onUpdated(updatedTabId, changeInfo) {
      if (updatedTabId !== tabId) return;
      if (changeInfo.status === "complete") {
        clearTimeout(timer);
        chrome.tabs.onUpdated.removeListener(onUpdated);
        resolve(true);
      }
    }

    chrome.tabs.onUpdated.addListener(onUpdated);
  });
}

async function ensureScraperInjected(tabId) {
  try {
    await chrome.scripting.executeScript({
      target: { tabId },
      files: ["content_scripts/scraper.js", "content_scripts/upie_scraper.js"]
    });
  } catch (_) {
  }
}

async function openShadowTab(url) {
  const tab = await chrome.tabs.create({ url, active: false, pinned: false });
  await waitForTabComplete(tab.id, 25000);
  await ensureScraperInjected(tab.id);
  await new Promise((resolve) => setTimeout(resolve, 1200));
  return tab.id;
}

async function performShadowIngest(jobUrl, proposalData) {
  const tabId = await openShadowTab(jobUrl);

  try {
    const scrape = await chrome.tabs.sendMessage(tabId, { action: "SCRAPE_FOR_SHADOW_MERGE" });
    if (!scrape || !scrape.success) {
      throw new Error(scrape?.error || "shadow_scrape_failed");
    }

    const payload = {
      url: jobUrl,
      html: scrape.data?.raw_html || "",
      text: scrape.data?.raw_text || scrape.textSnippet || "",
      page_type: "stealth_proposal_job_merge",
      job: scrape.data || null,
      client: null,
      conversation: null,
      proposal: proposalData || null,
      timestamp: Date.now()
    };

    const ingestRes = await postJson(ENDPOINTS.INGEST, payload);
    return { success: true, ingest: ingestRes };
  } finally {
    chrome.tabs.remove(tabId);
  }
}

async function performArchivedProposalIngest(proposalUrl) {
  const tabId = await openShadowTab(proposalUrl);

  try {
    const [proposalExec] = await chrome.scripting.executeScript({
      target: { tabId },
      func: () => (window.extractManualProposal ? window.extractManualProposal() : null)
    });

    const proposalData = proposalExec?.result;
    if (!proposalData) {
      throw new Error("extractManualProposal unavailable or returned empty");
    }

    const payload = {
      url: proposalUrl,
      html: "",
      text: proposalData.raw_text || proposalData.proposal_text || "",
      page_type: "proposal",
      proposal: proposalData,
      timestamp: Date.now()
    };

    const ingest = await postJson(ENDPOINTS.INGEST, payload);
    return { success: true, ingest };
  } finally {
    chrome.tabs.remove(tabId);
  }
}

async function sendJobsToUpie(jobs, sourceUrl = "") {
  if (!Array.isArray(jobs) || jobs.length === 0) return { success: true, skipped: true };

  const payload = {
    url: sourceUrl,
    html: "",
    text: jobs.map((j) => `${j.title || ""}\n${j.description || ""}`).join("\n\n"),
    page_type: "job_search",
    jobs,
    timestamp: Date.now()
  };

  return postJson(ENDPOINTS.INGEST, payload);
}

chrome.runtime.onMessage.addListener((request, sender, sendResponse) => {
  if (!request || !request.action) return false;

  const action = request.action;

  if (action === "SHOW_TOAST") return false;

  (async () => {
    try {
      if (action === "SEND_TO_Upie") {
        const payload = request.payload || {};

        if ((payload.query || "").trim()) {
          const executePayload = buildExecutePayload(
            payload.query,
            payload.context || {},
            payload.session_id || payload.room_id || "ext_global_session"
          );
          const data = await postJson(ENDPOINTS.EXECUTE, executePayload);
          sendResponse({ success: true, data });
          return;
        }

        const messagePayload = normalizeIngestPayload(payload, sender);

        if (payload.type === "conversation" || Array.isArray(payload?.data?.messages)) {
          const data = await postJson(ENDPOINTS.INGEST_CONVERSATION, {
            url: payload.url || sender?.tab?.url || "",
            messages: payload?.data?.messages || payload.messages || [],
            timestamp: Date.now()
          });
          sendResponse({ success: true, data });
          return;
        }

        const data = await postJson(ENDPOINTS.INGEST, messagePayload);
        sendResponse({ success: true, data });
        return;
      }

      if (action === "MANUAL_INGEST_PROPOSAL") {
        const data = await postJson(ENDPOINTS.INGEST, {
          url: request.data?.proposal_link || sender?.tab?.url || "",
          html: "",
          text: request.data?.raw_text || request.data?.proposal_text || "",
          page_type: "proposal",
          proposal: request.data || {},
          timestamp: Date.now()
        });
        sendResponse({ success: true, data });
        return;
      }

      if (action === "MANUAL_INGEST_CONVERSATION") {
        const data = await postJson(ENDPOINTS.INGEST_CONVERSATION, {
          url: request.data?.url || sender?.tab?.url || "",
          messages: request.data?.messages || [],
          timestamp: Date.now()
        });
        sendResponse({ success: true, data });
        return;
      }

      if (action === "CHECK_THREAD_STATUS") {
        sendResponse({
          success: true,
          exists: false,
          syncStatus: "unknown",
          messageCount: 0,
          summary: "Status endpoint disabled; using production brain ingestion only."
        });
        return;
      }

      if (action === "CHECK_PROPOSAL_STATUS") {
        sendResponse({
          success: true,
          exists: false,
          syncStatus: "unknown"
        });
        return;
      }

      if (action === "PERFORM_SHADOW_INGEST") {
        const jobUrl = request.payload?.jobUrl;
        const proposalData = request.payload?.proposalData;
        if (!jobUrl) {
          sendResponse({ success: false, error: "jobUrl missing" });
          return;
        }

        const out = await performShadowIngest(jobUrl, proposalData);
        sendResponse(out);
        return;
      }

      if (action === "PERFORM_SHADOW_INGEST_ARCHIVED") {
        const url = request.payload?.url;
        if (!url) {
          sendResponse({ success: false, error: "url missing" });
          return;
        }

        const out = await performArchivedProposalIngest(url);
        sendResponse(out);
        return;
      }

      const fallbackQuery = request.query || request.payload?.query || `Handle action: ${action}`;
      const data = await postJson(
        ENDPOINTS.EXECUTE,
        buildExecutePayload(fallbackQuery, request.context || request.payload?.context || {}, request.room_id || "ext_global_session")
      );
      sendResponse({ success: true, data });
    } catch (error) {
      console.error("Upie Background Error:", error);
      sendResponse({ status: "error", message: error.message || String(error) });
    }
  })();

  return true;
});

chrome.runtime.onInstalled.addListener(() => {
  console.log("Upie Production Brain Router initialized.");
});

chrome.tabs.onUpdated.addListener(async (tabId, changeInfo, tab) => {
  if (!tab.url || !tab.url.includes("/nx/search/jobs") || changeInfo.status !== "complete") return;

  try {
    const results = await chrome.scripting.executeScript({
      target: { tabId },
      func: function scrapeJobsFromPage() {
        const jobElements = document.querySelectorAll('[data-test="job-tile"]');
        const jobs = [];

        jobElements.forEach((job) => {
          const title = job.querySelector('[data-test="job-title"]')?.innerText || "";
          const description = job.querySelector('[data-test="job-description"]')?.innerText || "";
          const clientSpend = job.querySelector('[data-test="client-spend"]')?.innerText || "";
          const hireRate = job.querySelector('[data-test="client-hire-rate"]')?.innerText || "";

          jobs.push({
            title,
            description,
            client_spend: clientSpend,
            client_hire_rate: hireRate
          });
        });

        return jobs;
      }
    });

    const jobs = results?.[0]?.result || [];
    if (jobs.length > 0) {
      await sendJobsToUpie(jobs, tab.url || "");
    }
  } catch (e) {
    console.warn("Upie Background: job scan failed:", e.message || e);
  }
});
