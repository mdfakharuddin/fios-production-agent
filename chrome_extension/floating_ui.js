const FIOS_API_CHAT = "https://c4800kswgwggs0sg8o8kkogs.103.127.1.91.sslip.io/api/chat";
const FIOS_API_JOB = "https://c4800kswgwggs0sg8o8kkogs.103.127.1.91.sslip.io/api/job/analyze";

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
            width: 340px;
            background: rgba(15, 23, 42, 0.85);
            backdrop-filter: blur(20px);
            -webkit-backdrop-filter: blur(20px);
            border: 1px solid rgba(255, 255, 255, 0.1);
            color: #f8fafc;
            font-family: 'Outfit', sans-serif;
            padding: 20px;
            border-radius: 16px;
            z-index: 9999999;
            box-shadow: 0 20px 40px rgba(0, 0, 0, 0.4), inset 0 1px 0 rgba(255,255,255,0.1);
            animation: slideUp 0.5s cubic-bezier(0.16, 1, 0.3, 1);
            display: flex;
            flex-direction: column;
            gap: 16px;
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
            font-size: 17px;
            letter-spacing: 0.5px;
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
            letter-spacing: 0.5px;
        }
        .fios-status-dot {
            width: 8px;
            height: 8px;
            background: #10b981;
            border-radius: 50%;
            animation: pulseGlow 2s infinite;
            transition: background 0.3s ease;
        }
        .fios-btn {
            width: 100%;
            padding: 12px;
            border-radius: 10px;
            font-family: 'Outfit', sans-serif;
            font-weight: 600;
            font-size: 14px;
            cursor: pointer;
            border: none;
            transition: all 0.2s cubic-bezier(0.4, 0, 0.2, 1);
            display: flex;
            justify-content: center;
            align-items: center;
            gap: 8px;
        }
        #fios-generate-reply {
            background: rgba(255, 255, 255, 0.05);
            color: #cbd5e1;
            border: 1px solid rgba(255, 255, 255, 0.08);
        }
        #fios-generate-reply:hover {
            background: rgba(255, 255, 255, 0.1);
            color: #fff;
            transform: translateY(-2px);
        }
        #fios-generate-proposal {
            background: linear-gradient(135deg, #4f46e5 0%, #3b82f6 100%);
            color: white;
            box-shadow: 0 4px 14px rgba(59, 130, 246, 0.3);
        }
        #fios-generate-proposal:hover {
            box-shadow: 0 6px 20px rgba(59, 130, 246, 0.5);
            transform: translateY(-2px);
            background: linear-gradient(135deg, #4338ca 0%, #2563eb 100%);
        }
        .fios-btn:active {
            transform: translateY(1px) !important;
        }
        .fios-icon {
            width: 16px;
            height: 16px;
        }
        #fios-content-area {
            font-size: 13px;
            color: #94a3b8;
            line-height: 1.5;
            background: rgba(0, 0, 0, 0.25);
            padding: 14px;
            border-radius: 10px;
            border: 1px solid rgba(255,255,255,0.05);
            min-height: 48px;
            display: flex;
            align-items: center;
            justify-content: center;
            text-align: center;
            transition: all 0.3s ease;
        }
        .fios-success-text {
            color: #34d399 !important;
            font-weight: 600;
        }
        .fios-highlight-text {
            color: #60a5fa !important;
            font-weight: 600;
        }
    `;
    document.head.appendChild(style);

    fiosPanel = document.createElement("div");
    fiosPanel.id = "fios-floating-panel";

    fiosPanel.innerHTML = `
        <div id="fios-panel-header">
            <div class="fios-brand">
                <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round">
                    <polygon points="12 2 2 7 12 12 22 7 12 2"></polygon>
                    <polyline points="2 17 12 22 22 17"></polyline>
                    <polyline points="2 12 12 17 22 12"></polyline>
                </svg>
                FIOS Agent
            </div>
            <div class="fios-status-indicator">
                <div class="fios-status-dot" id="fios-status-dot"></div>
                <span id="fios-status-text">Online</span>
            </div>
        </div>

        <div id="fios-content-area">
            Waiting for Upwork context...
        </div>

        <div>
            <button id="fios-generate-proposal" class="fios-btn">
                <svg class="fios-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><path d="M12 2v20M17 5H9.5a3.5 3.5 0 0 0 0 7h5a3.5 3.5 0 0 1 0 7H6"></path></svg>
                Auto-Fill Proposal
            </button>
            <button id="fios-generate-reply" class="fios-btn" style="margin-top:10px;">
                <svg class="fios-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"></path></svg>
                Smart Reply
            </button>
        </div>
    `;

    document.body.appendChild(fiosPanel);

    attachPanelEvents();

    return fiosPanel;
}

function attachPanelEvents() {
    document.getElementById("fios-generate-reply").onclick = generateReply;
    document.getElementById("fios-generate-proposal").onclick = generateAndInjectProposal;
}

function updateStatus(text, state = "info") {
    const statusText = document.getElementById("fios-status-text");
    const contentArea = document.getElementById("fios-content-area");
    const statusDot = document.getElementById("fios-status-dot");
    
    // Update top status text explicitly
    if (statusText) {
        if (state === "processing") statusText.innerText = "Processing";
        else if (state === "ready" || state === "success") statusText.innerText = "Ready";
        else if (state === "error") statusText.innerText = "Error";
        else statusText.innerText = "Online";
    }

    // Update main text
    if (contentArea) {
        contentArea.innerHTML = text;
        if (state === "success") contentArea.classList.add("fios-success-text");
        else contentArea.classList.remove("fios-success-text");
    }
    
    // Update dot animations & colors
    if (statusDot) {
        if (state === "processing") {
            statusDot.style.background = "#f59e0b"; // Yellow
            statusDot.style.animation = "none";
            statusDot.style.boxShadow = "none";
        } else if (state === "ready" || state === "success") {
            statusDot.style.background = "#10b981"; // Green
            statusDot.style.animation = "pulseGlow 2s infinite";
        } else if (state === "error") {
            statusDot.style.background = "#ef4444"; // Red
            statusDot.style.animation = "none";
            statusDot.style.boxShadow = "none";
        } else {
            statusDot.style.background = "#10b981";
            statusDot.style.animation = "pulseGlow 2s infinite";
        }
    }
}

async function generateReply() {
    updateStatus("Analyzing conversation thread...", "processing");

    const messages = document.querySelectorAll('[data-test="message-text"]');

    if (!messages.length) {
        updateStatus("No messages found to analyze.", "error");
        return;
    }

    const lastMessage = messages[messages.length - 1].innerText;

    const response = await callFIOSChat(`Client said: ${lastMessage}`);

    injectReply(response);
    updateStatus("🧠 Smart Reply injected and ready!", "success");
}

async function generateProposal() {
    updateStatus("Scanning job details...", "processing");

    const title = document.querySelector('[data-test="job-title"]')?.innerText || document.querySelector('h1')?.innerText || "";
    const description = document.querySelector('[data-test="job-description"]')?.innerText || document.querySelector('.job-description')?.innerText || "";

    const payload = {
        user_id: "upwork_user",
        job_data: {
            title: title,
            description: description
        }
    };

    try {
        const res = await fetch(FIOS_API_JOB, {
            method: "POST",
            headers: {
                "Content-Type": "application/json"
            },
            body: JSON.stringify(payload)
        });

        const result = await res.json();
        updateStatus(`Win Probability: <span class="fios-highlight-text">${result.win_probability}%</span>`, "ready");
        
        if (result.win_probability > 75) {
            generateAndInjectProposal();
        }
    } catch (e) {
        updateStatus("Analysis Failed check API.", "error");
        console.error(e);
    }
}

async function generateAndInjectProposal() {
    updateStatus("Generating optimized proposal...", "processing");

    const title = document.querySelector('[data-test="job-title"]')?.innerText || document.querySelector('h1')?.innerText || "";
    const description = document.querySelector('[data-test="job-description"]')?.innerText || document.querySelector('.job-description')?.innerText || "";

    const message = `
Write a proposal for this job:

Title: ${title}

Description: ${description}
`;

    const response = await callFIOSChat(message);
    injectProposalIntoUpwork(response);

    updateStatus("🚀 Proposal generated and injected!", "success");
}

async function callFIOSChat(message) {
    try {
        const res = await fetch(FIOS_API_CHAT, {
            method: "POST",
            headers: {
                "Content-Type": "application/json"
            },
            body: JSON.stringify({
                user_id: "upwork_user",
                message: message
            })
        });

        const result = await res.json();
        return result.response;
    } catch (e) {
        console.error("Chat failure:", e);
        return "Failed to connect to FIOS backend.";
    }
}

function injectReply(text) {
    const box = document.querySelector('[data-test="message-compose-input"]');
    if (box) {
        box.innerText = text;
    }
}

function injectProposalIntoUpwork(proposalText) {
    const textarea = document.querySelector('textarea, [contenteditable="true"]');

    if (!textarea) {
        updateStatus("Proposal editor not found on page.", "error");
        return;
    }

    textarea.focus();

    if (textarea.tagName === "TEXTAREA") {
        textarea.value = proposalText;
    } else {
        textarea.innerText = proposalText;
    }

    textarea.dispatchEvent(new Event("input", { bubbles: true }));
}

function autoInitializeFIOS() {
    createFIOSPanel();
    console.log("FIOS Floating UI initialized");
    
    // Auto-analyze job if on a job page or proposal page
    if (window.location.href.includes("/jobs/") || window.location.href.includes("/proposals/")) {
        generateProposal();
    }
}

setTimeout(autoInitializeFIOS, 3000);
