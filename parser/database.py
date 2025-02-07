from contextlib import asynccontextmanager
import logging
import os
import ssl
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy import Column, String, Integer
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from dotenv import load_dotenv
from sqlalchemy.pool import AsyncAdaptedQueuePool  # Use SQLAlchemy's async pooling

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL")

# Configure SSL context for asyncpg - disable verification
ssl_context = ssl.create_default_context()
ssl_context.check_hostname = False  # Disable hostname verification
ssl_context.verify_mode = ssl.CERT_NONE  # Disable SSL verification

engine = create_async_engine(
    DATABASE_URL,
    echo=True,
    connect_args={
        "ssl": ssl_context,
        "statement_cache_size": 0  # 🔥 Disable prepared statements
    },
    poolclass=NullPool  # Use NullPool when using PgBouncer
)

# Configure session factory
SessionLocal = sessionmaker(
    autocommit=False,  # Transactions must be explicitly committed
    autoflush=False,   # Avoid automatic state flushing
    bind=engine,       # Bind to the async engine
    class_=AsyncSession # Use async session class
)

# Define Base for models
Base = declarative_base()

async def get_db():
    async with SessionLocal() as db:
        try:
            yield db
        except Exception as e:
            logging.error(f"❌ Error in database session: {e}")
            raise
        finally:
            await db.close()  # Ensure session is always closed
            
@asynccontextmanager
async def get_dbb():
    async with SessionLocal() as db:
        try:
            yield db
        except Exception as e:
            logging.error(f"❌ Error in session lifecycle: {e}")
            await db.rollback()
            raise
        finally:
            await db.close()

async def init_db():
    import models  # Import models to ensure they are registered
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)  # Create tables if they don't exist
