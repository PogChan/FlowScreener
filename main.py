import pandas as pd
import streamlit as st
from datetime import datetime, timedelta
from helper import *
from db import *
import numpy as np
import time

flowFile = st.file_uploader("Upload Flow File")
multiLegs = st.checkbox('MultiLegs?')


if flowFile is not None:
    # Load data into a DataFrame
    flows = pd.read_csv(flowFile)

    # Set Chrome options to disable cache
    chrome_options = webdriver.ChromeOptions()
    chrome_options.add_argument("--disable-application-cache")
    chrome_options.add_argument("--incognito")  # Use incognito mode to avoid using existing cache
    chrome_options.add_argument("--headless")  # Run in headless mode
    chrome_options.add_argument("--no-sandbox")  # Recommended for some headless environments
    chrome_options.add_argument("--disable-dev-shm-usage")  # Recommended for some headless environments

    # Initialize ChromeDriver with WebDriver Manager
    driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=chrome_options)

    # Load the existing cache
    create_database()

    today = datetime.today()
    this_week_friday = (today + timedelta((4 - today.weekday()) % 7)).replace(hour=0, minute=0, second=0, microsecond=0)
    next_week_friday = (this_week_friday + timedelta(days=7)).replace(hour=23, minute=59, second=59, microsecond=999999)
    last_week_sunday = (today - timedelta(days=today.weekday() + 1)).replace(hour=0, minute=0, second=0, microsecond=0)

    st.write(this_week_friday)
    st.write(next_week_friday)
    st.write(last_week_sunday)
    flows['ExpirationDate'] = pd.to_datetime(flows['ExpirationDate'], errors='coerce')

    if not multiLegs:
        flows = flows[(flows['ExpirationDate'] >= this_week_friday) & (flows['ExpirationDate'] <= next_week_friday)]

    updated_rows = []

    # Loop through flows for symbols with ER=True
    for _, row in flows[flows['ER'] == 'T'].drop_duplicates(subset='Symbol').iterrows():
        symbol = row['Symbol']
        cached_date_str = get_cached_date(symbol)

        st.write(symbol, 'Cached', cached_date_str)
        # Check if cached date is within this and next week
        if cached_date_str:
            cached_date = datetime.strptime(cached_date_str, "%Y-%m-%d")

            if last_week_sunday <= cached_date <= next_week_friday:
                earnings_date = cached_date_str
            else:
                earnings_date = get_earnings_date(symbol, driver)
                if earnings_date:
                    update_cache(symbol, earnings_date)
        else:
            earnings_date = get_earnings_date(symbol, driver)
            if earnings_date:
                update_cache(symbol, earnings_date)

        updated_rows.append({"Symbol": symbol, "EarningsDate": earnings_date})


    # Close the browser
    driver.quit()

    # Merge the updated earnings dates back into flows DataFrame
    updated_df = pd.DataFrame(updated_rows)
    flows = flows.merge(updated_df, on='Symbol', how='left')

    flows['Buy/Sell'] = flows['Side'].apply(lambda x: 'BUY' if x in ['A', 'AA'] else 'SELL')
    
    st.title("Flows:")
    st.write(flows)

    grouped_flows = flows.groupby(['Symbol', 'Buy/Sell', 'Strike', 'ExpirationDate', 'CallPut']).agg({
        'Spot': lambda x: f"{min(x)}-{max(x)}",            # Combine Spot as min-max string
        'Volume': 'sum',                                   # Sum the Volume
        'Price': 'median',                                 # Median of the Price
        'Premium': 'sum',                                  # Sum the Premium
        'OI': 'first',                                     # Retain the first OI
        'ER': 'first',                                     # Take the first as it should be the same
        'EarningsDate': 'first',        
        'ImpliedVolatility': 'mean',                       # Average Implied Volatility
        'MktCap': 'first',                                 # Take the first as it should be the same
        'Sector': 'first',                                 # Take the first as it should be the same
        'StockEtf': 'first',                               # Take the first as it should be the same
        'Dte': 'first',                                    # Take the first as it should be the same
        'Uoa': 'first',                                    # Take the first as it should be the same
        'Weekly': 'first',                               # Take the first as it should be the same
        'Side': 'first',
        'Type': 'first',
        'CreatedDate': lambda x: f"{min(x)}-{max(x)}", 
        'CreatedTime': lambda x: f"{min(x)}-{max(x)}"
    }).reset_index()
    
    conditions = [
        (grouped_flows['Buy/Sell'] == 'SELL') & (grouped_flows['CallPut'] == 'CALL'),
        (grouped_flows['Buy/Sell'] == 'BUY') & (grouped_flows['CallPut'] == 'CALL'),
        (grouped_flows['Buy/Sell'] == 'SELL') & (grouped_flows['CallPut'] == 'PUT'),
        (grouped_flows['Buy/Sell'] == 'BUY') & (grouped_flows['CallPut'] == 'PUT')
    ]
    directions = ['BEARISH', 'BULLISH', 'BULLISH', 'BEARISH']
    grouped_flows['Direction'] = np.select(conditions, directions, default='neutral')

    # For normal flkow you would want to ensure that Identify symbols where all entries have the same direction cause thats good directional bais not straddle shits
    consistent_direction_symbols = (
        grouped_flows.groupby('Symbol')['Direction']
        .nunique()
        .loc[lambda x: x == 1]  # Filter to only symbols with a single unique direction
        .index
    )

    grouped_flows = grouped_flows[grouped_flows['Volume'] > 300]

    # consistent symbols with the same direciton
    consistent_df = grouped_flows[grouped_flows['Symbol'].isin(consistent_direction_symbols)]
    #inconsistent symbols with multiple directions
    remaining_df = grouped_flows[~grouped_flows['Symbol'].isin(consistent_direction_symbols)]
    
    if multiLegs:
        # Step 1: Filter for symbols with more than one entry and a high premium
        grouped_flows = grouped_flows[grouped_flows['Premium'] > 100000]
        multi_leg_candidates = grouped_flows.groupby(['Symbol', 'Direction', 'ExpirationDate']).filter(lambda x: len(x) > 1)
        
        st.dataframe(multi_leg_candidates)  # Display initial multi-leg candidates

        # Step 2: Define the multi-leg check function with a diagnostic for "EWZ"
        def is_multi_leg(group):
            # Check conditions for multi-leg criteria
            expiration_check = group['ExpirationDate'].nunique() == 1
            created_date_check = group['CreatedDate'].nunique() == 1
            created_time_check = group['CreatedTime'].nunique() == 1
            call_put_check = set(group['CallPut']) == {'CALL', 'PUT'}
            direction_check = group['Direction'].nunique() == 1
            
            # All conditions must be met
            return expiration_check and created_date_check and created_time_check and call_put_check and direction_check

        # Apply the multi-leg filter
        multi_leg_symbols = multi_leg_candidates.groupby(['Symbol', 'Direction', 'ExpirationDate']).filter(is_multi_leg)

        # Display the result in Streamlit
        st.title('Multi Legs worth Noting')
        st.dataframe(multi_leg_symbols)
        st.stop()




    st.dataframe(consistent_df)
    st.dataframe(remaining_df)
    filtered_remaining = []
    for symbol in remaining_df['Symbol'].unique():
        symbol_df = remaining_df[remaining_df['Symbol'] == symbol]
        
        # Calculate total premium for bullish and bearish directions
        bullish_premium = symbol_df[symbol_df['Direction'] == 'BULLISH']['Premium'].sum()
        bearish_premium = symbol_df[symbol_df['Direction'] == 'BEARISH']['Premium'].sum()
        total_premium = bullish_premium + bearish_premium
        percentagePrems =  0.7
        # Keep only if one direction accounts for 60% or more of the total premium
        if (bullish_premium / total_premium >= percentagePrems) or (bearish_premium / total_premium >= percentagePrems):
            filtered_remaining.append(symbol_df)

    # Concatenate the filtered remaining data
    filtered_remaining_df = pd.concat(filtered_remaining, ignore_index=True)
    st.write('Remaining After filtering', filtered_remaining_df)

 
    # Combine consistent_df with the filtered remaining data for final result
    final_df = pd.concat([consistent_df, filtered_remaining_df], ignore_index=True)

    final_df= final_df[final_df['Premium'] > 50000]
    final_df = final_df[1.5 * final_df['Volume'] >= final_df['OI']]

    st.dataframe(final_df)
    #Greater than avreage OI #TODO
    filtered_flows = []

    # # Process each flow
    # for _, flow in final_df.iterrows():
    #     symbol = flow['Symbol']
    #     spot_price = flow['Spot'].split('-')[0]  # Extract the spot price from the range
    #     volume = flow['Volume']
    #     expiration_date = flow['ExpirationDate']  # Ensure this is a datetime object
    #     time.sleep(1)
    #     # Fetch options chain data for the symbol
    #     options_data = get_options_chain(symbol)
    #     if options_data:
    #         # Calculate average volume for 15 closest strikes to spot price, matching the expiration date
    #         avg_volume = calculate_avg_volume_for_expiration(options_data, spot_price, expiration_date)
            
    #         # Filter out flows whose volume is below the average for the matching expiration date
    #         if avg_volume is not None and volume >= avg_volume:
    #             filtered_flows.append(flow)
    # final_df = pd.DataFrame(filtered_flows)

    def highlight_er_row(row):
        return ['background-color: yellow' if row['ER'] == 'T' else '' for _ in row]

    # Apply the styling to the entire row based on the ER column
    flowStyle = final_df.style.apply(highlight_er_row, axis=1)
    # Use `st.write` to display the styled DataFrame

    st.title('Final Flows')
    st.write(flowStyle)