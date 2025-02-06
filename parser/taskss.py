import logging
from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from parser.database import get_dbb
import crud

async def check_relevance():
    """
    Check which apartments have been deleted from OLX and mark them as not relevant.
    """
    async with get_dbb() as db:
        try:
            # Fetch all apartments that are currently active
            stmt = select(crud.Apartment).where(crud.Apartment.ad_status == "successful")
            result = await db.execute(stmt)
            apartments = result.scalars().all()

            # Get the latest scraped apartments (you need to implement a function for this)
            latest_apartment_urls = await crud.get_latest_scraped_urls(db)

            # Check for missing apartments
            non_relevant_apartments = []
            for apartment in apartments:
                if apartment.url not in latest_apartment_urls:
                    apartment.ad_status = "not_relevant"
                    non_relevant_apartments.append(apartment)

            if non_relevant_apartments:
                await db.commit()
                logging.info(f"✅ Marked {len(non_relevant_apartments)} apartments as 'not_relevant'.")

                # Notify the admin via Telegram
                await notify_admin(non_relevant_apartments)

        except Exception as e:
            logging.error(f"❌ Error during relevance check: {e}")

async def notify_admin(non_relevant_apartments):
    """
    Notify the admin about non-relevant apartments via Telegram.
    """
    from telegram import Bot
    bot_token = "YOUR_TELEGRAM_BOT_TOKEN"
    admin_chat_id = "YOUR_ADMIN_CHAT_ID"

    bot = Bot(token=bot_token)

    message = "🚨 The following apartments are no longer available on OLX:\n\n"
    for apartment in non_relevant_apartments[:10]:  # Limit messages to avoid spam
        message += f"🏠 {apartment.title} - {apartment.url}\n"

    try:
        await bot.send_message(chat_id=admin_chat_id, text=message)
        logging.info("✅ Admin notified about non-relevant apartments.")
    except Exception as e:
        logging.error(f"❌ Failed to send admin notification: {e}")
