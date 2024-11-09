import sqlite3
import streamlit as st

# SQLite database functions
def create_database(db_name="earnings_cache.db"):
    # st.write(f"Attempting to connect to database '{db_name}'...")
    conn = sqlite3.connect(db_name)
    cursor = conn.cursor()
    # st.write("Connected to database. Checking for 'earnings_dates' table...")

    cursor.execute('''CREATE TABLE IF NOT EXISTS earnings_dates (
                      Symbol TEXT PRIMARY KEY,
                      EarningsDate TEXT
                      )''')
    conn.commit()
    # st.write("Table 'earnings_dates' is ready in database.")

    conn.close()

def get_cached_date(symbol, db_name="earnings_cache.db"):
    # st.write(f"Retrieving cached earnings date for Symbol: {symbol} from '{db_name}'...")
    conn = sqlite3.connect(db_name)
    cursor = conn.cursor()
    cursor.execute("SELECT EarningsDate FROM earnings_dates WHERE Symbol = ?", (symbol,))
    result = cursor.fetchone()
    conn.close()

    # if result:
    #     st.write(f"Found earnings date for {symbol}: {result[0]}")
    # else:
    #     st.write(f"No earnings date found for {symbol}.")
    return result[0] if result else None

def update_cache(symbol, earnings_date, db_name="earnings_cache.db"):
    # st.write(f"Updating cache for Symbol: {symbol} with EarningsDate: {earnings_date} in '{db_name}'...")
    conn = sqlite3.connect(db_name)
    cursor = conn.cursor()
    cursor.execute("INSERT OR REPLACE INTO earnings_dates (Symbol, EarningsDate) VALUES (?, ?)", (symbol, earnings_date))
    conn.commit()
    # st.write(f"Cache updated for {symbol}.")
    conn.close()
