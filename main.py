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
    user_agent = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
    chrome_options.add_argument(f"user-agent={user_agent}")

    # Initialize ChromeDriver with WebDriver Manager
    driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=chrome_options)

    # Load the existing cache
    create_database()

    today = datetime.today()

    todayDATE = datetime.now().date()
    tomorrow = todayDATE + timedelta(days=1)

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

    if len(updated_rows) != 0 and not multiLegs:
        # Merge the updated earnings dates back into flows DataFrame
        updated_df = pd.DataFrame(updated_rows)
        flows = flows.merge(updated_df, on='Symbol', how='left')
        flows['EarningsDate'] = pd.to_datetime(flows['EarningsDate'], errors='coerce').dt.date
        flows = flows[~flows['EarningsDate'].isin([todayDATE, tomorrow])]
    if 'EarningsDate' not in flows.columns:
        flows['EarningsDate'] = None

    flows['ExpirationDate'] = pd.to_datetime(flows['ExpirationDate'],  errors='coerce').dt.date
    flows['Buy/Sell'] = flows['Side'].apply(lambda x: 'BUY' if x in ['A', 'AA'] else 'SELL')


    st.title("Flows:")
    st.write(flows)

    grouped_flows = flows.groupby(['Symbol', 'Buy/Sell', 'Strike', 'ExpirationDate', 'CallPut']).agg({
        # 'Moneiness':'first',
        'Spot': 'median',            # Combine Spot as min-max string
        'Volume': 'sum',
        'OI': 'first',
        'Price': 'median',
        'Premium': 'sum',
        'ER': 'first',                                     # Take the first as it should be the same
        'EarningsDate': 'first',
        'CreatedDate': lambda x: f"{min(x)}-{max(x)}",
        'CreatedTime': lambda x: f"{min(x)}-{max(x)}",
        'ImpliedVolatility': 'mean',                       # Average Implied Volatility
        'MktCap': 'first',                                 # Take the first as it should be the same
        'Sector': 'first',                                 # Take the first as it should be the same
        'StockEtf': 'first',                               # Take the first as it should be the same
        'Dte': 'first',                                    # Take the first as it should be the same
        'Uoa': 'first',                                    # Take the first as it should be the same
        'Weekly': 'first',                               # Take the first as it should be the same
        'Side': 'first',
        'Type': 'first',
    }).reset_index()

    #These are just determining the raw direction of the stock
    conditions = [
        (grouped_flows['Buy/Sell'] == 'SELL') & (grouped_flows['CallPut'] == 'CALL'),
        (grouped_flows['Buy/Sell'] == 'BUY') & (grouped_flows['CallPut'] == 'CALL'),
        (grouped_flows['Buy/Sell'] == 'SELL') & (grouped_flows['CallPut'] == 'PUT'),
        (grouped_flows['Buy/Sell'] == 'BUY') & (grouped_flows['CallPut'] == 'PUT')
    ]
    directions = ['BEARISH', 'BULLISH', 'BULLISH', 'BEARISH']
    grouped_flows['Direction'] = np.select(conditions, directions, default='neutral')

    st.write(grouped_flows)
    # For normal flkow you would want to ensure that Identify symbols where all entries have the same direction cause thats good directional bais not straddle shits
    consistent_direction_symbols = (
        grouped_flows.groupby('Symbol')['Direction']
        .nunique()
        .loc[lambda x: x == 1]  # Filter to only symbols with a single unique direction
        .index
    )

    # grouped_flows = grouped_flows[grouped_flows['Volume'] > 300]

    # consistent symbols with the same directions
    consistent_df = grouped_flows[grouped_flows['Symbol'].isin(consistent_direction_symbols)]
    #inconsistent symbols with multiple directions
    remaining_df = grouped_flows[~grouped_flows['Symbol'].isin(consistent_direction_symbols)]

    if multiLegs:
        # Step 1: Filter for symbols with more than one entry and high premium
        # We are interested only in trades with premiums over $100,000 to narrow down
        flows = flows[flows['Premium'] > 100000]
        multi_leg_candidates = flows.groupby(['Symbol', 'CreatedDate', 'CreatedTime']).filter(lambda x: len(x) > 1)
        st.dataframe(multi_leg_candidates)  # Display initial multi-leg candidates for review

        # Step 2: Define the multi-leg check function
        def is_multi_leg(group):
            # Ensure there is at least one BUY and one SELL

            st.write(group['Symbol'].iloc[0], group)
            has_buy = (group['Buy/Sell'] == 'BUY').any()
            has_sell = (group['Buy/Sell'] == 'SELL').any()

            # Ensure there is at least one CALL and one PUT in the group
            call_put_check = {'CALL', 'PUT'}.issubset(group['CallPut'].unique())

            if has_buy and has_sell and call_put_check:

                # # Calculate the net premium spent
                # total_buy_premium = group[group['Buy/Sell'] == 'BUY']['Premium'].sum()
                # total_sell_premium = group[group['Buy/Sell'] == 'SELL']['Premium'].sum()
                # net_premium_spent = total_buy_premium - total_sell_premium

                # # We want to ensure the trader is spending at least $80,000 in net
                # if net_premium_spent >= 10000:
                #     return True
                return True
            return False

        # Apply the multi-leg filter to find qualifying groups
        multi_leg_symbols = multi_leg_candidates.groupby(['Symbol', 'CreatedDate', 'CreatedTime']).filter(is_multi_leg)
        multi_leg_symbols['Premium'] = multi_leg_symbols.apply(
            lambda row: -row['Premium'] if row['Buy/Sell'] == 'SELL' else row['Premium'], axis=1
        )
        # Display the result in Streamlit
        st.title('Multi Legs worth Noting')
        st.dataframe(multi_leg_symbols)
        st.stop()


    #Now you want to make sure that those with two directions are actually trades with a 30% hedge.
    st.dataframe(consistent_df)
    st.dataframe(remaining_df)
    filtered_remaining = []
    for symbol in remaining_df['Symbol'].unique():
        symbol_df = remaining_df[remaining_df['Symbol'] == symbol]

        # Step 1: Sort the symbol_df by relevant columns to align buy/sell pairs
        symbol_df = symbol_df.sort_values(by=['ExpirationDate', 'CallPut', 'Strike', 'Buy/Sell'])

        st.write(symbol, symbol_df)
        # Step 2: Identify and remove net-zero activity (matching buy/sell pairs)
        to_drop = []

        for i in range(len(symbol_df) - 1):
            row1 = symbol_df.iloc[i]
            row2 = symbol_df.iloc[i + 1]
            # Check if the current row and the next row form a buy/sell pair with net-zero effect
            if (
                row1['Symbol'] == row2['Symbol'] and
                row1['ExpirationDate'] == row2['ExpirationDate'] and
                row1['CallPut'] == row2['CallPut'] and
                row1['Strike'] == row2['Strike'] and
                row1['Buy/Sell'] != row2['Buy/Sell'] and
                abs(row1['Premium'] - row2['Premium']) <= 50000
            ):
                to_drop.extend([i, i + 1])

        # Drop the identified rows (net-zero buy/sell pairs)
        symbol_df = symbol_df.drop(symbol_df.index[to_drop])
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

    ### The fnal shits
    # Combine consistent_df with the filtered remaining data for final result
    final_df = pd.concat([consistent_df, filtered_remaining_df], ignore_index=True)

    # make sure that Volume is at least 1.5x for each of the same Symbol, EXpiration, side etc. cause like if after aggregating and ur still not that big of an OI then gg bro
    final_df = final_df[1.5 * final_df['Volume'] >= final_df['OI']]
    final_df = final_df[final_df['Volume'] > 300]

    #Aggregate all the symbols and then we can determine if the total trades on the stock is of a decent size.
    totalPremiumPerStock = final_df.groupby(['Symbol', 'Direction']).agg({
        'Volume': 'sum',
        'Premium': 'sum'
    }).reset_index()
    totalPremiumPerStock= totalPremiumPerStock[totalPremiumPerStock['Premium'] > 100000]

    final_df = final_df[final_df['Symbol'].isin(totalPremiumPerStock['Symbol'])]
    #PC Ratios calcaultion. get the unqiue symolbs and then get the pc for each
    # Create a dictionary to store the put-to-call ratios for each unique symbol and expiration date combination
    pc_ratios = {
        (symbol, expiration_date): stockPC(symbol, expiration_date)
        for symbol, expiration_date in final_df[['Symbol', 'ExpirationDate']].drop_duplicates().itertuples(index=False)
    }

    # Convert the dictionary to a DataFrame for merging
    pc_df = pd.DataFrame(
        [(symbol, expiration_date, pc_value) for (symbol, expiration_date), pc_value in pc_ratios.items()],
        columns=['Symbol', 'ExpirationDate', 'PC']
    )

    # Merge back with the final_df using both Symbol and ExpirationDate
    final_df = final_df.merge(pc_df, on=['Symbol', 'ExpirationDate'], how='left')


    final_df['Moneiness'] = final_df.apply(lambda flow: moneiness(flow, get_options_chain(flow['Symbol'])), axis=1)
    final_df['StrikeDiff'] = final_df['Moneiness'].apply(lambda x: int(x.split('-')[1]) if '-' in x else 0)
    final_df = final_df[final_df['StrikeDiff'] <= 10]
    final_df = final_df.drop(columns=['StrikeDiff'])


    flowTrackingCols = ['Symbol', 'Buy/Sell','ExpirationDate', 'Moneiness', 'CallPut', 'Volume', 'Price', 'PC']
    remaining_columns = [col for col in final_df.columns if col not in flowTrackingCols]
    final_column_order = flowTrackingCols + remaining_columns
    final_df = final_df[final_column_order]

    final_df.reset_index(drop=True, inplace=True)
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
    final_df['Premium'] = final_df['Premium'].astype(float)
    final_df['Premium'] = final_df.apply(
            lambda row: -row['Premium'] if row['Buy/Sell'] == 'SELL' else row['Premium'], axis=1
    )
    final_df['Premium'] = final_df['Premium'].apply(lambda x: f"{x:,.2f}")

    def highlight_er_row(row):
        return ['background-color: yellow' if row['ER'] == 'T' else '' for _ in row]

    # Apply the styling to the entire row based on the ER column
    flowStyle = final_df.style.apply(highlight_er_row, axis=1)
    # Use `st.write` to display the styled DataFrame

    st.title('Final Flows')
    st.write(flowStyle)
