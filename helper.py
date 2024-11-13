from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from webdriver_manager.chrome import ChromeDriverManager
from bs4 import BeautifulSoup
import streamlit as st
from datetime import datetime
import requests
import pandas as pd

# Function to get earnings date for a specific stock using an existing driver
@st.cache_data(ttl=43200)
def get_earnings_date(stock_symbol, _driver):
    url = f'https://www.nasdaq.com/market-activity/stocks/{stock_symbol}/earnings'
    _driver.get(url)

    try:
        WebDriverWait(_driver, 3).until(
            EC.presence_of_element_located((By.CLASS_NAME, 'announcement-date'))
        )
        html_content = _driver.page_source
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

@st.cache_data(ttl=43200)
# Define function to fetch options chain data from API
def get_options_chain(symbol):
    url = f"https://www.optionsprofitcalculator.com/ajax/getOptions?stock={symbol.upper()}&reqId=1"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36",
        "Accept-Language": "en-US,en;q=0.9",
        "Referer": "https://www.optionsprofitcalculator.com/"
    }
    # st.write(url)
    response = requests.get(url, headers=headers)

    if response.status_code == 200:
        return response.json()
    else:
        st.error(f"Failed to fetch options chain for {symbol}. Status code: {response.status_code}")
        return None
    
@st.cache_data(ttl=43200)
def calculate_avg_volume_for_expiration(options_data, spot_price, expiration_date):
    spot_price = float(spot_price)  # Ensure spot price is float
    expiration_date_str = expiration_date.strftime("%Y-%m-%d")  # Convert expiration date to match options data format

    # Check if expiration date exists in the options data
    if expiration_date_str not in options_data['options']:
        st.warning(f"No matching expiration date ({expiration_date_str}) in options data.")
        return None

    # Get call and put options for the specific expiration date
    calls = options_data['options'][expiration_date_str].get('c', {})
    puts = options_data['options'][expiration_date_str].get('p', {})

    # Collect strikes and volumes
    strikes = []
    volumes = []
    for strike, data in calls.items():
        strikes.append(float(strike))
        volumes.append(data['v'])
    for strike, data in puts.items():
        strikes.append(float(strike))
        volumes.append(data['v'])

    # Create DataFrame and calculate average volume for 15 closest strikes
    df = pd.DataFrame({'Strike': strikes, 'Volume': volumes})
    df['Distance'] = abs(df['Strike'] - spot_price)
    df = df.nsmallest(15, 'Distance')  # Get 15 closest strikes
    avg_volume = df['Volume'].mean()  # Calculate average volume

    return avg_volume