from contextlib import asynccontextmanager
import logging
import os
import ssl
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy import Column, String, Integer
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from dotenv import load_dotenv

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL")

# Configure SSL context for asyncpg - disable verification
ssl_context = ssl.create_default_context()
ssl_context.check_hostname = False  # Disable hostname verification
ssl_context.verify_mode = ssl.CERT_NONE  # Disable SSL verification

engine = create_async_engine(DATABASE_URL, echo=True)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine, class_=AsyncSession)

# Define Base for models
Base = declarative_base()

# Async dependency for getting the database session
async def get_db():
    async with SessionLocal() as db:
        try:
            yield db
        except Exception as e:
            logging.error(f"❌ Error in database session: {e}")
            raise
        finally:
            await db.close()  # Ensure the session is closed after use
            
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
