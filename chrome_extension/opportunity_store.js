async function storeOpportunity(job, score) {
    const data = await chrome.storage.local.get(["opportunities"]);
    let opportunities = data.opportunities || [];
    
    opportunities.push({
        job: job,
        score: score,
        timestamp: Date.now()
    });
    
    await chrome.storage.local.set({
        opportunities: opportunities
    });
}
