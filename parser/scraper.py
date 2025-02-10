import datetime
import os
from urllib.parse import urlparse
import httpx
import requests
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.wait import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
import asyncio
import parser.crud as crud
import re
from datetime import datetime
from sqlalchemy.ext.asyncio import AsyncSession
from parser.database import get_db
from parser.filter_oblast import map_location_with_region
semaphore = asyncio.Semaphore(50)
BROWSERSTACK_USERNAME = "bohdansavyshchev_gh6ixa"
BROWSERSTACK_ACCESS_KEY = "Nn79kCkNpyEw7J4zwjAs"
REMOTE_SELENIUM_URL = f"https://{BROWSERSTACK_USERNAME}:{BROWSERSTACK_ACCESS_KEY}@hub-cloud.browserstack.com/wd/hub"

WEBHOOK_URL = "https://your-vercel-app.vercel.app/webhook/"  # Replace with your Vercel webhook

BASE_URLS = [
    "https://www.olx.ua/uk/nedvizhimost/kvartiry/dolgosrochnaya-arenda-kvartir/lv/?currency=USD&page=",
    "https://www.olx.ua/uk/nedvizhimost/kvartiry/prodazha-kvartir/lv/?currency=USD&page=",
    "https://www.olx.ua/uk/nedvizhimost/posutochno-pochasovo/posutochno-pochasovo-kvartiry/lv/?currency=USD&page=",
]

def setup_selenium():
    """Setup Selenium WebDriver for BrowserStack Automate"""
    print("🛠️ Setting up Selenium on BrowserStack...")

    try:
        options = webdriver.FirefoxOptions()

        # ✅ Set BrowserStack capabilities
        options.set_capability("browserName", "Firefox")
        options.set_capability("browserVersion", "latest")
        options.set_capability("platformName", "Windows 10")
        options.set_capability("buildName", "browserstack-build-1")
        options.set_capability("projectName", "OLX Scraper")
        options.set_capability("browserstack.debug", True)
        options.set_capability("browserstack.networkLogs", True)

        # ✅ Start remote WebDriver session
        driver = webdriver.Remote(
            command_executor=REMOTE_SELENIUM_URL,
            options=options
        )

        print("✅ Selenium WebDriver started successfully on BrowserStack!")
        return driver

    except Exception as e:
        print(f"❌ Selenium setup failed: {e}")
        raise e


async def scrape_titles_and_urls(driver, base_url, page_number):
    """Scrape apartment titles and URLs from OLX listings"""
    async with semaphore:
        full_url = f"{base_url}{page_number}"
        print(f"🚀 Fetching page: {full_url}")
        driver.get(full_url)

        try:
            WebDriverWait(driver, 10).until(
                EC.presence_of_element_located((By.CLASS_NAME, "css-1apmciz"))
            )
        except:
            print("⚠️ Listings not found on page.")
            return []

        parsed_url = urlparse(full_url)
        path_parts = parsed_url.path.split('/')
        type_deal = path_parts[3] if len(path_parts) >= 5 else None
        type_object = path_parts[4] if len(path_parts) >= 5 else None

        apartments = []
        last_height = driver.execute_script("return document.body.scrollHeight")

        while True:
            driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
            await asyncio.sleep(3)

            listings = driver.find_elements(By.CLASS_NAME, "css-1apmciz")
            if not listings:
                print("⚠️ No new listings found, stopping scroll.")
                break

            for listing in listings:
                try:
                    title_element = listing.find_element(By.CSS_SELECTOR, "a.css-qo0cxu")
                    title = title_element.text
                    url = title_element.get_attribute("href")

                    apartments.append({
                        "title": title,
                        "url": url,
                        "type_deal": type_deal,
                        "type_object": type_object
                    })
                except Exception as e:
                    print(f"❌ Error processing listing: {e}")

            new_height = driver.execute_script("return document.body.scrollHeight")
            if new_height == last_height:
                break
            last_height = new_height

        return apartments

async def scrape_apartment_details(driver, apartment_url, title, type_deal, type_object):
    """Scrape details of a specific apartment"""
    driver.get(apartment_url)

    try:
        WebDriverWait(driver, 10).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, "h3.css-fqcbii"))
        )
    except:
        print(f"⚠️ Page {apartment_url} did not load properly.")
        return None

    try:
        price = driver.find_element(By.CSS_SELECTOR, "h3.css-fqcbii").text
        description = driver.find_element(By.CSS_SELECTOR, "div.css-1o924a9").text
        features = driver.find_element(By.CSS_SELECTOR, "div.css-41yf00").text
        location_date_element = driver.find_element(By.CSS_SELECTOR, "div.css-13l8eec").text
        user = driver.find_element(By.CSS_SELECTOR, "h4.css-lyp0yk").text

        location_date = map_location_with_region(location_date_element.replace('Львівська область', '').strip())

        data = {
            "title": title,
            "price": price,
            "description": description,
            "location_date": location_date,
            "features": features,
            "url": apartment_url,
            "type_deal": type_deal,
            "type_object": type_object,
            "user": user
        }

        send_data_to_webhook(data)
        return data

    except Exception as e:
        print(f"❌ Error scraping details: {e}")
        return None

async def scrape_and_save_images(driver, apartment_url, apartment_id, db: AsyncSession):
    """Scrape and save images of an apartment"""
    image_dir = f"images/apartment_{apartment_id}_{datetime.datetime.now().strftime('%Y%m%d%H%M%S')}"
    os.makedirs(image_dir, exist_ok=True)

    driver.get(apartment_url)
    await asyncio.sleep(2)

    try:
        image_containers = driver.find_elements(By.CSS_SELECTOR, 'div[data-cy="adPhotos-swiperSlide"]')

        async with httpx.AsyncClient() as client:
            for index, container in enumerate(image_containers):
                img_element = container.find_element(By.TAG_NAME, "img")
                img_url = img_element.get_attribute("src")
                
                if img_url:
                    response = await client.get(img_url)
                    image_path = f"{image_dir}/image_{index + 1}.jpg"
                    with open(image_path, 'wb') as handler:
                        handler.write(response.content)

                    image_data = {
                        "filename": f"image_{index + 1}.jpg",
                        "date": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                        "content_type": "image/jpeg",
                        "file_path": image_path,
                        "order": index + 1
                    }

                    await crud.add_image_to_apartment(db=db, apartment_id=apartment_id, image_data=image_data)

    except Exception as e:
        print(f"❌ Error saving images: {e}")

async def scrape_and_save(total_pages=5):
    """Main scraper function."""
    global SCRAPER_RUNNING  # ✅ Declare global before using it


    print("✅ Scraper started...")
    SCRAPER_RUNNING = True  # ✅ Correctly modifying the global variable

    driver = setup_selenium()

    try:
        async for db in get_db():
            try:
                results_by_url = {}

                if not BASE_URLS:
                    print("🚫 BASE_URLS is empty. Stopping scraper.")
                    SCRAPER_RUNNING = False  # ✅ Reset flag
                    return

                for base_url in BASE_URLS:
                    print(f"🔍 Fetching URL: {base_url}")
                    if not SCRAPER_RUNNING:
                        print("🚫 Scraper stopped while running.")
                        return  

                    url_results = []
                    for page in range(1, total_pages + 1):
                        print(f"📄 Scraping page {page}...")
                        if not SCRAPER_RUNNING:
                            print("🚫 Scraper stopped while fetching pages.")
                            return 

                        apartments = await scrape_titles_and_urls(driver, base_url, page)
                        url_results.extend(apartments)
                    
                    results_by_url[base_url] = url_results

                # Process the scraped apartments
                for base_url, apartments in results_by_url.items():
                    print(f"🏡 Processing apartments for URL: {base_url}")

                    for apartment in apartments:
                        print(f"🔎 Scraping apartment: {apartment['title']} - {apartment['url']}")
                        if not SCRAPER_RUNNING:
                            print("🚫 Scraper stopped while processing apartments.")
                            return  

                        details = await scrape_apartment_details(
                            driver, apartment['url'], apartment['title'], 
                            apartment['type_deal'], apartment['type_object']
                        )

                        if details:
                            try:
                                print(f"💾 Saving to database: {details['title']}")
                                saved_apartment = await crud.create_or_update_apartment(db, details)
                                apartment_id = saved_apartment.id
                                await scrape_and_save_images(driver, apartment['url'], apartment_id, db)
                            except Exception as e:
                                print(f"❌ Error saving apartment details or images: {e}")

            finally:
                await db.close()

    except Exception as e:
        print(f"❌ Error in scraper: {e}")

    finally:
        driver.quit()
        SCRAPER_RUNNING = False  # ✅ Reset flag after execution
        print("✅ Scraper finished successfully!")
def send_data_to_webhook(scraped_data):
    """Send the scraped data to the webhook"""
    try:
        response = requests.post(WEBHOOK_URL, json={"scraped_data": scraped_data})
        print("✅ Data successfully sent to webhook" if response.status_code == 200 else f"❌ Webhook error: {response.text}")
    except Exception as e:
        print(f"❌ Failed to send data: {e}")