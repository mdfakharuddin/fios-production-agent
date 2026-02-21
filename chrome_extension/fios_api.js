const FIOS_API_URL = "https://c4800kswgwggs0sg8o8kkogs.103.127.1.91.sslip.io/api/chat";

async function queryFIOS(message, conversationId=null, metadata={}) {

    const payload = {
        user_id: "upwork_user",
        message: message,
        conversation_id: conversationId,
        metadata: metadata
    };

    try {
        const response = await fetch(FIOS_API_URL, {
            method: "POST",
            headers: {
                "Content-Type": "application/json"
            },
            body: JSON.stringify(payload)
        });

        const data = await response.json();
        return data;

    } catch (error) {
        console.error("FIOS API Error:", error);
        return null;
    }
}

async function sendJobsToFIOS(jobs) {
    for (const job of jobs) {
        try {
            const response = await fetch(
                "https://c4800kswgwggs0sg8o8kkogs.103.127.1.91.sslip.io/api/job/analyze",
                {
                    method: "POST",
                    headers: {
                        "Content-Type": "application/json"
                    },
                    body: JSON.stringify({
                        user_id: "upwork_user",
                        job_data: job
                    })
                }
            );
            const result = await response.json();
            console.log("FIOS Opportunity Score:", result);
            
            // If local storage is requested:
            if (typeof storeOpportunity === 'function') {
                await storeOpportunity(job, result);
            }
        } catch (error) {
            console.error("FIOS job scan error:", error);
        }
    }
}
