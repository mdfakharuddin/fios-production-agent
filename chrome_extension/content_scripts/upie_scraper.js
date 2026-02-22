(function() {
  'use strict';

  if (window.upieSilentScraperLoaded) return;
  window.upieSilentScraperLoaded = true;

  const API_BASE = "https://api.themenuagency.com/fios";
  const ENDPOINTS = {
    EXECUTE: `${API_BASE}/brain/execute`,
    INGEST: `${API_BASE}/api/v1/ingest`,
    INGEST_CONVERSATION: `${API_BASE}/api/v1/ingest/conversation`,
    HEALTH: `${API_BASE}/health`
  };

  function extractRoomId() {
    const match = window.location.href.match(/rooms\/([^\/]+)/);
    const roomId = match ? match[1] : null;
    if (roomId) {
      try {
        if (chrome.runtime && chrome.runtime.id) {
          chrome.storage.local.set({ current_room_id: roomId }).catch(e => {
            console.warn("Upie: Async storage error", e);
          });
        }
      } catch (e) {
        console.warn("Upie: Extension context likely invalidated", e);
      }
    }
    return roomId;
  }

  function detectSender(node) {
    const parent = node.closest('[data-test="message-item"], article, .up-d-story');
    if (!parent) return "Participant";
    const senderEl = parent.querySelector('.sender-name, strong, b, [data-test="sender-name"]');
    return (senderEl?.innerText || "Participant").trim();
  }

  function detectPageType() {
    const href = String(window.location.href || "").toLowerCase();
    if (href.includes("/messages")) return "conversation";
    if (href.includes("/jobs/") || href.includes("/freelance-jobs/") || href.includes("job-details")) return "job";
    if (href.includes("/proposals")) return "proposal";
    if (href.includes("/profile/") || href.includes("/freelancers/~")) return "profile";
    if (href.includes("/search/jobs")) return "job_search";
    return "generic";
  }

  function extractJobContext() {
    if (typeof window.extractJobDetails === "function") {
      try {
        return window.extractJobDetails();
      } catch (_) {
      }
    }
    return {
      title: document.title || "",
      description: "",
      raw_text: document.body?.innerText || ""
    };
  }

  function extractClientContext() {
    if (typeof window.extractClientSidebar === "function") {
      try {
        return window.extractClientSidebar();
      } catch (_) {
      }
    }
    return null;
  }

  function extractConversationContext() {
    if (typeof window.extractConversation === "function") {
      try {
        return window.extractConversation();
      } catch (_) {
      }
    }

    const raw = Array.from(document.querySelectorAll('[data-test="message-item"], article, [role="listitem"]'));
    const messages = raw
      .map((el) => ({
        sender: (el.querySelector('.sender-name, strong, b')?.innerText || "Participant").trim(),
        text: (el.innerText || "").trim(),
        role: "participant"
      }))
      .filter((m) => m.text);

    return { messages };
  }

  function extractConversationMessages() {
    const roomId = extractRoomId();
    const nodes = document.querySelectorAll('[data-test="message-text"], .message-text, .up-chat-message-text');
    
    if (nodes.length > 0) {
      return Array.from(nodes).map(node => ({
        room_id: roomId,
        text: node.innerText.trim(),
        sender: detectSender(node),
        timestamp: Date.now()
      }));
    }

    const conversation = extractConversationContext();
    const messages = Array.isArray(conversation)
      ? conversation
      : Array.isArray(conversation?.messages)
      ? conversation.messages
      : [];

    return messages
      .map((m) => ({
        room_id: roomId,
        message_id: m.message_id || null,
        sender: m.sender || m.author || "Participant",
        role: m.role || "participant",
        text: m.text || m.content || "",
        time: m.time || null,
        timestamp: Date.now(),
        attachments: Array.isArray(m.attachments) ? m.attachments : []
      }))
      .filter((m) => m.text && m.text.trim().length > 0);
  }

  function extractFullContext() {
    const htmlSnippet = document.body?.outerHTML || document.documentElement?.outerHTML || "";
    const textSnippet = document.body?.innerText || "";
    return {
      url: window.location.href,
      room_id: extractRoomId(),
      html: htmlSnippet,
      text: textSnippet,
      raw_html: htmlSnippet,
      raw_text: textSnippet,
      job: extractJobContext(),
      client: extractClientContext(),
      conversation: extractConversationContext()
    };
  }

  function isChatPage() {
    return detectPageType() === "conversation";
  }

  let lastIngestSignature = "";
  let ingestInFlight = false;

  async function silentIngest() {
    if (ingestInFlight) return;

    const roomId = extractRoomId();
    const payload = {
      room_id: roomId,
      url: window.location.href,
      html: document.body?.outerHTML || document.documentElement?.outerHTML || "",
      text: document.body?.innerText || "",
      page_type: detectPageType(),
      job: extractJobContext(),
      client: extractClientContext(),
      conversation: extractConversationContext(),
      timestamp: Date.now()
    };

    const signature = [
      payload.url,
      payload.page_type,
      String(payload.text || "").slice(0, 400)
    ].join("|");

    if (signature === lastIngestSignature) return;

    ingestInFlight = true;
    try {
      await fetch(ENDPOINTS.INGEST, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload)
      });
      lastIngestSignature = signature;
    } catch (_) {
    } finally {
      ingestInFlight = false;
    }
  }

  async function syncConversation() {
    if (!isChatPage()) return;

    const roomId = extractRoomId();
    const payload = {
      room_id: roomId,
      url: window.location.href,
      messages: extractConversationMessages(),
      client: extractClientContext(),
      job: extractJobContext(),
      timestamp: Date.now()
    };

    if (!Array.isArray(payload.messages) || payload.messages.length === 0) return;

    try {
      await fetch(ENDPOINTS.INGEST_CONVERSATION, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload)
      });
    } catch (_) {
    }
  }

  let lastUrl = window.location.href;
  let mutationTimer = null;

  function onUrlChange() {
    const currentUrl = window.location.href;
    if (currentUrl === lastUrl) return;
    lastUrl = currentUrl;
    silentIngest();
    if (isChatPage()) syncConversation();
  }

  function scheduleMutationIngest() {
    if (mutationTimer) clearTimeout(mutationTimer);
    mutationTimer = setTimeout(() => {
      silentIngest();
    }, 1200);
  }

  window.addEventListener("load", () => {
    silentIngest();
    if (isChatPage()) syncConversation();
  });

  window.addEventListener("popstate", onUrlChange);
  window.addEventListener("hashchange", onUrlChange);

  const pushState = history.pushState;
  const replaceState = history.replaceState;
  history.pushState = function() {
    const ret = pushState.apply(this, arguments);
    onUrlChange();
    return ret;
  };
  history.replaceState = function() {
    const ret = replaceState.apply(this, arguments);
    onUrlChange();
    return ret;
  };

  setInterval(onUrlChange, 1000);

  const observer = new MutationObserver(() => {
    scheduleMutationIngest();
  });

  if (document.body) {
    observer.observe(document.body, { childList: true, subtree: true });
  } else {
    window.addEventListener("DOMContentLoaded", () => {
      observer.observe(document.body, { childList: true, subtree: true });
    });
  }

  setInterval(silentIngest, 30000);
  setInterval(syncConversation, 10000);

  // Boot immediately after inject.
  silentIngest();

  window.detectPageType = detectPageType;
  window.extractJobContext = extractJobContext;
  window.extractClientContext = extractClientContext;
  window.extractConversationContext = extractConversationContext;
  window.extractConversationMessages = extractConversationMessages;
  window.extractFullContext = extractFullContext;
  window.extractRoomId = extractRoomId;
  window.upieSilentIngest = silentIngest;
  window.upieSyncConversation = syncConversation;

  chrome.runtime.onMessage.addListener((request, sender, sendResponse) => {
    if (request.action === "EXTRACT_PAGE_CONTENT") {
      sendResponse(extractFullContext());
    }
    return true;
  });
})();
