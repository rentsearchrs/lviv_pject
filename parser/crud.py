from collections import defaultdict
from datetime import datetime
import logging
import os
import shutil
from datetime import datetime, timedelta
from mangum import Mangum
from typing import List, Optional
from fastapi import Body, FastAPI, BackgroundTasks, Depends, File, HTTPException, Path, Query, Request, UploadFile, logger, APIRouter
from fastapi.staticfiles import StaticFiles
import jwt
from pydantic import BaseModel
from sqlalchemy.orm import Session
from sqlalchemy import func, select
from parser.auth import verify_password
from parser.database import get_db, get_dbb, init_db
from parser.decode_token import create_access_token, decode_token
from parser.models import Apartment, File_apartment, Order, StopWord, TeamLeed, TelegramChannel, Template, Rieltor, TrapBlacklist
from parser.schemas import ApartmentResponse, AssignTeamLeaderRequest,  FileApartmentResponse, RieltorResponse, RieltorSchema, ImageOrderUpdate, OrderCreate, OrderResponse, RieltorCreate, RieltorResponsee
import parser.crud as crud
import asyncio
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.ext.asyncio import AsyncSession
from contextlib import asynccontextmanager
from sqlalchemy.exc import SQLAlchemyError
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from dotenv import load_dotenv
import tempfile
url = os.getenv("base_url2")
async def get_apartments_by_realtor(db: AsyncSession, realtor_id: int):
    stmt = select(Apartment).where(Apartment.rieltor_id == realtor_id)
    result = await db.execute(stmt)
    return result.scalars().all()

async def create_or_update_apartment(db: AsyncSession, apartment_data):
    try:
        # Check if an apartment with the same URL already exists
        stmt = select(Apartment).where(Apartment.url == apartment_data['url'])
        result = await db.execute(stmt)
        existing_apartment = result.scalar_one_or_none()

        if existing_apartment:
            # Update existing apartment
            for key, value in apartment_data.items():
                setattr(existing_apartment, key, value)
            await db.commit()
            await db.refresh(existing_apartment)
            return existing_apartment
        else:
            # Create a new apartment if it doesn't exist
            new_apartment = Apartment(**apartment_data)
            db.add(new_apartment)
            await db.commit()
            await db.refresh(new_apartment)
            return new_apartment

    except Exception as e:
        print(f"Error creating or updating apartment: {e}")
from sqlalchemy.orm import joinedload

# Asynchronously fetch all apartments from the DB
async def get_all_apartments(db: AsyncSession):
    try:
        stmt = select(Apartment)
        result = await db.execute(stmt)
        return result.scalars().all()
    except NoResultFound:
        return []
    except Exception as e:
        print(f"Error fetching apartments: {e}")
        return []
    

    
# Fetch apartments by status

async def get_apartments_by_status(db: AsyncSession, status: str):
    try:
        stmt = select(Apartment).where(Apartment.ad_status == status)
        result = await db.execute(stmt)
        return result.scalars().all()
    except NoResultFound:
        return []
    except Exception as e:
        print(f"Error fetching apartments by status: {e}")
        return []

# Update the status of an apartment
async def update_apartment_status(db: AsyncSession, apartment_id: int, new_status: str):
    try:
        stmt = (
            update(Apartment)
            .where(Apartment.id == apartment_id)
            .values(ad_status=new_status)
            .execution_options(synchronize_session="fetch")
        )
        await db.execute(stmt)
        await db.commit()
    except Exception as e:
        print(f"Error updating apartment status: {e}")

logger = logging.getLogger(__name__)
async def create_order(
    db: AsyncSession, name: str, phone: str, telegram_username: Optional[str] = None,
    apartment_id: Optional[int] = None, client_wishes: Optional[str] = None, 
    search_time: Optional[str] = None, residents: Optional[str] = None,
    budget: Optional[str] = None, district: Optional[str] = None, rooms: Optional[str] = None,
    area: Optional[str] = None, team_leader_id: Optional[str] = None
):
    try:
        db_order = Order(
            apartment_id=apartment_id,
            name=name,
            phone=phone,
            telegram_username=telegram_username,  # ✅ NEW FIELD
            client_wishes=client_wishes,
            search_time=search_time,
            residents=residents,
            budget=budget,  # ✅ Save budget input
            district=district,  # ✅ Save "Район"
            rooms=rooms,  # ✅ Save "Кількість кімнат"
            area=area,  # ✅ Save "Площа (м²)"
            team_leader_id=team_leader_id
        )
        
        db.add(db_order)
        await db.commit()
        await db.refresh(db_order)
        logger.info(f"Order created successfully with ID: {db_order.id}")
        return db_order

    except SQLAlchemyError as e:
        logger.error(f"SQLAlchemy error: {e}")
        await db.rollback()
        return None
    except Exception as e:
        logger.error(f"Unexpected error in create_order: {e}")
        await db.rollback()
        return None



async def get_all_orders(db: AsyncSession):
    stmt = select(Order)
    result = await db.execute(stmt)
    orders = result.scalars().all()  # Fetch all orders as a list
    return orders

async def add_image_to_apartment(db: AsyncSession, apartment_id: int, image_data: dict):
    db_image = File_apartment(apartment_id=apartment_id, **image_data)
    db.add(db_image)
    await db.commit()
    await db.refresh(db_image)
    return db_image

async def delete_image(db: AsyncSession, image_id: int) -> bool:
    result = await db.execute(select(File_apartment).where(File_apartment.id == image_id))
    db_image = result.scalars().first()
    
    if db_image:
        try:
            os.remove(db_image.file_path)  # Remove from filesystem
        except FileNotFoundError:
            pass  # The file may have already been deleted
        await db.delete(db_image)  # Remove from database
        await db.commit()
        return True
    return False
async def get_images_by_apartment_id(db: AsyncSession, apartment_id: int) -> List[File_apartment]:
    result = await db.execute(
        select(File_apartment)
        .where(File_apartment.apartment_id == apartment_id)
        .order_by(File_apartment.order)  # Ensure this is working
    )
    images = result.scalars().all()
    print("Images fetched by apartment:", images)
    return images

async def reorder_images(db: AsyncSession, order_updates: List[ImageOrderUpdate]) -> None:
    """
    Update the order of images based on the provided order updates.
    """
    for update in order_updates:
        result = await db.execute(select(File_apartment).where(File_apartment.id == update.image_id))
        db_image = result.scalars().first()
        
        if db_image:
            db_image.order = update.new_order
            db.add(db_image)  # Add the updated image to the session

    # Commit the changes to persist the updates
    await db.commit()





async def update_apartment_fix_fields(db: AsyncSession, apartment_id: int, update_data: dict):
    try:
        # Select the apartment by ID
        stmt = select(Apartment).where(Apartment.id == apartment_id)
        result = await db.execute(stmt)
        apartment = result.scalar_one_or_none()
        
        if not apartment:
            return None  # Return None if the apartment doesn't exist
        
        # Update only the `*_fix` fields from the update_data dictionary
        fix_fields = ["title_fix", "price_fix", "location_date_fix", "features_fix", "owner_fix", 
                      "square_fix", "room_fix", "residential_complex_fix", "floor_fix", 
                      "superficiality_fix", "classs_fix", "url_fix", "user_fix", "phone_fix"]
        
        for field in fix_fields:
            if field in update_data:
                setattr(apartment, field, update_data[field])

        # Commit the changes
        await db.commit()
        await db.refresh(apartment)
        return apartment

    except SQLAlchemyError as e:
        print(f"Error updating apartment fix fields: {e}")
        await db.rollback()
        return None
    












async def get_all_apartments_and_photo(db: AsyncSession, request: Request):
    query = (
        select(Apartment)
        .options(joinedload(Apartment.files))
        .filter(Apartment.ad_status == "successful")  # Add filter for ad_status
    )
    result = await db.execute(query)
    apartments = result.unique().scalars().all()


    return [
        ApartmentResponse(
            id = apartment.id,
            type_deal = apartment.type_deal,
            type_object = apartment.type_object,
            title=apartment.title_fix or apartment.title,
            price=apartment.price_fix or apartment.price, 
            location_date=apartment.location_date_fix or apartment.location_date,
            description = apartment.description,
            features=apartment.features_fix or apartment.features,
            owner=apartment.owner_fix or apartment.owner,
            square=apartment.square_fix or apartment.square,
            room=apartment.room_fix or apartment.room,
            residential_complex=apartment.residential_complex_fix or apartment.residential_complex,
            floor=apartment.floor_fix or apartment.floor,
            superficiality=apartment.superficiality_fix or apartment.superficiality,
            classs=apartment.classs_fix or apartment.classs,
            url=apartment.url_fix or apartment.url,
            ad_status = apartment.ad_status,
            #on_map = apartment.on_map,
            user=apartment.user_fix or apartment.user,
            phone=apartment.phone_fix or apartment.phone,
            id_olx = apartment.id_olx,
            files=[
                FileResponse(
                    id=file.id,
                    filename=file.filename,
                    date=file.date,
                    content_type=file.content_type,
                    # Construct the full URL for the image without /static/
                    file_path=f"{url}/{file.file_path.lstrip('/')}",  # Ensure correct URL formation
                    order=file.order
                ) for file in apartment.files
            ]
        ) for apartment in apartments
    ]
async def get_all_apartments_and_photo_all(db: AsyncSession, request: Request):
    query = select(Apartment).options(joinedload(Apartment.files))
    result = await db.execute(query)
    apartments = result.unique().scalars().all()

    return [
        ApartmentResponse(
            id = apartment.id,
            type_deal = apartment.type_deal,
            type_object = apartment.type_object,
            title = apartment.title,
            price = apartment.price, 
            location_date = apartment.location_date,
            description = apartment.description,
            features = apartment.features,
            owner = apartment.owner,
            square = apartment.square,
            room = apartment.room,
            residential_complex = apartment.residential_complex,
            floor = apartment.floor,
            superficiality = apartment.superficiality,
            classs = apartment.classs,
            url = apartment.url,
            ad_status = apartment.ad_status,
            #on_map = apartment.on_map,
            user = apartment.user,
            phone = apartment.phone,
            id_olx = apartment.id_olx,

            title_fix = apartment.title_fix,
            price_fix = apartment.price_fix,
            location_date_fix = apartment.location_date_fix,
            features_fix = apartment.features_fix,
            owner_fix = apartment.owner_fix,
            square_fix = apartment.square_fix,
            room_fix = apartment.room_fix,
            residential_complex_fix = apartment.residential_complex_fix,
            floor_fix = apartment.floor_fix,
            superficiality_fix = apartment.superficiality_fix,
            classs_fix = apartment.classs_fix,
            url_fix = apartment.url_fix,
            user_fix = apartment.user_fix,
            phone_fix = apartment.phone_fix,
            files=[
                FileResponse(
                    id=file.id,
                    filename=file.filename,
                    date=file.date,
                    content_type=file.content_type,
                    # Construct the full URL for the image without /static/
                    file_path=f"http://127.0.0.1:8000/{file.file_path.lstrip('/')}",  # Ensure correct URL formation
                    order=file.order
                ) for file in apartment.files
            ]
        ) for apartment in apartments
    ]
async def get_apartment_by_id(db: AsyncSession, apartment_id: int) -> Optional[ApartmentResponse]:
    # Eagerly load `files` and `rieltor` relationships
    query = (
        select(Apartment)
        .options(joinedload(Apartment.files), joinedload(Apartment.rieltor))
        .where(Apartment.id == apartment_id)
    )
    result = await db.execute(query)

    # Use `.unique()` to handle joined eager loads against collections
    apartment = result.unique().scalar_one_or_none()

    if not apartment:
        return None

    # Construct the response with realtor information
    return ApartmentResponse(
        id=apartment.id,
        type_deal=apartment.type_deal,
        type_object=apartment.type_object,
        title=apartment.title,
        price=apartment.price,
        location_date=apartment.location_date,
        description=apartment.description,
        features=apartment.features,
        owner=apartment.owner,
        square=apartment.square,
        room=apartment.room,
        residential_complex=apartment.residential_complex,
        floor=apartment.floor,
        superficiality=apartment.superficiality,
        classs=apartment.classs,
        url=apartment.url,
        ad_status=apartment.ad_status,
        user=apartment.user,
        phone=apartment.phone,
        id_olx=apartment.id_olx,
        title_fix=apartment.title_fix,
        price_fix=apartment.price_fix,
        location_date_fix=apartment.location_date_fix,
        features_fix=apartment.features_fix,
        owner_fix=apartment.owner_fix,
        square_fix=apartment.square_fix,
        room_fix=apartment.room_fix,
        residential_complex_fix=apartment.residential_complex_fix,
        floor_fix=apartment.floor_fix,
        superficiality_fix=apartment.superficiality_fix,
        classs_fix=apartment.classs_fix,
        url_fix=apartment.url_fix,
        user_fix=apartment.user_fix,
        phone_fix=apartment.phone_fix,
        last_contact_date=apartment.last_contact_date,
        next_contact_date=apartment.next_contact_date,
        lease_end_date=apartment.lease_end_date,
        rieltor=RieltorSchema.from_orm(apartment.rieltor) if apartment.rieltor else None,  # Include realtor info
        files=[
            FileResponse(
                id=file.id,
                filename=file.filename,
                date=file.date,
                content_type=file.content_type,
                file_path=f"http://127.0.0.1:8000/{file.file_path.lstrip('/')}",
            )
            for file in apartment.files
        ]
    )

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

def hash_password(password: str) -> str:
    return pwd_context.hash(password)

async def create_rieltor(db, rieltor):
    hashed_password = pwd_context.hash(rieltor.password)  # Hash the password
    new_rieltor = Rieltor(username=rieltor.username, password=hashed_password)
    db.add(new_rieltor)
    await db.commit()  # Use await with AsyncSession
    await db.refresh(new_rieltor)
    return new_rieltor

async def get_rieltor_by_username(db, username: str):
    stmt = select(Rieltor).where(Rieltor.username == username)
    result = await db.execute(stmt)
    return result.scalar_one_or_none()  # Returns the first matching Rieltor or None

async def assign_apartment_to_agent(db: AsyncSession, apartment_id: int):
    agents = await db.execute(select(Rieltor.id))
    agent_ids = [agent.id for agent in agents.scalars().all()]
    if not agent_ids:
        raise ValueError("No agents available for assignment")

    # Assign in a round-robin fashion
    apartment = await db.execute(select(Apartment).where(Apartment.id == apartment_id))
    apartment = apartment.scalar_one_or_none()
    if not apartment:
        raise ValueError("Apartment not found")

    assigned_agent = agent_ids[len(agent_ids) % len(agent_ids)]
    apartment.rieltor_id = assigned_agent
    await db.commit()
    return apartment


async def update_contact_dates(db: AsyncSession, apartment_id: int, weeks: int = 2):
    apartment = await db.execute(select(Apartment).where(Apartment.id == apartment_id))
    apartment = apartment.scalar_one_or_none()
    if not apartment:
        raise ValueError("Apartment not found")

    apartment.last_contact_date = datetime.now()
    apartment.next_contact_date = datetime.now() + datetime.timedelta(weeks=weeks)
    await db.commit()
    return apartment

async def update_lease_end_date(db: AsyncSession, apartment_id: int, months: int):
    apartment = await db.execute(select(Apartment).where(Apartment.id == apartment_id))
    apartment = apartment.scalar_one_or_none()
    if not apartment:
        raise ValueError("Apartment not found")

    apartment.lease_end_date = datetime.now() + datetime.timedelta(days=months * 30)
    await db.commit()
    return apartment

async def assign_apartment_to_agent(db: AsyncSession, apartment_id: int):
    """
    Assign an apartment to a realtor in a round-robin fashion.
    """
    # Fetch all realtor IDs
    stmt = select(Rieltor.id).order_by(Rieltor.id)  # Order ensures round-robin consistency
    result = await db.execute(stmt)
    realtor_ids = [row[0] for row in result.fetchall()]

    if not realtor_ids:
        raise ValueError("No realtors available for assignment")

    # Fetch the last assigned realtor ID (track progress for round-robin)
    stmt_last = select(Apartment.rieltor_id).where(Apartment.rieltor_id != None).order_by(Apartment.id.desc()).limit(1)
    result_last = await db.execute(stmt_last)
    last_realtor_id = result_last.scalar()

    # Find the next realtor ID in round-robin order
    if last_realtor_id is None or last_realtor_id not in realtor_ids:
        next_realtor_id = realtor_ids[0]  # Start with the first realtor
    else:
        current_index = realtor_ids.index(last_realtor_id)
        next_realtor_id = realtor_ids[(current_index + 1) % len(realtor_ids)]

    # Assign the apartment to the next realtor
    stmt_apartment = select(Apartment).where(Apartment.id == apartment_id)
    result_apartment = await db.execute(stmt_apartment)
    apartment = result_apartment.scalar_one_or_none()

    if not apartment:
        raise ValueError("Apartment not found")

    apartment.rieltor_id = next_realtor_id
    await db.commit()

    return apartment
from sqlalchemy.orm import selectinload

async def get_all_realtors(db: AsyncSession):
    result = await db.execute(
        select(Rieltor).options(selectinload(Rieltor.apartments))
    )
    return result.scalars().all()



async def assign_team_leader(db: AsyncSession, realtor_id: int, team_leader_id: int):
    # Ensure the team leader exists
    team_leader_stmt = select(TeamLeed).where(TeamLeed.id == team_leader_id)
    result = await db.execute(team_leader_stmt)
    team_leader = result.scalar_one_or_none()

    if not team_leader:
        raise ValueError("Team Leader not found")

    # Ensure the realtor exists
    realtor_stmt = select(Rieltor).where(Rieltor.id == realtor_id)
    result = await db.execute(realtor_stmt)
    realtor = result.scalar_one_or_none()

    if not realtor:
        raise ValueError("Realtor not found")

    # Update the team_leader_id for the realtor
    update_stmt = (
        update(Rieltor)
        .where(Rieltor.id == realtor_id)
        .values(team_leader_id=team_leader_id)
    )
    await db.execute(update_stmt)
    await db.commit()

    return realtor

async def get_realtors_by_team_leader(db: AsyncSession, team_leader_id: int):
    stmt = select(TeamLeed).where(TeamLeed.team_leader_id == team_leader_id)
    result = await db.execute(stmt)
    return result.scalars().all()

async def get_team_leaders(db: AsyncSession):
    stmt = select(Rieltor).where(Rieltor.type == "team_leader")
    result = await db.execute(stmt)
    return result.scalars().all()

async def create_rieltor(db: AsyncSession, rieltor: RieltorCreate):
    # Hash the password
    hashed_password = hash_password(rieltor.password)
    new_rieltor = Rieltor(
        username=rieltor.username,
        password=hashed_password,
        name=rieltor.name,
        type=rieltor.type  # "team_leader" or "realtor"
    )
    db.add(new_rieltor)
    await db.commit()
    await db.refresh(new_rieltor)
    return new_rieltor

async def create_team_leader(db: AsyncSession, username: str, password: str, name: Optional[str] = None):
    try:
        hashed_password = hash_password(password)  # Hash the password

        # Create a new Team Leader
        new_team_leader = TeamLeed(
            username=username,
            password=hashed_password,
            name=name,
            type="team_leader"
        )

        db.add(new_team_leader)
        await db.commit()
        await db.refresh(new_team_leader)
        return new_team_leader
    except Exception as e:
        await db.rollback()
        raise ValueError(f"Error creating Team Leader: {e}")
from telegram.ext import Defaults
bot_token = os.getenv("bot_token")

bot = Bot(token=bot_token)
import re
async def lock_apartment_for_sending(db: AsyncSession, apartment_id: int):
    """
    Mark an apartment as in-progress for sending.
    """
    try:
        result = await db.execute(
            select(Apartment).filter(
                Apartment.id == apartment_id,
                Apartment.is_sending == False
            ).with_for_update()  # Lock the row
        )
        apartment = result.scalar_one_or_none()

        if apartment:
            apartment.is_sending = True
            db.add(apartment)
            await db.commit()
            await db.refresh(apartment)
            return apartment
        else:
            return None
    except Exception as e:
        await db.rollback()
        logging.error(f"❌ Failed to lock apartment {apartment_id}: {e}")
        return None


async def release_apartment_lock(db: AsyncSession, apartment: Apartment, success: bool, is_sent_to_channel: str = None):
    """
    Reset the lock and update sending status, ensuring `sent_to_sent_channel` is updated correctly.
    """
    try:
        apartment.is_sending = False  # Always reset lock

        if success:
            if is_sent_to_channel == "sent to telegram channel":
                apartment.sent_to_sent_channel = True  # ✅ Fix: Ensure it is marked as sent
                logging.info(f"✅ Apartment {apartment.id} marked as sent_to_sent_channel=True")
            else:
                apartment.last_posted_at = datetime.utcnow()  # ✅ Only update for other categories

        db.add(apartment)
        await db.commit()
        await db.refresh(apartment)
        logging.info(f"🔄 Updated apartment {apartment.id}: sent_to_sent_channel={apartment.sent_to_sent_channel}")

    except Exception as e:
        await db.rollback()
        logging.error(f"❌ Failed to release lock for apartment {apartment.id}: {e}")




UAH_TO_USD_RATE = 41.50  # Conversion rate
async def send_with_retry(chat_id, media_group, retries=5, base_delay=5):
    """
    Send media group to Telegram with retry logic for flood control.
    """
    for attempt in range(retries):
        try:
            await bot.send_media_group(chat_id=chat_id, media=media_group)
            logging.info(f"✅ Successfully sent to channel {chat_id}")
            return
        except RetryAfter as e:
            delay = e.retry_after or base_delay * (2 ** attempt)
            logging.warning(f"⚠️ Flood control triggered. Retrying in {delay} seconds...")
            await asyncio.sleep(delay)
        except TimedOut:
            logging.error(f"❌ Timed out while sending to channel: {chat_id}")
        except Exception as e:
            logging.error(f"❌ Error sending to channel {chat_id}: {e}")
            raise e

def parse_price(price: str) -> float:
    """
    Parse the price string to extract numeric value in USD.
    Supports prices in UAH ('грн') and USD ('$').
    """
    if not price:
        return 0.0

    # Remove unnecessary characters
    clean_price = re.sub(r"[^\d]", "", price)

    if 'грн' in price:
        return float(clean_price) / UAH_TO_USD_RATE  # Convert UAH to USD
    elif '$' in price:
        return float(clean_price)  # Already in USD
    else:
        return float(clean_price)  # Default case
async def get_pending_apartments(db: AsyncSession):
    """
    Fetch pending apartments grouped by TelegramChannel with additional filtering.
    Exclude apartments that are already sent or recently posted, and lock rows during processing.
    """
    try:
        # Fetch relevant Telegram channels
        channels = await db.execute(
            select(TelegramChannel).filter(
                TelegramChannel.category.in_(["sent to telegram channel", "successful"])
            )
        )
        channels = channels.scalars().all()

        apartments_by_channel = []

        for channel in channels:
            query = select(Apartment).options(joinedload(Apartment.files))

            if channel.category == "sent to telegram channel":
                query = query.filter(
                    or_(
                        Apartment.ad_status == None,  # Handle NULL
                        Apartment.ad_status == ""  # Handle empty string
                    ),
                    or_(
                        Apartment.sent_to_sent_channel == False,
                        Apartment.sent_to_sent_channel == None   # Handle NULL values
                    )
                )
            elif channel.category == "successful":
                query = query.filter(Apartment.ad_status == "successful")

            query = query.filter(
                Apartment.type_deal == channel.type_deal,
                Apartment.type_object == channel.type_object
            )

            result = await db.execute(query)
            apartments = result.unique().scalars().all()

            # Apply price filtering
            if channel.price_from is not None or channel.price_to is not None:
                apartments = [
                    apt for apt in apartments
                    if (
                        (channel.price_from is None or parse_price(apt.price) >= channel.price_from) and
                        (channel.price_to is None or parse_price(apt.price) <= channel.price_to)
                    )
                ]
            # Location filtering
            if channel.location_type == "city":
                apartments = [apt for apt in apartments if "Львів" in apt.location_date]
            elif channel.location_type == "region":
                apartments = [apt for apt in apartments if "," not in apt.location_date]
            elif channel.location_type == "outskirts_of_the_city":
                outskirts_locations = {
                    "Малехів", "Грибовичі", "Дубляни", "Сокільники", "Солонка", 
                    "Зубра", "Рудно", "Лапаївка", "Зимна Вода", "Винники", 
                    "Підберізці", "Лисиничі", "Давидів", "Підгірці"
                }
                apartments = [apt for apt in apartments if apt.location_date in outskirts_locations]

            if apartments:
                apartments_by_channel.append((channel, apartments))

        return apartments_by_channel

    except Exception as e:
        logging.error(f"❌ Error fetching pending apartments with filters: {e}")
        return []






async def fetch_template(db: AsyncSession, template_name: str = "telegram_channel"):
    """
    Fetch a message template from the database.
    """
    try:
        result = await db.execute(select(Template).where(Template.name == template_name))
        template = result.scalar_one_or_none()
        return template.template_text if template else "Default template"
    except Exception as e:
        logging.error(f"❌ Error fetching template: {e}")
        return "Default template"

def format_message(apartment, template_text):
    """
    Format message using all available attributes of an apartment object.
    """
    apartment_data = {key: (getattr(apartment, key) or "N/A") for key in vars(apartment)}
    try:
        return template_text.format(**apartment_data)
    except KeyError as e:
        return f"Error: Missing key {e} in the template."
from telegram.error import TimedOut, RetryAfter


async def send_ad_to_telegram(db: AsyncSession, apartment_id: int):
    """
    Send an ad to Telegram and update necessary fields based on the channel category.
    Even if sending fails or times out, `sent_to_sent_channel` is set to True.
    """
    apartment = await lock_apartment_for_sending(db, apartment_id)
    if not apartment:
        logging.info(f"⏳ Apartment {apartment_id} is already being processed. Skipping.")
        return

    try:
        # Fetch Telegram channels for the apartment's type
        channels = await db.execute(
            select(TelegramChannel).filter(
                TelegramChannel.type_deal == apartment.type_deal,
                TelegramChannel.type_object == apartment.type_object,
                or_(
                    and_(
                        TelegramChannel.category == "sent to telegram channel",
                        apartment.sent_to_sent_channel == False  # Ensure it's not already marked
                    ),
                    and_(
                        TelegramChannel.category == "successful",
                        apartment.ad_status == "successful",
                        TelegramChannel.channel_id != apartment.last_posted_channel_id
                    )
                )
            )
        )
        channels = channels.scalars().all()

        if not channels:
            logging.warning(f"⚠️ No eligible channels found for apartment {apartment_id}")
            await release_apartment_lock(db, apartment, success=False)
            return

        # Fetch and format the message template
        template_text = await fetch_template(db, template_name="telegram_channel")
        message_text = format_message(apartment, template_text)
        media_group = [
            InputMediaPhoto(
                media=f"https://a3ff-217-31-72-114.ngrok-free.app/{file.file_path.lstrip('/')}",
                caption=message_text if idx == 0 else None
            )
            for idx, file in enumerate(apartment.files[:5])
        ]

        sent_any = False
        for channel in channels:
            try:
                await send_with_retry(channel.channel_id, media_group)
                sent_any = True  # ✅ Mark as sent if it succeeds

                # ✅ Always set sent_to_sent_channel=True even if there are errors
                apartment.sent_to_sent_channel = True

                # ✅ Only update last_posted_at for "successful" category
                if channel.category == "successful":
                    apartment.last_posted_channel_id = channel.channel_id
                    apartment.last_posted_at = datetime.utcnow()

                logging.info(f"✅ Successfully sent apartment {apartment_id} to {channel.channel_id}")

            except TimedOut:
                logging.error(f"❌ Timeout error while sending apartment {apartment_id} to {channel.channel_id}")
                sent_any = True  # ✅ Still mark as sent even on timeout
                apartment.sent_to_sent_channel = True  # ✅ Ensure it's marked as sent
                break  # Stop further attempts to avoid Telegram blocking

            except Exception as e:
                logging.error(f"❌ Failed to send apartment {apartment_id} to {channel.channel_id}: {e}")
                sent_any = True  # ✅ Mark as sent even on failure
                apartment.sent_to_sent_channel = True  # ✅ Ensure it's marked as sent

        # ✅ Ensure `sent_to_sent_channel=True` no matter what happens
        await release_apartment_lock(db, apartment, success=True, is_sent_to_channel="sent to telegram channel")

    except Exception as e:
        logging.error(f"❌ Unexpected error for apartment {apartment.id}: {e}")
        # ✅ Even if an error occurs, still mark as sent
        apartment.sent_to_sent_channel = True
        await release_apartment_lock(db, apartment, success=True, is_sent_to_channel="sent to telegram channel")



from telegram.error import TelegramError

async def send_with_retry(chat_id, media_group, retries=5, base_delay=5):
    for attempt in range(retries):
        try:
            response = await bot.send_media_group(chat_id=chat_id, media=media_group)
            logging.info(f"✅ Successfully sent to channel {chat_id}: {response}")
            return
        except Exception as e:
            logging.error(f"❌ Error sending to channel {chat_id}: {e}")
            raise e



def extract_retry_after(error):
    """
    Extract retry_after seconds from TelegramError if available.
    """
    try:
        return int(re.search(r"Retry in (\d+) seconds", str(error)).group(1))
    except Exception:
        return None


async def count_daily_published_apartments(db: AsyncSession):
    """
    Count the number of apartments published today.
    """
    try:
        start_of_day = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
        query = select(Apartment).filter(Apartment.last_posted_at >= start_of_day)
        result = await db.execute(query)
        apartments = result.scalars().all()

        return len(apartments)
    except Exception as e:
        logging.error(f"❌ Error counting daily published apartments: {e}")
        return 0
    

async def send_daily_summary(db: AsyncSession):
    """
    Send a daily summary of published apartments to Telegram channels.
    """
    try:
        # Count the apartments published today
        total_published = await count_daily_published_apartments(db)

        # Fetch all relevant Telegram channels
        channels_query = select(TelegramChannel).filter(
            TelegramChannel.category.in_(["sent to telegram channel", "successful"])
        )
        result = await db.execute(channels_query)
        channels = result.scalars().all()

        # Prepare the summary message
        message_text = (
            f"Today the RentSearch team added another {total_published} exclusive objects. "
            "Hurry up and sign up for a review 🧐!"
        )

        # Send the message to each channel
        for channel in channels:
            try:
                await bot.send_message(chat_id=channel.channel_id, text=message_text)
                logging.info(f"✅ Summary sent to channel {channel.channel_id}")
            except Exception as e:
                logging.error(f"❌ Failed to send summary to channel {channel.channel_id}: {e}")
    except Exception as e:
        logging.error(f"❌ Error sending daily summary: {e}")


# ✅ Fetch all Telegram channels
async def get_all_telegram_channels(db: AsyncSession):
    result = await db.execute(select(TelegramChannel))
    return result.unique().scalars().all()

# ✅ Add a new Telegram channel
async def add_telegram_channel(db: AsyncSession, category: str, type_deal: str, channel_id: str, type_object:str, price_from: Optional[int] = None, price_to: Optional[int] = None, location_type: str = "all"):
    new_channel = TelegramChannel(type_object=type_object, category=category, type_deal=type_deal, channel_id=channel_id, price_from = price_from, price_to = price_to, location_type = location_type)
    db.add(new_channel)
    await db.commit()
    await db.refresh(new_channel)
    return new_channel

# ✅ Update the status of an apartment
async def update_apartment_status(db: AsyncSession, apartment_id: int, new_status: str):
    result = await db.execute(select(Apartment).filter(Apartment.id == apartment_id))
    apartment = result.unique().scalar_one_or_none()
    if apartment:
        apartment.ad_status = new_status
        await db.commit()
        await db.refresh(apartment)
        return apartment
    return None


