(function() {
  'use strict';

  if (!chrome.runtime || !chrome.runtime.id) return;
  if (window.vantageControllerLoaded) return;
  window.vantageControllerLoaded = true;

  // ── Shadow DOM bootstrap ─────────────────────────────────────────────────
  const container = document.createElement('div');
  container.id = 'vantage-controller-root';
  container.style.position = 'fixed';
  container.style.top = '0';
  container.style.left = '0';
  container.style.width = '100vw';
  container.style.height = '100vh';
  container.style.zIndex = '2147483647';
  container.style.pointerEvents = 'none';
  document.body.appendChild(container);

  const shadow = container.attachShadow({ mode: 'open' });
  const styleLink = document.createElement('link');
  styleLink.rel = 'stylesheet';
  styleLink.href = chrome.runtime.getURL('content_scripts/floating_ui.css');
  shadow.appendChild(styleLink);

  const panelHTML = `
    <div id="vantage-floating-controller">
      <!-- Skeleton Load Mask overlaying the whole app excluding header -->
      <div id="vantage-skeleton" class="vantage-skeleton-overlay vantage-hidden">
        <div class="vantage-spinner"></div>
        <div class="vantage-skel-text" id="vantage-skel-msg">Processing...</div>
      </div>

      <div id="vantage-header">
        <div id="vantage-logo">
          <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" style="margin-right: 2px; color: var(--accent);">
            <path d="M12 2a5 5 0 0 0-5 5v1a4 4 0 0 0-4 4 3 3 0 0 0 3 3 2 2 0 0 1 2 2 4 4 0 0 0 8 0 2 2 0 0 1 2-2 3 3 0 0 0 3-3 4 4 0 0 0-4-4V7a5 5 0 0 0-5-5Z"></path>
            <path d="M9 14.5v-2a2 2 0 1 1 4 0v2"></path>
            <path d="M11 19a1 1 0 1 0 2 0 1 1 0 1 0-2 0Z"></path>
          </svg>
          Vantage Chat
        </div>
        <div class="vantage-header-actions" style="position:relative;">
          <button id="vantage-btn-menu" class="vantage-icon-btn" title="Menu">
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><line x1="3" y1="12" x2="21" y2="12"></line><line x1="3" y1="6" x2="21" y2="6"></line><line x1="3" y1="18" x2="21" y2="18"></line></svg>
          </button>
          
          <div id="vantage-dropdown-menu" class="vantage-hidden">
            <button class="vantage-dropdown-item" id="vantage-btn-new-chat">
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" style="margin-right:6px"><polygon points="14 2 18 6 7 17 3 17 3 13 14 2"></polygon><line x1="3" y1="22" x2="21" y2="22"></line></svg> New Chat
            </button>
            <button class="vantage-dropdown-item" id="vantage-btn-export-chat">
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" style="margin-right:6px"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"></path><polyline points="7 10 12 15 17 10"></polyline><line x1="12" y1="15" x2="12" y2="3"></line></svg> Export Chat Log
            </button>
            <div style="height:1px; background:var(--border-light); margin:4px 0;"></div>
            <button class="vantage-dropdown-item" id="vantage-btn-theme">
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" style="margin-right:6px"><path d="M21 12.79A9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79z"></path></svg> Toggle Dark Theme
            </button>
            <div style="height:1px; background:var(--border-light); margin:4px 0;"></div>
            <button class="vantage-dropdown-item" id="vantage-btn-extract-convo">
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" style="margin-right:6px"><polyline points="22 12 18 12 15 21 9 3 6 12 2 12"></polyline></svg> Sync Room to DB
            </button>
          </div>

          <button id="vantage-btn-close" class="vantage-icon-btn" title="Close">
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><line x1="18" y1="6" x2="6" y2="18"></line><line x1="6" y1="6" x2="18" y2="18"></line></svg>
          </button>
        </div>
      </div>

      <!-- ======================================= -->
      <!-- PANE 1: BRAIN CHAT (Persistent AI)     -->
      <!-- ======================================= -->
      <div id="vantage-pane-chat" class="vantage-pane active">
        <div id="vantage-chat-history">
           <div class="vantage-chat-msg vantage-chat-ai">
             <p>I am Vantage. I have access to your historical proposals, past pricing, and similarity vectors.</p>
             <p>Ask me to query a past client, generate a draft, or calculate your average rate.</p>
           </div>
        </div>
        <div id="vantage-chat-input-area">
          <textarea id="vantage-chat-input" placeholder="Ask your brain anything..."></textarea>
          <button id="vantage-btn-chat-send">
            <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><line x1="22" y1="2" x2="11" y2="13"></line><polygon points="22 2 15 22 11 13 2 9 22 2"></polygon></svg>
          </button>
        </div>
      </div>

    </div>
  `;

  const panelWrap = document.createElement('div');
  panelWrap.innerHTML = panelHTML;
  const panel = panelWrap.firstElementChild;
  shadow.appendChild(panel);

  // ── Stable State Management ────────────────────────────────────────────────
  let isLoading = false;
  let chatHistory = [];

  // ── Drag Logic ─────────────────────────────────────────────────────────────
  const header = shadow.getElementById('vantage-header');
  let offset = {x:0, y:0};
  const onMouseMove = (e) => {
    let newX = e.clientX - offset.x;
    let newY = e.clientY - offset.y;
    const pad = 10, maxX = window.innerWidth - panel.offsetWidth - pad, maxY = window.innerHeight - panel.offsetHeight - pad;
    if (newX < pad) newX = pad; if (newX > maxX) newX = maxX;
    if (newY < pad) newY = pad; if (newY > maxY) newY = maxY;
    panel.style.left = newX + 'px';
    panel.style.top  = newY + 'px';
  };
  const onMouseUp = () => { window.removeEventListener('mousemove', onMouseMove); window.removeEventListener('mouseup', onMouseUp); };
  header.addEventListener('mousedown', e => {
    if (e.target.closest('button')) return;
    offset.x = e.clientX - panel.offsetLeft; offset.y = e.clientY - panel.offsetTop;
    panel.style.right = 'auto'; panel.style.bottom = 'auto'; // release strict CSS right/bottom
    window.addEventListener('mousemove', onMouseMove); window.addEventListener('mouseup', onMouseUp);
  });

  // ── UI Element Refs ────────────────────────────────────────────────────────
  const elClose = shadow.getElementById('vantage-btn-close');
  const elSkeleton = shadow.getElementById('vantage-skeleton');
  const elSkelMsg = shadow.getElementById('vantage-skel-msg');

  // Controls
  elClose.addEventListener('click', () => panel.classList.add('vantage-hidden'));

  const btnMenu = shadow.getElementById('vantage-btn-menu');
  const dropdownMenu = shadow.getElementById('vantage-dropdown-menu');
  
  btnMenu.addEventListener('click', (e) => {
    e.stopPropagation();
    dropdownMenu.classList.toggle('vantage-hidden');
  });

  shadow.addEventListener('click', (e) => {
    if (!e.target.closest('#vantage-dropdown-menu') && !btnMenu.contains(e.target)) {
      dropdownMenu.classList.add('vantage-hidden');
    }
  });

  // ── Session & Chat Persistence ──────────────────────────────────────────
  let chatSessionId = uuidv4(); // Unique session ID for each chat thread
  let activeRoomId = null; // Tracks the current Upwork room
  let clientMetadata = {}; // Tracks client profile info for the UI header
  let sidebarPollTimer = null; 
  let sidebarObserver = null;
  let clientProfileCaptured = false; // Prevents duplicate cards per room

  function uuidv4() {
    return 'xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx'.replace(/[xy]/g, function(c) {
      var r = Math.random() * 16 | 0, v = c == 'x' ? r : (r & 0x3 | 0x8);
      return v.toString(16);
    });
  }

  function startNewSession(reason = "manually") {
    chatHistory = []; // Clear local memory array
    chatSessionId = uuidv4(); // Rotate session ID for a fresh start
    clientMetadata = {}; // Reset metadata
    const historyView = shadow.getElementById('vantage-chat-history');
    if(historyView) {
      historyView.innerHTML = `
        <div class="vantage-chat-msg vantage-chat-ai">
          <p><strong>✨ Fresh Session Started</strong></p>
          <p>Chat memory cleared and session rotated (${reason}). How can I assist you further?</p>
        </div>
      `;
    }
  }

  shadow.getElementById('vantage-btn-new-chat').addEventListener('click', () => {
    dropdownMenu.classList.add('vantage-hidden');
    startNewSession("New Chat clicked");
  });

  // Listen for room changes from scraper and rotate session accordingly
  window.addEventListener('Vantage_THREAD_INFO', (e) => {
    const newRoomId = e.detail.roomId;
    const threadSummary = e.detail.summary; // Capture DB summary if exists
    
    if (newRoomId && newRoomId !== activeRoomId) {
      console.log(`Vantage UI: Room Shift Detected from ${activeRoomId} to ${newRoomId}. Rotating Session.`);
      activeRoomId = newRoomId;
      clientProfileCaptured = false; // Reset for new room
      startNewSession("Room context changed");
      
      if (sidebarPollTimer) clearInterval(sidebarPollTimer);
      if (sidebarObserver) sidebarObserver.disconnect();
      
      let isInteractionPromptShown = false;
      const checkSidebar = () => {
        if (clientProfileCaptured) return;
        try {
          const sidebarData = window.extractClientSidebar();
          if (sidebarData && !sidebarData.is_loading && sidebarData.location) {
            console.log("Vantage UI: Sidebar data captured! Rendering card.");
            clientMetadata = sidebarData;
            renderClientMetadataCard(e.detail.name, threadSummary);
            clientProfileCaptured = true;
            if (sidebarPollTimer) clearInterval(sidebarPollTimer);
            if (sidebarObserver) sidebarObserver.disconnect();
          } else if (sidebarData && sidebarData.is_loading) {
            if (sidebarData.needs_interaction && !isInteractionPromptShown) {
               console.log("Vantage UI: Client Profile section found but closed. Waiting for user to open it...");
               isInteractionPromptShown = true;
            }
          }
        } catch(err) {}
      };

      // 2. Start a mutation observer but target elements that change during sidebar interaction
      sidebarObserver = new MutationObserver((mutations) => {
        // Simple throttle: only check if there's a significant change (like a new section appearing)
        const hasRelevantChange = mutations.some(m => m.addedNodes.length > 0);
        if (hasRelevantChange) checkSidebar();
      });
      sidebarObserver.observe(document.body, { childList: true, subtree: true });

      // 3. Fallback Long Polling (up to 60 seconds)
      let sidebarPolls = 0;
      sidebarPollTimer = setInterval(() => {
        sidebarPolls++;
        checkSidebar();
        if (sidebarPolls >= 60 || clientProfileCaptured) {
          clearInterval(sidebarPollTimer);
        }
      }, 1000);
    }
  });

  function renderClientMetadataCard(threadName, summary) {
    const historyView = shadow.getElementById('vantage-chat-history');
    if (!historyView) return;

    // Detect Client Category based on hires
    const hires = parseInt(clientMetadata.hires_count || "0");
    const isRepeat = clientMetadata.is_repeat_with_me === true;
    
    let category = "New Client";
    if (isRepeat) {
      category = `Repeat Client`;
    } else if (hires === 0) {
      category = "New Client";
    } else if (hires === 1) {
      category = "First Project";
    } else if (hires === 2) {
      category = "2 Projects";
    } else if (hires === 3) category = "3 Projects";
    else if (hires > 3) category = "Active Client";

    const timeOnly = clientMetadata.local_time?.match(/\d{1,2}:\d{2}\s?(?:AM|PM)/i)?.[0] || 'N/A';

    const metaDiv = document.createElement('div');
    metaDiv.className = 'vantage-chat-msg vantage-chat-ai';
    metaDiv.style.padding = "10px 14px";
    metaDiv.style.fontSize = "12px";
    metaDiv.style.borderLeft = "4px solid var(--accent)";
    metaDiv.style.background = "var(--surface)";
    metaDiv.style.borderRadius = "8px";
    metaDiv.style.marginBottom = "10px";
    metaDiv.style.boxShadow = "0 2px 8px rgba(0,0,0,0.05)";
    
    let summaryHtml = "";
    if (summary) {
      summaryHtml = `
        <div style="margin-top: 10px; padding-top: 10px; border-top: 1px solid rgba(0,0,0,0.06);">
          <div style="font-size: 10px; font-weight: 700; text-transform: uppercase; color: var(--text-muted); margin-bottom: 4px; letter-spacing: 0.5px;">
            Conversation Overview
          </div>
          <div style="font-size: 11.5px; color: var(--text-main); font-style: italic; line-height: 1.5;">
            "${summary}"
          </div>
        </div>
      `;
    }

    const isPeak = clientMetadata.best_time_strategy?.includes('🚀');

    metaDiv.innerHTML = `
      <div style="font-weight: bold; font-size: 13.5px; color: var(--text-main); margin-bottom: 2px;">
        ${threadName || 'Client'} <span style="font-weight: normal; color: var(--text-muted); font-size: 11.5px;">(${category}, ${timeOnly})</span>
      </div>
      <div style="margin: 4px 0; color: var(--text-main); font-size: 12px; display: flex; align-items: center; gap: 6px;">
        <span><b>${clientMetadata.total_spent || '$0'}</b> spent</span>
        <span style="color: rgba(0,0,0,0.1);">|</span>
        <span><b>${clientMetadata.hires_count || '0'}</b> 💼</span>
        <span style="color: rgba(0,0,0,0.1);">|</span>
        <span><b>${clientMetadata.hire_rate || '0%'}</b> hire rate</span>
      </div>
      <div style="display: flex; align-items: center; gap: 4px; font-weight: 600; color: ${isPeak ? '#10b981' : 'var(--accent)'}; font-size: 11px; margin-top: 4px;">
        ${isPeak ? 'Active – good time to pitch 🚀' : '💡 Strategy: ' + clientMetadata.best_time_strategy?.split('.')[0]}
      </div>
      ${summaryHtml}
    `;
    historyView.appendChild(metaDiv);
    historyView.scrollTo(0, historyView.scrollHeight);
  }

  shadow.getElementById('vantage-btn-export-chat').addEventListener('click', () => {
    dropdownMenu.classList.add('vantage-hidden');
    let textToExport = "Vantage Intelligence - Chat Export\n================================\n\n";
    if (chatHistory.length === 0) {
      textToExport += "No chat history to export.";
    } else {
      chatHistory.forEach(msg => {
        textToExport += `[${msg.role.toUpperCase()}]\n${msg.content}\n\n`;
      });
    }

    const blob = new Blob([textToExport], { type: 'text/plain;charset=utf-8' });
    const url = URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.href = url;
    link.download = `Vantage_Chat_${new Date().toISOString().replace(/:/g, '-')}.txt`;
    link.click();
    URL.revokeObjectURL(url);
  });

  let isDarkTheme = false;
  shadow.getElementById('vantage-btn-theme').addEventListener('click', () => {
    dropdownMenu.classList.add('vantage-hidden');
    const controller = shadow.getElementById('vantage-floating-controller');
    isDarkTheme = !isDarkTheme;
    if (isDarkTheme) {
      controller.classList.add('vantage-dark-mode');
      shadow.getElementById('vantage-btn-theme').innerHTML = `<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" style="margin-right:6px"><circle cx="12" cy="12" r="5"></circle><line x1="12" y1="1" x2="12" y2="3"></line><line x1="12" y1="21" x2="12" y2="23"></line><line x1="4.22" y1="4.22" x2="5.64" y2="5.64"></line><line x1="18.36" y1="18.36" x2="19.78" y2="19.78"></line><line x1="1" y1="12" x2="3" y2="12"></line><line x1="21" y1="12" x2="23" y2="12"></line><line x1="4.22" y1="19.78" x2="5.64" y2="18.36"></line><line x1="18.36" y1="5.64" x2="19.78" y2="4.22"></line></svg> Toggle Light Theme`;
    } else {
      controller.classList.remove('vantage-dark-mode');
      shadow.getElementById('vantage-btn-theme').innerHTML = `<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" style="margin-right:6px"><path d="M21 12.79A9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79z"></path></svg> Toggle Dark Theme`;
    }
  });

  shadow.getElementById('vantage-btn-extract-convo').addEventListener('click', () => {
     dropdownMenu.classList.add('vantage-hidden');
     if (typeof window.extractConversation === 'undefined') {
        alert("Sync Error: Context extractor not loaded or this is not a messaging page.");
        return;
     }
     const btn = shadow.getElementById('vantage-btn-extract-convo');
     btn.innerHTML = `<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" style="margin-right:6px"><circle cx="12" cy="12" r="10"></circle><polyline points="12 6 12 12 16 14"></polyline></svg> Syncing...`;
     
     try {
       const payload = window.extractConversation();
       const roomMatch = location.href.match(/room_([a-f0-9]+)/);
       payload.room_id = roomMatch ? roomMatch[1] : location.href.match(/messages\/rooms\/([^?\/]+)/)[1];
       payload.conversation_link = location.href.split('?')[0]; 
       chrome.runtime.sendMessage({ action: "MANUAL_INGEST_CONVERSATION", data: payload }, (res) => {
         btn.innerHTML = `<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" style="margin-right:6px"><polyline points="20 6 9 17 4 12"></polyline></svg> Synced!`;
         setTimeout(() => {
           btn.innerHTML = `<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" style="margin-right:6px"><polyline points="22 12 18 12 15 21 9 3 6 12 2 12"></polyline></svg> Sync Room to DB`;
         }, 3000);
       });
     } catch (e) { alert("Failed to extract active conversation. Are you in a room?"); }
  });

  // ── Communication Utility ──────────────────────────────────────────────────
  function setUIState(loading, msg="Synthesizing Strategy...") {
    isLoading = loading;
    if(loading) elSkelMsg.innerText = msg;
    elSkeleton.classList.toggle('vantage-hidden', !loading);
    shadow.querySelectorAll('.vantage-btn').forEach(b => b.disabled = loading);
  }

  async function sendToBrain(event_type, additionalPayload = {}) {
    if (isLoading) return;
    
    const url = window.location.href;
    let roomId = null;
    if (url.includes('/messages/')) {
      const match = url.match(/room_([a-f0-9]+)/);
      if (match) roomId = match[1];
      else {
        const altMatch = url.match(/messages\/rooms\/([^?\/]+)/);
        if (altMatch) roomId = altMatch[1];
      }
    }

    const payload = {
      action: event_type,
      room_id: roomId,
      session_id: chatSessionId, // Inject unique session ID
      url: url,
      timestamp: new Date().toISOString(),
      ...additionalPayload
    };

    return new Promise((resolve) => {
      chrome.runtime.sendMessage(payload, (response) => resolve(response));
    });
  }

  // ── Auto Sync Prompt System ────────────────────────────────────────────────
  function initializeAutoSync() {
    try {
      const isRoom = location.href.includes('/messages/rooms/');
      const isProposal = location.href.includes('/proposals/') && !location.href.includes('proposals/active');

      if (!isRoom && !isProposal) return;

      setTimeout(async () => {
        if (isRoom) {
          const match = location.href.match(/room_([a-f0-9]+)/);
          const roomId = match ? match[1] : null;
          if (!roomId) return;

          // Check if thread exists in db (using raw fetch avoiding Chrome send message loop issues)
          try {
            const res = await fetch(`http://127.0.0.1:8000/api/v1/conversations/check?room_id=${roomId}`);
            const data = await res.json();
            
            // If data is null/not_found, it's a new room. Prompt User.
            if (!data || data.status === "not_found" || data.status === "error") {
              triggerSyncPrompt("New Room Detected!", "Would you like to sync this chat into your Vantage Database?", "SYNC ROOM", () => {
                shadow.getElementById('vantage-btn-extract-convo').click();
              });
            }
          } catch(e) {}
        } else if (isProposal) {
          const propIdMatch = location.href.match(/proposals\/([^?\/]+)/);
          if(!propIdMatch) return;
          const propId = propIdMatch[1];
          try {
            const res = await fetch(`http://127.0.0.1:8000/api/v1/sync/status/proposal?proposal_id=${propId}`);
            const data = await res.json();
            if(!data || data.status === "not_found") {
               triggerSyncPrompt("Unsynced Proposal Found", "Would you like Vantage to remember this proposal?", "SAVE PROPOSAL", () => {
                 shadow.getElementById('vantage-btn-extract-prop').click();
               });
            }
          } catch(e) {}
        }
      }, 3500); // Wait for page to breathe
    } catch(e) {}
  }

  function triggerSyncPrompt(title, text, btnText, callback) {
    const historyView = shadow.getElementById('vantage-chat-history');
    if(!historyView) return;
    
    // Only prompt if user hasn't started chatting
    if(chatHistory.length > 0) return;

    const div = document.createElement('div');
    div.className = 'vantage-chat-msg vantage-chat-ai';
    div.style.border = "1px solid var(--accent)";
    div.innerHTML = `
      <p><strong>🚨 ${title}</strong></p>
      <p>${text}</p>
      <button class="vantage-btn" style="margin-top: 10px; width: 100%; border-radius: 6px; padding: 6px; background: var(--accent); color: white; border: none; cursor: pointer; font-weight: bold;">
        ${btnText}
      </button>
    `;

    div.querySelector('button').addEventListener('click', () => {
      div.innerHTML = "<p><i>Syncing...</i></p>";
      callback();
    });

    historyView.appendChild(div);
    historyView.scrollTo(0, historyView.scrollHeight);
  }

  // Trigger auto sync logic on boot
  initializeAutoSync();

  // ── Helper mapping dict to html ────────────────────────────────────────────
  function formatMarkdown(obj) {
    if(!obj) return "";
    if(typeof obj === "string") return obj;
    let md = "";
    Object.keys(obj).forEach(k => {
      const v = obj[k];
      if(Array.isArray(v)) {
        md += `<strong>${k}</strong>:\n• ${v.join('\n• ')}\n\n`;
      } else {
        md += `<strong>${k}</strong>: ${v}\n\n`;
      }
    });
    return md.trim();
  }

  // ── Handlers: Chat Pane (Persistent Chat Module) ────────────────────────────
  const chatInput = shadow.getElementById('vantage-chat-input');
  const chatSendBtn = shadow.getElementById('vantage-btn-chat-send');
  const chatLog = shadow.getElementById('vantage-chat-history');

  function renderChat() {
    chatLog.innerHTML = '';
    chatHistory.forEach(m => {
      const d = document.createElement('div');
      d.className = `vantage-chat-msg ${m.role === 'user' ? 'vantage-chat-user' : 'vantage-chat-ai'}`;
      
      const p = document.createElement('p');
      p.innerText = m.content;
      d.appendChild(p);

      chatLog.appendChild(d);
    });
    chatLog.scrollTop = chatLog.scrollHeight;
  }

  async function handleChatSend() {
    const txt = chatInput.value.trim();
    if (!txt) return;

    chatHistory.push({ role: 'user', content: txt });
    renderChat();
    chatInput.value = "";
    
    chatInput.disabled = true;
    chatSendBtn.disabled = true;

    // Detect natural language command to sync room
    const lowerTxt = txt.toLowerCase();
    const isSyncCommand = lowerTxt.includes('sync') || lowerTxt.includes('save') || lowerTxt.includes('collect');
    const isRoomCommand = lowerTxt.includes('room') || lowerTxt.includes('message') || lowerTxt.includes('chat') || lowerTxt.includes('all');
    
    if (isSyncCommand && isRoomCommand && window.location.href.includes('/messages/')) {
      chatHistory.push({ role: 'ai', content: "Initializing auto-scroll and full thread sync. Please wait while I load and capture older messages..." });
      renderChat();
      
      window.dispatchEvent(new Event('Vantage_SYNC_FULL'));
      
      // Listen for completion
      const syncDoneHandler = () => {
        chatHistory.push({ role: 'ai', content: "✅ Full Room Sync Complete! The entire conversation history has been stored in your Vantage Database." });
        renderChat();
        chatInput.disabled = false;
        chatSendBtn.disabled = false;
        setTimeout(() => chatInput.focus(), 100);
        window.removeEventListener('Vantage_SYNC_COMPLETE', syncDoneHandler);
      };
      window.addEventListener('Vantage_SYNC_COMPLETE', syncDoneHandler);
      return; // Skip normal LLM processing for this specific explicit command
    }

    // Attach live screen context implicitly so the Free Chat isn't blind
    let activeData = null;
    try {
      if (window.location.href.includes('/messages/')) {
        let convo = null;
        if (typeof window.extractConversation === 'function') {
           convo = window.extractConversation();
        } else if (typeof extractConversation === 'function') {
           convo = extractConversation();
        }
        if (convo) {
           activeData = { type: "conversation", payload: convo };
        }
      }
    } catch (e) { console.error("Could not append live context", e); }

    // Maintain active memory: send only the last 15 messages of the current chat session
    const activeMemory = chatHistory.slice(-15);

    const res = await sendToBrain("free_chat", { 
      query: txt, 
      context: JSON.stringify(activeMemory),
      data: activeData 
    });
    chatInput.disabled = false;
    chatSendBtn.disabled = false;
    chatInput.focus();

    if (res && res.data) {
      let content = typeof res.data === 'string' ? res.data : formatMarkdown(res.data);
      chatHistory.push({ role: 'ai', content: content });
      renderChat();
    } else {
      chatHistory.push({ role: 'ai', content: "I encountered an error connecting to the Brain." });
      renderChat();
    }
  }

  chatSendBtn.addEventListener('click', handleChatSend);
  chatInput.addEventListener('keydown', (e) => {
    if(e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleChatSend();
    }
  });

})();
