import pandas as pd
import streamlit as st
from datetime import datetime, timedelta
from helper import *
from db import *
import numpy as np
import time
import yfinance as yf

def get_earnings_date(symbol: str):
    try:
        ticker = yf.Ticker(symbol)
        cal = ticker.calendar
        if 'Earnings Date' in cal.index:
            return cal.loc['Earnings Date'][0]  # returns a Timestamp
    except:
        pass
    return None

flowFile = st.file_uploader("Upload Flow File")
multiLegs = st.checkbox('MultiLegs?', value= True)


if flowFile is not None:
    # Load data into a DataFrame
    flows = pd.read_csv(flowFile)

    # Set Chrome options to disable cache
    # chrome_options = webdriver.ChromeOptions()
    # chrome_options.add_argument("--disable-application-cache")
    # chrome_options.add_argument("--incognito")  # Use incognito mode to avoid using existing cache
    # chrome_options.add_argument("--headless")  # Run in headless mode
    # chrome_options.add_argument("--no-sandbox")  # Recommended for some headless environments
    # chrome_options.add_argument("--disable-dev-shm-usage")  # Recommended for some headless environments
    # user_agent = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
    # chrome_options.add_argument(f"user-agent={user_agent}")

    # # Initialize ChromeDriver with WebDriver Manager
    # driver = webdriver.Chrome(service=Service(ChromeDriverManager("131.0.6778.205").install()), options=chrome_options)

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

    # # Loop through flows for symbols with ER=True
    # for _, row in flows[flows['ER'] == 'T'].drop_duplicates(subset='Symbol').iterrows():
    #     symbol = row['Symbol']
    #     cached_date_str = get_cached_date(symbol)

    #     st.write(symbol, 'Cached', cached_date_str)
    #     # Check if cached date is within this and next week
    #     if cached_date_str:
    #         cached_date = datetime.strptime(cached_date_str, "%Y-%m-%d")

    #         if last_week_sunday <= cached_date <= next_week_friday:
    #             earnings_date = cached_date_str
    #         else:
    #             earnings_date = get_earnings_date(symbol)
    #             if earnings_date:
    #                 update_cache(symbol, earnings_date.strftime("%Y-%m-%d"))
    #     else:
    #         earnings_date = get_earnings_date(symbol)
    #         if earnings_date:
    #             update_cache(symbol, earnings_date.strftime("%Y-%m-%d"))

    #     updated_rows.append({"Symbol": symbol,
    #                          "EarningsDate": earnings_date if earnings_date else None})

    # Close the browser
    # driver.quit()

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


    flows['CreatedDateTime'] = pd.to_datetime(
        flows['CreatedDate'] + ' ' + flows['CreatedTime'], format='%m/%d/%Y %I:%M:%S %p'
    )

    # Step 4: Drop the original CreatedDate and CreatedTime columns
    flows = flows.drop(columns=['CreatedDate', 'CreatedTime'])
    # Step 2: Sort the DataFrame by the new datetime column to ensure chronological order
    flows = flows.sort_values('CreatedDateTime', ascending=True)

    # Step 3: Reset the index
    cols = ['CreatedDateTime'] + [col for col in flows.columns if col not in ['CreatedDateTime', 'CreatedDate', 'CreatedTime']]
    flows = flows[cols]

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
        'CreatedDateTime': 'last',
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

    # st.write(grouped_flows)
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
        # 1) Filter down to true multi-legs
        multi_leg_candidates = (
            flows
            .groupby(['Symbol', 'CreatedDateTime'])
            .filter(lambda g: len(g) > 1)
            .copy()
        )

        # Make sell premiums negative
        multi_leg_candidates['Premium'] = multi_leg_candidates.apply(
            lambda r: -r['Premium'] if r['Buy/Sell'] == 'SELL' else r['Premium'],
            axis=1
        )

        # 2) Build a “signature” for each timestamped group
        def make_signature(g):
            cnt = (
                g
                .groupby(['Buy/Sell', 'CallPut', 'Strike', 'ExpirationDate'])
                .size()
                .reset_index(name='count')
            )
            return ";".join(
                sorted(
                    f"{row['Buy/Sell']}_{row['CallPut']}_{row['Strike']}_{row['ExpirationDate']}_{row['count']}"
                    for _, row in cnt.iterrows()
                )
            )

        # Create signature without using include_group_columns
        sigs = (
            multi_leg_candidates
            .groupby(['Symbol', 'CreatedDateTime'])
            .apply(lambda g: pd.Series({'Signature': make_signature(g)}))
            .reset_index()
        )

        # 3) Attach signatures
        multi_leg_candidates = multi_leg_candidates.merge(
            sigs,
            on=['Symbol', 'CreatedDateTime'],
            how='left'
        )

        st.write(multi_leg_candidates)
        # 4) Aggregate within each unique leg (Symbol, CallPut, Strike, Buy/Sell, Expiry, Signature)
        agg = (
            multi_leg_candidates
            .groupby(['Symbol', 'CallPut', 'Strike', 'Buy/Sell', 'ExpirationDate', 'Signature'], as_index=False)
            .agg(
                TotalVolume=('Volume', 'sum'),
                TotalPremium=('Premium', 'sum'),
                MinOI=('OI', 'min'),
                PriceMean=('Price', 'mean'),
                SetCount=('Symbol', 'size')
            )
        )

        # 5) Merge the totals back in
        merged = multi_leg_candidates.merge(
            agg,
            on=['Symbol', 'CallPut', 'Strike', 'Buy/Sell', 'ExpirationDate', 'Signature'],
            how='left',
            suffixes=('_orig', '')
        )
        merged = merged.sort_values(['CreatedDateTime'], ascending=False).reset_index(drop=True)
        st.title('merged')
        st.write(merged)
        #Simple clean nup
        # 6) Drop duplicates to get one row per signature
        multi_leg_candidates = merged.drop_duplicates(
            subset=['Symbol', 'CallPut', 'Strike', 'Buy/Sell', 'ExpirationDate', 'Signature'],
            keep='first'
        )
        multi_leg_candidates = multi_leg_candidates.copy()
        multi_leg_candidates.drop(columns=['Premium', 'Volume', 'Price'], inplace=True)
        multi_leg_candidates = multi_leg_candidates.rename(columns={
            'TotalVolume': 'Volume',
            'TotalPremium': 'Premium',
            'PriceMean': 'Price'
        })
        multi_leg_candidates = multi_leg_candidates[abs(multi_leg_candidates['Premium']) > 100000]

        st.write(multi_leg_candidates)


        def filter_out_straddles_strangles(group):
            # st.write(group['Symbol'].iloc[0], group)
            # Check if there is both a BUY CALL and BUY PUT
            buy_call = (group['Buy/Sell'] == 'BUY') & (group['CallPut'] == 'CALL')
            buy_put = (group['Buy/Sell'] == 'BUY') & (group['CallPut'] == 'PUT')

            # Only proceed if both BUY CALL and BUY PUT exist
            if buy_call.any() and buy_put.any():
                # Calculate total premiums for BUY CALL and BUY PUT
                buy_call_premium = group.loc[buy_call, 'Premium'].sum()
                buy_put_premium = group.loc[buy_put, 'Premium'].sum()

                # Calculate the total premium for both BUY CALL and BUY PUT combined
                total_premium = buy_call_premium + buy_put_premium

                # Check if both sides contribute within a similar range (e.g., 40% - 60%)
                call_contribution = buy_call_premium / total_premium
                put_contribution = buy_put_premium / total_premium
                # If both sides contribute within a similar range (e.g., 40% - 60%), keep the group
                if 0.4 <= call_contribution <= 0.6 and 0.4 <= put_contribution <= 0.6:
                    return False  # Keep the group

            # If there isn't both or if premiums are not high enough, keep the group
            return True

        # Step 2: Define the multi-leg check function
        def is_multi_leg(group):
            # Ensure there is at least one BUY and one SELL

            # st.write(group['Symbol'].iloc[0], group)
            has_buy = (group['Buy/Sell'] == 'BUY').any()
            has_sell = (group['Buy/Sell'] == 'SELL').any()

            # Ensure there is at least one CALL and one PUT in the group
            call_put_check = {'CALL', 'PUT'}.issubset(group['CallPut'].unique())
            group['Color'] = group['Color'].str.upper()
            # Check for exactly one 'White' color in the group
            white_count = (group['Color'] == 'WHITE').sum()
            # and white_count <= 1
            if has_buy and has_sell and call_put_check and white_count == 0:
                # if (group['ER'] == 'T').any():
                #     return True
                # st.write(group)

                if not (group['Volume'] > group['OI']).all():
                    return False

                # Calculate the net premium spent (Commented out as per your code)
                total_buy_premium = group[group['Buy/Sell'] == 'BUY']['Premium'].sum()
                total_sell_premium = group[group['Buy/Sell'] == 'SELL']['Premium'].sum()
                net_premium_spent = total_buy_premium + total_sell_premium
                # IF Negative spend, make sure the ones that
                # if net_premium_spent < 0:
                #     sell_legs = group[group['Buy/Sell'] == 'SELL']
                #     # Apply the ITM check for each sell leg
                #     sell_otm = sell_legs.apply(
                #         lambda row: (row['CallPut'] == 'CALL' and row['Strike'] > row['Spot']) or
                #                     (row['CallPut'] == 'PUT' and row['Strike'] < row['Spot']),
                #         axis=1
                #     )
                #     # If all sell legs are OTM, then the negative net premium guarantees a profit
                #     # if the underlying doesn't move; so we don't consider it a multi leg.
                #     if sell_otm.all():
                #         return False
                return True
            return False

        # Apply the multi-leg filter to find qualifying groups
        multi_leg_symbols = multi_leg_candidates.groupby(['Symbol', 'CreatedDateTime']).filter(is_multi_leg)
        #Then remove the conflcting stranggle multi legs
        multi_leg_symbols = multi_leg_symbols.groupby('Symbol').filter(filter_out_straddles_strangles)


        # removeTickers = ['SPY', 'SPXW', 'SPX','NVDA', 'SMCI', 'NFLX', 'CUBE', 'TSLA', 'RUT', 'IWM', 'QQQ', 'NDXP', 'NDX', 'AAPL', 'AMZN', 'FBTC', 'GOOGL', 'RUTW']
        # multi_leg_symbols = multi_leg_symbols[~multi_leg_symbols['Symbol'].isin(removeTickers)]

        multi_leg_symbols['Separator'] = '@@@'

        desired_cols = ['CreatedDateTime', 'Symbol', 'Buy/Sell', 'CallPut', 'Strike', 'Spot', 'ExpirationDate', 'Premium', 'Volume', 'OI', 'Price', 'Side', 'Color', 'SetCount', 'ImpliedVolatility', 'Dte', 'ER', 'Separator']
        desired_order =  desired_cols
        # + [col for col in multi_leg_symbols.columns if col not in desired_cols]
        multi_leg_symbols = multi_leg_symbols[desired_order]
        multi_leg_symbols = multi_leg_symbols.sort_values(['Symbol', 'CreatedDateTime']).reset_index(drop=True)
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
