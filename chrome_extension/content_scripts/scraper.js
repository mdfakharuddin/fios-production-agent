// Scrapes data from the active Upwork page

chrome.runtime.onMessage.addListener((request, sender, sendResponse) => {
  if (request.action === "EXTRACT_PAGE_DATA") {
    console.log("Upie: Received extraction request.");
    const pageUrl = window.location.href;
    let extractedData = null;
    let dataType = "unknown";

    if (pageUrl.includes("upwork.com/ab/proposals") || pageUrl.includes("upwork.com/nx/proposals/archived") || pageUrl.includes("upwork.com/nx/proposals/active")) {
      extractedData = extractProposalsList();
      dataType = "proposals";
    } else if (pageUrl.includes("upwork.com/nx/proposals/")) {
      extractedData = extractSingleProposal();
      dataType = "proposals";
    } else if (pageUrl.includes("upwork.com/jobs/") || pageUrl.includes("upwork.com/freelance-jobs/")) {
      extractedData = extractJobDetails();
      dataType = "job_details";
    } else if (pageUrl.includes("upwork.com/messages")) {
      extractedData = extractConversation();
      dataType = "conversation";
    } else if (pageUrl.includes("/freelancers/~") || pageUrl.includes("/profile/")) {
      extractedData = extractFreelancerProfile();
      dataType = "profile_sync";
    } else if (pageUrl.includes("/contracts/")) {
      extractedData = {
        title: document.title || "Contract Page",
        raw_text: document.body.innerText.substring(0, 20000),
        raw_html: document.body.outerHTML.substring(0, 500000)
      };
      dataType = "dom_snapshot";
    } else if (pageUrl.includes("/apply") || pageUrl.includes("/submit")) {
      extractedData = extractProposalSubmission();
      dataType = "proposal_submission";
    } else {
      extractedData = { 
        title: document.title || "Unknown Page", 
        raw_text: document.body.innerText.substring(0, 10000) 
      };
      dataType = "generic_page";
    }

    if (extractedData) {
      chrome.runtime.sendMessage({
        action: "SEND_TO_Upie",
        payload: { type: dataType, data: extractedData, url: pageUrl, timestamp: new Date().toISOString() }
      }, (response) => {
        if (response && response.success) {
          sendResponse({ status: "success", type: dataType, records: Array.isArray(extractedData) ? extractedData.length : 1 });
        } else {
          sendResponse({ status: "error", error: response ? response.error : "Unknown backend error" });
        }
      });
      return true; 
    }
  }

  if (request.action === "SCRAPE_FOR_SHADOW_MERGE") {
    console.log("Upie: Shadow Scrape Triggered on this tab.");
    try {
      const jobData = extractJobDetails();
      sendResponse({ 
        success: true, 
        data: jobData,
        pageTitle: document.title,
        textSnippet: document.body.innerText.substring(0, 500)
      });
    } catch (e) {
      sendResponse({ success: false, error: e.message });
    }
    return true;
  }

  if (request.action === "SHOW_TOAST") {
    showToast(request.message, request.type || "info");
    return true;
  }
});

// --- Stealth Automation ---

// SPAs (Single Page Applications) like Upwork don't reload the page on navigation.
// The most bulletproof way to detect React Router navigation is a simple polling interval.
let lastStealthUrl = "";

const PROPOSAL_URL_REGEX = /upwork\.com\/nx\/proposals\/(?:archived\/|active\/)?(\d+)/;
const MESSAGES_URL_REGEX = /upwork\.com\/(?:ab\/)?messages\//;
const DOM_SNAPSHOT_COOLDOWN_MS = 15000;
const MAX_DOM_HTML_CHARS = 2000000; // Keep payload bounded for extension messaging.
let lastDomSnapshotAt = 0;
let domSnapshotTimer = null;

function classifyPageType(url) {
  const u = (url || "").toLowerCase();
  if (u.includes("/messages/")) return "conversation";
  if (u.includes("/jobs/") || u.includes("/freelance-jobs/") || u.includes("/job-details")) return "job";
  if (u.includes("/proposals/")) return "proposal";
  if (u.includes("/profile/") || u.includes("/freelancers/~")) return "profile";
  if (u.includes("/contracts/")) return "contract";
  if (u.includes("/search/jobs")) return "job_search";
  return "generic";
}

function sendDomSnapshot(trigger = "navigation") {
  const now = Date.now();
  if ((now - lastDomSnapshotAt) < DOM_SNAPSHOT_COOLDOWN_MS) return;
  lastDomSnapshotAt = now;

  const rawHtml = (document.body && document.body.outerHTML) ? document.body.outerHTML : "";
  const payload = {
    type: "dom_snapshot",
    data: {
      html: rawHtml.length > MAX_DOM_HTML_CHARS ? rawHtml.slice(0, MAX_DOM_HTML_CHARS) : rawHtml,
      page_text: (document.body && document.body.innerText) ? document.body.innerText.slice(0, 180000) : "",
      page_type: classifyPageType(window.location.href),
      title: document.title || "",
      trigger
    },
    url: window.location.href,
    timestamp: new Date().toISOString()
  };

  safeSendMessage({ action: "SEND_TO_Upie", payload }, () => {});
}

function scheduleDomSnapshot(trigger = "mutation") {
  if (domSnapshotTimer) clearTimeout(domSnapshotTimer);
  domSnapshotTimer = setTimeout(() => sendDomSnapshot(trigger), 1000);
}

function checkStealthTrigger() {
  const currentUrl = window.location.href;
  // Use canonical URL (no query params) to avoid jitter/looping on minor UI updates
  const canonicalUrl = currentUrl.split('?')[0].split('#')[0];
  
  if (canonicalUrl !== lastStealthUrl) {
    lastStealthUrl = canonicalUrl;
    sendDomSnapshot("route_change");

    // Ignore image viewer modals or generic overlays
    if (currentUrl.includes("ImageViewerModal") || currentUrl.includes("_modalInfo")) {
       return;
    }

    // Job pages: ZERO automation. Only respond to popup requests.
    if (currentUrl.includes('/jobs/') || currentUrl.includes('/freelance-jobs/') || currentUrl.includes('/job-details')) {
      return;
    }
    
    // 1. Check for Proposal Pages
    if (PROPOSAL_URL_REGEX.test(canonicalUrl)) {
      console.log("Upie Stealth: Detected Proposal Change.");
      setTimeout(stealthFetchJobDetails, 3500); 
    }
    
    // 2. Check for Message Threads
    if (MESSAGES_URL_REGEX.test(canonicalUrl)) {
      console.log("Upie Stealth: Detected Message Thread Change.");
      const roomId = getRoomId();
      if (roomId) handleRoomChange(roomId);
    }
  }
}

// Safe messaging helper to avoid "Extension context invalidated" errors
function safeSendMessage(message, callback) {
  if (chrome.runtime && chrome.runtime.id) {
    chrome.runtime.sendMessage(message, (response) => {
      if (chrome.runtime.lastError) {
        console.warn("Upie: Runtime error (context likely invalidated):", chrome.runtime.lastError.message);
      } else if (callback) {
        callback(response);
      }
    });
  } else {
    console.warn("Upie: Extension context invalidated. Stopping operations.");
    return false;
  }
  return true;
}

let isScraping = false;
let captureActive = false;
let messageBuffer = new Map(); // Use Map to store unique messages by ID or composite key
let lastRoomId = "";

let isSyncing = false;
let stopSyncRequested = false;
let autoSyncInterval = null;
let autoSyncEnabled = false;

// Load persisted auto-sync setting
chrome.storage.local.get(['upieAutoSync'], (res) => {
  autoSyncEnabled = !!res.upieAutoSync;
  if (autoSyncEnabled) startAutoSyncLoop();
});

chrome.storage.onChanged.addListener((changes) => {
  if (changes.upieAutoSync) {
    autoSyncEnabled = changes.upieAutoSync.newValue;
    if (autoSyncEnabled) startAutoSyncLoop();
    else stopAutoSyncLoop();
  }
});

// Listen for Floating UI Events
window.addEventListener('Upie_START_CAPTURE', () => {
  console.log("Upie: Passive Capture Started.");
  captureActive = true;
  startBuffering();
});

window.addEventListener('Upie_STOP_CAPTURE', () => {
  console.log("Upie: Passive Capture Stopped.");
  captureActive = false;
});

window.addEventListener('Upie_FLUSH_DATA', () => {
  console.log("Upie: Flushing Buffered Data...");
  flushBuffer();
});

window.addEventListener('Upie_CLEAR_BUFFER', () => {
  console.log("Upie: Buffer Cleared.");
  messageBuffer.clear();
  updateUICount();
});

function startBuffering() {
  // Initial capture
  captureVisibleMessages();
  
  // Observe for new messages as user scrolls
  const container = findScrollContainer();
  if (container) {
    const observer = new MutationObserver(() => {
      if (captureActive) captureVisibleMessages();
    });
    observer.observe(container, { childList: true, subtree: true });
    
    // Also listen for scroll to be safe
    container.addEventListener('scroll', () => {
      if (captureActive) captureVisibleMessages();
    }, { passive: true });
  }
}

function findScrollContainer() {
  return document.querySelector('.scroll-wrapper, [role="log"], .fe-message-list-viewport, .message-list-container, .up-chat-room-scroll-container, .air3-scroll-container') || 
         Array.from(document.querySelectorAll('div')).find(el => {
           const style = window.getComputedStyle(el);
           return (style.overflowY === 'auto' || style.overflowY === 'scroll') && el.scrollHeight > el.clientHeight;
         });
}

function captureVisibleMessages() {
  const convo = extractConversation();
  const currentMessages = Array.isArray(convo) ? convo : (convo.messages || []);
  let added = false;
  currentMessages.forEach(msg => {
    const key = msg.message_id || `${msg.sender}:${msg.text.substring(0, 100)}:${msg.time}`;
    if (!messageBuffer.has(key)) {
      messageBuffer.set(key, msg);
      added = true;
    }
  });
  if (added) {
    updateUICount();
    window.dispatchEvent(new CustomEvent('Upie_BUFFER_UPDATE', { 
      detail: { messages: Array.from(messageBuffer.values()) } 
    }));
  }
}

function updateUICount() {
  window.dispatchEvent(new CustomEvent('Upie_COUNT_UPDATE', { 
    detail: { count: messageBuffer.size } 
  }));
}

function flushBuffer() {
  if (messageBuffer.size === 0) {
    showToast("⚠️ Nothing to send.");
    return;
  }
  const messages = Array.from(messageBuffer.values());
  syncMessages(messages, 'partially_synced');
  messageBuffer.clear();
  updateUICount();
}

function syncMessages(messages, status = 'partially_synced') {
    if (messages.length === 0) return;
    
    const threadName = extractThreadName();
    const roomId = lastRoomId || getRoomId() || "unknown_room";

    const payload = {
        type: "conversation",
        data: {
          thread_name: threadName,
          room_id: roomId,
          messages: messages,
          client_sidebar: extractClientSidebar(),
          sync_status: status
        },
        url: window.location.href,
        timestamp: new Date().toISOString()
    };

    safeSendMessage({ action: 'SEND_TO_Upie', payload: payload }, (response) => {
        if (response && response.success) {
            console.log("Upie: Sync Successful.");
            if (!isSyncing) {
                window.dispatchEvent(new CustomEvent('Upie_SYNC_COMPLETE'));
                showToast(`✅ Synced ${messages.length} messages`);
            }
        } else {
            showToast("❌ Sync Failed", "error");
        }
    });
}

function getRoomId() {
  const match = window.location.href.match(/room_([a-f0-9]+)/);
  return match ? match[1] : null;
}

function handleRoomChange(roomId) {
  if (roomId === lastRoomId) return;
  lastRoomId = roomId;

  console.log(`Upie: Room Change Detected -> ${roomId}`);
  messageBuffer.clear();
  updateUICount();

  // Query backend for thread status (Sync Check)
  safeSendMessage({
    action: "CHECK_THREAD_STATUS",
    roomId: roomId
  }, (response) => {
    const threadName = extractThreadName();
    const eventDetail = {
      roomId: roomId,
      name: threadName,
      exists: response && response.exists,
      msgCount: response ? response.messageCount : 0,
      lastSync: response ? response.lastSync : null,
      syncStatus: response ? response.syncStatus : 'not_synced',
      lastMessagePreview: response ? response.lastMessagePreview : "",
      summary: response ? response.summary : "",
      // ── Phase 1: forward all intelligence fields ──────────────────
      analytics:   response ? (response.analytics   || {}) : {},
      actionItems: response ? (response.actionItems  || []) : [],
      riskFlags:   response ? (response.riskFlags    || []) : [],
      // ─────────────────────────────────────────────────────────────
      error: response && (response.error || (!response.success && response.hasOwnProperty('success')))
    };

    if (!response || (response.exists === undefined && response.error)) {
      eventDetail.error = true;
    }

    window.dispatchEvent(new CustomEvent('Upie_THREAD_INFO', { detail: eventDetail }));

    if (response && response.exists) {
      console.log(`Upie: Thread ${roomId} already in DB. Status: ${response.syncStatus}`);
    }
  });
}

function extractConversation() {
  let messages = [];
  const messageNodes = document.querySelectorAll('.up-d-story, .up-d-story-item, [data-test="message-item"], .up-chat-message, .message-item, article, [role="listitem"]');
  console.log(`Upie: Analyzing ${messageNodes.length} nodes for messages.`);

messageNodes.forEach(msg => {
    const fullText = msg.innerText;
    
    // 0. Extract Message ID from DOM
    let messageId = msg.getAttribute('data-message-id') || msg.id || null;
    if (!messageId) {
      // Try to find in a nested element if it's a wrapper
      messageId = msg.querySelector('[data-message-id]')?.getAttribute('data-message-id');
    }
    
    // 1. Hunt for Sender
    let sender = msg.querySelector('.user-name, .sender-name, .name, [data-test="sender-name"], .up-avatar-text, strong, b, span[aria-label]')?.innerText;
    
    // 2. Hunt for Time
    let time = msg.querySelector('.message-time, time, .up-chat-message-time, [data-test="message-time"], .time, span.text-muted')?.innerText;
    if (!time) {
      const timeMatch = fullText.match(/\d{1,2}:\d{2}\s?(?:AM|PM)/i);
      if (timeMatch) time = timeMatch[0];
    }

    // 3. Hunt for Role
    let role = "freelancer"; // Default
    if (msg.classList.contains('client-message') || msg.querySelector('.client-label, [data-test="client-role"]')) {
      role = "client";
    }

    // 4. Hunt for Attachments
    const attachmentLinks = Array.from(msg.querySelectorAll('a[href*="/messages/room/"][href*="/download/"], .attachment-link')).map(a => a.href);

    // 5. Hunt for Text
    const contentEl = msg.querySelector('.message-text, .up-chat-message-text, .message-content, [data-test="message-text"], .up-d-story-content-text, p, span[data-test="message-content"]');
    let text = contentEl ? contentEl.innerText.trim() : "";
    
    if (!text && fullText.length > 5) {
      text = fullText.replace(sender || "", "").replace(time || "", "").trim();
    }

    if (text && text.length > 0) {
      messages.push({
        message_id: messageId,
        sender: (sender || "Participant").trim(),
        role: role,
        text: text.trim(),
        time: (time || null),
        attachments: attachmentLinks
      });
    }
  });

  // Unique messages by sender and start of text to avoid double counting
  const uniqueMessages = [];
  const seen = new Set();
  messages.forEach(m => {
    const key = `${m.sender}:${m.text.substring(0, 100)}`;
    if (!seen.has(key)) {
      uniqueMessages.push(m);
      seen.add(key);
    }
  });

  console.log(`Upie: Captured ${uniqueMessages.length} unique messages.`);
  if (uniqueMessages.length > 0) {
    console.log("Upie: Data Preview (Latest 3):", uniqueMessages.slice(-3));
  }

  return {
    thread_name: extractThreadName(),
    client_sidebar: extractClientSidebar(),
    messages: uniqueMessages
  };
}

function extractClientSidebar() {
  const sidebar = document.querySelector('.sidebar, .right-sidebar, .up-chat-room-settings, [data-test="room-settings"], aside.up-chat-room-settings');
  if (!sidebar) return null;

  // New Upwork UI: Data is tucked under "Client profile" accordion
  // 1. Check if the "Client profile" section exists at all
  const hasProfileTab = sidebar.innerText.includes('Client profile');
  const hasAboutClientHeader = sidebar.innerText.includes('About the client');
  
  // 2. Determine if it's "Ready" (expanded and showing data) or just "Found but closed/loading"
  const hasStats = sidebar.innerText.includes('hire rate') || sidebar.innerText.includes('spent') || sidebar.querySelector('.info-section');
  
  if (!hasStats) {
    if (hasProfileTab || hasAboutClientHeader) {
      return { is_loading: true, needs_interaction: true }; // Target found, but user needs to open it
    }
    return { is_loading: true }; // Sidebar frame exists, but no client content yet
  }

  const text = sidebar.innerText;
  
  // Scraper Phase 2: Targeted extraction from Upwork's specific sidebar structures
  const clientName = sidebar.querySelector('.profile-title')?.innerText?.trim();
  const locationEl = sidebar.querySelector('[data-location]');
  const localTimeText = locationEl?.innerText?.trim(); // e.g. "11:27 AM GMT (5 h behind)"
  
  // Extract specific sections from the "About the client" panel if available
  const sections = Array.from(sidebar.querySelectorAll('.info-section'));
  let country = "";
  let city = "";
  let jobsPosted = "";
  let hireRate = "";
  let hiresCount = "0";
  let totalSpent = "";
  let rating = "";
  let memberSince = "";
  let isRepeatWithMe = false;
  let preciseLocalTime = "";

  sections.forEach(sec => {
    const secText = sec.innerText;
    if (secText.includes('reviews')) rating = secText.trim();
    
    // Explicitly check for repeat relationship with user
    if (secText.toLowerCase().includes('worked with you') || secText.toLowerCase().includes('jobs with you')) {
       isRepeatWithMe = true;
    }

    const strongTag = sec.querySelector('strong.text-dark-on-inverse');
    const subTextEl = sec.querySelector('.text-light-on-inverse');
    if (strongTag && subTextEl && subTextEl.innerText.match(/\d{1,2}:\d{2}/)) {
       country = strongTag.innerText.trim();
       const subText = subTextEl.innerText.trim();
       city = subText.split(/\d/)[0].trim().replace(',', '');
       const timeMatch = subText.match(/\d{1,2}:\d{2}\s?(?:AM|PM)/i);
       if (timeMatch) preciseLocalTime = timeMatch[0];
    }

    if (secText.includes('posted')) jobsPosted = secText.trim().split('\n')[0];
    if (secText.includes('hire rate')) hireRate = secText.match(/\d+%/)?.[0];
    if (secText.includes('spent')) totalSpent = secText.match(/\$\d+[KkM+]?\+?\stotal\sspent/)?.[0]?.replace(' total spent', '');
    if (secText.includes('Member since')) memberSince = secText.trim();
  });

  // Fallback: If sections didn't catch everything (new layout), scrape the whole sidebar text
  if (!hireRate) hireRate = text.match(/\d+%\shire\srate/i)?.[0]?.match(/\d+%/)?.[0];
  if (hiresCount === "0") hiresCount = text.match(/(\d+)\shires/i)?.[1] || "0";
  if (!totalSpent) totalSpent = text.match(/\$\d+[KkM+]?\+?\stotal\sspent/i)?.[0]?.replace(/ total spent/i, '');
  if (!rating) rating = text.match(/\d\s?of\s?\d\s?reviews/i)?.[0];

  // Calculate Best Time Strategy
  const finalTime = preciseLocalTime || localTimeText || "";
  let bestTimeNote = "Send a reply to stay on their radar.";
  if (finalTime) {
      const timeOnly = finalTime.match(/\d{1,2}:\d{2}\s?(?:AM|PM)/i)?.[0];
      if (timeOnly) {
          bestTimeNote = `The client's local time is ${timeOnly}. Replying now ensures you're at the top of their list for their next morning check.`;
          // If it's early morning for them (e.g. 8-11 AM), note that they are likely active.
          const hourMatch = timeOnly.match(/^(\d{1,2})/);
          const isAM = timeOnly.toUpperCase().includes('AM');
          if (hourMatch && isAM) {
              const hour = parseInt(hourMatch[1]);
              if (hour >= 8 && hour <= 11) bestTimeNote = `🚀 Client is currently in their peak morning hours (${timeOnly}). Send a reply NOW for highest response probability!`;
          }
      }
  }

  return {
    client_name: clientName,
    local_time: finalTime || null,
    location: country ? `${city ? city + ', ' : ''}${country}` : null,
    hire_rate: hireRate || null,
    hires_count: hiresCount,
    total_spent: totalSpent || null,
    jobs_posted: jobsPosted || null,
    rating: rating || null,
    member_since: memberSince || null,
    is_repeat_with_me: isRepeatWithMe,
    best_time_strategy: bestTimeNote
  };
}

// Ensure functions are strictly exposed to floating_ui.js
window.extractConversation = extractConversation;
window.extractClientSidebar = extractClientSidebar;
window.extractThreadName = extractThreadName;

function extractThreadName() {
  const selectors = [
    '.up-chat-room-header-title',
    '.fe-message-thread-header h4',
    '[data-test="room-title"]',
    '.air3-card-header-title',
    '.room-title',
    '.up-chat-room-title',
    'h1'
  ];
  
  for (const selector of selectors) {
    const el = document.querySelector(selector);
    if (el && el.innerText.trim()) return el.innerText.replace(/\n/g, ' ').trim();
  }
  
  return document.title.replace(' - Upwork', '') || "Unknown Thread";
}

function showToast(message, type = "info") {
  const toast = document.createElement("div");
  toast.style.position = "fixed";
  toast.style.bottom = "20px";
  toast.style.right = "20px";
  toast.style.padding = "10px 20px";
  toast.style.borderRadius = "5px";
  toast.style.color = "white";
  toast.style.backgroundColor = type === "error" ? "#f44336" : "#4CAF50";
  toast.style.zIndex = "999999";
  toast.style.boxShadow = "0 2px 5px rgba(0,0,0,0.2)";
  toast.innerText = message;
  document.body.appendChild(toast);
  setTimeout(() => toast.remove(), 4000);
}

console.log("Upie: Scraper Content Script Injected on " + window.location.href);
sendDomSnapshot("initial_load");

// Keep collecting structural changes for HTML-drift immunity.
const semanticDomObserver = new MutationObserver((mutations) => {
  const relevant = mutations.some((m) => m.addedNodes && m.addedNodes.length > 0);
  if (relevant) {
    scheduleDomSnapshot("mutation_observer");
  }
});
semanticDomObserver.observe(document.body, { childList: true, subtree: true });

window.addEventListener('Upie_SYNC_FULL', async () => {
    console.log("Upie: Starting Full History Sync...");
    isSyncing = true;
    stopSyncRequested = false;
    await performFullSync();
});

window.addEventListener('Upie_SYNC_NEW', () => {
    console.log("Upie: Starting New Message Sync...");
    const data = extractConversation();
    syncMessages(data.messages, 'partially_synced');
});

window.addEventListener('Upie_STOP_SYNC', () => {
    console.log("Upie: Stopping Sync...");
    stopSyncRequested = true;
    isSyncing = false;
});

window.addEventListener('Upie_REFRESH_SUMMARY', () => {
    console.log("Upie: Refreshing Summary...");
    // Just sync latest to trigger summary re-gen on backend
    const data = extractConversation();
    syncMessages(data.messages.slice(-5), 'partially_synced');
});

async function performFullSync() {
    const scrollContainer = findScrollContainer();
    if (!scrollContainer) {
        showToast("Error: Scroll container not found", "error");
        isSyncing = false;
        return;
    }

    let previousHeight = 0;
    let attempts = 0;
    
    while (!stopSyncRequested && attempts < 100) { // Safety limit
        previousHeight = scrollContainer.scrollHeight;
        scrollContainer.scrollTop = 0; // Scroll to top to trigger load
        
        await new Promise(r => setTimeout(r, 2000)); // Wait for content load
        
        const data = extractConversation();
        syncMessages(data.messages, 'partially_synced'); // Sync batches as we go

        if (scrollContainer.scrollHeight === previousHeight) {
            attempts++;
            if (attempts > 5) break; // Finished or stuck
        } else {
            attempts = 0;
        }
    }
    
    if (!stopSyncRequested) {
        const finalData = extractConversation();
        syncMessages(finalData.messages, 'fully_synced');
        showToast("✅ Full Thread Synced");
    }
    
    isSyncing = false;
    window.dispatchEvent(new CustomEvent('Upie_SYNC_COMPLETE'));
}

function startAutoSyncLoop() {
  if (autoSyncInterval) return;
  console.log("Upie: Starting Auto-Sync Loop...");
  autoSyncInterval = setInterval(() => {
    if (captureActive || isSyncing) return;
    const data = extractConversation();
    if (data.messages.length > 0) {
      syncMessages(data.messages, 'partially_synced');
    }
  }, 120000); // Every 2 minutes
}

function stopAutoSyncLoop() {
  if (autoSyncInterval) {
    clearInterval(autoSyncInterval);
    autoSyncInterval = null;
    console.log("Upie: Auto-Sync Loop Stopped.");
  }
}

// 1. Check on initial page load - handled by loop
// Removed redundant load-time triggers here to prevent double-firing

// 2. Poll the URL every 1200ms
setInterval(checkStealthTrigger, 1200);

window.addEventListener('focus', () => {
  checkStealthTrigger(); 
});


// Heartbeat to confirm injection - silenced
setInterval(() => {
  // console.log("Upie: Scraper Heartbeat - Active on " + window.location.href);
}, 60000); 


async function stealthFetchJobDetails() {
  try {
    // 1. Find the link to the original Job Posting
    showToast("🔍 Upie: Searching for Job Link...");
    let jobHref = null;
    const allLinks = document.querySelectorAll('a');
    
    // First try: look for explicit text matches (Case-insensitive)
    for (let el of allLinks) {
      const t = el.innerText.toLowerCase().trim();
      if (t === "view job posting" || t === "view job" || t === "job details" || t === "original job posting" || t.includes("view job posting")) {
        jobHref = el.href;
        console.log("Upie Stealth: Found link by text match:", t, "->", jobHref);
        break;
      }
    }
    
    // Second try: look by URL pattern specifically for job hashes
    if (!jobHref) {
      for (let el of allLinks) {
        if ((el.href.includes("/jobs/~") || el.href.includes("/freelance-jobs/")) && !el.href.includes("/proposals")) {
          jobHref = el.href;
          console.log("Upie Stealth: Found link by URL pattern:", jobHref);
          break;
        }
      }
    }
    
    // 1.5 Extract current proposal data
    const proposalData = extractSingleProposal();
    
    if (!jobHref) {
      console.log("Upie Stealth: No Job Link found on this proposal page. Sending isolated proposal data.");
      showToast("⚠️ Upie: Job Link not found. Saving Proposal only.", "info");
      // Fallback: Send just the proposal if we can't find the job description link
      chrome.runtime.sendMessage({
        action: "SEND_TO_Upie",
        payload: {
          type: "proposals",
          data: proposalData,
          url: window.location.href,
          timestamp: new Date().toISOString()
        }
      });
      return;
    }
    
    // 2. Perform Human-Like "Shadow Tab" Extraction
    showToast("👤 Upie: Simulating human click (Shadow Tab)...");
    console.log("Upie Stealth: Handing off to background for Shadow Ingest:", jobHref);
    
    chrome.runtime.sendMessage({
      action: "PERFORM_SHADOW_INGEST",
      payload: {
        jobUrl: jobHref,
        proposalData: proposalData[0]
      }
    }, (res) => {
      if (res && res.success) {
        console.log("✅ Upie Stealth: Shadow Ingest Successful!");
        showToast("✅ Upie: Human-like ingestion successful!");
      } else {
        console.error("❌ Upie Stealth: Shadow Ingest Failed:", res);
        showToast("❌ Upie: Stealth fetch blocked by firewall.", "error");
      }
    });
      } catch(e) {
    console.error("Upie Stealth Automation Failed:", e);
    showToast("❌ Upie Critical Error: " + e.message, "error");
  }
}

// --- Bulk Sync Automation ---

async function bulkSyncArchivedProposals() {
    console.log("Upie: Starting Bulk Archived Sync...");
    const links = Array.from(document.querySelectorAll('a[href*="/nx/proposals/"]'))
        .filter(a => /\d+/.test(a.href) && !a.href.includes('/proposals/archive/') && !a.href.includes('/job-details/'))
        .map(a => a.href);
    
    // Remove duplicates
    const uniqueLinks = [...new Set(links)];
    
    if (uniqueLinks.length === 0) {
        showToast("No archived proposals found on this page.", "error");
        return;
    }

    showToast(`🚀 Starting Bulk Sync for ${uniqueLinks.length} proposals...`);
    
    for (let i = 0; i < uniqueLinks.length; i++) {
        const url = uniqueLinks[i];
        console.log(`Upie Bulk: [${i+1}/${uniqueLinks.length}] Ingesting: ${url}`);
        
        // Use background to open shadow tab and scrape
        await new Promise((resolve) => {
            chrome.runtime.sendMessage({
                action: "PERFORM_SHADOW_INGEST_ARCHIVED",
                payload: { url }
            }, (res) => {
                if (res && res.success) {
                    console.log(`✅ Success: ${url}`);
                } else {
                    console.error(`❌ Failed: ${url}`, res?.error);
                }
                // Small delay between tabs to be polite
                setTimeout(resolve, 3000);
            });
        });
        
        // Update UI progress if we had a progress bar, for now just log
        if (i % 5 === 0 && i > 0) {
            showToast(`Progress: ${i}/${uniqueLinks.length} synced...`);
        }
    }
    
    showToast("✅ Bulk Sync Complete!", "success");
}

async function bulkSyncConversations() {
    console.log("Upie: Starting Bulk Conversation Sync...");
    
    // Find all room links in the sidebar
    const roomLinks = Array.from(document.querySelectorAll('a[href*="/messages/rooms/"]'));
    const uniqueRoomIds = [...new Set(roomLinks.map(a => {
        const m = a.href.match(/rooms\/([^/?]+)/);
        return m ? m[1] : null;
    }))].filter(id => id !== null);

    if (uniqueRoomIds.length === 0) {
        showToast("No conversation rooms found in sidebar.", "error");
        return;
    }

    showToast(`🚀 Starting Bulk Sync for ${uniqueRoomIds.length} threads...`);
    
    for (let i = 0; i < uniqueRoomIds.length; i++) {
        const roomId = uniqueRoomIds[i];
        const roomUrl = `https://www.upwork.com/messages/rooms/${roomId}`;
        
        console.log(`Upie Bulk Convo: [${i+1}/${uniqueRoomIds.length}] Opening room: ${roomId}`);
        
        // Navigation - we use location.href for simplicity in the same tab
        window.location.href = roomUrl;
        
        // Wait for page to load and scraper to be ready
        await new Promise(r => setTimeout(r, 5000));
        
        // Since the page reloads/navigates, the script instance might change.
        // We need a way to persist the 'bulk state'.
        // Better: Use storage to keep track of remaining rooms and trigger sync on load.
        chrome.storage.local.set({ 
            upie_bulk_convo_queue: uniqueRoomIds.slice(i + 1),
            upie_bulk_convo_active: true
        });
        
        // Trigger the full sync for THIS room
        await performFullSync();
        
        // The loop will break here if we navigate. 
        // We need to handle the 'next' room in the 'on load' logic.
        break; 
    }
}

// Logic to continue bulk sync after navigation
chrome.storage.local.get(['upie_bulk_convo_queue', 'upie_bulk_convo_active'], async (res) => {
    if (res.upie_bulk_convo_active && res.upie_bulk_convo_queue && res.upie_bulk_convo_queue.length > 0) {
        console.log(`Upie Bulk: Continuing sync. ${res.upie_bulk_convo_queue.length} rooms remaining.`);
        
        // First, sync current room
        await new Promise(r => setTimeout(r, 3000)); // Wait for render
        await performFullSync();
        
        // Move to next
        const nextRooms = res.upie_bulk_convo_queue;
        const currentRoomId = nextRooms.shift();
        
        if (currentRoomId) {
            chrome.storage.local.set({ upie_bulk_convo_queue: nextRooms });
            window.location.href = `https://www.upwork.com/messages/rooms/${currentRoomId}`;
        } else {
            chrome.storage.local.set({ upie_bulk_convo_active: false });
            showToast("✅ All Conversations Synced!", "success");
        }
    } else if (res.upie_bulk_convo_active) {
        chrome.storage.local.set({ upie_bulk_convo_active: false });
        showToast("✅ All Conversations Synced!", "success");
    }
});

window.addEventListener('Upie_BULK_SYNC_CONVOS', bulkSyncConversations);
window.addEventListener('Upie_BULK_SYNC_ARCHIVE', bulkSyncArchivedProposals);

// --- Extraction Logic ---

function extractProposalsList() {
  // Scrapes the proposals list (Active, Archived, etc.)
  let proposals = [];
  // Note: Upwork's DOM changes frequently. This looks for typical proposal row patterns.
  // Currently targeting elements that look like proposal cards/rows.
  const rowElements = document.querySelectorAll('[data-test="proposal-item"], .up-card-section:has(h4)');
  
  if (rowElements.length === 0) {
     // Fallback if the DOM classes changed
     const titles = document.querySelectorAll('h4.mb-0, .job-title');
     titles.forEach(t => {
       proposals.push({
         title: t.innerText.trim(),
         status: "Archived/Active", // Will need refinement based on exact DOM structure
         date: new Date().toISOString(), // Mocking date if unobtainable
         raw_html: t.parentElement.innerHTML
       });
     });
  } else {
    rowElements.forEach(row => {
      const titleEl = row.querySelector('h4, a.up-n-link');
      const dateEl = row.querySelector('.text-light, [data-test="submitted-date"]');
      const statusEl = row.querySelector('.up-badge, [data-test="proposal-status"]');
      
      proposals.push({
        title: titleEl ? titleEl.innerText.trim() : "Unknown Title",
        submitted_date: dateEl ? dateEl.innerText.trim() : null,
        status: statusEl ? statusEl.innerText.trim() : "Unknown",
        raw_text: row.innerText
      });
    });
  }
  
  return proposals;
}

function extractSingleProposal() {
  // Scrapes a specific sent/active proposal page (e.g. upwork.com/nx/proposals/...)
  const titleEl = document.querySelector('h1, h2, h3, .job-title, [data-test="job-title"]');
  const statusEl = document.querySelector('.up-badge, [data-test="proposal-status"]');
  const coverLetterEl = document.querySelector('[data-test="cover-letter"], .cover-letter, blockquote');
  const bidEl = document.querySelector('[data-test="bid-amount"], .budget-item strong');
  
  // Extract all page text for "hunting" specific data
  const pageText = document.body.innerText;
  
  let hiringActivity = {};
  // Search for hiring activity patterns
  const activityMatch = pageText.match(/(\d+)\s+proposals/i);
  if (activityMatch) hiringActivity.proposals = activityMatch[0];
  
  const messagedMatch = pageText.match(/(\d+)\s+messaged/i);
  if (messagedMatch) hiringActivity.messaged = messagedMatch[0];

  let clientInfo = {};
  // Hunt for Client Metadata using text patterns
  const hireRateMatch = pageText.match(/(\d+)%\s+hire rate/i);
  if (hireRateMatch) clientInfo.hire_rate = hireRateMatch[0];
  
  const spentMatch = pageText.match(/\$(\d+[KkMmg]?)?\s+total spent/i);
  if (spentMatch) clientInfo.total_spent = spentMatch[0];
  
  const ratingMatch = pageText.match(/Rating is ([\d\.]+)\s+out of 5/i);
  if (ratingMatch) clientInfo.rating = ratingMatch[1];

  const locationMatch = pageText.match(/(Canada|United States|United Kingdom|Australia|India|Pakistan|Bangladesh|Germany|France)/i); // Common locations
  if (locationMatch) clientInfo.location = locationMatch[0];
  
  const coverText = coverLetterEl ? coverLetterEl.innerText.trim() : "";
  
  return [{
    title: titleEl ? titleEl.innerText.trim() : (pageText.match(/Job details\n(.*)/)?.[1] || "Unknown Title"),
    status: statusEl ? statusEl.innerText.trim() : "Active",
    proposal_text: coverText,
    cover_letter: coverText, // Keep both for backward/forward compatibility
    bid_amount: bidEl ? bidEl.innerText.trim() : "",
    hiring_activity: hiringActivity,
    client_info: clientInfo,
    raw_text: coverText ? "" : pageText.substring(0, 5000) // Only send full text as fallback
  }];
}

// ── Strict Manual Extraction for Upie Manual Collector ───────────────────
window.extractManualProposal = function() {
    let title = document.title.replace(' - Upwork', '').replace('Proposal: ', '').trim();
    const h1 = document.querySelector('h1');
    if (h1 && h1.innerText.length > 3) title = h1.innerText.trim();

    // Semantic traversal avoiding brittle CSS
    const textNodeScrape = (labelRegex) => {
        const nodes = Array.from(document.querySelectorAll('h1, h2, h3, h4, h5, h6, strong, label, div'));
        for (let el of nodes) {
            // Must be exact or very close to prevent giant div matches
            if (labelRegex.test(el.innerText) && el.innerText.length < 50) {
                let sibling = el.nextElementSibling;
                if (sibling && sibling.innerText.trim().length > 0) return sibling.innerText.trim();
                let parentSibling = el.parentElement?.nextElementSibling;
                if (parentSibling && parentSibling.innerText.trim().length > 0) return parentSibling.innerText.trim();
            }
        }
        return "";
    };

    let proposalText = textNodeScrape(/Cover Letter/i) || document.querySelector('blockquote, [data-test="cover-letter"]')?.innerText || "";
    let bidAmount = textNodeScrape(/(Bid|Your proposed terms|Hourly Rate)/i) || document.querySelector('.budget-item strong, [data-test="bid-amount"]')?.innerText || "";
    let jobDescription = textNodeScrape(/Job details|Job Description/i) || document.querySelector('.job-description, [data-test="job-description-text"]')?.innerText || "";
    let timeline = textNodeScrape(/(Timeline|Project Length|Less than|More than)/i) || "";
    
    // Status Resolution
    let status = "Active";
    const bodyText = document.body.innerText;
    if (bodyText.match(/\bArchived\b/i) || bodyText.match(/\bWithdrawn\b/i)) status = "Archived";
    if (bodyText.match(/\bDeclined\b/i)) status = "Declined";
    if (bodyText.match(/\bHired\b/i)) status = "Hired";

    // Clean Bid
    let cleanBid = bidAmount.split('\n')[0].replace(/[^0-9.$]/g, '');

    return {
        proposal_link: location.href.split('?')[0], // Unique Context ID
        job_title: title,
        client_name: "Hidden by Upwork", // Client name is generally masked on archived proposals
        proposal_text: proposalText.replace(/\s+/g, ' ').trim(),
        bid_amount: cleanBid,
        job_description: jobDescription.replace(/\n/g, ' ').substr(0, 3000), // Clean layout breaks
        timeline: timeline.replace(/\n/g, ' ').substr(0, 100),
        outcome: status,
        raw_text: bodyText.substring(0, 15000) // Let backend LLM perform deep extraction if needed
    };
};

function extractJobDetails() {
  // Scrapes a specific Job description page
  const titleEl = document.querySelector('h1.up-card-title, h1');
  const descEl = document.querySelector('.job-description, [data-test="job-description-text"]');
  const budgetEl = document.querySelector('[data-test="budget"], .budget-item');
  const skillsEls = document.querySelectorAll('[data-test="skill"], .up-skill-badge');

  let skills = [];
  skillsEls.forEach(s => skills.push(s.innerText.trim()));

  return {
    title: titleEl ? titleEl.innerText.trim() : "Unknown Job",
    description: descEl ? descEl.innerText.trim() : "Unknown Description",
    budget: budgetEl ? budgetEl.innerText.trim() : "Unknown Budget",
    skills: skills,
    raw_text: document.body.innerText.substring(0, 30000), // First 30k chars to ensure we capture Client History/Activity
    raw_html: document.body.outerHTML.substring(0, 500000)
  };
}

// ============================================================================

// ============================================================================
// Upie ON-DEMAND CONTEXT PROVIDER (HYBRID AI ASSIST)
// ============================================================================

/*
chrome.runtime.onMessage.addListener((request, sender, sendResponse) => {
  if (request.action === "EXTRACT_PAGE_CONTENT") {
    console.log("Upie: Received EXTRACT_PAGE_CONTENT from Popup");
    try {
      if (location.href.includes('/messages/')) {
         sendResponse(window.extractConversation());
      } else if (location.href.includes('/proposals/')) {
         sendResponse(window.extractManualProposal());
      } else if (location.href.includes('/jobs/') || location.href.includes('job-details')) {
         sendResponse(extractJobDetails());
      } else {
         sendResponse({ raw_text: document.body.innerText.substring(0, 15000) });
      }
    } catch(e) {
      console.error("Upie Context Extract Err:", e);
      sendResponse({ status: "error", message: e.message });
    }
    return true; // Keep channel open for async if needed
  }
});
*/

function extractFreelancerProfile() {
  const nameEl = document.querySelector('.up-name-wrapper h2, h1');
  const titleEl = document.querySelector('.up-profile-title, h1');
  const overviewEl = document.querySelector('.up-profile-description, [data-test="profile-overview"]');
  const rateEl = document.querySelector('.up-rate, [data-test="hourly-rate"]');
  const skillsEls = document.querySelectorAll('.up-skill-badge');

  let skills = [];
  skillsEls.forEach(s => skills.push(s.innerText.trim()));

  return {
    name: nameEl ? nameEl.innerText.trim() : "User",
    title: titleEl ? titleEl.innerText.trim() : "",
    overview: overviewEl ? overviewEl.innerText.trim() : "",
    hourly_rate: rateEl ? parseFloat(rateEl.innerText.replace(/[^0-9.]/g, '')) : 0,
    skills: skills,
    raw_text: document.body.innerText.substring(0, 15000),
    raw_html: document.body.outerHTML.substring(0, 500000)
  };
}

function extractProposalSubmission() {
  // Scrapes the "Apply for Job" / "Submit Proposal" page
  const coverLetterEl = document.querySelector('textarea, .cover-letter-area');
  const bidEl = document.querySelector('input[type="number"], .bid-amount-input');
  const jobTitleEl = document.querySelector('h1, .job-title');

  return {
    job_title: jobTitleEl ? jobTitleEl.innerText.trim() : "Unknown Job",
    cover_letter: coverLetterEl ? coverLetterEl.value : "",
    bid_amount: bidEl ? parseFloat(bidEl.value) : 0,
    timestamp: new Date().toISOString(),
    raw_text: document.body.innerText.substring(0, 20000),
    raw_html: document.body.outerHTML.substring(0, 500000)
  };
}

// Expose to window for UI buttons
window.extractFreelancerProfile = extractFreelancerProfile;
window.extractProposalSubmission = extractProposalSubmission;
