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
import time 
import random

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
    
session = requests.Session()
user_agents = [
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/92.0.4515.107 Safari/537.36',
    'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/14.1.2 Safari/605.1.15',
]


@st.cache_data(ttl=43200)
# Define function to fetch options chain data from API
def get_options_chain(symbol):
    url = f"https://www.optionsprofitcalculator.com/ajax/getOptions?stock={symbol.upper()}&reqId={random.randint(1, 1000000)}"
    headers = {
        'User-Agent': random.choice(user_agents),
        "Accept-Language": "en-US,en;q=0.9",
        'Referer': 'https://www.optionsprofitcalculator.com/',
        'Accept': 'application/json',
    }
    st.write(url)
    time.sleep(1)
    response = session.get(url, headers=headers)

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

@st.cache_data(ttl=43200)
def moneiness(flow, options_chain):
    strike = float(flow['Strike'])
    spot = float(flow['Spot'])
    option_type = flow['CallPut']  # Expecting 'CALL' or 'PUT'
    
    # Convert the expiration date to the correct string format
    expiration_date = flow['ExpirationDate']
    expiration_date_str = pd.to_datetime(expiration_date).strftime("%Y-%m-%d")
    
    # Extract all strikes from the options chain for the specific expiration
    strikes = []
    if expiration_date_str in options_chain['options']:
        expiry_options = options_chain['options'][expiration_date_str]
        
        calls = expiry_options.get('c', {})
        strikes.extend(float(strike) for strike in calls.keys())

    # Sort strikes for further calculations
    strikes = sorted(strikes)
    # st.write(strikes)
    # st.write(flow)
    # st.write(spot)
    
    # Find the closest strike to the spot price for ATM reference
    if strikes:
        closest_strike = min(strikes, key=lambda x: abs(x - spot))
    else:
        return "Unknown"  # If no strikes are found for the expiration

    # Calculate the absolute difference between the current strike and closest ATM strike
    abs_diff = abs(strike - closest_strike)
    
    # Determine the smallest increment between consecutive strikes (assuming strikes are evenly spaced)
    if len(strikes) > 1:
        min_increment = min([abs(strikes[i+1] - strikes[i]) for i in range(len(strikes) - 1)])
    else:
        min_increment = 1  # Default increment if there's only one strike (unlikely case)

    # Calculate how many steps away the current strike is from the closest ATM strike
    if min_increment is None or min_increment == 0:
        strike_diff = 0  # Treat as ATM if only one strike or no meaningful difference
    else:
        strike_diff = int(round(abs_diff / min_increment))

    # st.write(closest_strike)
    # st.write(f"Absolute Difference: {abs_diff}, Minimum Increment: {min_increment}, Strike Difference: {strike_diff}")
    
    # Determine moneyness and append number of strikes away if OTM or ITM
    if option_type == 'CALL':
        if strike < spot:
            return f"ITM-{strike_diff}" if strike_diff > 0 else "ITM"
        elif strike > spot:
            return f"OTM-{strike_diff}" if strike_diff > 0 else "OTM"
        else:
            return "ATM"
    
    elif option_type == 'PUT':
        if strike > spot:
            return f"ITM-{strike_diff}" if strike_diff > 0 else "ITM"
        elif strike < spot:
            return f"OTM-{strike_diff}" if strike_diff > 0 else "OTM"
        else:
            return "ATM"
    
    return "Unknown"  # In case of an unexpected option type


def stockPC(symbol):
    """
    Calculate the put-to-call ratio for the given stock's option chain based on open interest (OI)
    and average exposure from bid/ask price.

    Args:
    - flow (dict or pandas Series): A single flow containing information about the option, including the symbol.
    - option_chain (dict): A dictionary containing the options data for a given symbol, typically fetched from an API.

    Returns:
    - float: The Put-to-Call ratio based on OI and premium exposure.
    """
    option_chain = get_options_chain(symbol)
    # Initialize totals for puts and calls
    total_put_exposure = 0.0
    total_call_exposure = 0.0
    if option_chain:
        # Iterate through the options chain dictionary
        for expiration, options in option_chain['options'].items():
            # Options data is usually nested with 'c' for calls and 'p' for puts
            calls = options.get('c', {})
            puts = options.get('p', {})
            
            # Sum exposure for call options
            for strike, call_data in calls.items():
                if 'oi' in call_data and 'b' in call_data and 'a' in call_data:
                    # Calculate the average of bid and ask
                    avg_price = (call_data['b'] + call_data['a']) / 2
                    # Multiply by OI to get total premium exposure
                    total_call_exposure += call_data['oi'] * avg_price
            
            # Sum exposure for put options
            for strike, put_data in puts.items():
                if 'oi' in put_data and 'b' in put_data and 'a' in put_data:
                    # Calculate the average of bid and ask
                    avg_price = (put_data['b'] + put_data['a']) / 2
                    # Multiply by OI to get total premium exposure
                    total_put_exposure += put_data['oi'] * avg_price
        
        # Calculate the Put-to-Call ratio based on premium exposure (OI * Avg Bid/Ask)
        # To avoid division by zero, return a large value (e.g., float('inf')) if there is no call exposure
        if total_call_exposure == 0:
            return float('inf')  # P/C ratio tends to infinity if there are no calls
        else:
            return total_put_exposure / total_call_exposure

