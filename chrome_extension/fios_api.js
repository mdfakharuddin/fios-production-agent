const API_BASE = "https://api.themenuagency.com/fios";
const ENDPOINTS = {
  EXECUTE: `${API_BASE}/brain/execute`,
  INGEST: `${API_BASE}/api/v1/ingest`,
  INGEST_CONVERSATION: `${API_BASE}/api/v1/ingest/conversation`,
  HEALTH: `${API_BASE}/health`
};

async function queryFIOS(message, conversationId = null, context = {}) {
  const payload = {
    input: message,
    source: "upie_extension",
    conversation_id: conversationId || "ext_global_session",
    context: {
      timestamp: Date.now(),
      ...context
    }
  };

  try {
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
  } catch (error) {
    console.error("FIOS API Error:", error);
    return { status: "error", message: error.message || String(error) };
  }
}

async function sendJobsToFIOS(jobs) {
  try {
    const payload = {
      url: "",
      html: "",
      text: Array.isArray(jobs) ? jobs.map((job) => `${job.title || ""}\n${job.description || ""}`).join("\n\n") : "",
      page_type: "job_search",
      jobs: jobs || [],
      timestamp: Date.now()
    };

    const response = await fetch(ENDPOINTS.INGEST, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload)
    });

    if (!response.ok) {
      const text = await response.text();
      throw new Error(`HTTP ${response.status}: ${text.slice(0, 240)}`);
    }

    const result = await response.json();

    if (typeof storeOpportunity === "function" && Array.isArray(jobs)) {
      for (let i = 0; i < jobs.length; i += 1) {
        await storeOpportunity(jobs[i] || {}, result?.opportunities?.[i] || {});
      }
    }

    return result;
  } catch (error) {
    console.error("FIOS job scan error:", error);
    return { status: "error", message: error.message || String(error) };
  }
}

async function sendJobsToUpie(jobs) {
  return sendJobsToFIOS(jobs);
}
