from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker
from config import settings

engine = create_async_engine(
    settings.database_url
)
# Create a configured "Session" class, each session is each transaction
AsyncSessionLocal = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False, 
)

#it gives SQLAlchemy a place to collect all your table/model definitions.
class Base(DeclarativeBase):
    pass

async def get_db():
    async with AsyncSessionLocal() as session:
        yield session
        
        
