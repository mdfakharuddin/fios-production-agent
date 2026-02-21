from apscheduler.schedulers.asyncio import AsyncIOScheduler
from datetime import datetime
import asyncio

from FIOS.core.config import settings

class TaskManager:
    """Manages scheduled tasks for the FIOS architecture."""
    def __init__(self, scheduler: AsyncIOScheduler):
        self.scheduler = scheduler
        
    def add_nightly_job(self, func, *args, **kwargs):
        """Schedule a job to run every night at midnight."""
        self.scheduler.add_job(
            func, 
            'cron', 
            hour=0, 
            minute=0, 
            args=args, 
            kwargs=kwargs,
            id=f"{func.__name__}_nightly"
        )
        
    def add_weekly_job(self, func, day_of_week='sun', *args, **kwargs):
        """Schedule a job to run weekly."""
        self.scheduler.add_job(
            func, 
            'cron', 
            day_of_week=day_of_week, 
            hour=2, 
            minute=0, 
            args=args, 
            kwargs=kwargs,
            id=f"{func.__name__}_weekly"
        )

# Example placeholder tasks
async def sample_nightly_performance_analysis():
    print(f"[{datetime.now()}] Running nightly performance analysis...")

async def sample_weekly_community_research():
    print(f"[{datetime.now()}] Running weekly community research...")

def register_core_tasks(scheduler: AsyncIOScheduler):
    """Register all system-level cron jobs here."""
    manager = TaskManager(scheduler)
    manager.add_nightly_job(sample_nightly_performance_analysis)
    manager.add_weekly_job(sample_weekly_community_research)

