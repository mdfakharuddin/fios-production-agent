from apscheduler.schedulers.asyncio import AsyncIOScheduler
from core.orchestrator import orchestrator
import httpx
import os

class AutomationScheduler:
    """
    FIOS Background Automation Engine
    Runs periodic tasks like automated ghost detection and follow-ups.
    """
    def __init__(self):
        self.scheduler = AsyncIOScheduler()
        
    def start(self):
        # Scan every 6 hours
        self.scheduler.add_job(
            self.run_followup_scans,
            'interval',
            hours=6,
            id='followup_scan',
            replace_existing=True
        )
        self.scheduler.start()
        
    async def run_followup_scans(self):
        print("Running background ghost & follow-up scan...")
        # Hardcoding the user setup for the proxy
        # In a real environment, you'd iterate over all active User IDs
        user_id = "upwork_user"
        
        try:
            opportunities = await orchestrator.autonomous_followup_cycle(user_id=user_id)
            
            for opp in opportunities:
                if opp.get("should_followup"):
                    priority = opp.get("priority", "normal")
                    recommended_message = opp.get("recommended_message", "")
                    conversation_id = opp.get("conversation_id", "")
                    
                    print(f"Follow up required for {conversation_id}: {recommended_message}")
                    
                    # Example webhook notification (e.g. n8n or generic webhook)
                    webhook_url = os.getenv("N8N_WEBHOOK_URL")
                    if webhook_url:
                        async with httpx.AsyncClient() as client:
                            await client.post(webhook_url, json={
                                "event": "ghost_detected",
                                "conversation_id": conversation_id,
                                "message": recommended_message,
                                "priority": priority
                            })
                            
        except Exception as e:
            print(f"Error executing background task: {e}")

# Singleton instance
global_scheduler = AutomationScheduler()
