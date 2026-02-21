document.addEventListener('DOMContentLoaded', () => {

  // ── DOM References ─────────────────────────────────────────────────────────
  const $ = (id) => document.getElementById(id);

  const connDot      = $('conn-dot');
  const stateEmpty   = $('state-empty');
  const aiOutput     = $('ai-output');
  const aiLoader     = $('ai-loader');
  const aiResults    = $('ai-results');

  // Gear panel
  const gearPanel    = $('gear-panel');
  const gearOverlay  = $('gear-overlay');
  const openGear     = $('open-gear');
  const closeGear    = $('close-gear');

  // Gear controls
  const togProp      = $('tog-prop');
  const togConvo     = $('tog-convo');
  const togLowlat    = $('tog-lowlat');
  const togNostrat   = $('tog-nostrat');
  const gProposals   = $('g-proposals');
  const gConvos      = $('g-convos');
  const gLastSync    = $('g-last-sync');

  // Track in-flight to prevent double clicks
  let aiInFlight = false;

  // ── Gear Panel Toggle ──────────────────────────────────────────────────────
  function toggleGear(open) {
    if (open) {
      gearPanel.classList.add('open');
      gearOverlay.classList.add('open');
    } else {
      gearPanel.classList.remove('open');
      gearOverlay.classList.remove('open');
    }
  }
  openGear.addEventListener('click', () => toggleGear(true));
  closeGear.addEventListener('click', () => toggleGear(false));
  gearOverlay.addEventListener('click', () => toggleGear(false));

  // ── Settings Persistence ───────────────────────────────────────────────────
  const SETTINGS_KEYS = {
    vantage_prop_mode: togProp,
    vantage_convo_mode: togConvo,
    vantage_lowlat: togLowlat,
    vantage_nostrat: togNostrat,
  };

  // Load saved toggles
  chrome.storage.local.get(
    [...Object.keys(SETTINGS_KEYS), 'vantage_tone', 'vantage_length', 'vantage_last_sync'],
    (res) => {
      Object.entries(SETTINGS_KEYS).forEach(([key, el]) => {
        if (el) el.checked = res[key] === true;
      });
      // Radio groups
      if (res.vantage_tone) {
        const r = document.querySelector(`input[name="tone"][value="${res.vantage_tone}"]`);
        if (r) r.checked = true;
      }
      if (res.vantage_length) {
        const r = document.querySelector(`input[name="length"][value="${res.vantage_length}"]`);
        if (r) r.checked = true;
      }
      if (res.vantage_last_sync) {
        gLastSync.textContent = `Last synced: ${new Date(res.vantage_last_sync).toLocaleString()}`;
      }
    }
  );

  // Save toggles on change
  Object.entries(SETTINGS_KEYS).forEach(([key, el]) => {
    if (el) el.addEventListener('change', () => chrome.storage.local.set({ [key]: el.checked }));
  });

  // Save radios
  document.querySelectorAll('input[name="tone"]').forEach(r => {
    r.addEventListener('change', () => chrome.storage.local.set({ vantage_tone: r.value }));
  });
  document.querySelectorAll('input[name="length"]').forEach(r => {
    r.addEventListener('change', () => chrome.storage.local.set({ vantage_length: r.value }));
  });

  // ── Backend Health & Stats ─────────────────────────────────────────────────
  async function loadStats() {
    try {
      await fetch("http://127.0.0.1:8000/health").then(r => r.json());
      connDot.classList.remove('offline');
      const data = await fetch("http://127.0.0.1:8000/api/v1/sync/stats").then(r => r.json());
      gProposals.textContent = data.proposals ?? 0;
      gConvos.textContent = data.conversations ?? 0;
    } catch {
      connDot.classList.add('offline');
      gProposals.textContent = '—';
      gConvos.textContent = '—';
    }
  }
  loadStats();

  // ── Context Detection ──────────────────────────────────────────────────────
  chrome.tabs.query({ active: true, currentWindow: true }, (tabs) => {
    stateEmpty.classList.remove('hidden');
  });

  // ── AI Helpers ─────────────────────────────────────────────────────────────
  function setLoading(on) {
    aiOutput.classList.remove('hidden');
    if (on) {
      aiLoader.classList.remove('hidden');
      aiResults.innerHTML = '';
      aiResults.classList.add('hidden');
      aiInFlight = true;
      document.querySelectorAll('.main .btn').forEach(b => b.disabled = true);
    } else {
      aiLoader.classList.add('hidden');
      aiResults.classList.remove('hidden');
      aiInFlight = false;
      document.querySelectorAll('.main .btn').forEach(b => b.disabled = false);
    }
  }

  function block(label, html) {
    return `<div class="ai-block"><div class="ai-label">${label}</div><div class="ai-value">${html}</div></div>`;
  }

  function copyable(text, label) {
    const uid = 'c' + Math.random().toString(36).substr(2, 6);
    return `
      <div class="ai-block">
        <div style="display:flex;justify-content:space-between;align-items:center;">
          <div class="ai-label" style="margin:0">${label}</div>
          <button class="btn btn-copy" data-copy="${uid}">Copy</button>
        </div>
        <div class="ai-value" id="${uid}">${text}</div>
      </div>`;
  }

  function bindCopy() {
    aiResults.querySelectorAll('[data-copy]').forEach(btn => {
      btn.addEventListener('click', () => {
        const src = $(btn.dataset.copy);
        if (!src) return;
        navigator.clipboard.writeText(src.innerText).then(() => {
          btn.textContent = '✓ Copied';
          btn.style.background = '#dcfce7';
          btn.style.color = '#166534';
          setTimeout(() => { btn.textContent = 'Copy'; btn.style = ''; }, 1800);
        });
      });
    });
  }

  function errorBlock(msg) {
    return block('Error', `<span style="color:var(--danger)">${msg}</span>`);
  }

  function renderBrainMeta(res) {
    let html = '';
    // Confidence badge
    const conf = (res.confidence_level || '').toUpperCase();
    if (conf) {
      const cColor = conf === 'HIGH' ? 'var(--success)' : conf === 'LOW' ? 'var(--danger)' : 'var(--warning)';
      html += `<div style="margin-bottom:10px;"><span class="badge" style="background:${cColor}20;color:${cColor};padding:3px 10px;">Confidence: ${conf}</span></div>`;
    }
    // Reasoning summary bullets
    const reasoning = res.reasoning_summary || [];
    if (reasoning.length) {
      html += `<div class="ai-block"><div class="ai-label">AI Reasoning</div><div class="ai-value" style="font-size:12px;color:var(--muted);"><ul>${reasoning.map(r => `<li>${r}</li>`).join('')}</ul></div></div>`;
    }
    return html;
  }

  async function waitForPageLoad(tabId, maxWait = 15000) {
    const start = Date.now();
    while (Date.now() - start < maxWait) {
      const tab = await chrome.tabs.get(tabId);
      if (tab.status === 'complete') return true;
      await new Promise(r => setTimeout(r, 500));
    }
    return false; // timed out
  }

  async function getPageContent(tabId) {
    // Wait for the page to fully load (Cloudflare, SPA rendering, etc.)
    await waitForPageLoad(tabId);

    // Inject scraper on-demand (only if not already injected)
    try {
      await chrome.scripting.executeScript({
        target: { tabId },
        files: ['content_scripts/scraper.js']
      });
    } catch (e) {
      // Already injected or permissions issue — continue
    }

    // Wait for the script to initialize
    await new Promise(r => setTimeout(r, 500));

    return new Promise((resolve) => {
      chrome.tabs.sendMessage(tabId, { action: "EXTRACT_PAGE_CONTENT" }, (res) => {
        if (chrome.runtime.lastError) {
          console.warn("Vantage: Content script not reachable:", chrome.runtime.lastError.message);
          resolve({});
        } else {
          resolve(res || {});
        }
      });
    });
  }

  function getSettings() {
    return new Promise((resolve) => {
      chrome.storage.local.get(['vantage_tone', 'vantage_length'], (r) => {
        resolve({
          strict_voice_mode: r.vantage_tone === 'strict',
          tone: r.vantage_tone || 'balanced',
          length: r.vantage_length || 'medium'
        });
      });
    });
  }

  function recBadge(rec) {
    const r = (rec || '').toUpperCase();
    if (r === 'APPLY') return '<span class="badge badge-apply">APPLY</span>';
    if (r === 'SKIP') return '<span class="badge badge-skip">SKIP</span>';
    return '<span class="badge badge-caution">CAUTION</span>';
  }

  // Removed non-chat copilot logic

});
