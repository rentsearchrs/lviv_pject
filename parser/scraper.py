import datetime
import os
from urllib.parse import urlparse
import httpx
from selenium import webdriver
from selenium.webdriver.firefox.service import Service as FirefoxService
from selenium.webdriver.common.by import By
from selenium.webdriver.support.wait import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
import asyncio
import parser.crud
import re
from parser.database import get_db
from datetime import datetime
from sqlalchemy.ext.asyncio import AsyncSession
from parser.database import get_db
from parser.filter_oblast import map_location_with_region

semaphore = asyncio.Semaphore(50)
# Global flag to control scraper dynamically
SCRAPER_RUNNING = False
from selenium.webdriver.common.desired_capabilities import DesiredCapabilities

def setup_selenium():
    print("🛠️ Setting up Selenium...")

    try:
        REMOTE_SELENIUM_URL = "http://bohdansavyshchev_gh6ixa:Nn79kCkNpyEw7J4zwjAs@hub-cloud.browserstack.com/wd/hub"

        options = webdriver.FirefoxOptions()  

        # ✅ Set BrowserStack capabilities
        options.set_capability("browserName", "Firefox")
        options.set_capability("browserVersion", "131.0")
        options.set_capability("platformName", "Windows 10")  
        options.set_capability("buildName", "browserstack-build-1")
        options.set_capability("projectName", "BrowserStack Sample")
        options.set_capability("seleniumVersion", "4.0.0")

        # 🚀 Fix: Increase idle timeout (max 300 sec)
        options.set_capability("idleTimeout", 300)  # Keep browser alive longer

        # ✅ Start remote WebDriver session
        driver = webdriver.Remote(
            command_executor=REMOTE_SELENIUM_URL,
            options=options  
        )

        print("✅ Selenium WebDriver started successfully!")
        return driver

    except Exception as e:
        print(f"❌ Selenium setup failed: {e}")
        raise e


BASE_URLS = [
    "https://www.olx.ua/uk/nedvizhimost/kvartiry/dolgosrochnaya-arenda-kvartir/lv/?currency=USD&page=",
    "https://www.olx.ua/uk/nedvizhimost/kvartiry/prodazha-kvartir/lv/?currency=USD&page=",
    "https://www.olx.ua/uk/nedvizhimost/posutochno-pochasovo/posutochno-pochasovo-kvartiry/lv/?currency=USD&page=",

]

# Stage 1: Scrape apartment titles and URLs from each listings page

async def scrape_titles_and_urls(driver, base_url, page_number):
    async with semaphore:
        full_url = f"{base_url}{page_number}"
        
        print(f"🚀 Fetching page: {full_url}")
        driver.get(full_url)

        # ✅ Wait until listings load instead of using sleep()
        try:
            WebDriverWait(driver, 10).until(
                EC.presence_of_element_located((By.CLASS_NAME, "css-1apmciz"))
            )
        except:
            print("⚠️ Listings not found on page.")
            return []

        # Extract type_deal and type_object from the URL
        parsed_url = urlparse(full_url)
        path_parts = parsed_url.path.split('/')
        type_deal = path_parts[3] if len(path_parts) >= 5 else None
        type_object = path_parts[4] if len(path_parts) >= 5 else None

        # 🔄 Scrolling dynamically
        apartments = []
        last_height = driver.execute_script("return document.body.scrollHeight")

        while True:
            driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
            await asyncio.sleep(3)  # Small wait for new content

            # ✅ Check if new elements appeared
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

            # Check if we reached the bottom
            new_height = driver.execute_script("return document.body.scrollHeight")
            if new_height == last_height:
                break  # Exit loop if no new content is loading
            last_height = new_height

        return apartments

# Stage 2: Scrape additional details for each apartment from its individual page
async def scrape_apartment_details(driver, apartment_url, title, type_deal, type_object):
    driver.get(apartment_url)

    # ✅ Wait until main elements are visible
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

        location_date = location_date_element.replace('Львівська область', '').strip().replace(',', '').strip()
        location_date = map_location_with_region(location_date)

        # ✅ Try clicking "Show More" button
        try:
            button = driver.find_element(By.CSS_SELECTOR, ".css-1vgbwlu")
            driver.execute_script("arguments[0].click();", button)
            await asyncio.sleep(1)
        except:
            pass  # Button might not be there

        # ✅ Extract structured features
        features_map = {
            "owner": re.search(r"(Приватна особа|Бізнес)", features),
            "residential_complex": re.search(r"Назва ЖК:\s*(.+)", features),
            "floor": re.search(r"Поверх:\s*(\d+)", features),
            "superficiality": re.search(r"Поверховість:\s*(\d+)", features),
            "square": re.search(r"Загальна площа:\s*(\d+)", features),
            "classs": re.search(r"Клас житла:\s*(.+)", features),
            "room": re.search(r"Кількість кімнат:\s*(\d+)", features),
        }
        for key in features_map:
            features_map[key] = features_map[key].group(1) if features_map[key] else ""

        # ✅ Try fetching phone and ID
        phone = driver.find_element(By.CSS_SELECTOR, "a.css-v1ndtc").text if driver.find_elements(By.CSS_SELECTOR, "a.css-v1ndtc") else None
        id_olx = driver.find_element(By.CSS_SELECTOR, "span.css-12hdxwj").text if driver.find_elements(By.CSS_SELECTOR, "span.css-12hdxwj") else None

        return {
            "title": title,
            "price": price,
            "description": description,
            "features": features,
            "location_date": location_date,
            "owner": features_map.get("owner", "Unknown"),
            "residential_complex": features_map.get("residential_complex", ""),
            "floor": features_map.get("floor", ""),
            "superficiality": features_map.get("superficiality", ""),
            "square": features_map.get("square", ""),
            "classs": features_map.get("classs", ""),
            "room": features_map.get("room", ""),
            "url": apartment_url,
            "type_deal": type_deal,
            "type_object": type_object,
            "phone": phone,
            "id_olx": id_olx,
            "user": user
        }
    except Exception as e:
        print(f"❌ Error scraping details: {e}")
        return None


async def scrape_and_save_images(driver, apartment_url, apartment_id, db: AsyncSession):
    image_dir = f"images/apartment_{apartment_id}_{datetime.now().strftime('%Y%m%d%H%M%S')}"
    os.makedirs(image_dir, exist_ok=True)

    driver.get(apartment_url)
    await asyncio.sleep(2)

    # Locate all image containers using the data-cy attribute
    try:
        # Select all image elements within elements marked with data-cy="adPhotos-swiperSlide"
        image_containers = driver.find_elements(By.CSS_SELECTOR, 'div[data-cy="adPhotos-swiperSlide"]')
        
        async with httpx.AsyncClient() as client:
            for index, container in enumerate(image_containers):
                img_element = container.find_element(By.TAG_NAME, "img")
                img_url = img_element.get_attribute("src")
                
                if img_url:
                    # Download and save each image
                    response = await client.get(img_url)
                    image_path = f"{image_dir}/image_{index + 1}.jpg"  # Start index from 1
                    with open(image_path, 'wb') as handler:
                        handler.write(response.content)

                    # Prepare image data with an order field
                    image_data = {
                        "filename": f"image_{index + 1}.jpg",  # Start filename index from 1
                        "date": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                        "content_type": "image/jpeg",
                        "file_path": image_path,
                        "order": index + 1  # Set order starting from 1
                    }

                    # Save image information to the database
                    await crud.add_image_to_apartment(db=db, apartment_id=apartment_id, image_data=image_data)

    except Exception as e:
        print(f"Error saving images: {e}")


async def keep_browser_alive(driver):
    """Send periodic JavaScript commands to keep BrowserStack session active."""
    while SCRAPER_RUNNING:
        try:
            driver.execute_script("window.scrollBy(0, 1);")  # Small scroll to trigger activity
            print("🔄 Keep-alive signal sent to BrowserStack")
        except Exception as e:
            print(f"⚠️ Keep-alive error: {e}")
            break
        await asyncio.sleep(30)  # Send keep-alive every 30 seconds

async def scrape_and_save(total_pages=5):
    """Main scraper function."""
    global SCRAPER_RUNNING

    if SCRAPER_RUNNING:
        print("🚫 Scraper is already running. Exiting...")
        return

    print("✅ Scraper started...")
    SCRAPER_RUNNING = True  

    driver = setup_selenium()

    # ✅ Start keep-alive task
    keep_alive_task = asyncio.create_task(keep_browser_alive(driver))

    try:
        async for db in get_db():
            try:
                results_by_url = {}

                if not BASE_URLS:
                    print("🚫 BASE_URLS is empty. Stopping scraper.")
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
        SCRAPER_RUNNING = False  
        keep_alive_task.cancel()  # Stop keep-alive loop
        print("✅ Scraper finished successfully!")
