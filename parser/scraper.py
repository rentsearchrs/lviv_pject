import requests
import json
import time
from urllib.parse import urlparse

# ✅ BrowserStack Credentials
BROWSERSTACK_USERNAME = "bohdansavyshchev_gh6ixa"
BROWSERSTACK_ACCESS_KEY = "Nn79kCkNpyEw7J4zwjAs"
BROWSERSTACK_API_URL = "https://api.browserstack.com/automate/sessions.json"
WEBHOOK_URL = "https://your-vercel-app.vercel.app/webhook/"

BASE_URLS = [
    "https://www.olx.ua/uk/nedvizhimost/kvartiry/dolgosrochnaya-arenda-kvartir/lv/?currency=USD&page=",
    "https://www.olx.ua/uk/nedvizhimost/kvartiry/prodazha-kvartir/lv/?currency=USD&page=",
    "https://www.olx.ua/uk/nedvizhimost/posutochno-pochasovo/posutochno-pochasovo-kvartiry/lv/?currency=USD&page=",
]

def start_browserstack_session():
    """Trigger BrowserStack Automate session."""
    payload = {
        "url": BASE_URLS[0],  # Start scraping from the first URL
        "browser": "firefox",
        "browser_version": "latest",
        "os": "Windows",
        "os_version": "10",
        "resolution": "1920x1080",
        "build": "OLX-Scraper",
        "name": "OLX-Scraping-Task",
        "browserstack.debug": True,
        "browserstack.local": False,
        "browserstack.networkLogs": True
    }

    response = requests.post(
        BROWSERSTACK_API_URL,
        auth=(BROWSERSTACK_USERNAME, BROWSERSTACK_ACCESS_KEY),
        json=payload
    )

    if response.status_code == 200:
        session_data = response.json()
        session_id = session_data.get("automation_session", {}).get("hashed_id")
        print(f"✅ Started BrowserStack Session: {session_id}")
        return session_id
    else:
        print(f"❌ Error starting session: {response.text}")
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
