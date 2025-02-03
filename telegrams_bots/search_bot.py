import asyncio
import os
import re
import aiohttp
import requests
import logging
from telegram import  InputMediaPhoto, KeyboardButton, ReplyKeyboardMarkup, ReplyKeyboardRemove, Update, InlineKeyboardButton, InlineKeyboardMarkup
from apscheduler.schedulers.asyncio import AsyncIOScheduler
import telegram
from telegram.ext import ApplicationBuilder, CommandHandler, CallbackQueryHandler, ContextTypes, PicklePersistence
from telegram.ext import MessageHandler, filters

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)

logger = logging.getLogger(__name__)
async def handle_text_input(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Handle free text input, particularly for Telegram username.
    """
    if context.user_data.get("username_requested"):
        username = update.message.text
        context.user_data["user_username"] = username  # Save the username
        language = context.user_data.get("language", "en")

        # Send confirmation message
        await update.message.reply_text(
            "Thank you for providing your details! We'll contact you soon." if language == "en" else
            "Дякуємо за надані дані! Ми зв’яжемося з вами найближчим часом."
        )

        # Clear request states
        context.user_data.pop("username_requested", None)


async def ask_for_contact(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()

    step = context.user_data.get("application_step", "contact_phone")
    language = context.user_data.get("language", "en")

    if step == "contact_phone":
        buttons = [
            [InlineKeyboardButton("📞 Send Phone Number", callback_data="send_phone")],
            [InlineKeyboardButton("⬅️ Back", callback_data="back")],
        ]
        keyboard = InlineKeyboardMarkup(buttons)
        await query.edit_message_text(
            "📞 Please share your phone number so we can contact you." if language == "en" else
            "📞 Надішліть свій номер телефону, щоб ми могли зв’язатися з вами.",
            reply_markup=keyboard
        )
    elif step == "contact_telegram":
        buttons = [
            [InlineKeyboardButton("💬 Send Telegram Username", callback_data="send_telegram")],
            [InlineKeyboardButton("⬅️ Back", callback_data="back")],
        ]
        keyboard = InlineKeyboardMarkup(buttons)
        await query.edit_message_text(
            "💬 Now, please share your Telegram username." if language == "en" else
            "💬 Тепер, будь ласка, надішліть свій нік у Telegram.",
            reply_markup=keyboard
        )
    elif step == "finish":
        buttons = [
            [InlineKeyboardButton("⬅️ Back to Main Menu", callback_data="main_menu")],
        ]
        keyboard = InlineKeyboardMarkup(buttons)
        await query.edit_message_text(
            "🎉 Thank you! We will contact you soon." if language == "en" else
            "🎉 Дякуємо! Ми зв’яжемося з вами найближчим часом.",
            reply_markup=keyboard
        )
    else:
        await query.edit_message_text(
            "Unexpected error. Resetting application." if language == "en" else "Несподівана помилка. Заявка скидається."
        )
        context.user_data["application_step"] = "contact_phone"
        await submit_application(update, context)

async def continue_browsing(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handles the 'Continue Browsing' button click."""
    query = update.callback_query
    language = context.user_data.get("language", "en")
    await query.answer()

    # Check if there are saved filters
    if "selected_locations" in context.user_data:
        await query.edit_message_text(
            "Fetching properties based on your last filters..." if language == "en" else
            "Завантаження об'єктів за останніми фільтрами..."
        )
        
        # Call the filter_apartments directly with the saved filters
        await filter_apartments(update, context)
    else:
        # If no filters were saved, start from the beginning
        await query.edit_message_text(
            "No filters found. Please start a new search." if language == "en" else
            "Фільтри не знайдені. Будь ласка, почніть новий пошук."
        )
        await filter_properties(update, context)
# ✅ Submit Application (Start)
async def submit_application(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    templates = {
        "Подобова оренда": [
            ("Що саме вам потрібно", ["Подобова оренда", "Оренда", "Продаж"]),
            ("Який тип нерухомості вас цікавить", ["Квартира", "Будинок", "Котедж", "Комерція", "Бізнес", "Земля", "Офіс"]),
            ("Вибрати місто", ["Львів"]),
            ("Місто, околиці чи обласні центри", ["Місто", "Околиці міста", "Обласні центри"]),
            ("Район", ["Вказати район"]),
            ("Вулиця (за бажанням)", ["Вказати вулицю"]),
            ("Яка кількість осіб буде проживати", ["Вказати кількість осіб"]),
            ("Скільки у вас часу на пошуки", ["Терміново", "До 1 дня", "1-3 дні", "До тижня"]),
            ("Яка ціль оренди", ["Відпочинок", "Бізнес", "Туризм", "Переїзд на постійне місце проживання"]),
            ("Бюджет", ["Вказати бюджет"]),
            ("Кількість кімнат", ["Вказати кількість кімнат"]),
            ("Площа (м²)", ["Вказати площу м²"]),
            ("На який термін ви розглядаєте оренду", ["До 1 місяця", "1-3 місяці", "3-6 місяців", "Більше 6 місяців"]),
            ("Домашні улюбленці", ["Так", "Ні"]),
            ("Додаткові побажання", ["Додати коментар"]),
            ("Контактні дані", ["Надіслати номер телефону"]),
            ("Нік у Telegram", ["Надіслати нік Telegram"]),
            ("Завершення", []),
        ],
        "Оренда": [
            ("Що саме вам потрібно", ["Подобова оренда", "Оренда", "Продаж"]),
            ("Який тип нерухомості вас цікавить", ["Квартира", "Будинок", "Котедж", "Комерція", "Бізнес", "Земля", "Офіс"]),
            ("Вибрати місто", ["Львів"]),
            ("Місто, околиці чи обласні центри", ["Місто", "Околиці міста", "Обласні центри"]),
            ("Район", ["Вказати район"]),
            ("Вулиця (за бажанням)", ["Вказати вулицю"]),
            ("Яка кількість осіб буде проживати", ["Вказати кількість осіб"]),
            ("Скільки у вас часу на пошуки", ["Терміново", "1-3 дні", "Тиждень", "Місяць"]),
            ("Яка ціль оренди", ["Відпочинок", "Бізнес", "Туризм", "Переїзд на постійне місце проживання"]),
            ("Бюджет", ["Вказати бюджет"]),
            ("Кількість кімнат", ["Вказати кількість кімнат"]),
            ("Площа (м²)", ["Вказати площу м²"]),
            ("На який термін ви розглядаєте оренду", ["До 1 року", "1 рік", "2-3 роки", "Довше 3 років"]),
            ("Домашні улюбленці", ["Так", "Ні"]),
            ("Додаткові побажання", ["Додати коментар"]),
            ("Контактні дані", ["Надіслати номер телефону"]),
            ("Нік у Telegram", ["Надіслати нік Telegram"]),
            ("Завершення", []),
        ],
        "Покупка": [
            ("Що саме вам потрібно", ["Подобова оренда", "Оренда", "Продаж"]),
            ("Який тип нерухомості вас цікавить", ["Квартира", "Будинок", "Котедж", "Комерція", "Бізнес", "Земля", "Офіс"]),
            ("Вибрати місто", ["Львів"]),
            ("Місто, околиці чи обласні центри", ["Місто", "Околиці міста", "Обласні центри"]),
            ("Район", ["Вказати район"]),
            ("Вулиця (за бажанням)", ["Вказати вулицю"]),
            ("Бюджет", ["Вказати бюджет"]),
            ("Кількість кімнат", ["Вказати кількість кімнат"]),
            ("Площа (м²)", ["Вказати площу м²"]),
            ("Ціль покупки", ["Житло для себе", "Інвестиція", "Оренда для здачі", "Бізнес"]),
            ("Домашні улюбленці", ["Так", "Ні"]),
            ("Додаткові побажання", ["Додати коментар"]),
            ("Контактні дані", ["Надіслати номер телефону"]),
            ("Нік у Telegram", ["Надіслати нік Telegram"]),
            ("Завершення", []),
        ],
    }
    # Determine the source of the update (callback query or message)
    query = update.callback_query
    message = update.message

    if query:
        await query.answer()

    language = context.user_data.get("language", "uk")
    step = context.user_data.get("application_step", 0)
    template_type = context.user_data.get("template_type")
    current_template = templates.get(template_type, [])

    # Step 0: Ask for template type if not already selected
    if not template_type:
        context.user_data["application_step"] = 0
        buttons = [[InlineKeyboardButton(option, callback_data=option)] for option in templates.keys()]
        keyboard = InlineKeyboardMarkup(buttons)
        text = "Що саме вам потрібно?" if language == "uk" else "What are you looking for?"
        if query:
            await query.edit_message_text(text, reply_markup=keyboard)
        elif message:
            await message.reply_text(text, reply_markup=keyboard)
        return

    # Validate the selected template
    if not current_template:
        error_text = "Помилка у виборі шаблону. Спробуйте ще раз." if language == "uk" else "Template error. Please try again."
        if query:
            await query.edit_message_text(error_text)
        elif message:
            await message.reply_text(error_text)
        return

    # Handle each step in the template
    if step < len(current_template):
        question, options = current_template[step]

        # Handle manual input steps
        if question in [
            "Район",
            "Вулиця (за бажанням)",
            "Бюджет",
            "Кількість кімнат",
            "Площа (м²)",
            "Яка кількість осіб буде проживати",
        ]:
            prompt = f"📝 {question}: {options[0]}"
            if query:
                await query.message.reply_text(prompt)
            elif message:
                await message.reply_text(prompt)
            context.user_data["waiting_for_input"] = question
            return
            # Check if the current step requires a specific input
        if question == "Контактні дані":
                # Ask for phone number
                contact_button = KeyboardButton(
                    "📞 Надіслати номер телефону" if language == "uk" else "📞 Send Phone Number",
                    request_contact=True
                )
                keyboard = ReplyKeyboardMarkup([[contact_button]], resize_keyboard=True, one_time_keyboard=True)
                await query.message.reply_text(
                    "📞 Надішліть ваш номер телефону, щоб ми могли зв’язатися з вами." if language == "uk" else
                    "📞 Please share your phone number so we can contact you.",
                    reply_markup=keyboard
                )
                context.user_data["application_step"] += 1  # Move to the next step after contact
                return
        elif question == "Нік у Telegram":
                # Ask for Telegram nickname
                await query.message.reply_text(
                    "💬 Напишіть ваш нік у Telegram." if language == "uk" else
                    "💬 Please send your Telegram nickname."
                )
                context.user_data["application_step"] += 1  # Wait for user response
                return
        # Handle non-text-input steps
        selected_option = context.user_data.get(f"selected_step_{step}")
        buttons = [
            [InlineKeyboardButton(f"✔️ {opt}" if opt == selected_option else opt, callback_data=opt)]
            for opt in options
        ]

        # Add navigation buttons
        if step > 0:
            buttons.append([InlineKeyboardButton("⬅️ Назад", callback_data="back")])
        if selected_option:
            buttons.append([InlineKeyboardButton("✅ Підтвердити", callback_data="confirm")])

        keyboard = InlineKeyboardMarkup(buttons)
        if query:
            await query.edit_message_text(question, reply_markup=keyboard)
        elif message:
            await message.reply_text(question, reply_markup=keyboard)
    else:
        order_data = {
            "name": context.user_data.get("user_name"),
            "phone": context.user_data.get("user_phone"),
            "telegram_username": context.user_data.get("user_username"),
            "client_wishes": context.user_data.get("client_wishes", "Requested help from manager"),
            "search_time": context.user_data.get("search_time", ""),
            "residents": context.user_data.get("residents", ""),
            "budget": context.user_data.get("budget"),
            "district": context.user_data.get("district"),
            "rooms": context.user_data.get("rooms"),
            "area": context.user_data.get("area"),
        }
        async with aiohttp.ClientSession() as session:
            async with session.post("http://127.0.0.1:8000/orders/", json=order_data) as response:
                if response.status == 200:
                    await query.edit_message_text(
                        "🎉 Ваша заявка успішно подана!" if language == "uk" else "🎉 Your application has been submitted!"
                    )
                else:
                    await query.edit_message_text(
                        "Виникла помилка при подачі заявки. Спробуйте ще раз." if language == "uk" else "An error occurred while submitting your application. Please try again."
                    )

        context.user_data.clear()  # Clear user data after submission

async def notify_new_objects(application):
    """Fetch and notify new objects."""
    logger.info("Executing notify_new_objects task...")
    persistence = application.persistence
    user_data = persistence.user_data if persistence else {}

    for chat_id, data in user_data.items():
        subscriptions = data.get("subscriptions", [])
        language = data.get("language", "en")

        if not subscriptions:
            logger.info(f"No subscriptions found for user {chat_id}")
            continue

        for subscription in subscriptions:
            matched_objects = await fetch_new_objects(subscription)

            if matched_objects:
                logger.info(f"Sending {len(matched_objects)} objects to user {chat_id}")
                await send_notifications(application.bot, chat_id, matched_objects)
            else:
                logger.info(f"No new objects found for subscription: {subscription}")
async def send_notifications(bot, chat_id, matched_objects):
    """Send notifications to the user about matched objects."""
    if not matched_objects:
        logger.info(f"No matched objects to notify for chat_id: {chat_id}")
        return

    template_text = await fetch_bot_template()  # Fetch template dynamically

    for obj in matched_objects:
        try:
            message = format_message(obj, template_text)  # Format the message dynamically
            images = obj.get('files', [])[:10]  # Limit to 10 images

            if images:
                media_group = []
                for i, image in enumerate(images):
                    if 'file_path' in image:
                        if i == 0:
                            media_group.append(InputMediaPhoto(image['file_path'], caption=message, parse_mode="Markdown"))
                        else:
                            media_group.append(InputMediaPhoto(image['file_path']))

                await bot.send_media_group(chat_id=chat_id, media=media_group)
            else:
                await bot.send_message(
                    chat_id=chat_id,
                    text=message,
                    parse_mode="Markdown",
                    disable_web_page_preview=False
                )

            logger.info(f"Message sent to chat_id: {chat_id} for object ID: {obj['id']}")
        except Exception as e:
            logger.error(f"Failed to send message to chat_id: {chat_id}. Error: {e}")


async def fetch_new_objects(subscription):
    """Fetch new objects matching the subscription criteria."""
    try:
        logger.info(f"Fetching new objects for subscription: {subscription}")
        response = requests.get("http://127.0.0.1:8000/get_orders_and_photo/")
        response.raise_for_status()
        all_objects = response.json()

        matched_objects = []
        for obj in all_objects:
            type_deal = obj.get("type_deal", "").strip().lower()
            type_object = obj.get("type_object", "").strip().lower()
            location_date = obj.get("location_date", "").strip().lower()
            room = str(obj.get("room", "")).strip()
            price = obj.get("price", "").replace(",", "").split(" ")[0]

            if (
                type_deal == subscription.get("type_deal", "").strip().lower()
                and type_object in map(str.lower, subscription.get("type_object", []))
                and location_date in map(str.lower, subscription.get("location_date", []))
                and room in subscription.get("rooms", [])
                and any(price.startswith(b) for b in subscription.get("budget", []))
            ):
                logger.info(f"Matched object ID {obj['id']} with subscription.")
                matched_objects.append(obj)

        logger.info(f"Total matched objects: {len(matched_objects)}")
        return matched_objects

    except Exception as e:
        logger.error(f"Error fetching new objects: {e}")
        return []



# Replace 'YOUR_BOT_TOKEN' with your actual bot token
TOKEN = '7753051633:AAEGm7Kso2OkqETA49telj-D6FDJUGqKvhk'
FILTER_STEPS = {
    "city_or_region": 1,
    "location_date": 2,
    "type_deal": 3,
    "type_object": 4,
    "residential_complex": 5,
    "rooms": 6,
    "budget": 7
}
async def change_subscription(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()

    # Redirect to filter_properties for reconfiguration
    await filter_properties(update, context)

async def stop_subscription(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    language = context.user_data.get("language", "en")
    await query.answer()

    context.user_data["subscription_active"] = False

    await query.edit_message_text(
        "Your subscription notifications have been paused." if language == "en" else "Ваші повідомлення про підписку призупинені."
    )
    await show_navigation_options(update, context)

async def delete_subscription(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    language = context.user_data.get("language", "en")
    await query.answer()

    context.user_data.pop("subscriptions", None)

    await query.edit_message_text(
        "Your subscription has been deleted." if language == "en" else "Вашу підписку було видалено."
    )
    await show_navigation_options(update, context)

async def manage_subscription(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    language = context.user_data.get("language", "en")
    await query.answer()

    subscriptions = context.user_data.get("subscriptions", [])
    if not subscriptions:
        await query.edit_message_text(
            "You currently have no active subscriptions." if language == "en" else "У вас немає активних підписок."
        )
        return

    subscription_texts = []
    for i, subscription in enumerate(subscriptions, start=1):
        type_deal = subscription.get("type_deal", "Н/Д") or "Н/Д"  # Ensure it's not None
        location = ', '.join(subscription.get("location_date", ["Н/Д"]))
        type_object = ', '.join(subscription.get("type_object", ["Н/Д"]))
        rooms = ', '.join(subscription.get("rooms", []))
        district = ', '.join(subscription.get("district", ["Н/Д"]))
        budget = ', '.join(subscription.get("budget", []))

        subscription_texts.append(
            (f"№{i}\n"
             f"Category: {type_deal.capitalize()}\n"
             f"City: {location}\n"
             f"Type: {type_object}\n"
             f"Rooms: {rooms}\n"
             f"District: {district}\n"
             f"Price: {budget}\n") if language == "en" else
            (f"№{i}\n"
             f"Категорія: {type_deal.capitalize()}\n"
             f"Місто: {location}\n"
             f"Тип: {type_object}\n"
             f"Кімнати: {rooms}\n"
             f"Район: {district}\n"
             f"Ціна: {budget}\n")
        )

    subscription_text = "\n\n".join(subscription_texts)

    buttons = [
        [InlineKeyboardButton("Change Subscription" if language == "en" else "Змінити підписку", callback_data="change_subscription")],
        [InlineKeyboardButton("Stop Notifications" if language == "en" else "Зупинити повідомлення", callback_data="stop_subscription")],
        [InlineKeyboardButton("Delete Subscription" if language == "en" else "Видалити підписку", callback_data="delete_subscription")],
        [InlineKeyboardButton("Back" if language == "en" else "Назад", callback_data="back")]
    ]
    keyboard = InlineKeyboardMarkup(buttons)

    await query.edit_message_text(
        (f"Your current subscriptions:\n\n{subscription_text}" if language == "en" else
         f"Ваші поточні підписки:\n\n{subscription_text}"),
        reply_markup=keyboard
    )



async def save_subscription(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    language = context.user_data.get("language", "en")
    await query.answer()

    subscription = {
        "type_deal": context.user_data.get("type_deal"),
        "location_date": context.user_data.get("selected_locations", []),
        "type_object": context.user_data.get("type_object_selection", []),
        "rooms": context.user_data.get("selected_rooms", []),
        "district": context.user_data.get("selected_districts", []),
        "budget": context.user_data.get("selected_budgets", [])
    }

    if "subscriptions" not in context.user_data:
        context.user_data["subscriptions"] = []

    context.user_data["subscriptions"].append(subscription)

    await query.edit_message_text(
        "Subscription saved successfully!" if language == "en" else "Підписка успішно збережена!"
    )
    await show_navigation_options(update, context)




async def ask_to_save_subscription(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    language = context.user_data.get("language", "en")
    await query.answer()

    buttons = [
        [InlineKeyboardButton("Save Subscription" if language == "en" else "Зберегти підписку", callback_data="save_subscription")],
        [InlineKeyboardButton("Skip" if language == "en" else "Пропустити", callback_data="skip_subscription")]
    ]
    keyboard = InlineKeyboardMarkup(buttons)

    await query.edit_message_text(
        ("Would you like to save these settings as a subscription for new object notifications?" if language == "en" else
         "Бажаєте зберегти ці налаштування як підписку для нових повідомлень про об'єкти?"),
        reply_markup=keyboard
    )

async def skip_subscription(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    language = context.user_data.get("language", "en")
    await query.answer()

    await query.edit_message_text(
        "Filters applied, but no subscription was saved." if language == "en" else "Фільтри застосовані, але підписка не була збережена."
    )
    await show_navigation_options(update, context)









async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:


    # Display the Start button
    buttons = [
        [InlineKeyboardButton("English", callback_data="lang_en"), InlineKeyboardButton("Ukrainian", callback_data="lang_uk")]
    ]
    keyboard = InlineKeyboardMarkup(buttons)

    # Prompt user to select language
    await update.message.reply_text(
        "Welcome! Please select your language / Радий бачити тебе, Імʼя 🤗 Якою мовою тобі зручніше зі мною спілкуватися?:",
        reply_markup=keyboard
    )


async def language_selection(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()

    # Determine the language
    language = "en" if query.data == "lang_en" else "uk"
    context.user_data["language"] = language

    # Message based on language
    message = (
        "You selected English. Please choose an action:" if language == "en" else
        "Ви обрали українську мову. Будь ласка, оберіть дію:"
    )
    await query.edit_message_text(message)

    # Show the main menu
    await show_main_menu(update, context)

async def show_main_menu(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    language = context.user_data.get("language", "en")
    is_returning_user = "saved_ads" in context.user_data  # Example condition

    # Define menu buttons based on user type
    if is_returning_user:
        buttons = [
            [
                InlineKeyboardButton("Search for Real Estate" if language == "en" else "Шукати нерухомість", callback_data="city_or_region"),
                InlineKeyboardButton("Continue Browsing" if language == "en" else "Продовжити перегляд",  callback_data="continue_browsing"),
            ],
            [
                InlineKeyboardButton("Rent/Sell" if language == "en" else "Здати/Продати",  url="https://t.me/RentSearchOwner_bot"),
                InlineKeyboardButton("Submit an Application 🟡" if language == "en" else "Надішліть заявку 🟡",  callback_data="submit_application"),
            ],
            [
                InlineKeyboardButton("Manager’s Help" if language == "en" else "Допомога менеджера",  callback_data="managers_help"),
                InlineKeyboardButton("Look at Your Favorite" if language == "en" else "Подивитись на свої збережені",  callback_data="show_saved_ads"),
            ],
            [
                InlineKeyboardButton("My Rental" if language == "en" else "Моя оренда", callback_data="my_rental"),
                InlineKeyboardButton("My Subscription 🟡" if language == "en" else "Моя підписка 🟡",  callback_data="my_subscription"),
            ],
        ]
    else:
        buttons = [
            [
                InlineKeyboardButton("Search for Real Estate" if language == "en" else "Шукати нерухомість", callback_data="city_or_region"),
                InlineKeyboardButton("Rent/Sell" if language == "en" else "Здати/Продати", url="https://t.me/RentSearchOwner_bot"),
            ],
            [
                InlineKeyboardButton("Submit an Application 🟡" if language == "en" else "Надішліть заявку 🟡", callback_data="submit_application"),
                InlineKeyboardButton("Manager’s Help" if language == "en" else "Допомога менеджера", callback_data="managers_help"),
            ],
            [
                InlineKeyboardButton("Look at Your Favorite" if language == "en" else "Подивитись на свої збережені", callback_data="show_saved_ads"),
                InlineKeyboardButton("My Rental" if language == "en" else "Моя оренда", callback_data="my_rental"),
            ],
        ]

    keyboard = InlineKeyboardMarkup(buttons)
    await update.callback_query.message.reply_text("Please choose an action:" if language == "en" else "Будь ласка, оберіть дію:", reply_markup=keyboard)

# Begin filtering process
async def filter_properties(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query if hasattr(update, "callback_query") else None
    message = update.message if hasattr(update, "message") else None
    if query:
        reply_method = query.message.reply_text
    elif message:
        reply_method = message.reply_text
    else:
        logging.error("filter_properties called without a valid update.")
        return

    lang = context.user_data.get("language", "en")

    # Define the buttons
    buttons = [
        [
            InlineKeyboardButton("City" if lang == "en" else "Місто", callback_data="city"),
            InlineKeyboardButton("Region" if lang == "en" else "Регіон", callback_data="region"),
            InlineKeyboardButton("Suburbs" if lang == "en" else "Передмістя", callback_data="suburbs"),

        ],
        [InlineKeyboardButton("Back" if lang == "en" else "Назад", callback_data="back")],
    ]
    keyboard = InlineKeyboardMarkup(buttons)

    # Send the message with the buttons
    await reply_method(
        "Are you looking for a property in a city, region, or suburb?" if lang == "en" else "Шукаєте нерухомість у місті, регіоні чи передмісті?",
        reply_markup=keyboard,
    )
    context.user_data["step"] = FILTER_STEPS["city_or_region"]



async def button_click(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    step = context.user_data.get("step")
    lang = context.user_data.get("language", "en")

    callback_dataa = query.data
    # Handle "Manager's Help" callback
    if callback_dataa == "managers_help":
        context.user_data["manager_help_requested"] = True
        await request_contact(update, context)
        return
    # Handle `submit_application`
    if callback_dataa == "submit_application":
        context.user_data["application_step"] = 0  # Reset step to start
        context.user_data["template_type"] = None  # Reset template type
        await submit_application(update, context)
        return

    # Handle template selection
    if callback_dataa in ["Подобова оренда", "Оренда", "Продаж"]:
        context.user_data["template_type"] = callback_dataa
        context.user_data["application_step"] = 1  # Move to the first step
        await submit_application(update, context)
        return

    # Handle options selection within steps
    if context.user_data.get("application_step", 0) > 0:
        step = context.user_data["application_step"]
        if callback_dataa == "confirm":
            context.user_data["application_step"] += 1  # Move to the next step
        elif callback_dataa == "back":
            context.user_data["application_step"] = max(0, step - 1)  # Go to the previous step
        else:
            context.user_data[f"selected_step_{step}"] = callback_dataa  # Save the selected option
        await submit_application(update, context)
        return


    if query.data == "continue_browsing":
        # If filters are available, show properties directly
        if context.user_data.get("selected_locations"):
            await filter_apartments(update, context)  # Show results immediately
        else:
            # If no filters, start a new search
            await query.edit_message_text(
                "No saved filters found. Starting a new search." if lang == "en" else
                "Немає збережених фільтрів. Почніть новий пошук."
            )
            await filter_properties(update, context)
        return

    # Handle "Request a Call" - Save Apartment ID Before Requesting Contact
    if callback_dataa == "request_call":
        apartment_id = context.user_data.get("current_apartment_id")  # Retrieve current apartment ID
        if apartment_id:
            context.user_data["request_call_apartment_id"] = apartment_id  # Save the ID for the order
            context.user_data["manager_help_requested"] = False  # Ensure this is not a manager help request
            await request_contact(update, context)  # Request user contact details
        else:
            await query.message.reply_text(
                "❌ Error: No apartment selected!" if language == "en" else "❌ Помилка: Квартира не вибрана!"
            )
        return


    if query.data == "save_subscription":
        await save_subscription(update, context)
        return  # Stop further processing for this callback
    elif query.data == "skip_subscription":
        await skip_subscription(update, context)
        return  # Stop further processing for this callback
    elif query.data == "my_subscription":  # Handle My Subscription 🟡 button
        await manage_subscription(update, context)
        return

    elif query.data == "change_subscription":
        print("Changing subscription...")
        await change_subscription(update, context)
    elif query.data == "stop_subscription":
        print("Stopping subscription...")
        await stop_subscription(update, context)
    elif query.data == "delete_subscription":
        print("Deleting subscription...")
        await delete_subscription(update, context)


    # Handle callback query data
    if query.data == "city_or_region":
        await filter_properties(update, context)  # Search for Real Estate
    elif query.data == "show_saved_ads":
        await show_saved_ads(update, context)  # Show Saved Ads
        return




    if query.data == "next":
        current_index = context.user_data["current_apartment_index"]
        filtered_apartments = context.user_data.get("filtered_apartments", [])
        if current_index < len(filtered_apartments) - 1:
            context.user_data["current_apartment_index"] += 1
            await show_apartment(update, context)
        else:
            await query.edit_message_text("No more properties to show." if lang == "en" else "Більше немає об'єктів для перегляду.")

    elif query.data == "remove_saved":
        current_index = context.user_data["current_saved_index"]
        saved_ads = context.user_data.get("saved_ads", [])

        if saved_ads and current_index < len(saved_ads):
            removed_ad = saved_ads.pop(current_index)
            await query.edit_message_text(f"Property #{removed_ad['id']} removed from saved." if lang == "en" else f"Властивість #{removed_ad['id']} вилучено зі списку збереження.")

            if saved_ads:
                context.user_data["current_saved_index"] = min(current_index, len(saved_ads) - 1)
                await show_saved_ad(update, context)
            else:
                await update.callback_query.message.reply_text("You have no more saved ads." if lang == "en" else "У вас більше немає збережених оголошень.")

    if query.data == "saved_previous":
        # Move to the previous saved ad if it exists
        context.user_data["current_saved_index"] = max(0, context.user_data["current_saved_index"] - 1)
        await show_saved_ad(update, context)

    elif query.data == "saved_next":
        # Move to the next saved ad if it exists
        saved_ads = context.user_data.get("saved_ads", [])
        context.user_data["current_saved_index"] = min(
            len(saved_ads) - 1, context.user_data["current_saved_index"] + 1
        )
        await show_saved_ad(update, context)

    elif query.data == "show_3_saved_ads":
        # Show up to three saved ads starting from the current index
        current_index = context.user_data.get("current_saved_index", 0)
        saved_ads = context.user_data.get("saved_ads", [])

        for i in range(current_index, min(current_index + 3, len(saved_ads))):
            context.user_data["current_saved_index"] = i  # Update index before each ad
            await show_saved_ad(update, context)

        # Set current index to the last of the three ads shown (or max available)
        context.user_data["current_saved_index"] = min(current_index + 3, len(saved_ads) - 1)


    elif query.data == "previous":
        # Decrease index and show previous apartment
        context.user_data["current_apartment_index"] = max(0, context.user_data["current_apartment_index"] - 1)
        await show_apartment(update, context)

    elif query.data == "show_3_ads":
        # Get the starting index
        current_index = context.user_data.get("current_apartment_index", 0)
        filtered_apartments = context.user_data["filtered_apartments"]

        # Display up to three apartments starting from the current index
        for i in range(current_index, min(current_index + 3, len(filtered_apartments))):
            await show_apartment(update, context, index=i)

        # Update the index to the next apartment after the displayed ones
        context.user_data["current_apartment_index"] = min(current_index + 3, len(filtered_apartments) - 1)


    elif query.data == "save":
        current_index = context.user_data.get("current_apartment_index", 0)
        apartment = context.user_data["filtered_apartments"][current_index]

        if "saved_ads" not in context.user_data:
            context.user_data["saved_ads"] = []

        if apartment not in context.user_data["saved_ads"]:
            context.user_data["saved_ads"].append(apartment)
            await query.answer("✅ Property saved successfully!")
        else:
            await query.answer("❗ Property is already saved.")

        return  # Ensure the button stays



    elif query.data == "back":
        await handle_back(update, context)
        return


    elif query.data == "back":
        step = context.user_data.get("step")
        if step == FILTER_STEPS["city_or_region"]:  # Якщо в меню фільтрації -> повертаємось в головне меню
            await show_main_menu(update, context)

        # Якщо користувач був у виборі міст, повертаємо його до районів
        if context.user_data.get("showing_cities", False):
            context.user_data["showing_cities"] = False
            await ask_for_locations(query, context, show_cities=False)
        
        # Якщо був у виборі районів, повертаємо до попереднього фільтру
        elif step == FILTER_STEPS["location_date"]:
            await filter_properties(query, context)  # Повертаємо на вибір типу пошуку
        
        else:
            await go_to_previous_step(query, context)


    # Retrieve the current state of showing cities; default to False if not set
    show_cities = context.user_data.get("showing_cities", False)

    if query.data == "back_to_districts":
        # Handle going back to the district selection view
        context.user_data["showing_cities"] = False  # Reset the state to allow district selection
        await handle_back_to_districts(update, context)

    elif query.data.startswith("location_"):
        # Toggle selection of a district or city based on current step
        selected_location = query.data.split("_")[-1]

        # Toggle selection based on the current step (districts or cities)
        if show_cities:
            # Toggle city selection
            await ask_for_locations(query, context, selected_location, show_cities=True)
        else:
            # Toggle district selection
            await ask_for_locations(query, context, selected_location, show_cities=False)


    elif query.data == "apply_location":
        # Retrieve user data
        selected_suburbs = context.user_data.get("selected_suburbs", [])
        selected_districts = context.user_data.get("selected_districts", [])
        selected_cities = context.user_data.get("selected_cities", [])
        city_mode = context.user_data.get("city_or_region") == "city"
        show_cities = context.user_data.get("showing_cities", False)
        language = context.user_data.get("language", "en")

        combined_locations = selected_suburbs + selected_cities + selected_districts

        if combined_locations:
            # Save all selected locations
            context.user_data["location_date"] = combined_locations
            context.user_data["selected_locations"] = combined_locations
            context.user_data["showing_cities"] = False

            # Proceed to the next filter step (deal types)
            await ask_for_deal_types(query, context)
        else:
            # If no selection was made, prompt the user
            await query.answer(
                "Please select at least one location before applying."
                if language == "en" else "Будь ласка, виберіть хоча б одне місце перед застосуванням."
            )





    elif query.data == "apply_residential_complex":
        selected_complexes = context.user_data.get("selected_complexes", [])
        if selected_complexes:
            # Move forward to the rooms step only after applying residential complexes
            context.user_data["step"] = FILTER_STEPS["rooms"]
            await ask_for_rooms(query, context)
        else:
            await query.answer("Please select at least one complex before applying.")


    # Handle budget selection toggle
    elif query.data.startswith("budget_"):
        selected_budget = query.data.split("_")[-1]
        selected_budgets = context.user_data.get("selected_budgets", [])

        # Toggle the budget selection (add or remove)
        if selected_budget in selected_budgets:
            selected_budgets.remove(selected_budget)
        else:
            selected_budgets.append(selected_budget)
        context.user_data["selected_budgets"] = selected_budgets

        # Re-render the budget selection menu with updated check marks
        await ask_for_budget(query, context)


    if step == FILTER_STEPS["city_or_region"]:
        context.user_data["city_or_region"] = query.data
        await ask_for_locations(query, context)

    elif step == FILTER_STEPS["type_deal"]:
        context.user_data["type_deal"] = query.data
        await ask_for_property_types(query, context)

    if step == FILTER_STEPS["type_object"]:
        # Toggle the selected property type without moving to the next step
        selected_type = query.data.split("_")[-1]
        selected_types = context.user_data.get("type_object_selection", [])

        # Toggle selection (add or remove the property type)
        if selected_type in selected_types:
            selected_types.remove(selected_type)
        else:
            selected_types.append(selected_type)
        context.user_data["type_object_selection"] = selected_types

        # Re-render the property type selection with updated check marks
        await ask_for_property_types(query, context)

    elif step == FILTER_STEPS["residential_complex"]:
        selected_complex = query.data.split("_")[-1]
        await ask_for_residential_complexes(query, context, selected_complex)

    elif query.data == "apply_rooms":
        context.user_data["step"] = FILTER_STEPS["budget"]
        await ask_for_budget(query, context)

    # Apply budget selection and proceed to filtering apartments
    elif query.data == "apply_budget":
        context.user_data["step"] = FILTER_STEPS["budget"]
        await filter_apartments(update, context)
    # Handle "Apply" button click for property types
    elif query.data == "apply_type_object":
        # Save selected property types
        selected_types = [
            button.callback_data.split("_")[-1]
            for button_row in context.user_data.get("property_buttons", [])
            for button in button_row
            if button.text.endswith("✔️")
        ]
        context.user_data["type_object_selection"] = selected_types

        # Move to the residential complex selection step
        context.user_data["step"] = FILTER_STEPS["residential_complex"]
        await ask_for_residential_complexes(query, context)



    # Handle Residential Complex selection and Apply
    if query.data == "apply_residential_complex":
        selected_complexes = context.user_data.get("selected_complexes", [])
        
        if selected_complexes:
            # Move forward to the rooms step after applying residential complexes
            context.user_data["step"] = FILTER_STEPS["rooms"]
            await ask_for_rooms(query, context)
        else:
            await query.answer("Please select at least one complex before applying.")

    # Handle Room selection and Apply
    elif step == FILTER_STEPS["rooms"] and query.data.startswith("room_"):
        selected_room = query.data.split("_")[-1]
        selected_rooms = context.user_data.get("selected_rooms", [])

        # Toggle the room selection (add or remove)
        if selected_room in selected_rooms:
            selected_rooms.remove(selected_room)
        else:
            selected_rooms.append(selected_room)
        context.user_data["selected_rooms"] = selected_rooms

        # Re-render the room selection menu with updated check marks
        await ask_for_rooms(query, context)  # Stay on room selection until "Apply" is clicked



async def handle_back(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    step = context.user_data.get("step")
    # Go back to previous step if possible
    if step > 1:
        context.user_data["step"] = step - 1
        await go_to_previous_step(query, context)
    else:
        # Якщо повернутися неможливо, відображаємо головне меню
        await show_main_menu(update, context)

async def button_click_apply(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()

    # Save selected property types (those with "✔️" in the text)
    selected_types = [
        button.callback_data.split("_")[-1]
        for button_row in context.user_data.get("property_buttons", [])
        for button in button_row
        if button.text.endswith("✔️")
    ]
    context.user_data["type_object_selection"] = selected_types

    # Set the step to residential_complex and ask for residential complexes
    context.user_data["step"] = FILTER_STEPS["residential_complex"]
    await ask_for_residential_complexes(query, context)


# Helper function to navigate to the previous step
async def go_to_previous_step(query, context):
    step = context.user_data.get("step")
    if step == FILTER_STEPS["city_or_region"]:
        await filter_properties(query, context)
    elif step == FILTER_STEPS["location_date"]:
        await ask_for_locations(query, context)
    elif step == FILTER_STEPS["type_deal"]:
        await ask_for_deal_types(query, context)
    elif step == FILTER_STEPS["type_object"]:
        await ask_for_property_types(query, context)
    elif step == FILTER_STEPS["residential_complex"]:
        await ask_for_residential_complexes(query, context)    
    elif step == FILTER_STEPS["rooms"]:
        await ask_for_rooms(query, context)

async def ask_for_locations(query, context, selected_location=None, show_cities=False):
    try:
        # Fetch data from your API
        response = requests.get('http://127.0.0.1:8000/get_orders_and_photo/')
        response.raise_for_status()
        apartments_data = response.json()
        language = context.user_data.get("language", "en")

        # Handle suburbs selection
        if context.user_data.get("city_or_region") == "suburbs":
            suburbs_list = [
                "Малехів", "Грибовичі", "Дубляни", "Сокільники", "Солонка",
                "Зубра", "Рудно", "Лапаївка", "Зимна Вода", "Винники",
                "Підберізці", "Лисиничі", "Давидів", "Підгірці"
            ]

            # Normalize and match suburbs
            matching_suburbs = [
                suburb for suburb in suburbs_list
                if any(suburb.lower() in apt.get("location_date", "").lower() for apt in apartments_data)
            ]

            selected_suburbs = context.user_data.get("selected_suburbs", [])

            # Toggle selection
            if selected_location is not None and selected_location.isdigit():
                suburb_index = int(selected_location)
                if suburb_index < len(matching_suburbs):
                    suburb_name = matching_suburbs[suburb_index]
                    if suburb_name in selected_suburbs:
                        selected_suburbs.remove(suburb_name)
                    else:
                        selected_suburbs.append(suburb_name)
                    context.user_data["selected_suburbs"] = selected_suburbs

            # Create buttons for suburbs
            buttons = [
                [InlineKeyboardButton(f"{suburb} {'✔️' if suburb in selected_suburbs else ''}", callback_data=f"location_{index}")]
                for index, suburb in enumerate(matching_suburbs)
            ]

            # Add Apply and Back buttons
            if matching_suburbs:
                buttons.append([
                    InlineKeyboardButton("Apply" if language == "en" else "Застосувати", callback_data="apply_location"),
                    InlineKeyboardButton("Back" if language == "en" else "Назад", callback_data="back")
                ])
            else:
                buttons.append([
                    InlineKeyboardButton("Back" if language == "en" else "Назад", callback_data="back")
                ])

            # Render the keyboard
            await query.edit_message_text(
                "Please select one or more suburbs:" if language == "en" else "Оберіть одне або кілька передмість:",
                reply_markup=InlineKeyboardMarkup(buttons)
            )
            context.user_data["step"] = FILTER_STEPS["location_date"]
            return

        # Other location types (city or region) processing remains unchanged
        # The rest of your location handling code goes here...



        # Determine if the user wants cities or regions
        city_mode = context.user_data.get("city_or_region") == "city"
        # If the user is in "Region" mode, handle district selection or show cities within selected districts
        if not city_mode:
            selected_districts = context.user_data.get("selected_districts", [])
            context.user_data["showing_cities"] = show_cities  # Track if cities are being shown

            if not show_cities:
                # Step 1: Display unique districts for selection
                districts = sorted(set(
                    [apt['location_date'].split(", ")[0] for apt in apartments_data if "район" in apt['location_date']]
                ))

                # Toggle selection for a specific district if selected_location is provided
                if selected_location is not None and selected_location.isdigit():
                    district = districts[int(selected_location)]
                    if district in selected_districts:
                        selected_districts.remove(district)
                    else:
                        selected_districts.append(district)
                    context.user_data["selected_districts"] = selected_districts

                # Create buttons for each district with check marks for selected districts
                buttons = [
                    [InlineKeyboardButton(f"{district} {'✔️' if district in selected_districts else ''}", callback_data=f"location_{index}")]
                    for index, district in enumerate(districts)
                ]

                # Add the "Apply" and "Back" buttons
                buttons.append([
                    InlineKeyboardButton("Apply" if language == "en" else "Застосувати", callback_data="apply_location"),
                    InlineKeyboardButton("Back" if language == "en" else "Назад", callback_data="back")
                ])
                keyboard = InlineKeyboardMarkup(buttons)

                # Prompt user to select districts
                await query.edit_message_text(
                    "Please select one or more districts:" if language == "en" else "Оберіть один або кілька районів:",
                    reply_markup=keyboard
                )

            else:
                # Step 2: Display cities within the selected districts, but store "District, City" format
                selected_cities = context.user_data.get("selected_cities", [])

                # Filter for cities within the selected districts
                cities_in_districts = sorted(set(
                    (apt['location_date'].split(", ")[0], apt['location_date'].split(", ")[1])  # (District, City)
                    for apt in apartments_data
                    if any(district in apt['location_date'] for district in selected_districts)
                ))

                # Ensure that there are cities to display
                if not cities_in_districts:
                    await query.edit_message_text(
                        "No cities available for the selected districts. Please go back and select other districts."
                        if language == "en" else
                        "Немає міст для вибраних районів. Будь ласка, поверніться і оберіть інші райони."
                    )
                    return

                # Toggle selection for a specific city if provided
                if selected_location is not None and selected_location.isdigit():
                    city_index = int(selected_location)
                    if city_index < len(cities_in_districts):
                        district_city = list(cities_in_districts)[city_index]  # Convert set to list for indexing
                        full_location = f"{district_city[0]}, {district_city[1]}"
                        if full_location in selected_cities:
                            selected_cities.remove(full_location)
                        else:
                            selected_cities.append(full_location)
                        context.user_data["selected_cities"] = selected_cities

                # Create buttons displaying only city names, but storing full format in context
                buttons = [
                    [InlineKeyboardButton(f"{city} {'✔️' if f'{district}, {city}' in selected_cities else ''}", callback_data=f"location_{index}")]
                    for index, (district, city) in enumerate(cities_in_districts)
                ]

                # Add the "Apply" and "Back to Districts" buttons
                buttons.append([
                    InlineKeyboardButton("Apply" if language == "en" else "Застосувати", callback_data="apply_location"),
                    InlineKeyboardButton("Back to Districts" if language == "en" else "Назад до районів", callback_data="back_to_districts")
                ])
                keyboard = InlineKeyboardMarkup(buttons)

                # Prompt user to select cities within the districts
                await query.edit_message_text(
                    "Please select one or more cities within the selected districts:"
                    if language == "en" else
                    "Оберіть одне або кілька міст у вибраних районах:",
                    reply_markup=keyboard
                )

        else:
            # City mode: Filter and display city locations directly
            unique_locations = sorted(set(
                [apt['location_date'] for apt in apartments_data if "Львів" in apt['location_date']]
            ))

            # Retrieve or update the list of selected locations
            selected_locations = context.user_data.get("selected_locations", [])

            # Toggle selection for a specific location if provided
            if selected_location is not None and selected_location.isdigit():
                location_index = int(selected_location)
                if location_index < len(unique_locations):
                    location_name = unique_locations[location_index]
                    if location_name in selected_locations:
                        selected_locations.remove(location_name)
                    else:
                        selected_locations.append(location_name)
                    context.user_data["selected_locations"] = selected_locations

            # Create buttons for each location with check marks
            buttons = [
                [InlineKeyboardButton(f"{location} {'✔️' if location in selected_locations else ''}", callback_data=f"location_{index}")]
                for index, location in enumerate(unique_locations)
            ]

            # Add the "Apply" and "Back" buttons
            buttons.append([
                InlineKeyboardButton("Apply" if language == "en" else "Застосувати", callback_data="apply_location"),
                InlineKeyboardButton("Back" if language == "en" else "Назад", callback_data="back")
            ])
            keyboard = InlineKeyboardMarkup(buttons)

            # Prompt user to select locations
            await query.edit_message_text(
                "Please select one or more locations:" if language == "en" else "Оберіть одне або кілька місць:",
                reply_markup=keyboard
            )

        # Update the user's current step
        context.user_data["step"] = FILTER_STEPS["location_date"]

    except requests.exceptions.RequestException as e:
        logging.error(f"Error fetching locations: {e}")
        await query.edit_message_text(
            "Sorry, there was an error retrieving the locations."
            if language == "en" else
            "На жаль, сталася помилка під час отримання місць."
        )




async def handle_district_selection(update, context):
    query = update.callback_query
    selected_district_index = int(query.data.split("_")[-1])
    await ask_for_locations(query, context, selected_location=selected_district_index)

async def handle_city_selection(update, context):
    query = update.callback_query
    selected_city_index = int(query.data.split("_")[-1])
    await ask_for_locations(query, context, selected_location=selected_city_index)

async def handle_apply_location(update, context):
    query = update.callback_query
    language = context.user_data.get("language", "en")

    # Retrieve selected locations
    selected_suburbs = context.user_data.get("selected_suburbs", [])
    selected_districts = context.user_data.get("selected_districts", [])
    selected_cities = context.user_data.get("selected_cities", [])

    # Combine all selected locations
    combined_locations = selected_suburbs + selected_districts + selected_cities

    if combined_locations:
        # Save combined locations for filtering
        context.user_data["selected_locations"] = combined_locations
        context.user_data["location_date"] = combined_locations

        # Provide feedback to the user
        selected_locations_text = ', '.join(combined_locations)
        await query.edit_message_text(
            f"Selected Locations: {selected_locations_text}" if language == "en" else f"Вибрані місця: {selected_locations_text}"
        )

        # Proceed to the next filter step (e.g., deal types)
        await ask_for_deal_types(query, context)
    else:
        # If no locations were selected, prompt the user
        await query.answer(
            "Please select at least one location before applying."
            if language == "en" else "Будь ласка, виберіть хоча б одне місце перед застосуванням."
        )






DEAL_TYPE_TRANSLATIONS = {
    'posutochno-pochasovo': {
        'en': 'Per Day/Hourly Rent',
        'uk': 'Погодинна/Подобова оренда'
    },
    'kvartiry': {
        'en': 'Apartments',
        'uk': 'Квартири'
    },
    'doma': {
        'en': 'Houses',
        'uk': 'Будинки'
    }
}

PROPERTY_TYPE_TRANSLATIONS = {
    'posutochno-pochasovo-doma': {
        'en': 'Per Day Rent of a House',
        'uk': 'Подобова оренда будинку'
    },
    'posutochno-pochasovo-kvartiry': {
        'en': 'Per Day Rent of an Apartment',
        'uk': 'Подобова оренда квартири'
    },
    'dolgosrochnaya-arenda-kvartir': {
        'en': 'Long-term Rent of an Apartment',
        'uk': 'Довгострокова оренда квартири'
    },
    'arenda-domov': {
        'en': 'Rent of Houses',
        'uk': 'Оренда будинків'
    },
    'prodazha-kvartir': {
        'en': 'Sale of Apartments',
        'uk': 'Продаж квартир'
    },
    'prodazha-domov': {
        'en': 'Sale of Houses',
        'uk': 'Продаж будинків'
    }
}
async def handle_back_to_districts(update, context):
    query = update.callback_query
    language = context.user_data.get("language", "en")

    # Reset the state to show districts
    context.user_data["showing_cities"] = False
    context.user_data["selected_cities"] = []  # Clear selected cities
    context.user_data["selected_suburbs"] = []  # Optionally clear suburbs if needed

    # Call `ask_for_locations` to display districts or suburbs again
    await ask_for_locations(query, context, show_cities=False)
async def ask_for_deal_types(query, context):
    try:
        # Fetch apartment data from your API
        response = requests.get('http://127.0.0.1:8000/get_orders_and_photo/')
        response.raise_for_status()
        apartments_data = response.json()

        # Retrieve selected locations (now a list)
        selected_locations = context.user_data.get("selected_locations", [])
        language = context.user_data.get("language", "en")

        # Get unique deal types for selected locations
        unique_deal_types = list(set(
            apt['type_deal'] for apt in apartments_data if any(loc in apt['location_date'] for loc in selected_locations)
        ))

        # Generate buttons with translated labels
        deal_buttons = [
            [InlineKeyboardButton(DEAL_TYPE_TRANSLATIONS[deal][language], callback_data=deal)]
            for deal in unique_deal_types if deal in DEAL_TYPE_TRANSLATIONS
        ]

        deal_buttons.append([InlineKeyboardButton("Back" if language == "en" else "Назад", callback_data="back")])
        keyboard = InlineKeyboardMarkup(deal_buttons)

        # Prompt user for deal type selection
        await query.edit_message_text(
            "Would you like to buy or rent?" if language == "en" else "Ви хочете купити чи орендувати?",
            reply_markup=keyboard
        )
        context.user_data["step"] = FILTER_STEPS["type_deal"]

    except requests.exceptions.RequestException as e:
        logging.error(f"Error fetching deal types: {e}")
        await query.edit_message_text(
            "Sorry, there was an error retrieving the deal types."
            if language == "en" else "На жаль, сталася помилка під час отримання типів угод."
        )

async def ask_for_property_types(query, context, selected_type=None):
    try:
        response = requests.get('http://127.0.0.1:8000/get_orders_and_photo/')
        response.raise_for_status()
        apartments_data = response.json()

        selected_locations = context.user_data.get("selected_locations", [])
        selected_deal_type = context.user_data.get("type_deal")
        language = context.user_data.get("language", "en")

        unique_property_types = list(set([
            apt['type_object'] for apt in apartments_data
            if any(loc in apt['location_date'] for loc in selected_locations) and apt['type_deal'] == selected_deal_type
        ]))

        selected_types = context.user_data.get("type_object_selection", [])

        # Toggle selection if a specific type is provided
        if selected_type:
            if selected_type in selected_types:
                selected_types.remove(selected_type)
            else:
                selected_types.append(selected_type)
            context.user_data["type_object_selection"] = selected_types

        buttons = [
            [InlineKeyboardButton(f"{PROPERTY_TYPE_TRANSLATIONS[pt][language]} {'✔️' if pt in selected_types else ''}", callback_data=f"type_object_{pt}")]
            for pt in unique_property_types if pt in PROPERTY_TYPE_TRANSLATIONS
        ]

        buttons.append([
            InlineKeyboardButton("Apply" if language == "en" else "Застосувати", callback_data="apply_type_object"),
            InlineKeyboardButton("Back" if language == "en" else "Назад", callback_data="back")
        ])
        keyboard = InlineKeyboardMarkup(buttons)

        await query.edit_message_text(
            "Select the property types you are interested in:"
            if language == "en" else "Виберіть типи нерухомості, які вас цікавлять:",
            reply_markup=keyboard
        )
        context.user_data["step"] = FILTER_STEPS["type_object"]

    except requests.exceptions.RequestException as e:
        logging.error(f"Error fetching property types: {e}")
        await query.edit_message_text(
            "Sorry, there was an error retrieving the property types."
            if language == "en" else "На жаль, сталася помилка під час отримання типів нерухомості."
        )

async def ask_for_residential_complexes(query, context, selected_complex=None):
    try:
        # Fetch apartment data from API
        response = requests.get('http://127.0.0.1:8000/get_orders_and_photo/')
        response.raise_for_status()
        apartments_data = response.json()

        # Retrieve selected locations, deal type, and property types
        selected_locations = context.user_data.get("selected_locations", [])
        selected_deal_type = context.user_data.get("type_deal")
        selected_type_objects = context.user_data.get("type_object_selection", [])
        language = context.user_data.get("language", "en")

        # Extract unique residential complexes for the selected filters
        unique_residential_complexes = list(set(
            apt['residential_complex'] for apt in apartments_data
            if any(loc in apt['location_date'] for loc in selected_locations)
            and apt['type_deal'] == selected_deal_type
            and apt['type_object'] in selected_type_objects
        ))

        # Ensure "All Complexes" is an option, handling empty/null values
        if None in unique_residential_complexes:
            unique_residential_complexes.remove(None)
        unique_residential_complexes.insert(0, "All Complexes")  # Add "All Complexes" at the beginning

        # Retrieve selected residential complexes
        selected_complexes = context.user_data.get("selected_complexes", [])

        # Toggle selection if a complex was clicked
        if selected_complex is not None and selected_complex.isdigit():
            complex_index = int(selected_complex)
            if complex_index < len(unique_residential_complexes):
                complex_name = unique_residential_complexes[complex_index]

                # Toggle selection
                if complex_name in selected_complexes:
                    selected_complexes.remove(complex_name)
                else:
                    selected_complexes.append(complex_name)

                # Special behavior: If "All Complexes" is selected, clear other selections
                if complex_name == "All Complexes":
                    selected_complexes = ["All Complexes"]

                # Save updated selections
                context.user_data["selected_complexes"] = selected_complexes

        # Create buttons with checkmarks for selected complexes
        buttons = [
            [InlineKeyboardButton(
                f"{complex if complex else ('All Complexes' if language == 'en' else 'Всі Комплекси')} {'✔️' if complex in selected_complexes else ''}",
                callback_data=f"complex_{index}"
            )]
            for index, complex in enumerate(unique_residential_complexes)
        ]

        # Add Apply and Back buttons
        buttons.append([
            InlineKeyboardButton("Apply" if language == "en" else "Застосувати", callback_data="apply_residential_complex"),
            InlineKeyboardButton("Back" if language == "en" else "Назад", callback_data="back")
        ])
        keyboard = InlineKeyboardMarkup(buttons)

        # Define the message text
        message_text = (
            "Select the residential complex you are interested in:"
            if language == "en" else
            "Оберіть житловий комплекс, який вас цікавить:"
        )

        # Use safe edit function
        await edit_message_safely(query, message_text, keyboard)

        # Update step to residential_complex
        context.user_data["step"] = FILTER_STEPS["residential_complex"]

    except requests.exceptions.RequestException as e:
        logging.error(f"Error fetching residential complexes: {e}")
        await query.edit_message_text(
            "Sorry, there was an error retrieving the residential complexes."
            if language == "en" else
            "На жаль, сталася помилка під час отримання житлових комплексів."
        )



async def edit_message_safely(query, new_text, new_reply_markup):
    """
    Safely edits a message if the content or reply markup is different.
    """
    try:
        if query.message.text != new_text or query.message.reply_markup != new_reply_markup:
            await query.edit_message_text(new_text, reply_markup=new_reply_markup)
        else:
            await query.answer("No changes to display.")  # Notify the user if there's no change
    except Exception as e:
        logging.error(f"Error in edit_message_safely: {e}")

async def ask_for_rooms(query, context, selected_room=None):
    try:
        # Retrieve selected filters from context
        selected_locations = context.user_data.get("selected_locations", [])
        selected_deal_type = context.user_data.get("type_deal")
        selected_type_objects = context.user_data.get("type_object_selection", [])
        selected_rooms = context.user_data.get("selected_rooms", [])
        language = context.user_data.get("language", "en")

        # Fetch apartment data from API
        response = requests.get('http://127.0.0.1:8000/get_orders_and_photo/')
        response.raise_for_status()
        apartments_data = response.json()

        # Extract unique room options from the filtered apartments
        unique_rooms = sorted(set(
            apt['room'] for apt in apartments_data
            if any(loc in apt['location_date'] for loc in selected_locations)
            and apt['type_deal'] == selected_deal_type
            and apt['type_object'] in selected_type_objects
        ), key=lambda x: (x.isdigit(), x))  # Sort numbers first, then other options

        # Ensure unique_rooms has a fallback default
        if not unique_rooms:
            unique_rooms = ["1", "2", "3", "4", "5+"]

        # Toggle selection if a room was clicked
        if selected_room:
            if selected_room in selected_rooms:
                selected_rooms.remove(selected_room)
            else:
                selected_rooms.append(selected_room)

            # Save updated selection
            context.user_data["selected_rooms"] = selected_rooms

        # Create buttons for room selection with checkmarks
        buttons = [
            [InlineKeyboardButton(
                f"{room} Room(s) {'✔️' if room in selected_rooms else ''}"
                if language == "en"
                else f"{room} Кімната(и) {'✔️' if room in selected_rooms else ''}",
                callback_data=f"room_{room}"
            )]
            for room in unique_rooms
        ]

        # Add the "Apply" and "Back" buttons
        buttons.append([
            InlineKeyboardButton("Apply" if language == "en" else "Застосувати", callback_data="apply_rooms"),
            InlineKeyboardButton("Back" if language == "en" else "Назад", callback_data="back")
        ])

        keyboard = InlineKeyboardMarkup(buttons)

        # Define the message text
        message_text = (
            "How many rooms are you looking for?"
            if language == "en"
            else "Скільки кімнат ви шукаєте?"
        )

        # Use safe edit function to prevent unnecessary Telegram errors
        await edit_message_safely(query, message_text, keyboard)

        # Update the user's current step to "rooms"
        context.user_data["step"] = FILTER_STEPS["rooms"]

    except requests.exceptions.RequestException as e:
        logging.error(f"Error fetching room options: {e}")
        await query.edit_message_text(
            "Sorry, there was an error retrieving the room options."
            if language == "en"
            else "На жаль, сталася помилка під час отримання варіантів кімнат."
        )



UAH_TO_USD_RATE = 41.50  # Fixed exchange rate, update as needed

# Function to convert UAH to USD
def convert_to_usd(price_str):
    clean_price_str = re.sub(r'[^\d]', '', price_str)
    price = int(clean_price_str) if clean_price_str else 0

    # Check if the price is in UAH (often represented with 'грн')
    if 'грн' in price_str:
        return price / UAH_TO_USD_RATE  # Convert to USD
    return price  # Assume it's already in USD if no currency indicator

async def safe_edit_message(query, text, reply_markup=None):
    """
    Safely edit a message only if the content or reply markup is different.
    """
    try:
        current_text = query.message.text if query.message else None
        current_reply_markup = query.message.reply_markup if query.message else None

        # Compare new content with current content
        if current_text != text or current_reply_markup != reply_markup:
            await query.edit_message_text(text, reply_markup=reply_markup)
        else:
            await query.answer("No changes to display.")  # Optional user feedback
    except telegram.error.BadRequest as e:
        if "message is not modified" in str(e).lower():
            logging.warning("Attempted to modify message with identical content.")
        else:
            logging.error(f"Failed to edit message: {e}")
        
async def ask_for_budget(query, context, selected_budget=None):
    try:
        # Retrieve selected property types and current budget selections
        selected_type_objects = context.user_data.get("type_object_selection", [])
        selected_budgets = context.user_data.get("selected_budgets", [])
        language = context.user_data.get("language", "en")

        # Toggle selection if a budget option was clicked
        if selected_budget:
            if selected_budget in selected_budgets:
                selected_budgets.remove(selected_budget)
            else:
                selected_budgets.append(selected_budget)
            context.user_data["selected_budgets"] = selected_budgets  # Save updated selection

        # Define different budget options based on property type selection
        budget_options = []
        if any(pt in selected_type_objects for pt in ["dolgosrochnaya-arenda-kvartir", "arenda-domov"]):
            # Long-term rental budget
            budget_options = [
                [InlineKeyboardButton(f"Up to $400 / 16,600 грн {'✔️' if '400' in selected_budgets else ''}", callback_data="budget_400"),
                 InlineKeyboardButton(f"$400 - $450 / 16,600 - 18,675 грн {'✔️' if '450' in selected_budgets else ''}", callback_data="budget_450")],
                [InlineKeyboardButton(f"$450 - $650 / 18,675 - 26,975 грн {'✔️' if '650' in selected_budgets else ''}", callback_data="budget_650"),
                 InlineKeyboardButton(f"$650 - $800 / 26,975 - 33,200 грн {'✔️' if '800' in selected_budgets else ''}", callback_data="budget_800")],
                [InlineKeyboardButton(f"Over $800 / 33,200 грн {'✔️' if 'over' in selected_budgets else ''}", callback_data="budget_over")]
            ]
        elif any(pt in selected_type_objects for pt in ["prodazha-domov", "prodazha-kvartir"]):
            # Property sales budget
            budget_options = [
                [InlineKeyboardButton(f"Up to $50,000 / 1,800,000 грн {'✔️' if '50000' in selected_budgets else ''}", callback_data="budget_50000")],
                [InlineKeyboardButton(f"$50,000 - $100,000 / 1,800,000 - 3,600,000 грн {'✔️' if '100000' in selected_budgets else ''}", callback_data="budget_100000")],
                [InlineKeyboardButton(f"$100,000 - $200,000 / 3,600,000 - 7,200,000 грн {'✔️' if '200000' in selected_budgets else ''}", callback_data="budget_200000")],
                [InlineKeyboardButton(f"Over $200,000 / 7,200,000 грн {'✔️' if 'over' in selected_budgets else ''}", callback_data="budget_over")]
            ]
        elif any(pt in selected_type_objects for pt in ["posutochno-pochasovo-doma", "posutochno-pochasovo-kvartiry"]):
            # Short-term rental budget
            budget_options = [
                [InlineKeyboardButton(f"$10 - $20 / 415 - 830 грн {'✔️' if '20' in selected_budgets else ''}", callback_data="budget_20"),
                 InlineKeyboardButton(f"$20 - $30 / 830 - 1,245 грн {'✔️' if '30' in selected_budgets else ''}", callback_data="budget_30")],
                [InlineKeyboardButton(f"$30 - $50 / 1,245 - 2,075 грн {'✔️' if '50' in selected_budgets else ''}", callback_data="budget_50"),
                 InlineKeyboardButton(f"Over $50 / 2,075 грн {'✔️' if 'over' in selected_budgets else ''}", callback_data="budget_over")]
            ]
        else:
            # Default rental case if no valid property type is selected
            budget_options = [
                [InlineKeyboardButton(f"Up to $400 / 14,400 грн {'✔️' if '400' in selected_budgets else ''}", callback_data="budget_400"),
                 InlineKeyboardButton(f"$400 - $450 / 14,400 - 16,200 грн {'✔️' if '450' in selected_budgets else ''}", callback_data="budget_450")],
                [InlineKeyboardButton(f"$450 - $650 / 16,200 - 23,400 грн {'✔️' if '650' in selected_budgets else ''}", callback_data="budget_650"),
                 InlineKeyboardButton(f"$650 - $800 / 23,400 - 28,800 грн {'✔️' if '800' in selected_budgets else ''}", callback_data="budget_800")],
                [InlineKeyboardButton(f"Over $800 / 28,800 грн {'✔️' if 'over' in selected_budgets else ''}", callback_data="budget_over")]
            ]

        # Add the "Apply" and "Back" buttons
        budget_options.append([
            InlineKeyboardButton("Apply" if language == "en" else "Застосувати", callback_data="apply_budget"),
            InlineKeyboardButton("Back" if language == "en" else "Назад", callback_data="back")
        ])

        # Create the keyboard with the defined budget options
        keyboard = InlineKeyboardMarkup(budget_options)

        # Define the message text
        message_text = "What is your budget?" if language == "en" else "Який ваш бюджет?"

        # Safely update message to prevent Telegram errors
        await safe_edit_message(query, message_text, keyboard)

        # Update the user's current step to "budget"
        context.user_data["step"] = FILTER_STEPS["budget"]

    except requests.exceptions.RequestException as e:
        logging.error(f"Error fetching budget options: {e}")
        await query.edit_message_text(
            "Sorry, there was an error retrieving the budget options."
            if language == "en" else "На жаль, сталася помилка під час отримання варіантів бюджету."
        )


async def save_subscription(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    language = context.user_data.get("language", "en")
    # Save the current filter answers into subscriptions
    subscription = {
        "city_or_region": context.user_data.get("city_or_region"),
        "location_date": context.user_data.get("selected_locations", []),
        "type_deal": context.user_data.get("type_deal"),
        "type_object": context.user_data.get("type_object_selection", []),
        "residential_complex": context.user_data.get("selected_complexes", []),
        "rooms": context.user_data.get("selected_rooms", []),
        "budget": context.user_data.get("selected_budgets", [])
    }

    if "subscriptions" not in context.user_data:
        context.user_data["subscriptions"] = []

    context.user_data["subscriptions"].append(subscription)

    await query.edit_message_text("Subscription saved successfully!" if language == "en" else "Підписка успішно збережена!")
    await show_navigation_options(update, context)

def clean_price(price_str):
    clean_price_str = re.sub(r'[^\d]', '', price_str)
    return int(clean_price_str) if clean_price_str else 0 
 
async def filter_apartments(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    try:
        response = requests.get('http://127.0.0.1:8000/get_orders_and_photo/')
        response.raise_for_status()
        apartments_data = response.json()

        # Retrieve selected filters from user context
        selected_locations = context.user_data.get("selected_locations", [])
        selected_budgets = context.user_data.get("selected_budgets", [])
        selected_rooms = context.user_data.get("selected_rooms", [])
        selected_type_objects = context.user_data.get("type_object_selection", [])
        selected_residential_complexes = context.user_data.get("selected_complexes", [])
        selected_deal_type = context.user_data.get("type_deal")
        language = context.user_data.get("language", "en")

        # Debugging logs
        logging.debug(f"Selected locations: {selected_locations}")
        logging.debug(f"Selected budgets: {selected_budgets}")
        logging.debug(f"Selected rooms: {selected_rooms}")
        logging.debug(f"Selected type objects: {selected_type_objects}")
        logging.debug(f"Selected residential complexes: {selected_residential_complexes}")
        logging.debug(f"Selected deal type: {selected_deal_type}")



        def budget_in_range(price_str):
            # Convert and clean the price
            price_in_usd = convert_to_usd(price_str)

            # Match against each selected budget range
            for budget_option in selected_budgets:
                if budget_option == "400" and price_in_usd <= 400:
                    return True
                elif budget_option == "450" and 400 < price_in_usd <= 450:
                    return True
                elif budget_option == "650" and 450 < price_in_usd <= 650:
                    return True
                elif budget_option == "800" and 650 < price_in_usd <= 800:
                    return True
                elif budget_option == "20" and 10 <= price_in_usd <= 20:
                    return True
                elif budget_option == "30" and 20 < price_in_usd <= 30:
                    return True
                elif budget_option == "50" and 30 < price_in_usd <= 50:
                    return True
                elif budget_option == "over" and price_in_usd > 50:
                    return True
                elif budget_option == "over" and price_in_usd > 800:
                    return True
                elif budget_option == "50000" and price_in_usd <= 50000:
                    return True
                elif budget_option == "100000" and 50000 < price_in_usd <= 100000:
                    return True
                elif budget_option == "200000" and 100000 < price_in_usd <= 200000:
                    return True
                elif budget_option == "over" and price_in_usd > 200000:
                    return True
            return False

        # Apply filtering
        filtered_apartments = []
        for apt in apartments_data:
            apt_location = apt.get('location_date', '')  # Ensure no KeyError
            apt_price = apt.get('price', '0')
            apt_rooms = str(apt.get('room', '')).strip()
            apt_type = apt.get('type_object', '')
            apt_complex = apt.get('residential_complex', '')

            # Location Filtering (Match any selected location)
            location_match = not selected_locations or any(loc in apt_location for loc in selected_locations)

            # Type Filtering (If selected, must match)
            type_match = not selected_type_objects or apt_type in selected_type_objects

            # Room Filtering (Ensure proper format matching)
            room_match = not selected_rooms or any(room in apt_rooms for room in selected_rooms)

            # Budget Filtering (If selected, must match)
            budget_match = not selected_budgets or budget_in_range(apt_price)

            # Residential Complex Filtering (If selected, must match or be null)
            complex_match = not selected_residential_complexes or apt_complex in selected_residential_complexes or apt_complex == ""

            # Deal Type Filtering
            deal_match = apt.get('type_deal', '') == selected_deal_type

            # Check if apartment meets all conditions
            if location_match and type_match and room_match and budget_match and complex_match and deal_match:
                filtered_apartments.append(apt)

        logging.debug(f"Found {len(filtered_apartments)} apartments after filtering.")

        # If no apartments match, notify the user
        if not filtered_apartments:
            await update.callback_query.message.reply_text(
                "No apartments found matching your filters." if language == "en" else "Не знайдено квартир за вашими фільтрами."
            )
            return

        # Save filtered results and reset index
        context.user_data["filtered_apartments"] = filtered_apartments
        context.user_data["current_apartment_index"] = 0

        # Show the first matching apartment
        await show_apartment(update, context)
        await ask_to_save_subscription(update, context)

    except requests.exceptions.RequestException as e:
        logging.error(f"Error filtering apartments: {e}")
        await update.callback_query.message.reply_text(
            "Sorry, there was an error retrieving the properties."
            if language == "en" else "На жаль, сталася помилка при отриманні властивостей."
        )


def extract_features_by_category(features: str, categories: list) -> dict:
    """
    Extracts multiple feature categories from the 'features' text block and formats them as hashtags.
    
    :param features: The full multiline features string
    :param categories: List of feature categories to extract (e.g., ["Комфорт", "Мультимедіа", "Опалення"])
    :return: Dictionary with formatted strings as hashtags {category: "#feature1 #feature2 #feature3"}
    """
    extracted_features = {}

    for category in categories:
        pattern = rf"{category}:\s*(.+)"
        match = re.search(pattern, features)
        
        if match:
            # Extract text after the category label
            extracted_text = match.group(1).strip()
            # Split by comma and create hashtags
            extracted_features[f"features_{category}"] = " ".join(f"#{item.strip()}" for item in extracted_text.split(","))
        else:
            extracted_features[f"features_{category}"] = ""  # Empty string if category not found
    
    return extracted_features


def calculate_price_per_square(price_str: str, square_str: str) -> str:
    """
    Calculate the price per square meter.
    
    This function removes non-numeric characters, converts the values to floats,
    and returns the result as a formatted string. If conversion fails, returns "N/A".
    """
    try:
        # Remove any characters that are not digits or dots (adjust regex as needed)
        price_clean = re.sub(r'[^\d.]', '', price_str)
        square_clean = re.sub(r'[^\d.]', '', square_str)
        
        # Convert to floats
        price_value = float(price_clean)
        square_value = float(square_clean)
        
        if square_value == 0:
            return "N/A"
        
        price_per_sq = price_value / square_value
        # Format to 2 decimal places (adjust if necessary)
        return f"{price_per_sq:.2f}"
    except Exception as e:
        logging.error(f"Error calculating price per square meter: {e}")
        return "N/A"

def format_message(apartment, template_text, feature_categories=None):
    """
    Format message using all available attributes of an apartment.
    Also adds computed 'price_per_square' and dynamically extracted features.
    
    :param apartment: The apartment data (dict or object)
    :param template_text: The template text with placeholders
    :param feature_categories: List of feature categories to extract dynamically (e.g., ["Комфорт", "Мультимедіа"])
    """
    if isinstance(apartment, dict):
        apartment_data = {key: (apartment.get(key, "N/A") or "N/A") for key in apartment}
    else:
        apartment_data = {key: (getattr(apartment, key, "N/A") or "N/A") for key in vars(apartment)}
    
    # Compute price per square meter
    price = apartment_data.get('price_fix') if apartment_data.get('price_fix') != "N/A" else apartment_data.get('price')
    square = apartment_data.get('square_fix') if apartment_data.get('square_fix') != "N/A" else apartment_data.get('square')
    apartment_data['price_per_square'] = calculate_price_per_square(price, square)

    # Extract features dynamically
    features_text = apartment_data.get("features", "")
    if feature_categories:
        extracted_features = extract_features_by_category(features_text, feature_categories)
        apartment_data.update(extracted_features)  # Add extracted features to the data dictionary
    
    try:
        return template_text.format(**apartment_data)
    except KeyError as e:
        logging.error(f"Missing key {e} in template: {template_text}")
        return f"Error: Missing key {e} in the template."

feature_categories = ["Комфорт", "Опалення", "Мультимедіа"]



async def fetch_bot_template(template_name="telegram_bot"):
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(f"http://127.0.0.1:8000/templates/{template_name}") as response:
                if response.status == 200:
                    template = await response.json()
                    logging.debug(f"Fetched template: {template}")
                    return template.get('template_text', "Default template")
                else:
                    logging.error(f"Failed to fetch template. Status: {response.status}")
                    return "Default template"
    except Exception as e:
        logging.error(f"Error fetching template: {e}")
        return "Default template"


    
async def show_apartment(update, context: ContextTypes.DEFAULT_TYPE, index=None) -> None:
    try:
        language = context.user_data.get("language", "en")
        if index is None:
            index = context.user_data.get("current_apartment_index", 0)
        context.user_data["current_apartment_index"] = index

        filtered_apartments = context.user_data.get("filtered_apartments", [])
        if not filtered_apartments or index < 0 or index >= len(filtered_apartments):
            await update.callback_query.message.reply_text(
                "It seems that these are all the ads for today. As soon as we have new ads for you, we will immediately notify you 🙌 Or you can change the search criteria or ask our manager to pick something for you. Change criteria, Add search subscription Contact manager" if language == "en" else "Схоже, що це всі оголошення на сьогодні. Як тільки ми будемо мати нові оголошення для Вас, то відразу повідомимо 🙌 Або ж ви можете змінити критерії пошуку чи попросити нашого менеджера щось вам підібрати. Змінити критерії, Додати підписку пошуку звʼязати з менеджером"
            )
            return

        apartment = filtered_apartments[index]
        context.user_data["current_apartment_id"] = apartment["id"]  

        template_text = await fetch_bot_template()
        message = format_message(apartment, template_text, feature_categories)

        images = apartment.get('files', [])[:10]

        # Ensure we have images before proceeding
        if images:
            media_group = []
            for i, image in enumerate(images):
                if 'file_path' in image:
                    if i == 0:
                        media_group.append(InputMediaPhoto(image['file_path'], caption=message, parse_mode=ParseMode.MARKDOWN))
                    else:
                        media_group.append(InputMediaPhoto(image['file_path']))

            # Send media group (photos + caption)
            await context.bot.send_media_group(chat_id=update.effective_chat.id, media=media_group)

        else:
            # If no images, send text separately
            await update.callback_query.message.reply_text(message, parse_mode=ParseMode.MARKDOWN)

        buttons = [
            [
                InlineKeyboardButton("Previous" if language == "en" else "Попередній", callback_data="previous"),
                InlineKeyboardButton("Next" if language == "en" else "Наступний", callback_data="next"),
                InlineKeyboardButton("Show 3 Ads" if language == "en" else "Показати 3 оголошення", callback_data="show_3_ads")
            ],
            [InlineKeyboardButton("Save" if language == "en" else "Зберегти", callback_data="save")],
            [InlineKeyboardButton("Request a Call" if language == "en" else "Запросити дзвінок", callback_data="request_call")],
            [InlineKeyboardButton("Show on Map" if language == "en" else "Показати на карті", url=f"https://www.google.com/maps/search/?api=1&query={apartment['location_date']}")]
        ]
        keyboard = InlineKeyboardMarkup(buttons)

        # Send buttons in a separate message after media group
        await update.callback_query.message.reply_text("Please choose an action:" if language == "en" else "Будь ласка, оберіть дію:", reply_markup=keyboard)

    except Exception as e:
        logging.error(f"Error showing apartment: {e}")
        await update.callback_query.message.reply_text(
            "An error occurred while displaying the apartment." if language == "en" else "Сталася помилка при відображенні об'єкта."
        )
from telegram.constants import ParseMode

async def show_saved_ads(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    try:
        language = context.user_data.get("language", "en")
        saved_ads = context.user_data.get("saved_ads", [])

        # Handle both callback query and direct message
        if update.callback_query:
            query = update.callback_query
            await query.answer()
            chat_id = query.message.chat_id
        elif update.message:
            chat_id = update.message.chat_id
        else:
            logging.error("show_saved_ads called without a valid update.")
            return

        if saved_ads:
            template_text = await fetch_bot_template()

            for apartment in saved_ads:
                message = format_message(apartment, template_text, feature_categories)
                images = apartment.get('files', [])[:10]  # Limit to 10 images

                if images:
                    media_group = []
                    for i, image in enumerate(images):
                        if 'file_path' in image:
                            if i == 0:
                                media_group.append(InputMediaPhoto(image['file_path'], caption=message, parse_mode=ParseMode.MARKDOWN))
                            else:
                                media_group.append(InputMediaPhoto(image['file_path']))

                    await context.bot.send_media_group(chat_id=chat_id, media=media_group)
                else:
                    await context.bot.send_message(chat_id=chat_id, text=message, parse_mode=ParseMode.MARKDOWN)

        else:
            await context.bot.send_message(
                chat_id=chat_id,
                text="You haven't saved any ads yet." if language == "en" else "Ви ще не зберегли жодного оголошення."
            )

    except Exception as e:
        logging.error(f"Error showing saved ads: {e}")
        await context.bot.send_message(
            chat_id=chat_id,
            text="An error occurred while displaying the saved ads." if language == "en" else "Сталася помилка при відображенні збережених оголошень."
        )


async def show_saved_ad(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    try:
        language = context.user_data.get("language", "en")

        # Get the index of the current saved ad and list of saved ads
        current_index = context.user_data.get("current_saved_index", 0)
        saved_ads = context.user_data.get("saved_ads", [])

        # Ensure the current index is within bounds
        if not saved_ads or current_index < 0 or current_index >= len(saved_ads):
            await update.message.reply_text(
                "No saved properties available." if language == "en" else "Немає збережених оголошень."
            )
            return

        # Fetch the template dynamically
        template_text = await fetch_bot_template()

        # Get the current saved apartment and format the message dynamically
        apartment = saved_ads[current_index]
        message = format_message(apartment, template_text, feature_categories)

        # Retrieve images, limiting to a maximum of 10
        images = apartment.get('files', [])[:10]

        # Create the media group with text caption in the first image
        media_group = []
        for i, image in enumerate(images):
            if 'file_path' in image:
                image_url = image['file_path']
                logging.info(f"Adding image URL: {image_url}")
                if i == 0:
                    media_group.append(InputMediaPhoto(image_url, caption=message, parse_mode=ParseMode.MARKDOWN))
                else:
                    media_group.append(InputMediaPhoto(image_url))

        # Send the media group first if there are valid images
        if media_group:
            await context.bot.send_media_group(chat_id=update.effective_chat.id, media=media_group)
        else:
            await update.message.reply_text(message, parse_mode=ParseMode.MARKDOWN)

        # Navigation buttons
        buttons = [
            [
                InlineKeyboardButton("Previous" if language == "en" else "Попередній", callback_data="saved_previous"),
                InlineKeyboardButton("Next" if language == "en" else "Наступний", callback_data="saved_next"),
                InlineKeyboardButton("Show 3 Ads" if language == "en" else "Показати 3 оголошення", callback_data="show_3_saved_ads")
            ],
            [InlineKeyboardButton("Remove from Saved" if language == "en" else "Видалити з обраного", callback_data="remove_saved")],
            [InlineKeyboardButton("Request a Call" if language == "en" else "Запросити дзвінок", callback_data="request_call")],
            [InlineKeyboardButton("Show on Map" if language == "en" else "Показати на карті", url=f"https://www.google.com/maps/search/?api=1&query={apartment.get('location_date', '')}")]
        ]
        keyboard = InlineKeyboardMarkup(buttons)

        # Send buttons separately since `send_media_group` does not support reply_markup
        await update.message.reply_text("Please choose an action:" if language == "en" else "Будь ласка, оберіть дію:", reply_markup=keyboard)

    except Exception as e:
        logging.error(f"Error showing saved ad: {e}")
        await update.message.reply_text(
            "An error occurred while displaying the saved ad." if language == "en" else "Сталася помилка при відображенні збереженого оголошення."
        )

async def handle_start_button(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await start(update, context)

# Add a handler for the "Show Saved Ads" button
async def handle_show_saved_ads_button(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await show_saved_ads(update, context)  


async def request_contact(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Requests the user's phone number and automatically retrieves their Telegram username.
    """
    language = context.user_data.get("language", "en")

    # Handle CallbackQuery or Message
    message = update.message if update.message else update.callback_query.message

    # Request phone number first
    if "phone_number_received" not in context.user_data:
        contact_button = KeyboardButton(
            "📞 Share Contact" if language == "en" else "📞 Поділитися контактом", request_contact=True
        )
        contact_keyboard = ReplyKeyboardMarkup([[contact_button]], one_time_keyboard=True, resize_keyboard=True)

        await message.reply_text(
            "📞 Please share your phone number so we can contact you." if language == "en" else
            "📞 Надішліть ваш номер телефону, щоб ми могли зв’язатися з вами.",
            reply_markup=contact_keyboard
        )

        if update.callback_query:
            await update.callback_query.answer()

        context.user_data["phone_number_received"] = True
        return

    # Automatically retrieve Telegram username
    username = update.effective_user.username
    if username:
        context.user_data["user_username"] = f"@{username}"
    else:
        # If no username is set, request it manually
        if "username_received" not in context.user_data:
            await message.reply_text(
                "Now, please enter your Telegram username (starting with @)." if language == "en" else
                "Тепер, будь ласка, введіть ваш нік у Telegram (починаючи з @)."
            )
            context.user_data["username_received"] = True
            return

    # Confirmation message after receiving both phone number and username
    await message.reply_text(
        f"✅ Thank you! Your phone: {context.user_data.get('user_phone')}\nYour Telegram: {context.user_data.get('user_username')}\nWe'll contact you soon!"
        if language == "en" else
        f"✅ Дякуємо! Ваш телефон: {context.user_data.get('user_phone')}\nВаш Telegram: {context.user_data.get('user_username')}\nМи зв’яжемося з вами найближчим часом."
    )

    # Clear request states
    context.user_data.pop("phone_number_received", None)
    context.user_data.pop("username_received", None)


async def handle_contact(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Handle contact details received from the user and send them to FastAPI.
    """
    language = context.user_data.get("language", "en")
    user = update.message.from_user
    message = update.message
    contact = update.message.contact
    apartment_id = context.user_data.get("request_call_apartment_id")  # Retrieve saved apartment ID

    # If contact is shared, save phone number
    if message.contact:
        context.user_data["user_phone"] = message.contact.phone_number
        username = user.username  # Get Telegram username if available

        if username:
            context.user_data["user_username"] = f"@{username}"
        else:
            await message.reply_text(
                "📞 Phone number received! Now, please enter your Telegram username (starting with @)." if language == "en" else
                "📞 Номер телефону отримано! Тепер введіть свій нік у Telegram (починаючи з @)."
            )
            return  

    # If no contact but a username is sent manually, save it
    if message.text and "@" in message.text:
        context.user_data["user_username"] = message.text
        await message.reply_text(
            "✅ Username received! We are submitting your request now..." if language == "en" else
            "✅ Нік отримано! Ми надсилаємо вашу заявку..."
        )

    # Ensure both phone number and username are available before submission
    if not context.user_data.get("user_phone") or not context.user_data.get("user_username"):
        return

    # Build the order data
    order_data = {
        "name": user.first_name,
        "phone": context.user_data.get("user_phone"),
        "telegram_username": context.user_data.get("user_username"),
        "apartment_id": apartment_id,  # ✅ Include Apartment ID
        "client_wishes": context.user_data.get("client_wishes", "Requested help from manager"),
        "search_time": context.user_data.get("search_time", ""),
        "residents": context.user_data.get("residents", ""),
        "budget": context.user_data.get("budget"),
        "district": context.user_data.get("district"),
        "rooms": context.user_data.get("rooms"),
        "area": context.user_data.get("area"),
    }

    logging.info(f"🚀 Sending order data: {order_data}")

    # Send the order data to FastAPI
    async with aiohttp.ClientSession() as session:
        try:
            async with session.post("http://127.0.0.1:8000/orders/", json=order_data) as response:
                if response.status == 200:
                    result = await response.json()
                    await message.reply_text(
                        f"✅ Your request has been successfully submitted!\nOrder ID: {result['order_id']}"
                        if language == "en" else
                        f"✅ Ваша заявка успішно подана!\nID заявки: {result['order_id']}",
                        reply_markup=ReplyKeyboardRemove()
                    )
                else:
                    await message.reply_text(
                        "❌ An error occurred while submitting your request. Please try again later."
                        if language == "en" else
                        "❌ Сталася помилка при надсиланні заявки. Будь ласка, спробуйте ще раз пізніше."
                    )
        except Exception as e:
            logging.error(f"❌ Error submitting order: {e}")
            await message.reply_text(
                "❌ Server error! Please try again later."
                if language == "en" else
                "❌ Помилка сервера! Будь ласка, спробуйте ще раз пізніше."
            )

    # Clear stored data after submission
    context.user_data.clear()



async def show_navigation_options(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    language = context.user_data.get("language", "en")
    is_returning_user = "saved_ads" in context.user_data  # Example condition

    # Define menu buttons based on user type
    if is_returning_user:
        buttons = [
            [
                InlineKeyboardButton("Search for Real Estate" if language == "en" else "Шукати нерухомість", callback_data="city_or_region"),
                InlineKeyboardButton("Continue Browsing" if language == "en" else "Продовжити перегляд",  callback_data="continue_browsing"),
            ],
            [
                InlineKeyboardButton("Rent/Sell" if language == "en" else "Здати/Продати",  url="https://t.me/RentSearchOwner_bot"),
                InlineKeyboardButton("Submit an Application 🟡" if language == "en" else "Надішліть заявку 🟡",  callback_data="submit_application"),
            ],
            [
                InlineKeyboardButton("Manager’s Help" if language == "en" else "Допомога менеджера",  callback_data="managers_help"),
                InlineKeyboardButton("Look at Your Favorite" if language == "en" else "Подивитись на свої збережені",  callback_data="show_saved_ads"),
            ],
            [
                InlineKeyboardButton("My Rental" if language == "en" else "Моя оренда", callback_data="my_rental"),
                InlineKeyboardButton("My Subscription 🟡" if language == "en" else "Моя підписка 🟡",  callback_data="my_subscription"),
            ],
        ]
    else:
        buttons = [
            [
                InlineKeyboardButton("Search for Real Estate" if language == "en" else "Шукати нерухомість", callback_data="city_or_region"),
                InlineKeyboardButton("Rent/Sell" if language == "en" else "Здати/Продати", url="https://t.me/RentSearchOwner_bot"),
            ],
            [
                InlineKeyboardButton("Submit an Application 🟡" if language == "en" else "Надішліть заявку 🟡", callback_data="submit_application"),
                InlineKeyboardButton("Manager’s Help" if language == "en" else "Допомога менеджера", callback_data="managers_help"),
            ],
            [
                InlineKeyboardButton("Look at Your Favorite" if language == "en" else "Подивитись на свої збережені", callback_data="show_saved_ads"),
                InlineKeyboardButton("My Rental" if language == "en" else "Моя оренда", callback_data="my_rental"),
            ],
        ]

    keyboard = InlineKeyboardMarkup(buttons)
    await update.callback_query.message.reply_text("Please choose an action:" if language == "en" else "Будь ласка, оберіть дію:", reply_markup=keyboard)

def main():
    persistence_file = "bot_data.pkl"

    # Handle persistence file
    if os.path.exists(persistence_file):
        try:
            with open(persistence_file, "rb") as f:
                import pickle
                pickle.load(f)
        except (EOFError, pickle.UnpicklingError):
            logging.warning(f"Corrupted persistence file detected: {persistence_file}. Deleting it...")
            os.remove(persistence_file)

    persistence = PicklePersistence(filepath=persistence_file)

    application = ApplicationBuilder().token(TOKEN).persistence(persistence).build()
    # Add command handlers
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CallbackQueryHandler(button_click, pattern="^(managers_help|request_call|confirm_application|cancel_application)$"))
    application.add_handler(CallbackQueryHandler(continue_browsing, pattern="continue_browsing"))
    application.add_handler(CallbackQueryHandler(language_selection, pattern="^lang_"))
    application.add_handler(CallbackQueryHandler(button_click, pattern="^(?!apply_type_object).*$"))
    application.add_handler(CallbackQueryHandler(button_click_apply, pattern="^apply_type_object$"))
    application.add_handler(CallbackQueryHandler(save_subscription, pattern="^save_subscription$"))
    application.add_handler(CallbackQueryHandler(skip_subscription, pattern="^skip_subscription$"))
    application.add_handler(CallbackQueryHandler(handle_district_selection, pattern="^location_"))
    application.add_handler(CallbackQueryHandler(handle_city_selection, pattern="^location_"))
    application.add_handler(CallbackQueryHandler(handle_apply_location, pattern="^apply_location$"))
    application.add_handler(CallbackQueryHandler(handle_back_to_districts, pattern="^back_to_districts$"))
    application.add_handler(CallbackQueryHandler(manage_subscription, pattern="^my_subscription$"))
    application.add_handler(CallbackQueryHandler(change_subscription, pattern="^change_subscription$"))
    application.add_handler(CallbackQueryHandler(stop_subscription, pattern="^stop_subscription$"))
    application.add_handler(CallbackQueryHandler(delete_subscription, pattern="^delete_subscription$"))
    application.add_handler(MessageHandler(filters.Text("Start"), handle_start_button))
    application.add_handler(MessageHandler(filters.Text("Show Saved Ads"), handle_show_saved_ads_button))
    application.add_handler(MessageHandler(filters.CONTACT, handle_contact))
    application.add_handler(MessageHandler(filters.Text("Main Page"), start))
    application.add_handler(MessageHandler(filters.Text("Change Filter Settings"), filter_properties))
    application.add_handler(MessageHandler(filters.Text("Leave a Request"), handle_contact))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text_input))



    async def run():
        logging.info("Initializing bot...")
        scheduler = AsyncIOScheduler()

        try:
            scheduler.add_job(
                notify_new_objects,
                trigger="interval",
                minutes=1,
                kwargs={"application": application},
            )
            scheduler.start()
            logging.info("Scheduler started.")

            async with application:
                await application.initialize()
                logging.info("Application initialized.")

                await application.bot.delete_webhook(drop_pending_updates=True)
                logging.info("Webhook deleted.")

                await application.start()
                logging.info("Application started. Polling for updates...")

                try:
                    await application.updater.start_polling()
                    await asyncio.Event().wait()  # Keep the bot running
                except Exception as e:
                    logging.error(f"Polling error: {e}")
                finally:
                    logging.info("Stopping updater...")
                    await application.updater.stop()
        except Exception as e:
            logging.error(f"Critical error in run: {e}")
        finally:
            logging.info("Stopping application...")
            if application.is_running:
                await application.stop()
            logging.info("Bot stopped.")

    try:
        asyncio.run(run())
    except KeyboardInterrupt:
        logging.info("Bot interrupted. Shutting down...")

if __name__ == '__main__':
    logging.info("Bot script started.")
    main()