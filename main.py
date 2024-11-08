import pandas as pd
import streamlit as st
from datetime import datetime, timedelta
from helper import * 


flowFile = st.file_uploader("Upload Flow File")



if flowFile is not None:
    # Load data into a DataFrame
    flows = pd.read_csv(flowFile)

    # Set Chrome options to disable cache
    chrome_options = webdriver.ChromeOptions()
    chrome_options.add_argument("--disable-application-cache")
    chrome_options.add_argument("--incognito")  # Use incognito mode to avoid using existing cache

    # Initialize ChromeDriver with WebDriver Manager
    driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=chrome_options)

    # Load the existing cache
    create_database()

    today = datetime.today()
    this_week_friday = (today + timedelta((4 - today.weekday()) % 7)).replace(hour=0, minute=0, second=0, microsecond=0)
    next_week_friday = (this_week_friday + timedelta(days=7)).replace(hour=23, minute=59, second=59, microsecond=999999)

    st.write(this_week_friday)
    st.write(next_week_friday)
    flows['ExpirationDate'] = pd.to_datetime(flows['ExpirationDate'], errors='coerce')

    flows = flows[(flows['ExpirationDate'] >= this_week_friday) & (flows['ExpirationDate'] <= next_week_friday)]

    updated_rows = []

    # Loop through flows for symbols with ER=True
    for _, row in flows[flows['ER'] == 'T'].iterrows():
        symbol = row['Symbol']
        cached_date_str = get_cached_date(symbol)

        # Check if cached date is within this and next week
        if cached_date_str:
            cached_date = datetime.strptime(cached_date_str, "%Y-%m-%d")
            if this_week_friday <= cached_date <= next_week_friday:
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
    
    st.write("Flows:")
    st.write(flows)
    # flows.to_excel("output_data.xlsx", index=False)
    # st.success("File saved as 'output_data.xlsx'")