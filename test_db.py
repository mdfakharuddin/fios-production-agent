import asyncio
import asyncpg

async def main():
    db_url = "postgresql://postgres:postgres@localhost:5432/fios_db"
    try:
        conn = await asyncpg.connect(db_url)
        print("Connected!")
        await conn.close()
    except Exception as e:
        print("Error:", e)

asyncio.run(main())
