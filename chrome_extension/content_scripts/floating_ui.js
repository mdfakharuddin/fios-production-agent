(function() {
  'use strict';

  if (!chrome.runtime || !chrome.runtime.id) return;
  if (window.upieControllerLoaded) return;
  window.upieControllerLoaded = true;

  const API_BASE = "https://api.themenuagency.com/fios";
  const ENDPOINTS = {
    EXECUTE: `${API_BASE}/brain/execute`,
    INGEST: `${API_BASE}/api/v1/ingest`,
    INGEST_CONVERSATION: `${API_BASE}/api/v1/ingest/conversation`,
    HEALTH: `${API_BASE}/health`
  };

  function detectPageType() {
    if (typeof window.detectPageType === 'function') return window.detectPageType();
    const href = String(window.location.href || '').toLowerCase();
    if (href.includes('/messages')) return 'conversation';
    if (href.includes('/jobs/') || href.includes('/freelance-jobs/') || href.includes('job-details')) return 'job';
    if (href.includes('/proposals')) return 'proposal';
    if (href.includes('/search/jobs')) return 'job_search';
    return 'generic';
  }

  function extractJobContext() {
    if (typeof window.extractJobContext === 'function') return window.extractJobContext();
    if (typeof window.extractJobDetails === 'function') return window.extractJobDetails();
    return { title: document.title || '', raw_text: document.body?.innerText || '' };
  }

  function extractClientContext() {
    if (typeof window.extractClientContext === 'function') return window.extractClientContext();
    if (typeof window.extractClientSidebar === 'function') return window.extractClientSidebar();
    return null;
  }

  function extractConversationContext() {
    if (typeof window.extractConversationContext === 'function') return window.extractConversationContext();
    if (typeof window.extractConversation === 'function') return window.extractConversation();
    return { messages: [] };
  }

  function extractFullContext() {
    return {
      url: window.location.href,
      html: document.body?.outerHTML || document.documentElement?.outerHTML || '',
      text: document.body?.innerText || '',
      job: extractJobContext(),
      client: extractClientContext(),
      conversation: extractConversationContext()
    };
  }

  function extractRoomId() {
    if (typeof window.extractRoomId === 'function') return window.extractRoomId();
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
    return roomId || 'ext_global_session';
  }

  async function executeBrainCommand(query, eventType = 'free_chat') {
    const roomId = extractRoomId();
    const payload = {
      event_type: eventType,
      query: query,
      source: 'upie_extension',
      conversation_id: roomId,
      room_id: roomId,
      data: {
        room_id: roomId,
        url: window.location.href,
        page_type: detectPageType(),
        full_html: document.body?.outerHTML || document.documentElement?.outerHTML || '',
        page_text: document.body?.innerText || '',
        job: extractJobContext(),
        client: extractClientContext(),
        conversation: typeof window.extractConversationMessages === 'function' ? window.extractConversationMessages() : extractConversationContext(),
        timestamp: Date.now()
      }
    };

    const response = await fetch(ENDPOINTS.EXECUTE, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload)
    });

    if (!response.ok) {
      const text = await response.text();
      throw new Error(`Brain execute failed (${response.status}): ${text.slice(0, 240)}`);
    }

    const result = await response.json();
    return result.output || result.response || result.data || (typeof result === 'string' ? result : JSON.stringify(result));
  }

  function escapeHtml(value) {
    return String(value || '')
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;')
      .replace(/'/g, '&#39;');
  }

  function toHtmlLines(value) {
    return escapeHtml(value).replace(/\n/g, '<br>');
  }

  const container = document.createElement('div');
  container.id = 'upie-controller-root';
  container.style.cssText = 'position:fixed; top:0; left:0; width:100vw; height:100vh; z-index:2147483647; pointer-events:none;';
  document.body.appendChild(container);

  const shadow = container.attachShadow({ mode: 'open' });
  const logoUrl = chrome.runtime.getURL('icons/icon_48.png');

  const styleLink = document.createElement('link');
  styleLink.rel = 'stylesheet';
  styleLink.href = chrome.runtime.getURL('content_scripts/floating_ui.css');
  shadow.appendChild(styleLink);

  const panelHTML = `
    <div id="upie-floating-controller" class="panel" style="--logo-url: url('${logoUrl}');">
      <div class="upie-resize-handle upie-rh-n" data-dir="n"></div>
      <div class="upie-resize-handle upie-rh-s" data-dir="s"></div>
      <div class="upie-resize-handle upie-rh-e" data-dir="e"></div>
      <div class="upie-resize-handle upie-rh-w" data-dir="w"></div>
      <div class="upie-resize-handle upie-rh-ne" data-dir="ne"></div>
      <div class="upie-resize-handle upie-rh-nw" data-dir="nw"></div>
      <div class="upie-resize-handle upie-rh-se" data-dir="se"></div>
      <div class="upie-resize-handle upie-rh-sw" data-dir="sw"></div>

      <div id="upie-skeleton" class="upie-hidden">
        <div class="upie-spinner"></div>
        <div class="upie-skel-text" id="upie-skel-msg">Working with memory + archive...</div>
      </div>

      <div id="upie-header">
        <div id="upie-brand-container">
          <img src="${logoUrl}" alt="Upie" class="upie-logo-img">
          <div id="upie-brand-text">Upie Intelligence</div>
        </div>
        <div style="display:flex; align-items:center; gap:8px;">
          <span class="upie-status-dot"></span>
          <button id="upie-btn-hide" class="upie-pill-btn" style="padding:4px 8px;">Hide</button>
        </div>
      </div>

      <div id="upie-tab-nav">
        <button class="upie-tab-btn active" data-view="view-chat">Intelligence</button>
        <button class="upie-tab-btn" data-view="view-history">History</button>
        <button class="upie-tab-btn" data-view="view-replies">Replies</button>
        <button class="upie-tab-btn" data-view="view-proposal">Proposal</button>
        <button class="upie-tab-btn" data-view="view-intelligence">Dashboard</button>
      </div>

      <div id="view-chat" class="upie-view-pane active">
        <div id="upie-chat-history" class="chat-container custom-scroll">
          <div class="upie-msg-bubble upie-msg-ai">
            <span class="upie-msg-label">UpieAgent</span>
            <div class="upie-msg-content chat-message">Connected to production Brain Orchestrator. Ask for a reply, proposal, or strategy.</div>
          </div>
        </div>
        <div id="upie-chat-footer">
          <div id="upie-quick-actions">
            <button class="upie-pill-btn upie-qa" id="qa-analyze-job">Analyze Job</button>
            <button class="upie-pill-btn upie-qa" id="qa-suggest-reply">Suggest Reply</button>
            <button class="upie-pill-btn upie-qa" id="qa-write-proposal">Write Proposal</button>
          </div>
          <div id="upie-input-wrapper">
            <textarea id="upie-input-field" placeholder="Ask Upie anything..."></textarea>
            <button id="upie-send-btn" title="Send">
              <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><path d="M22 2L11 13M22 2l-7 20-4-9-9-4 20-7z"/></svg>
            </button>
          </div>
          <div class="assistant-status">Upie is using your memory and archive to generate this response.</div>
        </div>
      </div>

      <div id="view-history" class="upie-view-pane">
        <div id="upie-history-list" class="history-container custom-scroll p-20 secondary-text">Loading archive history...</div>
      </div>

      <div id="view-replies" class="upie-view-pane">
        <div class="dashboard-container custom-scroll p-20">
          <div class="upie-card">
            <div class="upie-card-title">Last Client Message</div>
            <div class="secondary-text" id="upie-reply-preview">No message detected.</div>
          </div>
          <div class="upie-card-title">Suggested Replies</div>
          <div id="upie-replies-container">
            <button class="upie-pill-btn" style="width:100%; border-radius:8px;" id="btn-gen-replies">Generate Replies</button>
          </div>
        </div>
      </div>

      <div id="view-proposal" class="upie-view-pane">
        <div class="proposals-container custom-scroll p-20">
          <div class="upie-card" style="display:flex; justify-content:space-between; align-items:center;">
            <div>
              <div class="upie-card-title">Win Probability</div>
              <div style="font-size:20px; font-weight:700;" id="upie-win-score">--</div>
            </div>
            <div class="upie-risk-tag risk-low" id="upie-risk-label">Fit: Evaluating</div>
          </div>
          <div class="upie-card" style="display:flex; flex-direction:column; min-height:240px;">
            <div class="upie-card-title">AI Draft</div>
            <textarea id="upie-proposal-editor" placeholder="Strategic proposal will appear here..."></textarea>
          </div>
          <div style="margin-top:12px; display:grid; grid-template-columns:1fr 1fr; gap:8px;">
            <button class="upie-pill-btn upie-accent" id="upie-btn-insert-prop">Insert into Upwork</button>
            <button class="upie-pill-btn" id="btn-regen-proposal">Regenerate</button>
          </div>
        </div>
      </div>

      <div id="view-intelligence" class="upie-view-pane">
        <div class="dashboard-container custom-scroll p-20">
          <div class="upie-card">
            <div class="upie-card-title">Client Insights</div>
            <div class="upie-stat-row"><span>Hire Rate:</span><span class="upie-stat-val" id="intel-hire-rate">--</span></div>
            <div class="upie-stat-row"><span>Total Spent:</span><span class="upie-stat-val" id="intel-total-spent">--</span></div>
            <div class="upie-stat-row"><span>Risk Score:</span><span class="upie-risk-tag risk-low" id="intel-risk">Stable</span></div>
          </div>
          <div class="upie-card">
            <div class="upie-card-title">Conversation Intelligence</div>
            <div class="secondary-text" id="intel-intent-text">Run analysis to load conversation intelligence from memory.</div>
          </div>
          <button class="upie-pill-btn upie-accent" style="width:100%;" id="btn-analyze-convo">Analyze Conversation</button>
        </div>
      </div>

    </div>
  `;

  const panelWrap = document.createElement('div');
  panelWrap.innerHTML = panelHTML;
  const panel = panelWrap.firstElementChild;
  shadow.appendChild(panel);

  const elInput = shadow.getElementById('upie-input-field');
  const btnSend = shadow.getElementById('upie-send-btn');
  const chatLog = shadow.getElementById('upie-chat-history');
  const skeleton = shadow.getElementById('upie-skeleton');
  const skelMsg = shadow.getElementById('upie-skel-msg');
  const elProposal = shadow.getElementById('upie-proposal-editor');
  const elWinScore = shadow.getElementById('upie-win-score');
  const elRepliesWrap = shadow.getElementById('upie-replies-container');
  const elReplyPreview = shadow.getElementById('upie-reply-preview');

  let isLoading = false;

  function addMessageToUI(role, content, agent = 'UpieAgent') {
    const text = (content == null) ? '' : String(content);
    const bubble = document.createElement('div');
    bubble.className = `upie-msg-bubble ${role === 'user' ? 'upie-msg-user' : 'upie-msg-ai'}`;
    const labelHtml = role === 'user' ? '' : `<span class="upie-msg-label">${escapeHtml(agent)}</span>`;
    bubble.innerHTML = `${labelHtml}<div class="upie-msg-content chat-message">${toHtmlLines(text)}</div>`;
    chatLog.appendChild(bubble);
    chatLog.scrollTop = chatLog.scrollHeight;
  }

  function setUIState(loading, msg = 'Processing...') {
    isLoading = loading;
    skelMsg.innerText = msg;
    panel.classList.toggle('is-loading', loading);
    skeleton.classList.toggle('upie-hidden', !loading);
  }

  function switchView(viewId) {
    shadow.querySelectorAll('.upie-tab-btn').forEach((btn) => {
      btn.classList.toggle('active', btn.dataset.view === viewId);
    });
    shadow.querySelectorAll('.upie-view-pane').forEach((paneEl) => {
      paneEl.classList.toggle('active', paneEl.id === viewId);
    });
    if (viewId === 'view-history') {
      loadHistoryFromServer();
    }
  }

  async function sendChatMessage(message) {
    if (!message || isLoading) return;

    addMessageToUI('user', message, 'You');
    setUIState(true, 'Generating response from memory + archive...');

    try {
      const output = await executeBrainCommand(message);
      addMessageToUI('assistant', output);
    } catch (error) {
      addMessageToUI('assistant', `Error: ${error.message || 'Failed to reach Brain Orchestrator.'}`);
    } finally {
      setUIState(false);
    }
  }

  function extractLatestClientMessage() {
    const convo = extractConversationContext();
    const messages = Array.isArray(convo?.messages) ? convo.messages : [];
    const latest = messages
      .filter((m) => (m.role || '').toLowerCase() === 'client' || (m.sender || '').toLowerCase().includes('client'))
      .pop();
    return latest?.text || 'No client message found in this thread yet.';
  }

  function parseReplyOptions(text) {
    const cleaned = String(text || '').trim();
    if (!cleaned) return [];

    const numbered = cleaned
      .split(/\n\s*(?:\d+\.|-|•)\s*/g)
      .map((line) => line.trim())
      .filter(Boolean);

    if (numbered.length >= 2) return numbered.slice(0, 5);

    return cleaned
      .split(/\n{2,}|\n/g)
      .map((line) => line.trim())
      .filter(Boolean)
      .slice(0, 5);
  }

  async function generateQuickReplies() {
    setUIState(true, 'Generating contextual replies...');
    try {
      const lastClientMessage = extractLatestClientMessage();
      elReplyPreview.innerText = lastClientMessage;

      const output = await executeBrainCommand(
        `Generate 3 context-aware reply options for this client message. Return plain text list only.\n\nClient message:\n${lastClientMessage}`
      );

      const replies = parseReplyOptions(output);
      if (replies.length === 0) {
        elRepliesWrap.innerHTML = `<div class="secondary-text">${toHtmlLines(output)}</div>`;
        return;
      }

      elRepliesWrap.innerHTML = replies.map((reply) => `
        <button class="upie-pill-btn upie-reply-opt" style="width:100%; margin-bottom:8px; padding:12px; border-radius:8px; text-align:left;">
          ${escapeHtml(reply)}
        </button>
      `).join('');

      shadow.querySelectorAll('.upie-reply-opt').forEach((btn) => {
        btn.addEventListener('click', () => injectToUpwork(btn.innerText.trim()));
      });
    } catch (error) {
      elRepliesWrap.innerHTML = `<div class="secondary-text">Failed to generate replies: ${escapeHtml(error.message || '')}</div>`;
    } finally {
      setUIState(false);
    }
  }

  async function generateProposal() {
    setUIState(true, 'Drafting proposal with archive + memory context...');
    try {
      const output = await executeBrainCommand('Generate a high-conversion Upwork proposal for the current job and client context.', 'generate_proposal');
      elProposal.value = String(output || '');

      const scoreMatch = String(output || '').match(/(\d{1,3})\s*%/);
      elWinScore.innerText = scoreMatch ? `${scoreMatch[1]}%` : 'Calculated';
    } catch (error) {
      elProposal.value = `Failed to generate proposal: ${error.message || 'Unknown error'}`;
      elWinScore.innerText = '--';
    } finally {
      setUIState(false);
    }
  }

  async function analyzeConversation() {
    setUIState(true, 'Analyzing conversation intelligence...');
    try {
      const output = await executeBrainCommand('Analyze the current client conversation and provide intent, risk, and next best action.', 'analyze_conversation');
      shadow.getElementById('intel-intent-text').innerText = String(output || 'No analysis returned.');

      const sidebar = extractClientContext() || {};
      shadow.getElementById('intel-hire-rate').innerText = sidebar.hire_rate || '--';
      shadow.getElementById('intel-total-spent').innerText = sidebar.total_spent || '--';

      const riskLabel = shadow.getElementById('intel-risk');
      const lowered = String(output || '').toLowerCase();
      riskLabel.classList.remove('risk-low', 'risk-mid', 'risk-high');
      if (lowered.includes('high risk')) {
        riskLabel.classList.add('risk-high');
        riskLabel.innerText = 'High';
      } else if (lowered.includes('medium risk') || lowered.includes('moderate risk')) {
        riskLabel.classList.add('risk-mid');
        riskLabel.innerText = 'Moderate';
      } else {
        riskLabel.classList.add('risk-low');
        riskLabel.innerText = 'Low';
      }
    } catch (error) {
      shadow.getElementById('intel-intent-text').innerText = `Analysis failed: ${error.message || 'Unknown error'}`;
    } finally {
      setUIState(false);
    }
  }

  async function analyzeJob() {
    setUIState(true, 'Analyzing job fit and strategy...');
    try {
      const output = await executeBrainCommand('Analyze this job opportunity and provide a concise win strategy.', 'job_analysis');
      addMessageToUI('assistant', output, 'OpportunityAgent');
      switchView('view-chat');
    } catch (error) {
      addMessageToUI('assistant', `Job analysis failed: ${error.message || 'Unknown error'}`, 'OpportunityAgent');
    } finally {
      setUIState(false);
    }
  }

  async function loadHistoryFromServer() {
    const listEl = shadow.getElementById('upie-history-list');
    listEl.innerText = 'Fetching conversation history from archive memory...';

    try {
      const output = await executeBrainCommand('Summarize my recent freelancer conversation history and key memory insights in concise bullets.');
      listEl.innerHTML = `<div>${toHtmlLines(output)}</div>`;
    } catch (error) {
      listEl.innerText = `Error loading history: ${error.message || 'Unknown error'}`;
    }
  }

  function injectToUpwork(text) {
    const box = document.querySelector('[data-test="message-compose-input"], textarea.message-compose-input, textarea, .up-textarea');
    if (!box) return;

    box.focus();
    if (box.tagName === 'TEXTAREA' || box.tagName === 'INPUT') {
      box.value = text;
    } else {
      box.innerText = text;
    }
    box.dispatchEvent(new Event('input', { bubbles: true }));
  }

  btnSend.addEventListener('click', () => {
    sendChatMessage(elInput.value.trim());
    elInput.value = '';
  });

  elInput.addEventListener('keydown', (event) => {
    if (event.key === 'Enter' && !event.shiftKey) {
      event.preventDefault();
      btnSend.click();
    }
  });

  shadow.querySelectorAll('.upie-tab-btn').forEach((btn) => {
    btn.addEventListener('click', () => switchView(btn.dataset.view));
  });

  shadow.getElementById('qa-analyze-job').addEventListener('click', analyzeJob);
  shadow.getElementById('qa-suggest-reply').addEventListener('click', () => {
    switchView('view-replies');
    generateQuickReplies();
  });
  shadow.getElementById('qa-write-proposal').addEventListener('click', () => {
    switchView('view-proposal');
    generateProposal();
  });

  shadow.getElementById('btn-gen-replies').addEventListener('click', generateQuickReplies);
  shadow.getElementById('btn-regen-proposal').addEventListener('click', generateProposal);
  shadow.getElementById('btn-analyze-convo').addEventListener('click', analyzeConversation);

  shadow.getElementById('upie-btn-insert-prop').addEventListener('click', () => injectToUpwork(elProposal.value));
  shadow.getElementById('upie-btn-hide').addEventListener('click', () => {
    panel.style.display = 'none';
  });

  let activeOp = null;
  let startX = 0;
  let startY = 0;
  let startT = 0;
  let startL = 0;
  let startW = 0;
  let startH = 0;
  let resizeDir = '';

  shadow.getElementById('upie-header').addEventListener('mousedown', (event) => {
    if (event.target.closest('button')) return;
    activeOp = 'drag';
    startX = event.clientX;
    startY = event.clientY;
    startT = panel.offsetTop;
    startL = panel.offsetLeft;
    panel.style.right = 'auto';
    panel.style.bottom = 'auto';
    event.preventDefault();
  });

  shadow.querySelectorAll('.upie-resize-handle').forEach((handle) => {
    handle.addEventListener('mousedown', (event) => {
      activeOp = 'resize';
      resizeDir = handle.dataset.dir;
      startX = event.clientX;
      startY = event.clientY;
      startW = panel.offsetWidth;
      startH = panel.offsetHeight;
      startT = panel.offsetTop;
      startL = panel.offsetLeft;
      event.preventDefault();
      event.stopPropagation();
    });
  });

  window.addEventListener('mousemove', (event) => {
    if (!activeOp) return;

    if (activeOp === 'drag') {
      panel.style.top = `${startT + (event.clientY - startY)}px`;
      panel.style.left = `${startL + (event.clientX - startX)}px`;
      return;
    }

    const dx = event.clientX - startX;
    const dy = event.clientY - startY;

    if (resizeDir.includes('e')) panel.style.width = `${Math.max(320, startW + dx)}px`;
    if (resizeDir.includes('s')) panel.style.height = `${Math.max(420, startH + dy)}px`;

    if (resizeDir.includes('w')) {
      const newWidth = Math.max(320, startW - dx);
      if (newWidth > 320) {
        panel.style.width = `${newWidth}px`;
        panel.style.left = `${startL + dx}px`;
      }
    }

    if (resizeDir.includes('n')) {
      const newHeight = Math.max(420, startH - dy);
      if (newHeight > 420) {
        panel.style.height = `${newHeight}px`;
        panel.style.top = `${startT + dy}px`;
      }
    }
  });

  window.addEventListener('mouseup', () => {
    activeOp = null;
  });

  chrome.storage.local.get(['upie_ui_state'], (res) => {
    const state = res.upie_ui_state;
    if (state) {
      if (state.top) panel.style.top = state.top;
      if (state.left) panel.style.left = state.left;
      if (state.width) panel.style.width = state.width;
      if (state.height) panel.style.height = state.height;
    } else {
      panel.style.top = '100px';
      panel.style.right = '40px';
    }
  });

  window.addEventListener('beforeunload', () => {
    chrome.storage.local.set({
      upie_ui_state: {
        top: panel.style.top,
        left: panel.style.left,
        width: panel.style.width,
        height: panel.style.height
      }
    });
  });
})();
