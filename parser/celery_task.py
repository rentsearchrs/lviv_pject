from celery import Celery
from asgiref.sync import async_to_sync
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.future import select
from sqlalchemy.orm import sessionmaker
from parser.database import DATABASE_URL
from parser.models import Apartment, Rieltor

app = Celery(
    "tasks",
    broker="sqla+postgresql://avnadmin:AVNS_WuKZ_IhjhElCEeNK1j6@pg-30cc2364-mark-23c7.l.aivencloud.com:21288/defaultdb",
    backend="db+postgresql://avnadmin:AVNS_WuKZ_IhjhElCEeNK1j6@pg-30cc2364-mark-23c7.l.aivencloud.com:21288/defaultdb",
)

engine = create_async_engine(DATABASE_URL, echo=True)
SessionLocal = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

async def async_assign_apartment_to_agent(db: AsyncSession, apartment_id: int):
    realtor_ids = [row[0] for row in (await db.execute(select(Rieltor.id).order_by(Rieltor.id))).fetchall()]
    if not realtor_ids:
        raise ValueError("No realtors available for assignment")

    last_realtor_id = (await db.execute(
        select(Apartment.rieltor_id).where(Apartment.rieltor_id != None).order_by(Apartment.id.desc()).limit(1)
    )).scalar()

    next_realtor_id = realtor_ids[0] if last_realtor_id is None else realtor_ids[(realtor_ids.index(last_realtor_id) + 1) % len(realtor_ids)]

    apartment = (await db.execute(select(Apartment).where(Apartment.id == apartment_id))).scalar_one_or_none()
    if not apartment:
        raise ValueError("Apartment not found")

    apartment.rieltor_id = next_realtor_id
    await db.commit()

async def async_auto_assign_apartments():
    async with SessionLocal() as db:
        unassigned_apartments = (await db.execute(select(Apartment).where(Apartment.rieltor_id == None))).scalars().all()
        for apartment in unassigned_apartments:
            await async_assign_apartment_to_agent(db, apartment.id)

@app.task
def auto_assign_apartments():
    async_to_sync(async_auto_assign_apartments)()
