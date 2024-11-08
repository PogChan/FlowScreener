from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from webdriver_manager.chrome import ChromeDriverManager
from bs4 import BeautifulSoup
import streamlit as st 
from datetime import datetime
import os
import pandas as pd 
import sqlite3

# Function to get earnings date for a specific stock using an existing driver
def get_earnings_date(stock_symbol, driver):
    url = f'https://www.nasdaq.com/market-activity/stocks/{stock_symbol}/earnings'
    driver.get(url)

    try:
        WebDriverWait(driver, 10).until(
            EC.presence_of_element_located((By.CLASS_NAME, 'announcement-date'))
        )
        html_content = driver.page_source
        soup = BeautifulSoup(html_content, 'html.parser')
        announcement_date_span = soup.find('span', class_='announcement-date')

        if announcement_date_span:
            date_str = announcement_date_span.get_text(strip=True)
            announcement_date = datetime.strptime(date_str, "%b %d, %Y").strftime("%Y-%m-%d")
            return announcement_date
        else:
            return None
    except Exception as e:
        st.write(f"An error occurred for {stock_symbol.upper()}: {e}")
        return None

# SQLite database functions
def create_database(db_name="earnings_cache.db"):
    conn = sqlite3.connect(db_name)
    cursor = conn.cursor()
    cursor.execute('''CREATE TABLE IF NOT EXISTS earnings_dates (
                      Symbol TEXT PRIMARY KEY,
                      EarningsDate TEXT
                      )''')
    conn.commit()
    conn.close()

def get_cached_date(symbol, db_name="earnings_cache.db"):
    conn = sqlite3.connect(db_name)
    cursor = conn.cursor()
    cursor.execute("SELECT EarningsDate FROM earnings_dates WHERE Symbol = ?", (symbol,))
    result = cursor.fetchone()
    conn.close()
    return result[0] if result else None

def update_cache(symbol, earnings_date, db_name="earnings_cache.db"):
    conn = sqlite3.connect(db_name)
    cursor = conn.cursor()
    cursor.execute("INSERT OR REPLACE INTO earnings_dates (Symbol, EarningsDate) VALUES (?, ?)", (symbol, earnings_date))
    conn.commit()
    conn.close()