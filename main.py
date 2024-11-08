import pandas as pd
import streamlit as st
from datetime import datetime, timedelta

flowFile = st.file_uploader("Upload Flow File")



if flowFile is not None:
    # Load data into a DataFrame
    flows = pd.read_csv(flowFile)


    flows = flows[~(flows['ER'] == 'T')]
    today = datetime.today()
    this_week_friday = (today + timedelta((4 - today.weekday()) % 7)).replace(hour=0, minute=0, second=0, microsecond=0)
    next_week_friday = (this_week_friday + timedelta(days=7)).replace(hour=23, minute=59, second=59, microsecond=999999)

    st.write(this_week_friday)
    st.write(next_week_friday)
    flows['ExpirationDate'] = pd.to_datetime(flows['ExpirationDate'], errors='coerce')

    flows = flows[(flows['ExpirationDate'] >= this_week_friday) & (flows['ExpirationDate'] <= next_week_friday)]

    st.write("Flows:")
    st.write(flows)

    # flows.to_excel("output_data.xlsx", index=False)
    # st.success("File saved as 'output_data.xlsx'")