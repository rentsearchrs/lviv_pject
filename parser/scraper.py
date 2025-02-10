import requests
import json
import time
from urllib.parse import urlparse

# ✅ BrowserStack Credentials
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


def scrape_apartment_details(driver, apartment_url):
    """Scrapes details from an individual apartment listing"""
    print(f"🔍 Scraping: {apartment_url}")
    driver.get(apartment_url)

    try:
        WebDriverWait(driver, 10).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, "h3.css-fqcbii"))
        )
    except:
        print(f"⚠️ Page {apartment_url} did not load properly.")
        return None

    try:
        # ✅ Extract data
        title = driver.find_element(By.CSS_SELECTOR, "h3.css-fqcbii").text
        price = driver.find_element(By.CSS_SELECTOR, "h3.css-fqcbii").text
        description = driver.find_element(By.CSS_SELECTOR, "div.css-1o924a9").text
        location = driver.find_element(By.CSS_SELECTOR, "div.css-13l8eec").text
        user = driver.find_element(By.CSS_SELECTOR, "h4.css-lyp0yk").text

        # ✅ Extract Image URLs
        image_urls = []
        image_elements = driver.find_elements(By.CSS_SELECTOR, 'div[data-cy="adPhotos-swiperSlide"] img')

        for img in image_elements:
            img_url = img.get_attribute("src")
            if img_url:
                image_urls.append(img_url)

        # ✅ Extract Contact Info (if available)
        phone = None
        phone_elements = driver.find_elements(By.CSS_SELECTOR, "a.css-v1ndtc")
        if phone_elements:
            phone = phone_elements[0].text

        # ✅ Extract ID
        id_olx = None
        id_elements = driver.find_elements(By.CSS_SELECTOR, "span.css-12hdxwj")
        if id_elements:
            id_olx = id_elements[0].text

        # ✅ Prepare Data
        apartment_data = {
            "title": title,
            "price": price,
            "description": description,
            "location": location,
            "user": user,
            "phone": phone,
            "id_olx": id_olx,
            "url": apartment_url,
            "images": image_urls
        }

        return apartment_data

    except Exception as e:
        print(f"❌ Error scraping apartment details: {e}")
        return None


def send_data_to_webhook(scraped_data):
    """Send the scraped data to the webhook."""
    try:
        response = requests.post(WEBHOOK_URL, json={"scraped_data": scraped_data})

        if response.status_code == 200:
            print("✅ Data successfully sent to webhook")
        else:
            print(f"❌ Error sending data to webhook: {response.text}")
    
    except Exception as e:
        print(f"❌ Failed to send data: {e}")


def scrape_and_send():
    """Main function to scrape apartments and send data to webhook"""
    driver = setup_selenium()

    try:
        for base_url in BASE_URLS:
            driver.get(base_url)
            time.sleep(3)

            listings = driver.find_elements(By.CLASS_NAME, "css-1apmciz")

            for listing in listings:
                try:
                    title_element = listing.find_element(By.CSS_SELECTOR, "a.css-qo0cxu")
                    apartment_url = title_element.get_attribute("href")

                    # ✅ Scrape apartment details
                    details = scrape_apartment_details(driver, apartment_url)
                    if details:
                        send_data_to_webhook(details)

                except Exception as e:
                    print(f"❌ Error processing listing: {e}")

    finally:
        driver.quit()
        print("✅ Scraping completed successfully!")


if __name__ == "__main__":
    scrape_and_send()
