
import streamlit as st

import page_calculator
import page_screenSelector
import info_page_v4

### Changes from v5 ###
# - AL_Intensity is determined in a first stage calculation using DLI and photoperiod
# - Two usage calculation methods:
#       METHOD 1: Traditional AlMA (strict DLI, shorten photoperiod, lights On/Off)
#       METHOD 2: Dimmable (strict DLI, strict photoperiod, lights dimmable)
### Changes from v6 ###
# - Reworded some inputs to be accurate to function (Tout influence)
# - Updated connection to growlights_v5.py which improves the speed of AL intensity calculation
# - screen library available on info page (v3)
# - updated alma_helpers_v2 to be compatible with the new Crop Data information
### Changes from v7.1
# - updated input label wording
### Updates for v8
# - calculated daily AL intensity fixed (no longer giving very large umol/m2/s)
# - as part of the solution to fix the daily AL intensity calculation, temperature influence to close the screen had to be removed
### Updates for v9
# - moved calculator page to its own script to reference the render script like the other tabs
# - added a tab for screen selection tool

# ---------- Sidebar for Info ---------- #

st.set_page_config(layout="centered")

st.sidebar.title("Navigation")

page = st.sidebar.radio("Go to:", ["Calculator","Screen Selector","Info"], index=0)
with st.sidebar:
    with open("Productsheets.pdf", "rb") as f:
        st.download_button(
            "Open Crop Data PDF",
            f,
            file_name="Productsheets.pdf",
            mime="application/pdf"
        )

if page == "Calculator":
    page_calculator.render()

elif page == "Screen Selector":
    page_screenSelector.render()

elif page == "Info":
    info_page_v4.render()
