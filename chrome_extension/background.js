// ── Vantage MASTER ROUTER ────────────────────────────────────────────────────────
// All intelligence logic has been unified into a single FastAPI backend endpoint.

importScripts("fios_api.js");
importScripts("shadow_tabs.js");
importScripts("opportunity_store.js");

const Vantage_BACKEND = "http://127.0.0.1:8000/brain/execute";

chrome.runtime.onMessage.addListener((request, sender, sendResponse) => {
  if (request.action) {
    if (request.action === "SHOW_TOAST") {
      // Forward toast to content script if needed, or handle locally
      return false;
    }

    // Handle raw background ingestion
    if (request.action === "SEND_TO_Vantage") {
      fetch("http://127.0.0.1:8000/api/v1/ingest", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(request.payload)
      })
      .then(res => res.json())
      .then(data => sendResponse({ success: true, data }))
      .catch(error => sendResponse({ success: false, error: error.message }));
      return true;
    }

    console.log("Vantage Background: Routing payload...", request.action);
    const eventType = request.action.toLowerCase();
    
    // Normalize payload to BrainRequest structure
    const payload = {
      event_type: eventType,
      room_id: request.room_id || request.payload?.room_id || null,
      job_context: request.job_context || request.payload?.data || null,
      mode: request.mode || "deep",
      user_preferences: request.user_preferences || {},
      query: request.query || request.payload?.query || null,
      context: request.context || request.payload?.context || null,
      outcome: request.outcome || request.payload?.outcome || null,
      amount: request.amount || request.payload?.amount || null,
      data: request.data || request.payload || null,
    };

    fetch(Vantage_BACKEND, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload)
    })
    .then(res => {
      if (!res.ok) throw new Error(`HTTP error! status: ${res.status}`);
      return res.json();
    })
    .then(data => {
      console.log("Vantage Background: Brain Success", data);
      sendResponse(data);
    })
    .catch(error => {
      console.error("Vantage Background Error:", error);
      sendResponse({ status: "error", message: error.message });
    });

    return true; // Keep message channel open for async response
  }
});

chrome.runtime.onMessage.addListener((request, sender, sendResponse) => {
  if (request.action === "MANUAL_INGEST_PROPOSAL") {
    fetch("http://127.0.0.1:8000/api/v1/ingest/proposal", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(request.data)
    })
    .then(res => res.json())
    .then(data => sendResponse(data))
    .catch(err => sendResponse({ status: "error", message: err.message }));
    return true;
  }
  
  if (request.action === "MANUAL_INGEST_CONVERSATION") {
    fetch("http://127.0.0.1:8000/api/v1/ingest/conversation", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(request.data)
    })
    .then(res => res.json())
    .then(data => sendResponse(data))
    .catch(err => sendResponse({ status: "error", message: err.message }));
    return true;
  }
});

chrome.runtime.onInstalled.addListener(() => {
    console.log("FIOS Opportunity Scanner Started");
    startShadowScanner();
});

chrome.tabs.onUpdated.addListener(async (tabId, changeInfo, tab) => {
    if (
        tab.url &&
        tab.url.includes("/nx/search/jobs") &&
        changeInfo.status === "complete"
    ) {
        chrome.scripting.executeScript({
            target: { tabId: tabId },
            func: function scrapeJobsFromPage() {
                const jobElements = document.querySelectorAll('[data-test="job-tile"]');
                let jobs = [];
                jobElements.forEach(job => {
                    const title = job.querySelector('[data-test="job-title"]')?.innerText || "";
                    const description = job.querySelector('[data-test="job-description"]')?.innerText || "";
                    const clientSpend = job.querySelector('[data-test="client-spend"]')?.innerText || "";
                    jobs.push({
                        title: title,
                        description: description,
                        client_spend: clientSpend
                    });
                });
                return jobs;
            }
        }).then((results) => {
            if (results && results[0] && results[0].result) {
                const jobs = results[0].result;
                if (jobs.length > 0) {
                    sendJobsToFIOS(jobs);
                }
            }
        });
    }
});
