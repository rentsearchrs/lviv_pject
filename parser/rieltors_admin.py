from celery import Celery
import jwt
import requests
from sqlalchemy import select
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update, Bot
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    ContextTypes,
    CallbackQueryHandler,
    MessageHandler,
    filters,
)
import os
from dotenv import load_dotenv
from parser.crud import get_apartments_by_realtor, update_apartment_fix_fields, create_or_update_apartment
from parser.models import Order, SubscribedChat, TeamLeed
from parser.database import SessionLocal, get_db
import shutil
from datetime import datetime
import asyncio

load_dotenv()
API_URL = "http://localhost:8000"  # Base URL of your FastAPI server
BOT_TOKEN = os.getenv("bot_token_admin_panel")
WEB_APP_URL = 'https://xhouse.xcorp.com.ua/'

# Global dictionary to store user tokens by Telegram user ID.
user_tokens = {}

# Initialize Celery
app = Celery("tasks", broker='sqla+postgresql://avnadmin:AVNS_WuKZ_IhjhElCEeNK1j6@pg-30cc2364-mark-23c7.l.aivencloud.com:21288/defaultdb')

# ---------------------------------------------------------------------------
# HELPER: Authorized HTTP request
# ---------------------------------------------------------------------------
def make_authorized_request(endpoint: str, method: str, token: str, **kwargs):
    headers = {"Authorization": f"Bearer {token}"}
    url = f"{API_URL}{endpoint}"
    if method.lower() == "get":
        return requests.get(url, headers=headers, **kwargs)
    elif method.lower() == "put":
        return requests.put(url, headers=headers, **kwargs)
    elif method.lower() == "post":
        return requests.post(url, headers=headers, **kwargs)

# ---------------------------------------------------------------------------
# NEW COMMAND HANDLER: Add Property
# ---------------------------------------------------------------------------
async def add_property_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Add a property using a message with details.
    Expected format (each field on a separate line after the command):
    
    📍 Address: 123 Main St, City
    🏠 Type: Apartment
    🔢 Rooms: 3
    📐 Area: 120
    🏗 Floor: 2
    🎨 Condition: Good
    🏡 Features: Balcony, Parking
    💰 Price: 150000
    📜 Ownership: Private
    🏷 Tags: modern, renovated

    (Photos will be added separately.)
    """
    token = user_tokens.get(update.effective_user.id)
    if not token:
        await update.message.reply_text("You need to log in first. Use /login.")
        return

    # Remove the command and get the rest of the message
    text_lines = update.message.text.splitlines()[1:]
    if not text_lines:
        await update.message.reply_text(
            "Please provide property details in the correct format:\n\n"
            "Example:\n"
            "📍 Address: 123 Main St, City\n"
            "🏠 Type: Apartment\n"
            "🔢 Rooms: 3\n"
            "📐 Area: 120\n"
            "🏗 Floor: 2\n"
            "🎨 Condition: Good\n"
            "🏡 Features: Balcony, Parking\n"
            "💰 Price: 150000\n"
            "📜 Ownership: Private\n"
            "🏷 Tags: modern, renovated"
        )
        return

    # Parse details from the message.
    property_data = {}
    for line in text_lines:
        if ":" in line:
            key, value = line.split(":", 1)
            key = key.strip()
            value = value.strip()
            if key.startswith("📍 Address"):
                property_data["location_date"] = value  # using location_date for address (change if needed)
            elif key.startswith("🏠 Type"):
                property_data["type_object"] = value
            elif key.startswith("🔢 Rooms"):
                property_data["room"] = value
            elif key.startswith("📐 Area"):
                property_data["square"] = value
            elif key.startswith("🏗 Floor"):
                property_data["floor"] = value
            elif key.startswith("🎨 Condition"):
                property_data["description"] = value
            elif key.startswith("🏡 Features"):
                property_data["features"] = value
            elif key.startswith("💰 Price"):
                property_data["price"] = value
            elif key.startswith("📜 Ownership"):
                property_data["owner"] = value
            elif key.startswith("🏷 Tags"):
                property_data["comment"] = value

    # Set default values
    property_data.setdefault("ad_status", "active")
    property_data.setdefault("type_deal", "sale")
    if "location_date" in property_data:
        property_data.setdefault("title", property_data["location_date"])

    # Decode the token to get the realtor's id and assign it.
    try:
        decoded_token = jwt.decode(token, options={"verify_signature": False})
        property_data["rieltor_id"] = decoded_token.get("id")
    except Exception as e:
        await update.message.reply_text(f"Error decoding token: {e}")
        return

    # Create or update the apartment via your CRUD function.
    async with SessionLocal() as db:
        new_apartment = await create_or_update_apartment(db, property_data)
        if new_apartment:
            await update.message.reply_text(f"Property added successfully with ID {new_apartment.id}.")
        else:
            await update.message.reply_text("Failed to add property. Please try again later.")

# ---------------------------------------------------------------------------
# CALLBACK HANDLERS (for inline menus)
# ---------------------------------------------------------------------------
async def handle_prop_list(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle the 'View list' option from My properties."""
    query = update.callback_query
    await query.answer()

    token = user_tokens.get(update.effective_user.id)
    if not token:
        await query.edit_message_text("You need to log in first. Use /login.")
        return

    try:
        decoded_token = jwt.decode(token, options={"verify_signature": False})
        realtor_id = decoded_token.get("id")
        if not realtor_id:
            await query.edit_message_text("Invalid token. Please log in again.")
            return

        async with SessionLocal() as db:
            apartments = await get_apartments_by_realtor(db, realtor_id)
            if not apartments:
                text = "No properties found for your account."
            else:
                text = "Your Apartments:\n" + "\n".join(
                    [f"ID: {apt.id}, Title: {apt.title}, Price: {apt.price}" for apt in apartments]
                )
        await query.edit_message_text(text)
    except Exception as e:
        await query.edit_message_text(f"Error retrieving properties: {str(e)}")

async def menu(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Display the main menu for the Realtor."""
    keyboard = [
        [InlineKeyboardButton("🏡 Properties", callback_data="menu_properties")],
        [InlineKeyboardButton("📞 Callback", callback_data="menu_callback")],
        [InlineKeyboardButton("💬 Applications", callback_data="menu_applications")],
        [InlineKeyboardButton("📊 Statistics", callback_data="menu_statistics")],
        [InlineKeyboardButton("📅 Reviews and Deals", callback_data="menu_reviews_deals")],
        [InlineKeyboardButton("👥 My Clients", callback_data="menu_my_clients")],
        [InlineKeyboardButton("📂 Documents", callback_data="menu_documents")],
        [InlineKeyboardButton("🔧 Settings", callback_data="menu_settings")],
        [InlineKeyboardButton("⏰ Schedule", callback_data="menu_schedule")],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    if update.message:
        await update.message.reply_text("📌 MAIN MENU Realtor", reply_markup=reply_markup)
    elif update.callback_query:
        await update.callback_query.edit_message_text("📌 MAIN MENU Realtor", reply_markup=reply_markup)

async def menu_callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle button presses from the main menu."""
    query = update.callback_query
    await query.answer()
    data = query.data

    if data == "menu_properties":
        keyboard = [
            [InlineKeyboardButton("➕ Add property", callback_data="prop_add")],
            [InlineKeyboardButton("📂 My properties", callback_data="prop_my_properties")],
            [InlineKeyboardButton("📌 Property status", callback_data="prop_status_menu")],
            [InlineKeyboardButton("⬅️ Back to main menu", callback_data="back_main")],
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text("🏡 PROPERTIES", reply_markup=reply_markup)

    elif data == "prop_my_properties":
        keyboard = [
            [InlineKeyboardButton("📜 View list", callback_data="prop_list")],
            [InlineKeyboardButton("✏️ Edit", callback_data="prop_edit")],
            [InlineKeyboardButton("📸 Add photo", callback_data="prop_add_photo")],
            [InlineKeyboardButton("📌 Status", callback_data="prop_status")],
            [InlineKeyboardButton("⬅️ Back", callback_data="menu_properties")],
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text("📂 My properties (options):\n📜 View list | ✏️ Edit | 📸 Add photo | 📌 Status", reply_markup=reply_markup)

    elif data == "prop_list":
        await handle_prop_list(update, context)

    elif data == "prop_edit":
        await query.edit_message_text(
            "To update fix fields, please use the command:\n"
            "/update_fix_fields <apartment_id> <field>=<new_value>\n"
            "Example: /update_fix_fields 123 title_fix=New Title"
        )

    elif data == "prop_add_photo":
        await query.edit_message_text(
            "To add a photo, please send a photo with the caption as the apartment ID.\n"
            "For example, if the apartment ID is 123, set the caption to '123'."
        )

    elif data == "prop_status":
        status_keyboard = [
            [InlineKeyboardButton("🟢 Active", callback_data="status_active")],
            [InlineKeyboardButton("🔴 Inactive", callback_data="status_inactive")],
            [InlineKeyboardButton("⏳ Pending", callback_data="status_pending")],
            [InlineKeyboardButton("🚨 Spam/Delete", callback_data="status_spam")],
            [InlineKeyboardButton("⬅️ Back", callback_data="prop_my_properties")],
        ]
        reply_markup = InlineKeyboardMarkup(status_keyboard)
        await query.edit_message_text("Select new status for the property:", reply_markup=reply_markup)

    elif data.startswith("status_"):
        selected = data.split("_", 1)[1]
        status_mapping = {
            "active": "successful",
            "inactive": "inactive",
            "pending": "pending",
            "spam": "spam"
        }
        target_status = status_mapping.get(selected)
        if not target_status:
            await query.edit_message_text("Unknown status selected.")
            return

        token = user_tokens.get(update.effective_user.id)
        if not token:
            await query.edit_message_text("Please log in first using /login.")
            return

        try:
            decoded_token = jwt.decode(token, options={"verify_signature": False})
            realtor_id = decoded_token.get("id")
            if not realtor_id:
                await query.edit_message_text("Invalid token. Please log in again.")
                return

            from models import Apartment
            async with SessionLocal() as db:
                stmt = select(Apartment).where(
                    Apartment.rieltor_id == realtor_id,
                    Apartment.ad_status == target_status
                )
                result = await db.execute(stmt)
                apartments = result.scalars().all()
                if not apartments:
                    message = f"No apartments found with status '{target_status}'."
                else:
                    message = f"Your Apartments with status '{target_status}':\n" + "\n".join(
                        [f"ID: {apt.id}, Title: {apt.title}, Price: {apt.price}" for apt in apartments]
                    )
            await query.edit_message_text(message)
        except Exception as e:
            await query.edit_message_text(f"Error fetching apartments: {str(e)}")
    elif data == "prop_add":
        # Here we simply instruct the user to use the /add_property command.
        instructions = (
            "To add a property, please use the /add_property command with the following format:\n\n"
            "/add_property\n"
            "📍 Address: 123 Main St, City\n"
            "🏠 Type: Apartment\n"
            "🔢 Rooms: 3\n"
            "📐 Area: 120\n"
            "🏗 Floor: 2\n"
            "🎨 Condition: Good\n"
            "🏡 Features: Balcony, Parking\n"
            "💰 Price: 150000\n"
            "📜 Ownership: Private\n"
            "🏷 Tags: modern, renovated\n\n"
            "Photos can be added separately."
        )
        await query.edit_message_text(instructions)
    # ... (Other branches for menu_callback_handler remain unchanged) ...
    elif data == "menu_callback":
        keyboard = [
            [InlineKeyboardButton("📞 New call", callback_data="callback_new")],
            [InlineKeyboardButton("🔄 Repeat call", callback_data="callback_repeat")],
            [InlineKeyboardButton("🔔 Reminder", callback_data="callback_reminder")],
            [InlineKeyboardButton("⬅️ Back to main menu", callback_data="back_main")],
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text("📞 CALL BACK", reply_markup=reply_markup)
    # (Other inline menu branches omitted for brevity)
    elif data == "back_main":
        await menu(update, context)
    else:
        await query.edit_message_text(f"You pressed: {data}")

# ---------------------------------------------------------------------------
# PHOTO HANDLER: For "Add photo" feature
# ---------------------------------------------------------------------------
async def photo_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Handle incoming photos. Expects the photo message to have a caption containing the apartment ID.
    """
    token = user_tokens.get(update.effective_user.id)
    if not token:
        await update.message.reply_text("You need to log in first. Use /login.")
        return

    caption = update.message.caption
    if not caption or not caption.isdigit():
        await update.message.reply_text("Please send a photo with the caption as the apartment ID (a number).")
        return

    apartment_id = int(caption)
    photo = update.message.photo[-1]
    file = await photo.get_file()
    temp_path = f"/tmp/{file.file_id}.jpg"
    await file.download_to_drive(temp_path)

    try:
        with open(temp_path, "rb") as img_file:
            files = {"files": (f"{file.file_id}.jpg", img_file, "image/jpeg")}
            response = requests.post(f"{API_URL}/apartments/{apartment_id}/upload_images", files=files)
        if response.status_code == 200:
            await update.message.reply_text("Photo uploaded successfully.")
        else:
            await update.message.reply_text("Failed to upload photo.")
    except Exception as e:
        await update.message.reply_text(f"Error uploading photo: {str(e)}")
    finally:
        if os.path.exists(temp_path):
            os.remove(temp_path)

# ---------------------------------------------------------------------------
# OTHER COMMAND HANDLERS
# ---------------------------------------------------------------------------
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle the /start command."""
    await update.message.reply_text("Welcome to the Realtor Bot! Use /login to log in.")

async def login(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Log in as a realtor using a username and password.
    Usage: /login <username> <password>
    """
    if len(context.args) != 2:
        await update.message.reply_text("Usage: /login <username> <password>")
        return

    username, password = context.args
    try:
        response = requests.post(f"{API_URL}/login", data={"username": username, "password": password})
        response_data = response.json()
        if response.status_code == 200:
            token = response_data["access_token"]
            user_tokens[update.effective_user.id] = token
            await update.message.reply_text("Login successful! Use /get_apartments to fetch your apartments.")
        else:
            await update.message.reply_text(f"Login failed: {response_data['detail']}")
    except Exception as e:
        await update.message.reply_text(f"Error during login: {str(e)}")

async def get_apartments(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Fetch the logged-in realtor's apartments."""
    token = user_tokens.get(update.effective_user.id)
    if not token:
        await update.message.reply_text("You need to log in first. Use /login.")
        return

    try:
        decoded_token = jwt.decode(token, options={"verify_signature": False})
        agent_id = decoded_token.get("id")
        if not agent_id:
            await update.message.reply_text("Invalid token. Please log in again.")
            return

        response = make_authorized_request(f"/agents/{agent_id}/apartments/", "get", token)
        response_data = response.json()
        if response.status_code == 200:
            if response_data:
                message = "Your Apartments:\n" + "\n".join(
                    [f"ID: {apt['id']}, Title: {apt['title']}, Price: {apt['price']}" for apt in response_data]
                )
            else:
                message = "No apartments found for your account."
            await update.message.reply_text(message)
        else:
            await update.message.reply_text(f"Error fetching apartments: {response_data['detail']}")
    except Exception as e:
        await update.message.reply_text(f"Error during request: {str(e)}")

async def search_by_id(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Search for an apartment by ID. Usage: /search_by_id <apartment_id>"""
    if len(context.args) != 1:
        await update.message.reply_text("Usage: /search_by_id <apartment_id>")
        return

    token = user_tokens.get(update.effective_user.id)
    if not token:
        await update.message.reply_text("You need to log in first. Use /login.")
        return

    apartment_id = context.args[0]
    try:
        decoded_token = jwt.decode(token, options={"verify_signature": False})
        agent_id = decoded_token.get("id")
        if not agent_id:
            await update.message.reply_text("Invalid token. Please log in again.")
            return

        headers = {"Authorization": f"Bearer {token}"}
        response = requests.get(
            f"{API_URL}/agents/{agent_id}/apartments/",
            headers=headers,
            params={"apartment_id": apartment_id}
        )
        response_data = response.json()
        if response.status_code == 200 and response_data:
            apt = response_data[0]
            message = (
                f"Apartment Details:\n"
                f"ID: {apt['id']}\n"
                f"Title: {apt['title']}\n"
                f"Price: {apt['price']}\n"
                f"Location: {apt['location_date']}\n"
                f"Rooms: {apt['room']}\n"
                f"Description: {apt['description']}\n"
            )
            await update.message.reply_text(message)
        else:
            await update.message.reply_text("Apartment not found or an error occurred.")
    except Exception as e:
        await update.message.reply_text(f"Error during request: {str(e)}")

async def start_notifications(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Start sending notifications for the current user."""
    token = user_tokens.get(update.effective_user.id)
    if not token:
        await update.message.reply_text("You need to log in first. Use /login.")
        return

    chat_id = str(update.effective_chat.id)
    async with SessionLocal() as db:
        try:
            stmt = select(SubscribedChat).where(SubscribedChat.chat_id == chat_id)
            result = await db.execute(stmt)
            existing_chat = result.scalar_one_or_none()
            if not existing_chat:
                new_chat = SubscribedChat(chat_id=chat_id)
                db.add(new_chat)
                await db.commit()
                print(f"Added chat_id {chat_id} to the database")
                await update.message.reply_text("Notifications started! You'll receive updates every 20 minutes.")
            else:
                print(f"chat_id {chat_id} already exists in the database")
                await update.message.reply_text("You're already subscribed to notifications.")
        except Exception as e:
            print(f"Error adding chat_id {chat_id} to the database: {e}")
            await update.message.reply_text(f"Error starting notifications: {str(e)}")

async def get_orders(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Fetch orders linked to the realtor's apartments."""
    token = user_tokens.get(update.effective_user.id)
    if not token:
        await update.message.reply_text("You need to log in first. Use /login.")
        return

    try:
        decoded_token = jwt.decode(token, options={"verify_signature": False})
        realtor_id = decoded_token.get("id")
        if not realtor_id:
            await update.message.reply_text("Invalid token. Please log in again.")
            return

        response = make_authorized_request("/get_orders/", "get", token, params={"realtor_id": realtor_id})
        response_data = response.json()
        if response.status_code == 200:
            if response_data:
                message = "Your Orders:\n" + "\n".join(
                    [f"ID: {order['id']}, Status: {order['ed_status']}, Apartment ID: {order['apartment_id']}" for order in response_data]
                )
            else:
                message = "No orders found for your account."
            await update.message.reply_text(message)
        else:
            await update.message.reply_text(f"Error fetching orders: {response_data['detail']}")
    except Exception as e:
        await update.message.reply_text(f"Error during request: {str(e)}")

async def update_order_status(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Update the status of a specific order.
    Usage: /update_order_status <order_id> <new_status>
    """
    token = user_tokens.get(update.effective_user.id)
    if not token:
        await update.message.reply_text("You need to log in first. Use /login.")
        return

    if len(context.args) != 2:
        await update.message.reply_text("Usage: /update_order_status <order_id> <new_status>")
        return

    order_id, new_status = context.args
    try:
        response = make_authorized_request(f"/get_orders/{order_id}/status", "put", token, json={"new_status": new_status})
        response_data = response.json()
        if response.status_code == 200:
            await update.message.reply_text(response_data["message"])
        else:
            await update.message.reply_text(f"Error updating order: {response_data['detail']}")
    except Exception as e:
        await update.message.reply_text(f"Error during request: {str(e)}")

async def get_statistics(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Fetch statistics for the logged-in realtor."""
    token = user_tokens.get(update.effective_user.id)
    if not token:
        await update.message.reply_text("You need to log in first. Use /login.")
        return

    try:
        decoded_token = jwt.decode(token, options={"verify_signature": False})
        agent_id = decoded_token.get("id")
        if not agent_id:
            await update.message.reply_text("Invalid token. Please log in again.")
            return

        response = requests.get(
            f"{API_URL}/agents/{agent_id}/statisticss/",
            headers={"Authorization": f"Bearer {token}"}
        )
        response_data = response.json()
        if response.status_code == 200:
            stats = response_data
            message = (
                f"📊 Realtor Statistics:\n"
                f"🔹 Total Apartments: {stats['total_apartments']}\n"
                f"🔹 Total Orders: {stats['total_orders']}\n"
                f"🔹 Completed Orders: {stats['completed_orders']}\n"
            )
            await update.message.reply_text(message)
        else:
            await update.message.reply_text(f"Error fetching statistics: {response_data.get('detail', 'Unknown error')}")
    except Exception as e:
        await update.message.reply_text(f"Error during request: {str(e)}")

async def view_orders(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """View orders assigned to the team leader."""
    chat_id = update.effective_user.id
    async with SessionLocal() as db:
        try:
            stmt_leader = select(TeamLeed)
            result_leader = await db.execute(stmt_leader)
            leader = result_leader.scalar_one_or_none()
            if not leader:
                await update.message.reply_text("You are not authorized as a team leader.")
                return

            stmt_orders = select(Order).where(Order.team_leader_id == leader.id)
            result_orders = await db.execute(stmt_orders)
            orders = result_orders.scalars().all()
            if not orders:
                await update.message.reply_text("No orders are currently assigned to you.")
                return

            message = "📋 Your Assigned Orders:\n" + "\n".join(
                [f"Order ID: {order.id}, Apartment ID: {order.apartment_id}" for order in orders]
            )
            await update.message.reply_text(message)
        except Exception as e:
            await update.message.reply_text(f"Error fetching orders: {str(e)}")

async def assign_order(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Assign an order to a realtor.
    Usage: /assign_order <order_id> <realtor_id>
    """
    if len(context.args) != 2:
        await update.message.reply_text("Usage: /assign_order <order_id> <realtor_id>")
        return

    order_id, realtor_id = context.args
    async with SessionLocal() as db:
        try:
            stmt_order = select(Order).where(Order.id == int(order_id))
            result_order = await db.execute(stmt_order)
            order = result_order.scalar_one_or_none()
            if not order:
                await update.message.reply_text(f"Order ID {order_id} not found.")
                return

            order.realtor_id = int(realtor_id)
            await db.commit()
            await update.message.reply_text(f"Order ID {order_id} assigned to Realtor ID {realtor_id}.")
        except Exception as e:
            await update.message.reply_text(f"Error assigning order: {str(e)}")

async def get_statisticss(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Fetch and display combined statistics for the team leader."""
    chat_id = update.effective_user.id
    async with SessionLocal() as db:
        try:
            stmt = select(TeamLeed)
            result = await db.execute(stmt)
            team_leader = result.scalar_one_or_none()
            if not team_leader:
                await update.message.reply_text("You are not authorized as a team leader.")
                return

            response = requests.get(f"{API_URL}/team_leader/{team_leader.id}/combined-stats")
            if response.status_code == 200:
                stats = response.json()
                general_stats = stats["generalStats"]
                general_stats_msg = (
                    f"📊 General Team Statistics:\n"
                    f"Total Orders: {general_stats['total_orders']}\n"
                    f"Orders (Last Day): {general_stats['orders_per_day']}\n"
                    f"Orders (Last Week): {general_stats['orders_per_week']}\n"
                    f"Orders (Last Month): {general_stats['orders_per_month']}\n"
                    f"Total Apartments: {general_stats['total_apartments']}\n"
                    f"Apartments with Orders: {general_stats['apartments_with_orders']}\n"
                    f"Apartments without Orders: {general_stats['apartments_without_orders']}\n"
                )
                realtor_stats = stats["realtorStats"]
                realtor_stats_msg = "📋 Realtor-Specific Statistics:\n"
                for realtor in realtor_stats:
                    realtor_stats_msg += (
                        f"\n🔹 {realtor['name']} (ID: {realtor['id']})\n"
                        f"  Total Apartments: {realtor['total_apartments']}\n"
                        f"  Total Orders: {realtor['total_orders']}\n"
                        f"  Completed Orders: {realtor['completed_orders']}\n"
                        f"  Pending Orders: {realtor['pending_orders']}\n"
                    )
                message = general_stats_msg + "\n" + realtor_stats_msg
                await update.message.reply_text(message)
            else:
                await update.message.reply_text(
                    f"Failed to fetch statistics: {response.json().get('detail', 'Unknown error')}"
                )
        except Exception as e:
            await update.message.reply_text(f"Error fetching statistics: {str(e)}")

# ---------------------------------------------------------------------------
# NEW COMMAND HANDLERS: For updating fix fields and adding property
# ---------------------------------------------------------------------------
async def update_fix_fields_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Update apartment fix fields.
    Usage: /update_fix_fields <apartment_id> <field>=<new_value>
    Example: /update_fix_fields 123 title_fix=New Title
    """
    token = user_tokens.get(update.effective_user.id)
    if not token:
        await update.message.reply_text("You need to log in first. Use /login.")
        return
    if len(context.args) < 2:
        await update.message.reply_text("Usage: /update_fix_fields <apartment_id> <field>=<new_value>")
        return

    try:
        apartment_id = int(context.args[0])
    except ValueError:
        await update.message.reply_text("Apartment ID must be a number.")
        return

    field_update = " ".join(context.args[1:])
    if "=" not in field_update:
        await update.message.reply_text("Invalid format. Use <field>=<value>.")
        return
    field, value = field_update.split("=", 1)

    async with SessionLocal() as db:
        updated_apartment = await update_apartment_fix_fields(db, apartment_id, {field: value})
        if updated_apartment:
            await update.message.reply_text(f"Apartment {apartment_id} updated: {field} set to {value}.")
        else:
            await update.message.reply_text("Failed to update apartment. Please check the apartment ID and try again.")

async def add_property_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Add a property using a message with details.
    Expected format (each field on a separate line after the command):
    
    📍 Address: 123 Main St, City
    🏠 Type: Apartment
    🔢 Rooms: 3
    📐 Area: 120
    🏗 Floor: 2
    🎨 Condition: Good
    🏡 Features: Balcony, Parking
    💰 Price: 150000
    📜 Ownership: Private
    🏷 Tags: modern, renovated

    (Photos are added separately.)
    """
    token = user_tokens.get(update.effective_user.id)
    if not token:
        await update.message.reply_text("You need to log in first. Use /login.")
        return

    # Skip the command line and get the rest of the message.
    text_lines = update.message.text.splitlines()[1:]
    if not text_lines:
        await update.message.reply_text(
            "Please provide property details in the correct format.\n\n"
            "Example:\n"
            "📍 Address: 123 Main St, City\n"
            "🏠 Type: Apartment\n"
            "🔢 Rooms: 3\n"
            "📐 Area: 120\n"
            "🏗 Floor: 2\n"
            "🎨 Condition: Good\n"
            "🏡 Features: Balcony, Parking\n"
            "💰 Price: 150000\n"
            "📜 Ownership: Private\n"
            "🏷 Tags: modern, renovated"
        )
        return

    property_data = {}
    for line in text_lines:
        if ":" in line:
            key, value = line.split(":", 1)
            key = key.strip()
            value = value.strip()
            if key.startswith("📍 Address"):
                property_data["location_date"] = value  # using location_date for address
            elif key.startswith("🏠 Type"):
                property_data["type_object"] = value
            elif key.startswith("🔢 Rooms"):
                property_data["room"] = value
            elif key.startswith("📐 Area"):
                property_data["square"] = value
            elif key.startswith("🏗 Floor"):
                property_data["floor"] = value
            elif key.startswith("🎨 Condition"):
                property_data["description"] = value
            elif key.startswith("🏡 Features"):
                property_data["features"] = value
            elif key.startswith("💰 Price"):
                property_data["price"] = value
            elif key.startswith("📜 Ownership"):
                property_data["owner"] = value
            elif key.startswith("🏷 Tags"):
                property_data["comment"] = value

    property_data.setdefault("ad_status", "active")
    property_data.setdefault("type_deal", "sale")
    if "location_date" in property_data:
        property_data.setdefault("title", property_data["location_date"])

    try:
        decoded_token = jwt.decode(token, options={"verify_signature": False})
        property_data["rieltor_id"] = decoded_token.get("id")
    except Exception as e:
        await update.message.reply_text(f"Error decoding token: {e}")
        return

    async with SessionLocal() as db:
        new_apartment = await create_or_update_apartment(db, property_data)
        if new_apartment:
            await update.message.reply_text(f"Property added successfully with ID {new_apartment.id}.")
        else:
            await update.message.reply_text("Failed to add property. Please try again later.")

# ---------------------------------------------------------------------------
# PHOTO HANDLER (unchanged)
# ---------------------------------------------------------------------------
async def photo_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Handle incoming photos. Expects the photo message to have a caption containing the apartment ID.
    """
    token = user_tokens.get(update.effective_user.id)
    if not token:
        await update.message.reply_text("You need to log in first. Use /login.")
        return

    caption = update.message.caption
    if not caption or not caption.isdigit():
        await update.message.reply_text("Please send a photo with the caption as the apartment ID (a number).")
        return

    apartment_id = int(caption)
    photo = update.message.photo[-1]
    file = await photo.get_file()
    temp_path = f"/tmp/{file.file_id}.jpg"
    await file.download_to_drive(temp_path)

    try:
        with open(temp_path, "rb") as img_file:
            files = {"files": (f"{file.file_id}.jpg", img_file, "image/jpeg")}
            response = requests.post(f"{API_URL}/apartments/{apartment_id}/upload_images", files=files)
        if response.status_code == 200:
            await update.message.reply_text("Photo uploaded successfully.")
        else:
            await update.message.reply_text("Failed to upload photo.")
    except Exception as e:
        await update.message.reply_text(f"Error uploading photo: {str(e)}")
    finally:
        if os.path.exists(temp_path):
            os.remove(temp_path)

# ---------------------------------------------------------------------------
# RUN BOT
# ---------------------------------------------------------------------------
def run_bot():
    """Run the Telegram bot."""
    application = ApplicationBuilder().token(BOT_TOKEN).build()

    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("login", login))
    application.add_handler(CommandHandler("get_apartments", get_apartments))
    application.add_handler(CommandHandler("search_by_id", search_by_id))
    application.add_handler(CommandHandler("start_notifications", start_notifications))
    application.add_handler(CommandHandler("get_orders", get_orders))
    application.add_handler(CommandHandler("update_order_status", update_order_status))
    application.add_handler(CommandHandler("get_statistics", get_statistics))
    application.add_handler(CommandHandler("view_orders", view_orders))
    application.add_handler(CommandHandler("assign_order", assign_order))
    application.add_handler(CommandHandler("get_statisticss", get_statisticss))
    application.add_handler(CommandHandler("menu", menu))
    application.add_handler(CommandHandler("update_fix_fields", update_fix_fields_command))
    # New command handler to add property
    application.add_handler(CommandHandler("add_property", add_property_command))

    # Register the callback query handler for inline keyboard buttons
    application.add_handler(CallbackQueryHandler(menu_callback_handler))

    # Register a message handler for photos (for the add photo feature)
    application.add_handler(MessageHandler(filters.PHOTO, photo_handler))

    application.run_polling()

if __name__ == "__main__":
    run_bot()
