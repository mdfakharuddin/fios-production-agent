const FIOS_API_CHAT = "https://api.themenuagency.com/fios/api/chat";
const FIOS_API_JOB = "https://api.themenuagency.com/fios/api/job/analyze";

let fiosPanel = null;

function createFIOSPanel() {
    if (fiosPanel) return fiosPanel;

    // Inject Google Font
    const fontLink = document.createElement("link");
    fontLink.href = "https://fonts.googleapis.com/css2?family=Outfit:wght@300;400;600;700&display=swap";
    fontLink.rel = "stylesheet";
    document.head.appendChild(fontLink);

    // Inject Styles
    const style = document.createElement("style");
    style.textContent = `
        @keyframes pulseGlow {
            0% { box-shadow: 0 0 0 0 rgba(16, 185, 129, 0.4); }
            70% { box-shadow: 0 0 0 8px rgba(16, 185, 129, 0); }
            100% { box-shadow: 0 0 0 0 rgba(16, 185, 129, 0); }
        }
        @keyframes slideUp {
            from { transform: translateY(20px); opacity: 0; }
            to { transform: translateY(0); opacity: 1; }
        }
        #fios-floating-panel {
            position: fixed;
            right: 24px;
            bottom: 24px;
            width: 360px;
            background: rgba(15, 23, 42, 0.9);
            backdrop-filter: blur(20px);
            -webkit-backdrop-filter: blur(20px);
            border: 1px solid rgba(255, 255, 255, 0.1);
            color: #f8fafc;
            font-family: 'Outfit', sans-serif;
            padding: 20px;
            border-radius: 20px;
            z-index: 9999999;
            box-shadow: 0 25px 50px -12px rgba(0, 0, 0, 0.5);
            animation: slideUp 0.5s cubic-bezier(0.16, 1, 0.3, 1);
            display: flex;
            flex-direction: column;
            gap: 16px;
            max-height: 80vh;
        }
        #fios-panel-header {
            display: flex;
            align-items: center;
            justify-content: space-between;
            border-bottom: 1px solid rgba(255, 255, 255, 0.08);
            padding-bottom: 12px;
        }
        .fios-brand {
            display: flex;
            align-items: center;
            gap: 8px;
            font-weight: 700;
            font-size: 18px;
            letter-spacing: -0.02em;
            background: linear-gradient(135deg, #38bdf8, #818cf8);
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
        }
        .fios-status-indicator {
            display: flex;
            align-items: center;
            gap: 6px;
            font-size: 11px;
            color: #94a3b8;
            font-weight: 600;
            text-transform: uppercase;
        }
        .fios-status-dot {
            width: 8px;
            height: 8px;
            background: #10b981;
            border-radius: 50%;
            animation: pulseGlow 2s infinite;
        }
        /* Chat UI Section */
        #fios-chat-container {
            display: flex;
            flex-direction: column;
            gap: 12px;
            flex-grow: 1;
            overflow: hidden;
        }
        #fios-chat-history {
            flex-grow: 1;
            overflow-y: auto;
            max-height: 250px;
            display: flex;
            flex-direction: column;
            gap: 10px;
            padding-right: 4px;
        }
        #fios-chat-history::-webkit-scrollbar {
            width: 4px;
        }
        #fios-chat-history::-webkit-scrollbar-thumb {
            background: rgba(255,255,255,0.1);
            border-radius: 10px;
        }
        .fios-message {
            padding: 10px 14px;
            border-radius: 12px;
            font-size: 13px;
            line-height: 1.5;
            max-width: 85%;
        }
        .fios-message-user {
            align-self: flex-end;
            background: rgba(59, 130, 246, 0.2);
            color: #e2e8f0;
            border: 1px solid rgba(59, 130, 246, 0.3);
        }
        .fios-message-agent {
            align-self: flex-start;
            background: rgba(255, 255, 255, 0.05);
            color: #f1f5f9;
            border: 1px solid rgba(255, 255, 255, 0.08);
        }
        #fios-chat-input-wrapper {
            display: flex;
            gap: 8px;
            background: rgba(0, 0, 0, 0.2);
            padding: 8px;
            border-radius: 12px;
            border: 1px solid rgba(255, 255, 255, 0.1);
        }
        #fios-chat-input {
            background: transparent;
            border: none;
            color: #fff;
            font-family: inherit;
            font-size: 13px;
            flex-grow: 1;
            outline: none;
        }
        #fios-chat-send {
            background: #3b82f6;
            border: none;
            border-radius: 8px;
            width: 28px;
            height: 28px;
            display: flex;
            align-items: center;
            justify-content: center;
            cursor: pointer;
            color: white;
            transition: opacity 0.2s;
        }
        #fios-chat-send:hover { opacity: 0.8; }
        
        .fios-btn {
            width: 100%;
            padding: 10px;
            border-radius: 10px;
            font-family: inherit;
            font-weight: 600;
            font-size: 13px;
            cursor: pointer;
            border: none;
            transition: all 0.2s;
            display: flex;
            justify-content: center;
            align-items: center;
            gap: 8px;
        }
        #fios-generate-proposal {
            background: linear-gradient(135deg, #4f46e5 0%, #3b82f6 100%);
            color: white;
        }
        #fios-generate-reply {
            background: rgba(255, 255, 255, 0.05);
            color: #cbd5e1;
            border: 1px solid rgba(255, 255, 255, 0.1);
        }
        .fios-btn:hover { transform: translateY(-1px); }
        .fios-btn:active { transform: translateY(0); }
        
        #fios-status-display {
            font-size: 12px;
            color: #94a3b8;
            text-align: center;
            background: rgba(0,0,0,0.2);
            padding: 8px;
            border-radius: 8px;
        }
    `;
    document.head.appendChild(style);

    fiosPanel = document.createElement("div");
    fiosPanel.id = "fios-floating-panel";

    fiosPanel.innerHTML = `
        <div id="fios-panel-header">
            <div class="fios-brand">FIOS Intelligence</div>
            <div class="fios-status-indicator">
                <div class="fios-status-dot" id="fios-status-dot"></div>
                <span id="fios-status-text">Online</span>
            </div>
        </div>

        <div id="fios-status-display">Waiting for project context...</div>

        <div id="fios-chat-container">
            <div id="fios-chat-history">
                <div class="fios-message fios-message-agent">System ready. How can I help you dominate this job market?</div>
            </div>
            <div id="fios-chat-input-wrapper">
                <input type="text" id="fios-chat-input" placeholder="Ask FIOS anything...">
                <button id="fios-chat-send">
                   <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="3"><path d="M22 2L11 13M22 2l-7 20-4-9-9-4 20-7z"></path></svg>
                </button>
            </div>
        </div>

        <div style="display: flex; gap: 8px;">
            <button id="fios-generate-proposal" class="fios-btn">Generate Proposal</button>
            <button id="fios-generate-reply" class="fios-btn">Smart Reply</button>
        </div>
    `;

    document.body.appendChild(fiosPanel);
    attachPanelEvents();
    return fiosPanel;
}

function attachPanelEvents() {
    const sendBtn = document.getElementById("fios-chat-send");
    const input = document.getElementById("fios-chat-input");

    const sendMessage = async () => {
        const text = input.value.trim();
        if (!text) return;
        
        input.value = "";
        addChatMessage(text, "user");
        
        updateStatus("Thinking...", "processing");
        const response = await callFIOSChat(text);
        addChatMessage(response, "agent");
        updateStatus("Online", "success");
    };

    sendBtn.onclick = sendMessage;
    input.onkeypress = (e) => { if (e.key === "Enter") sendMessage(); };

    document.getElementById("fios-generate-reply").onclick = generateReply;
    document.getElementById("fios-generate-proposal").onclick = generateAndInjectProposal;
}

function addChatMessage(text, sender) {
    const history = document.getElementById("fios-chat-history");
    const msg = document.createElement("div");
    msg.className = `fios-message fios-message-${sender}`;
    msg.innerText = text;
    history.appendChild(msg);
    history.scrollTop = history.scrollHeight;
}

function updateStatus(text, state = "info") {
    const statusText = document.getElementById("fios-status-text");
    const display = document.getElementById("fios-status-display");
    const dot = document.getElementById("fios-status-dot");
    
    if (statusText) statusText.innerText = state.toUpperCase();
    if (display && state !== "success" ) display.innerText = text;

    if (dot) {
        if (state === "processing") dot.style.background = "#f59e0b";
        else if (state === "error") dot.style.background = "#ef4444";
        else dot.style.background = "#10b981";
    }
}

async function generateReply() {
    updateStatus("Analyzing thread...", "processing");
    let messages = document.querySelectorAll('[data-test="message-text"], .msg-body, .message-content, [data-v-message-text], .text-body-sm.break-words');
    if (!messages.length) {
        addChatMessage("No conversation messages detected.", "agent");
        updateStatus("Online", "error");
        return;
    }
    const lastMessage = messages[messages.length - 1].innerText;
    const response = await callFIOSChat(`Generate a winning reply to: ${lastMessage}`);
    injectReply(response);
    addChatMessage("Generated and injected smart reply.", "agent");
    updateStatus("Online", "success");
}

async function generateProposal() {
    updateStatus("Analyzing job...", "processing");
    const title = document.querySelector('[data-test="job-title"]')?.innerText || document.querySelector('h1')?.innerText || "";
    const description = document.querySelector('[data-test="job-description"]')?.innerText || document.querySelector('.job-description')?.innerText || "";
    
    try {
        const res = await fetch(FIOS_API_JOB, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ user_id: "upwork_user", job_data: { title, description } })
        });
        const result = await res.json();
        updateStatus(`Win Probability: ${result.win_probability}%`, "success");
        if (result.win_probability > 75) generateAndInjectProposal();
    } catch (e) {
        updateStatus("Analysis Error", "error");
    }
}

async function generateAndInjectProposal() {
    updateStatus("Crafting proposal...", "processing");
    const title = document.querySelector('[data-test="job-title"]')?.innerText || document.querySelector('h1')?.innerText || "";
    const description = document.querySelector('[data-test="job-description"]')?.innerText || document.querySelector('.job-description')?.innerText || "";
    const response = await callFIOSChat(`Write a high-conversion proposal for: ${title}. Description: ${description}`);
    injectProposalIntoUpwork(response);
    addChatMessage("Proposal injected. Good luck!", "agent");
    updateStatus("Online", "success");
}

async function callFIOSChat(message) {
    try {
        const res = await fetch(FIOS_API_CHAT, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ user_id: "upwork_user", message: message })
        });
        const result = await res.json();
        return result.response || "No response details.";
    } catch (e) {
        return "Critical Error: Could not reach FIOS Brain. Check Coolify Logs.";
    }
}

function injectReply(text) {
    const box = document.querySelector('[data-test="message-compose-input"]');
    if (box) box.innerText = text;
}

function injectProposalIntoUpwork(proposalText) {
    const textarea = document.querySelector('textarea, [contenteditable="true"]');
    if (!textarea) return;
    textarea.focus();
    if (textarea.tagName === "TEXTAREA") textarea.value = proposalText;
    else textarea.innerText = proposalText;
    textarea.dispatchEvent(new Event("input", { bubbles: true }));
}

function autoInitializeFIOS() {
    createFIOSPanel();
    if (window.location.href.includes("/jobs/") || window.location.href.includes("/proposals/")) {
        generateProposal();
    }
}

setTimeout(autoInitializeFIOS, 3000);
