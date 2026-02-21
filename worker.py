import asyncio
from core.scheduler import global_scheduler

async def main():
    global_scheduler.start()
    while True:
        await asyncio.sleep(3600)

if __name__ == "__main__":
    asyncio.run(main())
