from typing import AsyncGenerator
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from core.config import settings

# Create async engine for PostgreSQL
engine = create_async_engine(
    settings.async_database_url,
    echo=False,
    future=True
)

# Create session factory
async_session_maker = async_sessionmaker(
    engine, 
    class_=AsyncSession, 
    expire_on_commit=False,
    autoflush=False
)

async def get_db_session() -> AsyncGenerator[AsyncSession, None]:
    """Dependency for getting async DB sessions."""
    async with async_session_maker() as session:
        try:
            yield session
        finally:
            await session.close()
