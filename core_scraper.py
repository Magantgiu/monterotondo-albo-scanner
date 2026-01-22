import sys
import time
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from webdriver_manager.chrome import ChromeDriverManager

# Improved debugging error messages
try:
    service = Service(ChromeDriverManager().install())
    driver = webdriver.Chrome(service=service)
except Exception as e:
    print(f'Error initializing WebDriver: {e}')
    sys.exit(1)

# Your existing core scraper code goes here:
# Add your scraping logic and functions

# Example function
def scrape_site(url):
    try:
        driver.get(url)
        # Add logic to scrape data from the page
    except Exception as e:
        print(f'Error scraping the site: {e}')
    finally:
        driver.quit()