
from collections import defaultdict
from datetime import datetime
import logging
import os
import shutil
from datetime import datetime, timedelta
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
import parser.scraper as scraper 
import asyncio
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.ext.asyncio import AsyncSession
from contextlib import asynccontextmanager
from sqlalchemy.exc import SQLAlchemyError
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from dotenv import load_dotenv
import tempfile
from passlib.context import CryptContext
load_dotenv()

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="token")
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI()


# Use a writable temporary directory for images
if "AWS_LAMBDA_FUNCTION_NAME" in os.environ:
    IMAGE_DIR = "/tmp/images"  # AWS Lambda allows writing to /tmp/
else:
    IMAGE_DIR = tempfile.mkdtemp()  # General case for local and other cloud environments

os.makedirs(IMAGE_DIR, exist_ok=True)
app.mount("/images", StaticFiles(directory=IMAGE_DIR), name="images")

# Allowed origins (frontend URL)
origins = [
    "https://router-lemon-beta-90.vercel.app",  # Angular frontend
    "https://lviv-pject.vercel.app",  
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,  # Allow only specific frontend origins
    allow_credentials=True,
    allow_methods=["*"],  # Allow all HTTP methods (GET, POST, PUT, DELETE, etc.)
    allow_headers=["*"],  # Allow all headers
)


# Endpoint to fetch apartments by status
@app.get("/apartments/{status}")
async def get_apartments_by_status(status: str, db: AsyncSession = Depends(get_db)):
    apartments = await crud.get_apartments_by_status(db, status)
    return apartments

@app.put("/apartments/{apartment_id}/status")
async def update_apartment_status(apartment_id: int, new_status: str = Query(...), db: AsyncSession = Depends(get_db)):
    if new_status not in ["new", "activation_soon", "inactive", "successful", "spam"]:
        raise HTTPException(status_code=400, detail="Invalid status")
    
    await crud.update_apartment_status(db, apartment_id, new_status)
    return {"message": "Status updated successfully"}


@app.put("/get_orders_and_photo_all/{apartment_id}/status")
async def update_apartment_status_all(
    apartment_id: int, 
    new_status: str = Query(...), 
    db: AsyncSession = Depends(get_db)
):
    if new_status not in ["new", "activation_soon", "inactive", "successful", "spam"]:
        raise HTTPException(status_code=400, detail="Invalid status")
    
    # Check if the apartment exists
    result = await db.execute(select(Apartment).filter(Apartment.id == apartment_id))
    apartment = result.scalar_one_or_none()

    if not apartment:
        raise HTTPException(status_code=404, detail="Apartment not found")
    
    # Update the apartment status
    apartment.ad_status = new_status
    await db.commit()  # Commit changes
    await db.refresh(apartment)  # Refresh the instance

    return {"message": f"Apartment {apartment_id} status updated to {new_status}"}



@app.put("/get_orders/{order_id}/status")
async def update_order_status(order_id: int, new_status: str, db: AsyncSession = Depends(get_db)):
    try:
        # Fetch the order by ID
        stmt = select(Order).where(Order.id == order_id)
        result = await db.execute(stmt)
        order = result.scalars().first()

        if not order:
            raise HTTPException(status_code=404, detail="Order not found")

        # Update the order status
        order.ed_status = new_status
        await db.commit()
        await db.refresh(order)

        logger.info(f"Order ID {order_id} status updated to {new_status}")
        return {"message": f"Order status updated to {new_status}"}

    except SQLAlchemyError as e:
        logger.error(f"Database error during status update: {e}")
        await db.rollback()
        raise HTTPException(status_code=500, detail="Database error. Please try again later.")
    except Exception as e:
        logger.error(f"Unexpected error during status update: {e}")
        raise HTTPException(status_code=500, detail="An unexpected error occurred.")
    
@app.put("/get_orders/{order_id}/status")
async def update_order_status(
    order_id: int, 
    new_status: str, 
    token: str = Depends(oauth2_scheme), 
    db: AsyncSession = Depends(get_db)
):
    try:
        user_id = decode_token(token)

        # Fetch the order and check ownership
        stmt = select(Order).join(Order.apartment).where(Order.id == order_id, Apartment.rieltor_id == int(user_id))
        result = await db.execute(stmt)
        order = result.scalars().first()

        if not order:
            raise HTTPException(status_code=403, detail="Not authorized to update this order")

        # Update the order status
        order.ed_status = new_status
        await db.commit()
        await db.refresh(order)

        logger.info(f"Order ID {order_id} status updated to {new_status} by user {user_id}")
        return {"message": f"Order status updated to {new_status}"}

    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token expired")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Invalid token")
    except SQLAlchemyError as e:
        logger.error(f"Database error during status update: {e}")
        raise HTTPException(status_code=500, detail="Database error. Please try again later.")




@app.get("/get_orders/", response_model=List[OrderResponse])
async def get_orders(
    realtor_id: int = Query(...),  # Pass realtor_id as a query parameter
    db: AsyncSession = Depends(get_db)
):
    try:
        # Fetch apartments owned by the realtor
        stmt_apartments = select(Apartment.id).where(Apartment.rieltor_id == realtor_id)
        result_apartments = await db.execute(stmt_apartments)
        apartment_ids = [row[0] for row in result_apartments.fetchall()]

        if not apartment_ids:
            return []  # Return an empty list if the realtor owns no apartments

        # Fetch orders associated with the realtor's apartments
        stmt_orders = select(Order).where(Order.apartment_id.in_(apartment_ids))
        result_orders = await db.execute(stmt_orders)
        orders = result_orders.scalars().all()

        return [OrderResponse.from_orm(order) for order in orders]

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error fetching orders: {str(e)}")
@app.post("/orders/")
async def create_order_endpoint(order: OrderCreate, db: AsyncSession = Depends(get_db)):
    logger.info(f"Received order request: {order}")
    try:
        created_order = await crud.create_order(
            db=db,
            apartment_id=order.apartment_id,
            name=order.name,
            phone=order.phone,
            telegram_username=order.telegram_username,  # ✅ NEW FIELD
            client_wishes=order.client_wishes,
            search_time=order.search_time,
            residents=order.residents,
            budget=order.budget,  # ✅ Handle budget
            district=order.district,  # ✅ Handle "Район"
            rooms=order.rooms,  # ✅ Handle "Кількість кімнат"
            area=order.area  # ✅ Handle "Площа (м²)"
        )
        if not created_order:
            raise HTTPException(status_code=500, detail="Order could not be created.")
        return {"message": "Order created successfully", "order_id": created_order.id}
    except Exception as e:
        logger.error(f"Error while creating order: {e}")
        raise HTTPException(status_code=500, detail="An unexpected error occurred.")

@app.get("/team_leader/orders/", response_model=List[OrderResponse])
async def get_unassigned_orders(
    team_leader_id: int = Query(...),  # Pass team_leader_id as a query parameter
    db: AsyncSession = Depends(get_db)
):
    try:
        # Query orders where apartment_id is NULL (unassigned)
        stmt = (
            select(Order)
            .options(joinedload(Order.apartment))
            .where(Order.apartment_id.is_(None))
        )
        result_orders = await db.execute(stmt)
        unassigned_orders = result_orders.scalars().all()

        return [OrderResponse.from_orm(order) for order in unassigned_orders]

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error fetching unassigned orders: {str(e)}")

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error fetching realtors: {str(e)}")
@app.get("/team_leaders/realtors", response_model=List[RieltorResponsee])
async def get_team_leader_realtors(
    team_leader_id: int = Query(...),
    db: AsyncSession = Depends(get_db)
):
    try:
        # Eagerly load relationships like apartments and their files
        stmt = (
            select(Rieltor)
            .options(
                joinedload(Rieltor.apartments).joinedload(Apartment.files)
            )
            .where(Rieltor.team_leader_id == team_leader_id)
        )
        
        result = await db.execute(stmt)
        realtors = result.unique().scalars().all()  # Use .unique() to handle joined eager loads
        
        return [RieltorResponsee.from_orm(realtor) for realtor in realtors]
    
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error fetching realtors: {str(e)}")
@app.put("/orders/{order_id}/assign")
async def assign_order_to_realtor(order_id: int, realtor_id: int, db: AsyncSession = Depends(get_db)):
    try:
        stmt = select(Order).where(Order.id == order_id)
        result = await db.execute(stmt)
        order = result.scalar_one_or_none()

        if not order:
            raise HTTPException(status_code=404, detail="Order not found")

        # Assign the order to the realtor
        order.apartment_id = realtor_id
        await db.commit()
        return {"message": "Order assigned successfully"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error assigning order: {str(e)}")

@app.put("/team_leader/orders/{order_id}/assign/")
async def assign_order_to_realtor(
    order_id: int,
    realtor_id: int = Query(...),  # Pass realtor_id as a query parameter
    db: AsyncSession = Depends(get_db)
):
    try:
        # Fetch the order by ID
        stmt_order = select(Order).where(Order.id == order_id)
        result_order = await db.execute(stmt_order)
        order = result_order.scalar_one_or_none()

        if not order:
            raise HTTPException(status_code=404, detail="Order not found")

        # Assign the order to the specified realtor
        order.apartment_id = realtor_id  # Use the realtor's apartment ID
        await db.commit()
        await db.refresh(order)

        return {"message": f"Order {order_id} assigned to Realtor {realtor_id}"}

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error assigning order: {str(e)}")
@app.get("/team_leader/{team_leader_id}/combined-stats", response_model=dict)
async def get_combined_team_leader_stats(
    team_leader_id: int, db: AsyncSession = Depends(get_db)
):
    try:
        # Fetch overall team statistics
        total_orders = await db.scalar(select(func.count(Order.id)))
        orders_per_day = await db.scalar(
            select(func.count(Order.id)).where(Order.created_at >= datetime.utcnow() - timedelta(days=1))
        )
        orders_per_week = await db.scalar(
            select(func.count(Order.id)).where(Order.created_at >= datetime.utcnow() - timedelta(weeks=1))
        )
        orders_per_month = await db.scalar(
            select(func.count(Order.id)).where(Order.created_at >= datetime.utcnow() - timedelta(days=30))
        )

        # Apartment statistics
        total_apartments = await db.scalar(select(func.count(Apartment.id)))
        apartments_with_orders = await db.scalar(
            select(func.count(Apartment.id)).where(Apartment.orders != None)
        )
        apartments_without_orders = total_apartments - apartments_with_orders

        # Fetch all realtors under the team leader
        stmt = select(Rieltor).where(Rieltor.team_leader_id == team_leader_id)
        result = await db.execute(stmt)
        realtors = result.scalars().all()

        realtor_stats = []

        for realtor in realtors:
            # Count processed apartments for the realtor
            total_apartments = await db.scalar(
                select(func.count(Apartment.id)).where(Apartment.rieltor_id == realtor.id)
            )

            # Count orders for the realtor
            total_orders = await db.scalar(
                select(func.count(Order.id)).where(Order.apartment.has(rieltor_id=realtor.id))
            )
            completed_orders = await db.scalar(
                select(func.count(Order.id)).where(
                    Order.apartment.has(rieltor_id=realtor.id), Order.ed_status == 'Completed'
                )
            )
            pending_orders = await db.scalar(
                select(func.count(Order.id)).where(
                    Order.apartment.has(rieltor_id=realtor.id), Order.ed_status == 'Pending'
                )
            )

            realtor_stats.append({
                "id": realtor.id,
                "name": realtor.name,
                "total_apartments": total_apartments,
                "total_orders": total_orders,
                "completed_orders": completed_orders,
                "pending_orders": pending_orders
            })

        # Return combined statistics
        return {
            "generalStats": {
                "total_orders": total_orders,
                "orders_per_day": orders_per_day,
                "orders_per_week": orders_per_week,
                "orders_per_month": orders_per_month,
                "total_apartments": total_apartments,
                "apartments_with_orders": apartments_with_orders,
                "apartments_without_orders": apartments_without_orders
            },
            "realtorStats": realtor_stats
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error fetching combined stats: {str(e)}")
@app.get("/get_orders_and_photo/", response_model=List[ApartmentResponse])
async def read_orders(request: Request, db: AsyncSession = Depends(get_db)):
    apartments = await crud.get_all_apartments_and_photo(db, request)
    return apartments

@app.get("/get_orders_and_photo_all/", response_model=List[ApartmentResponse])
async def read_orders(request: Request, db: AsyncSession = Depends(get_db)):
    apartments = await crud.get_all_apartments_and_photo_all(db, request)
    return apartments

@app.get("/get_apartment_and_photo/{apartment_id}", response_model=ApartmentResponse)
async def read_apartment(apartment_id: int, db: AsyncSession = Depends(get_db)):
    apartment = await crud.get_apartment_by_id(db, apartment_id)
    if not apartment:
        raise HTTPException(status_code=404, detail="Apartment not found")
    return apartment


from PIL import Image, ImageDraw, ImageFont

def add_watermark(input_image_path, output_image_path, watermark_text="Watermark"):
    image = Image.open(input_image_path).convert("RGBA")
    watermark = Image.new("RGBA", image.size, (255, 255, 255, 0))

    draw = ImageDraw.Draw(watermark)
    
    # Large font for better visibility
    try:
        font = ImageFont.truetype("arial.ttf", int(min(image.size) * 0.1))
    except IOError:
        font = ImageFont.load_default()
    
    # Center the watermark
    bbox = draw.textbbox((0, 0), watermark_text, font=font)
    text_width = bbox[2] - bbox[0]
    text_height = bbox[3] - bbox[1]

    position = ((image.size[0] - text_width) // 2, (image.size[1] - text_height) // 2)
    
    # Apply watermark with transparency
    draw.text(position, watermark_text, fill=(255, 255, 255, 180), font=font)

    # Combine the layers
    combined = Image.alpha_composite(image, watermark)
    combined = combined.convert("RGB")
    combined.save(output_image_path)

@app.put("/apartments/{apartment_id}/apply_watermark/{image_id}")
async def apply_watermark_to_existing_image(apartment_id: int, image_id: int, db: AsyncSession = Depends(get_db)):
    # Fetch the image from the database
    result = await db.execute(select(File_apartment).where(File_apartment.id == image_id))
    image_record = result.scalar_one_or_none()

    if not image_record:
        raise HTTPException(status_code=404, detail="Image not found")

    # Apply watermark using PIL
    try:
        input_path = image_record.file_path
        output_path = input_path.replace(".jpg", "_watermarked.jpg").replace(".png", "_watermarked.png")

        # Apply watermark function
        add_watermark(input_path, output_path)

        # Update the database with the new file path
        image_record.file_path = output_path
        await db.commit()
        await db.refresh(image_record)

        return {"message": "Watermark applied successfully!"}

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error applying watermark: {e}")



@app.post("/apartments/{apartment_id}/upload_images", response_model=List[FileApartmentResponse])
async def upload_images(apartment_id: int, files: List[UploadFile] = File(...), db: AsyncSession = Depends(get_db)):
    uploaded_images = []
    for idx, file in enumerate(files):
        file_path = f"{IMAGE_DIR}/apartment_{apartment_id}_{file.filename}"
        with open(file_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)
        
        # Add watermark before saving
        watermarked_path = f"{IMAGE_DIR}/apartment_{apartment_id}_watermarked_{file.filename}"
        add_watermark(file_path, watermarked_path)

        image_data = {
            "filename": file.filename,
            "date": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "content_type": file.content_type,
            "file_path": watermarked_path,
            "order": idx
        }
        db_image = await crud.add_image_to_apartment(db=db, apartment_id=apartment_id, image_data=image_data)
        uploaded_images.append(db_image)
    return uploaded_images
@app.delete("/images/{image_id}", status_code=204)
async def delete_image(image_id: int, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(File_apartment).where(File_apartment.id == image_id))
    db_image = result.scalars().first()
    
    if db_image:
        try:
            os.remove(db_image.file_path)  # Delete from file system
        except FileNotFoundError:
            pass
        
        await db.delete(db_image)  # Delete from database
        await db.commit()
        return {"message": "Image deleted successfully"}
    
    raise HTTPException(status_code=404, detail="Image not found")

@app.put("/apartments/{apartment_id}/reorder_images")
async def reorder_images(apartment_id: int, order_updates: List[ImageOrderUpdate], db: AsyncSession = Depends(get_db)):
    for update in order_updates:
        result = await db.execute(select(File_apartment).where(File_apartment.id == update.image_id))
        db_image = result.scalars().first()
        
        if db_image and db_image.apartment_id == apartment_id:
            db_image.order = update.new_order
            db.add(db_image)
    
    await db.commit()
    return {"message": "Image order updated successfully"}


# Background scraping task (runs on startup)
@app.on_event("startup")
async def startup_event():
    # Await the init_db() function to initialize the database
    await init_db()
    
    # Start scraping in the background
    asyncio.create_task(scraper.scrape_and_save(total_pages=3))  # Corrected to only pass total_pages
@asynccontextmanager
async def get_async_db():
    """This helper context manager correctly handles async generator for database session."""
    db = None
    try:
        db = get_db()
        db_session = await anext(db)
        yield db_session
    finally:
        await db.aclose() if db else None








@app.put("/apartments/{apartment_id}/update_fix_fields")
async def update_fix_fields(apartment_id: int, update_data: dict, db: AsyncSession = Depends(get_db)):
    updated_apartment = await crud.update_apartment_fix_fields(db, apartment_id, update_data)
    if not updated_apartment:
        raise HTTPException(status_code=404, detail="Apartment not found")
    return updated_apartment


from telegram import Bot
bot_token = os.getenv("bot_token")
channel_id =  "-1002484873200"
bot = Bot(token=bot_token)


async def get_template_text(db: AsyncSession, template_name: str = "telegram") -> str:
    result = await db.execute(select(Template).filter(Template.name == template_name))
    template = result.scalar_one_or_none()
    if not template:
        raise HTTPException(status_code=404, detail="Template not found")
    return template.template_text


@app.post("/get_orders_and_photo/publish_to_channel/{apartment_id}")
async def publish_to_channel(apartment_id: int, db: AsyncSession = Depends(get_db), template_name: str = "telegram"):
    # Fetch the apartment and ensure it exists
    result = await db.execute(
        select(Apartment)
        .filter(Apartment.id == apartment_id, Apartment.ad_status == "successful")
    )
    apartment = result.scalar_one_or_none()

    if not apartment:
        raise HTTPException(status_code=404, detail="Apartment not found or not successful")

    # Fetch and format the message template
    template_text = await get_template_text(db, template_name=template_name)
    try:
        # Use `_fix` fields if available, fallback to regular fields
        message = template_text.format(
            id=apartment.id,
            title=apartment.title_fix or apartment.title,
            location_date=apartment.location_date_fix or apartment.location_date,
            price=apartment.price_fix or apartment.price,
            room=apartment.room_fix or apartment.room,
            description=apartment.description,  # Assuming `_fix` is not needed here
            url=apartment.url_fix or apartment.url
        )

        # Publish the message to the Telegram channel
        await bot.send_message(chat_id=channel_id, text=message)
        return {"status": "success", "message": "Apartment published to Telegram channel"}

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Unexpected error: {e}")
@app.get("/templates")
async def get_templates(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Template))
    return result.scalars().all()

@app.post("/templates")
async def create_template(template_data: dict, db: AsyncSession = Depends(get_db)):
    new_template = Template(**template_data)
    db.add(new_template)
    await db.commit()
    await db.refresh(new_template)
    return new_template

@app.put("/templates/{template_id}")
async def update_template(template_id: int, template_data: dict, db: AsyncSession = Depends(get_db)):
    stmt = select(Template).where(Template.id == template_id)
    result = await db.execute(stmt)
    template = result.scalar_one_or_none()
    if not template:
        raise HTTPException(status_code=404, detail="Template not found")
    for key, value in template_data.items():
        setattr(template, key, value)
    await db.commit()
    await db.refresh(template)
    return template

@app.delete("/templates/{template_id}")
async def delete_template(template_id: int, db: AsyncSession = Depends(get_db)):
    stmt = select(Template).where(Template.id == template_id)
    result = await db.execute(stmt)
    template = result.scalar_one_or_none()
    if not template:
        raise HTTPException(status_code=404, detail="Template not found")
    await db.delete(template)
    await db.commit()
    return {"detail": "Template deleted successfully"}



@app.get("/templates/{template_name}")
async def get_template(template_name: str, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Template).where(Template.name == template_name))
    template = result.scalar_one_or_none()
    if not template:
        raise HTTPException(status_code=404, detail="Template not found")
    return {
        "id": template.id,
        "name": template.name,
        "template_text": template.template_text,
        "type": template.type
    }




@app.get("/search_apartments/")
async def search_apartments(
    db: AsyncSession = Depends(get_db),
    keyword: Optional[str] = None,
    price_from: Optional[int] = None,
    price_to: Optional[int] = None,
    rooms: Optional[List[int]] = Query(None),
):
    query = select(Apartment)

    # Apply filters
    if keyword:
        query = query.filter(Apartment.title.ilike(f"%{keyword}%"))
    if price_from is not None:
        query = query.filter(Apartment.price >= price_from)
    if price_to is not None:
        query = query.filter(Apartment.price <= price_to)
    if rooms:
        if 5 in rooms:
            query = query.filter(Apartment.room >= 5)  # For "Vishe"
        else:
            query = query.filter(Apartment.room.in_(rooms))

    result = await db.execute(query)
    apartments = result.scalars().all()
    return apartments



@app.post("/login")
async def login(
    form_data: OAuth2PasswordRequestForm = Depends(),
    db: AsyncSession = Depends(get_db)
):
    # Check in Rieltor table
    stmt_rieltor = select(Rieltor).where(Rieltor.username == form_data.username)
    result_rieltor = await db.execute(stmt_rieltor)
    rieltor = result_rieltor.scalar_one_or_none()

    if rieltor and verify_password(form_data.password, rieltor.password):
        access_token = create_access_token(data={"id": rieltor.id, "type": "realtor"})
        return {
            "access_token": access_token,
            "token_type": "bearer",
            "id": rieltor.id,
            "type": "realtor",
        }

    # Check in TeamLeed table
    stmt_team_lead = select(TeamLeed).where(TeamLeed.username == form_data.username)
    result_team_lead = await db.execute(stmt_team_lead)
    team_lead = result_team_lead.scalar_one_or_none()

    if team_lead and verify_password(form_data.password, team_lead.password):
        access_token = create_access_token(data={"id": team_lead.id, "type": "team_leader"})
        return {
            "access_token": access_token,
            "token_type": "bearer",
            "id": team_lead.id,
            "type": "team_leader",
        }

    raise HTTPException(status_code=401, detail="Invalid username or password")


@app.post("/users/", response_model=RieltorSchema)
async def create_user(user: RieltorCreate, db: AsyncSession = Depends(get_db)):
    existing_user = await crud.get_rieltor_by_username(db, username=user.username)  # Await the async function
    if existing_user:
        raise HTTPException(status_code=400, detail="Username already registered")

    new_user = await crud.create_rieltor(db=db, rieltor=user)
    return new_user






@app.post("/assign_apartment/{apartment_id}")
async def assign_apartment(apartment_id: int, db: AsyncSession = Depends(get_db)):
    apartment = await crud.assign_apartment_to_agent(db, apartment_id)
    return {"status": "success", "message": f"Apartment assigned to Rieltor {apartment.rieltor_id}"}

@app.put("/apartments/{apartment_id}/follow_up")
async def follow_up(apartment_id: int, db: AsyncSession = Depends(get_db)):
    updated_apartment = await crud.update_contact_dates(db, apartment_id)
    return {"status": "success", "message": "Contact dates updated", "apartment": updated_apartment}


@app.put("/apartments/{apartment_id}/set_lease")
async def set_lease(apartment_id: int, lease_months: int, db: AsyncSession = Depends(get_db)):
    apartment = await crud.update_lease_end_date(db, apartment_id, lease_months)
    return {"status": "success", "message": "Lease end date updated", "apartment": apartment}

from sqlalchemy.orm import joinedload, selectinload

@app.get("/agents/{agent_id}/apartments/")
async def get_agent_apartments(
    agent_id: int,
    apartment_id: Optional[int] = Query(None),
    db: AsyncSession = Depends(get_db)
):
    """
    Fetch apartments associated with a given agent ID.
    If apartment_id is provided, fetch only that specific apartment.
    """
    stmt = select(Apartment).where(Apartment.rieltor_id == agent_id)

    if apartment_id is not None:
        stmt = stmt.where(Apartment.id == apartment_id)  # Filter by apartment ID

    stmt = stmt.options(joinedload(Apartment.files))  # Eagerly load related files
    result = await db.execute(stmt)
    apartments = result.unique().scalars().all()

    if apartment_id and not apartments:
        raise HTTPException(status_code=404, detail=f"Apartment with ID {apartment_id} not found")

    return apartments



@app.get("/agents/{agent_id}/notifications/")
async def get_agent_notifications(agent_id: int, db: AsyncSession = Depends(get_db)):
    today = datetime.now()
    one_week_later = today + timedelta(days=7)

    stmt = select(Apartment).where(
        (Apartment.rieltor_id == agent_id) &
        ((Apartment.next_contact_date <= today) | (Apartment.lease_end_date <= one_week_later))
    )
    result = await db.execute(stmt)
    apartments = result.scalars().all()

    notifications = []
    for apt in apartments:
        if apt.next_contact_date and apt.next_contact_date <= today:
            notifications.append(f"Follow-up reminder for Apartment ID {apt.id}")
        if apt.lease_end_date and apt.lease_end_date <= one_week_later:
            notifications.append(f"Lease ending soon for Apartment ID {apt.id}")
    return {"notifications": notifications}


@app.put("/apartments/{apartment_id}/contacted")
async def mark_apartment_contacted(apartment_id: int, db: AsyncSession = Depends(get_db)):
    stmt = select(Apartment).where(Apartment.id == apartment_id)
    result = await db.execute(stmt)
    apartment = result.scalar_one_or_none()

    if not apartment:
        raise HTTPException(status_code=404, detail="Apartment not found")

    apartment.last_contact_date = datetime.now()
    apartment.next_contact_date = datetime.now() + timedelta(days=14)  # Set next follow-up in 2 weeks
    await db.commit()
    return {"message": "Apartment marked as contacted"}

@app.put("/apartments/{apartment_id}/archive")
async def archive_apartment(apartment_id: int, db: AsyncSession = Depends(get_db)):
    stmt = select(Apartment).where(Apartment.id == apartment_id)
    result = await db.execute(stmt)
    apartment = result.scalar_one_or_none()

    if not apartment:
        raise HTTPException(status_code=404, detail="Apartment not found")

    apartment.ad_status = "archived"
    await db.commit()
    return {"message": "Apartment archived successfully"}


@app.get("/agents/me/apartments/")
async def get_my_apartments(token: str = Depends(oauth2_scheme), db: AsyncSession = Depends(get_db)):
    try:
        agent_id = int(decode_token(token))
    except HTTPException as e:
        raise HTTPException(status_code=401, detail=f"Token validation failed: {str(e)}")

    stmt = select(Apartment).where(Apartment.rieltor_id == agent_id)
    result = await db.execute(stmt)
    apartments = result.scalars().all()
    return apartments

@app.post("/assign_apartments/auto")
def auto_assign_apartments_endpoint():
    """
    Endpoint to trigger the auto-assign Celery task.
    """
    from celery_task import auto_assign_apartments
    auto_assign_apartments.delay()
    return {"message": "Auto-assignment task triggered"}


@app.get("/realtors/", response_model=list[RieltorResponse])
async def read_realtors(db: AsyncSession = Depends(get_db)):
    realtors = await crud.get_all_realtors(db)
    return realtors



from fastapi import Query

@app.post("/assign_team_leader/")
async def assign_team_leader(
    request: AssignTeamLeaderRequest,
    db: AsyncSession = Depends(get_db)
):
    try:
        realtor = await crud.assign_team_leader(db, request.realtor_id, request.team_leader_id)
        return {"message": f"Realtor {request.realtor_id} assigned to Team Leader {request.team_leader_id}"}
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@app.get("/team_leaders/", response_model=List[RieltorResponse])
async def get_team_leaders(db: AsyncSession = Depends(get_db)):
    team_leaders = await crud.get_team_leaders(db)
    return [RieltorResponse.from_orm(tl) for tl in team_leaders]


@app.get("/team_leader/{team_leader_id}/realtors")
async def get_team_leader_realtors(
    team_leader_id: int,
    db: AsyncSession = Depends(get_db)
):
    try:
        stmt = select(Rieltor).where(Rieltor.team_leader_id == team_leader_id)
        result = await db.execute(stmt)
        realtors = result.scalars().all()
        return {"team_leader_id": team_leader_id, "realtors": realtors}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error fetching realtors: {e}")




@app.post("/team_leaders/", response_model=RieltorSchema)
async def create_team_leader(team_leader: RieltorCreate, db: AsyncSession = Depends(get_db)):
    try:
        # Ensure the team leader type is "team_leader"
        team_leader_data = team_leader.dict()
        team_leader_data["type"] = "team_leader"

        # Use the CRUD function to create the team leader
        new_team_leader = await crud.create_rieltor(db=db, rieltor=RieltorCreate(**team_leader_data))
        return new_team_leader

    except IntegrityError:
        await db.rollback()
        raise HTTPException(status_code=400, detail="Username already exists")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Unexpected error: {str(e)}")
    


@app.post("/team_leader/create")
async def create_team_leader(
    username: str,
    password: str,
    name: Optional[str] = None,
    db: AsyncSession = Depends(get_db)
):
    try:
        new_team_leader = await crud.create_team_leader(db, username, password, name)
        return {"message": "Team Leader created successfully", "id": new_team_leader.id}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))



@app.get("/team_leader/{team_leader_id}/realtors-stats")
async def get_team_leader_realtor_stats(team_leader_id: int, db: AsyncSession = Depends(get_db)):
    try:
        # Ensure the team leader exists
        team_leader_stmt = select(TeamLeed).where(TeamLeed.id == team_leader_id)
        team_leader_result = await db.execute(team_leader_stmt)
        team_leader = team_leader_result.scalar_one_or_none()
        if not team_leader:
            raise HTTPException(status_code=404, detail="Team Leader not found")

        # Fetch all realtors under the team leader
        realtor_stmt = (
            select(Rieltor)
            .where(Rieltor.team_leader_id == team_leader_id)
            .options(selectinload(Rieltor.apartments))
        )
        realtor_result = await db.execute(realtor_stmt)
        realtors = realtor_result.scalars().all()

        if not realtors:
            logger.info(f"No realtors found for Team Leader ID {team_leader_id}")
            return {"teamStats": {}, "realtorStats": []}

        teamStats = {"last7Days": 0, "previous3Weeks": 0, "last12Months": 0}
        realtorStats = []

        for realtor in realtors:
            stats = {
                "name": realtor.name or realtor.username,
                "last7Days": 0,
                "previous3Weeks": 0,
                "last12Months": 0,
                "apartments": len(realtor.apartments)  # Count apartments assigned to the realtor
            }

            for apartment in realtor.apartments:
                location_date = apartment.last_contact_date
                if location_date:
                    try:
                        # Handle location_date based on type
                        if isinstance(location_date, datetime):
                            pass  # Already a datetime object, no conversion needed
                        elif isinstance(location_date, int):  # Assuming Unix timestamp
                            location_date = datetime.fromtimestamp(location_date)
                        elif isinstance(location_date, str):  # ISO format string
                            location_date = datetime.fromisoformat(location_date)
                        else:
                            raise ValueError(f"Unsupported location_date type: {type(location_date)}")

                        days_diff = (datetime.now() - location_date).days

                        if days_diff <= 7:
                            stats["last7Days"] += 1
                            teamStats["last7Days"] += 1
                        elif 7 < days_diff <= 21:
                            stats["previous3Weeks"] += 1
                            teamStats["previous3Weeks"] += 1
                        elif days_diff <= 365:
                            stats["last12Months"] += 1
                            teamStats["last12Months"] += 1

                    except ValueError as ve:
                        logger.warning(f"Invalid location_date for Apartment ID {apartment.id}: {location_date}. Error: {ve}")
                        continue

            realtorStats.append(stats)

        # Team-wide summary
        team_summary = {
            "totalRealtors": len(realtors),
            "totalApartments": sum([len(realtor.apartments) for realtor in realtors]),
            **teamStats,
        }

        return {"teamStats": team_summary, "realtorStats": realtorStats}

    except Exception as e:
        logger.error(f"Error fetching realtor stats: {e}")
        raise HTTPException(status_code=500, detail=f"Error fetching realtor stats: {e}")

@app.get("/order_statistics/")
async def get_order_statistics(realtor_id: int, db: AsyncSession = Depends(get_db)):
    try:
        # Fetch order statistics for a specific realtor
        stmt = (
            select(Order)
            .join(Apartment)
            .where(Apartment.rieltor_id == realtor_id)
        )
        result = await db.execute(stmt)
        orders = result.scalars().all()

        # Process statistics (last 7 days, last 3 weeks, last 12 months)
        daily_stats, weekly_stats, monthly_stats = {}, {}, {}

        for order in orders:
            days_difference = (datetime.utcnow() - order.created_at).days
            if days_difference <= 7:
                daily_stats[order.created_at.strftime('%Y-%m-%d')] = daily_stats.get(order.created_at.strftime('%Y-%m-%d'), 0) + 1
            elif days_difference < 21:
                week_label = f"Week {days_difference // 7}"
                weekly_stats[week_label] = weekly_stats.get(week_label, 0) + 1
            elif days_difference < 365:
                month_label = order.created_at.strftime('%Y-%m')
                monthly_stats[month_label] = monthly_stats.get(month_label, 0) + 1
        return {
            "daily": daily_stats,
            "weekly": weekly_stats,
            "monthly": monthly_stats
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error fetching statistics: {str(e)}")
    

# ✅ Fetch all channels
@app.get("/telegram_channels")
async def get_channels(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(TelegramChannel))
    return result.scalars().all()


@app.post("/telegram_channels")
async def add_channel(channel_data: dict, db: AsyncSession = Depends(get_db)):
    try:
        # Extract fields and cast them to correct types
        price_from = int(channel_data.get("price_from")) if channel_data.get("price_from") else None
        price_to = int(channel_data.get("price_to")) if channel_data.get("price_to") else None

        new_channel = TelegramChannel(
            category=channel_data["category"],
            type_deal=channel_data["type_deal"],
            channel_id=channel_data["channel_id"],
            type_object=channel_data.get("type_object", ""),
            price_from=price_from,
            price_to=price_to,
            location_type=channel_data.get("location_type", "all"),
        )

        db.add(new_channel)
        await db.commit()
        return {"message": "Channel added successfully"}
    except IntegrityError:
        await db.rollback()
        return {"error": "A channel with this category already exists."}
    except ValueError as e:
        return {"error": f"Invalid input: {e}"}

# ✅ Delete a channel
@app.delete("/telegram_channels/{channel_id}")
async def delete_channel(channel_id: int, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(TelegramChannel).filter(TelegramChannel.id == channel_id))
    channel = result.scalar_one_or_none()
    if channel:
        await db.delete(channel)
        await db.commit()
        return {"message": "Channel deleted successfully"}
    return {"error": "Channel not found"}


@app.put("/apartments/{apartment_id}/status")
async def update_apartment_status(apartment_id: int, new_status: str, db: AsyncSession = Depends(get_db)):
    # ✅ Auto-send based on the new status
    return await crud.send_ad_to_telegram(db, apartment_id)


from apscheduler.schedulers.asyncio import AsyncIOScheduler

# ✅ Initialize APScheduler globally
scheduler = AsyncIOScheduler()

# ✅ Fetch all Telegram channels
@app.get("/telegram_channels")
async def get_channels(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(TelegramChannel))
    return result.scalars().all()


@app.post("/telegram_channels")
async def add_channel(channel_data: dict, db: AsyncSession = Depends(get_db)):
    existing_channel = await db.execute(
        select(TelegramChannel).filter(TelegramChannel.category == channel_data["category"])
    )
    if existing_channel.scalar_one_or_none():
        return {"error": "Channel with this category already exists."}
    
    try:
        new_channel = TelegramChannel(**channel_data)
        db.add(new_channel)
        await db.commit()
        return {"message": "Channel added successfully"}
    except Exception as e:
        await db.rollback()
        return {"error": f"Error adding channel: {str(e)}"}

@app.delete("/telegram_channels/{channel_id}")
async def delete_channel(channel_id: int, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(TelegramChannel).filter(TelegramChannel.id == channel_id))
    channel = result.scalar_one_or_none()
    if channel:
        await db.delete(channel)
        await db.commit()
        return {"message": "Channel deleted successfully"}
    return {"error": "Channel not found"}

@app.put("/apartments/{apartment_id}/status")
async def update_apartment_status(apartment_id: int, new_status: str, db: AsyncSession = Depends(get_db)):
    return await crud.send_ad_to_telegram(db, apartment_id)

async def automated_telegram_posting():
    """
    Process and send apartments in a structured order:
    1. Send "sent to telegram channel" (ad_status: None)
    2. Then send "successful" (ad_status: "successful")
    """
    global TELEGRAM_POSTING_RUNNING

    async with get_dbb() as db:
        try:
            while TELEGRAM_POSTING_RUNNING:
                apartments_by_channel = await crud.get_pending_apartments(db)
                if not apartments_by_channel:
                    logging.info("✅ No pending apartments to process.")
                    return

                for channel, apartments in apartments_by_channel:
                    if channel.category == "sent to telegram channel":
                        logging.info("📤 Sending announcements with ad_status: None...")
                    elif channel.category == "successful":
                        logging.info("🏆 Sending successful rollouts...")

                    for apartment in apartments:
                        if not TELEGRAM_POSTING_RUNNING:
                            logging.info("🚫 Auto-posting stopped.")
                            return

                        try:
                            await crud.send_ad_to_telegram(db, apartment.id)
                            logging.info(f"✅ Posted apartment {apartment.id}. Waiting 1 minute...")
                            await asyncio.sleep(60)  # 1-minute interval
                        except Exception as e:
                            logging.error(f"❌ Error processing apartment {apartment.id}: {e}")

        except Exception as e:
            logging.error(f"❌ Error during auto-posting: {e}")

@app.on_event("startup")
async def start_scheduler():
    """
    Start the APScheduler when the application starts.
    """
    global TELEGRAM_POSTING_RUNNING

    if not scheduler.running:
        scheduler.add_job(
            automated_telegram_posting,
            "interval",
            minutes=1,
            id="auto_posting_job",
            replace_existing=True,
            coalesce=True,
        )
        scheduler.start()
        TELEGRAM_POSTING_RUNNING = True  # Set the flag when scheduler starts
        logging.info("✅ Auto-posting scheduler started.")

@app.get("/start_autoposting/")
async def start_autoposting():
    """Start automated Telegram posting via API"""
    global TELEGRAM_POSTING_RUNNING

    if TELEGRAM_POSTING_RUNNING:
        return {"message": "Auto-posting is already running"}

    TELEGRAM_POSTING_RUNNING = True
    scheduler.resume_job("auto_posting_job")  # Resume the job if paused
    return {"message": "Auto-posting started"}

@app.get("/stop_autoposting/")
async def stop_autoposting():
    """Stop automated Telegram posting via API"""
    global TELEGRAM_POSTING_RUNNING

    if not TELEGRAM_POSTING_RUNNING:
        return {"message": "Auto-posting is not running"}

    TELEGRAM_POSTING_RUNNING = False
    scheduler.pause_job("auto_posting_job")  # Pause the job instead of stopping it
    return {"message": "Auto-posting stopped"}
@app.get("/realtor/me", response_model=RieltorResponse)
async def get_realtor_info(token: str = Depends(oauth2_scheme), db: AsyncSession = Depends(get_db)):
    """
    Fetch the currently logged-in realtor's information.
    """
    try:
        realtor_id = decode_token(token)  # Extract the realtor's ID from the JWT token
        stmt = select(Rieltor).where(Rieltor.id == realtor_id)
        result = await db.execute(stmt)
        realtor = result.scalar_one_or_none()

        if not realtor:
            raise HTTPException(status_code=404, detail="Realtor not found")

        return RieltorResponse.from_orm(realtor)

    except Exception as e:
        raise HTTPException(status_code=401, detail=f"Unauthorized: {str(e)}")
    
class WordModel(BaseModel):
    word: str  
@app.post("/admin/add_trap/")
async def add_trap_word(data: WordModel, db: AsyncSession = Depends(get_db)):
    new_trap = TrapBlacklist(keyword=data.word.lower())
    db.add(new_trap)
    await db.commit()
    return {"message": f"Added '{data.word}' to blacklist"}
@app.post("/admin/add_stop_word/")
async def add_stop_word(data: WordModel, db: AsyncSession = Depends(get_db)):
    new_word = StopWord(word=data.word.lower())
    db.add(new_word)
    await db.commit()
    return {"message": f"Added '{data.word}' to stop words"}

@app.delete("/admin/remove_trap/{word}")
async def remove_trap_word(word: str, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(TrapBlacklist).where(TrapBlacklist.keyword == word.lower()))
    trap = result.scalar_one_or_none()

    if trap:
        await db.delete(trap)
        await db.commit()
        return {"message": f"Removed '{word}' from blacklist"}
    
    raise HTTPException(status_code=404, detail="Word not found")
@app.delete("/admin/remove_trap/{word}")
async def remove_trap_word(word: str, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(TrapBlacklist).where(TrapBlacklist.keyword == word.lower()))
    trap = result.scalar_one_or_none()

    if trap:
        await db.delete(trap)
        await db.commit()
        return {"message": f"Removed '{word}' from blacklist"}
    
    raise HTTPException(status_code=404, detail="Word not found")
@app.delete("/admin/remove_stop_word/{word}")
async def remove_stop_word(word: str, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(StopWord).where(StopWord.word == word.lower()))
    stop_word = result.scalar_one_or_none()

    if stop_word:
        await db.delete(stop_word)
        await db.commit()
        return {"message": f"Removed '{word}' from stop words"}
    
    raise HTTPException(status_code=404, detail="Word not found")

@app.get("/admin/verification_ads/")
async def get_verification_ads(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Apartment).where(Apartment.requires_verification == True))
    apartments = result.scalars().all()
    return apartments
@app.put("/admin/verify_ad/{apartment_id}")
async def verify_ad(apartment_id: int, decision: str, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Apartment).where(Apartment.id == apartment_id))
    apartment = result.scalar_one_or_none()

    if not apartment:
        raise HTTPException(status_code=404, detail="Apartment not found")

    if decision == "spam":
        apartment.ad_status = "spam"
    elif decision == "relevant":
        apartment.ad_status = "active"
        apartment.requires_verification = False
    else:
        raise HTTPException(status_code=400, detail="Invalid decision")

    await db.commit()
    return {"message": f"Apartment {apartment_id} marked as {decision}"}
@app.get("/start_scraping/")
async def start_scraping(background_tasks: BackgroundTasks):
    """Start the scraper in the background."""
    global scraper

    if scraper.SCRAPER_RUNNING:
        return {"message": "Scraper is already running"}

    scraper.SCRAPER_RUNNING = True
    background_tasks.add_task(scraper.scrape_and_save, 1)  # Run scraper for 10 pages
    return {"message": "Scraping started"}

@app.get("/stop_scraping/")
async def stop_scraping():
    """Stop the scraper dynamically."""
    global scraper

    if not scraper.SCRAPER_RUNNING:
        return {"message": "Scraper is not running"}

    scraper.SCRAPER_RUNNING = False  # Set flag to stop scraper
    scraper.BASE_URLS.clear()  # Clear BASE_URLS to ensure the scraper stops immediately
    return {"message": "Scraping stopped"}

# Ensure correct WSGI configuration
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)