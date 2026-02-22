const UPWORK_JOB_SEARCH_URL = "https://www.upwork.com/nx/search/jobs/?sort=recency";

let shadowTabId = null;

async function createShadowTab() {
    const tab = await chrome.tabs.create({
        url: UPWORK_JOB_SEARCH_URL,
        active: false,
        pinned: false
    });

    shadowTabId = tab.id;
    console.log("Upie Shadow Tab created:", shadowTabId);
}

async function refreshShadowTab() {
    if (!shadowTabId) {
        await createShadowTab();
        return;
    }
    chrome.tabs.reload(shadowTabId);
}

function startShadowScanner() {
    createShadowTab();
    // Refresh every 10 minutes
    setInterval(refreshShadowTab, 10 * 60 * 1000);
}
