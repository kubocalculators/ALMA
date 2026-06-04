"""
If the user selects "info" in the side bar, the following inforamtion will be displayed
"""
# Updates since v1
# WAITING for confirmation on changes to main_v6 and then I will make the info page match what the calculator really does
# Updates for v4
# moved the list of common screens to the screen selection tool page

import streamlit as st
import pandas as pd

def render():

    st.title("How This Calculator Works")

    st.markdown("""

    First, the recommended growlight (AL) intensity, umol/m2/s, is determined from the climate data, crop specifications (including DLI and photoperiod), and screen limits.  \n
    - For each hour, it is determined if growlights are allowed to be on or not by the following criteria:
        - The hour is within the time window defined by the starting hour and the photoperiod
        - Solar radiation is lower than the set threshold
        - Outside temperature is not above the temperature setpoint
        - The month is not within the blackout range  \n
    Then, using all allowed hours, the hourly required growlight intensity is determined such that the DLI will be met exactly each day.  \n
    For each day, the solar radiation (after the screens) is first considered against the target DLI. Using bisection method, an hourly intensity target is determined for each day,
                which ensures the DLI is met at the end of the photoperiod. The growlight intensity makes up the difference between the solar radiation and the daily target for each hour.  \n
    **Here is an excerpt from the Python script which does this calculation:**  \n
        key = ["Year", "Month", "Day"]
        w["IntensityTarget_daily"] = 0

        for _, day_data in w.groupby(key):
            # day_data is a DataFrame containing all columns for just one day
            
            # Compute the daily intensity target based on solar radiation and targets (DLI & photoperiod)
            daily_target = bisection_method_intensity(day_data, dli_target, photoperiod)

            # Store daily target in w DataFrame
            w.loc[day_data.index, "IntensityTarget_daily"] = daily_target
        
        # Calculate the hourly AL Intensity needed to reach each daily intensity target
        w["AL_Intensity"] = (w["IntensityTarget_daily"] - w["Solar_Intensity"]).clip(lower=0).where(w["AL_Possible"], 0.0)

    """)

    st.subheader("Calculating Radiation at the Crop Level")

    st.markdown("""

    **Step 1:** Convert PAR (W/m2) to PAR (umol/m2/h)  \n
    **Step 2:** Radiation After the Roof = Transmissivity (80%) x PAR (umol/m2/h)  \n
    **Step 3:** Compute Screen Positions

    """)
    st.latex(r"""
    \mathrm{Screen\ Position\ (0-1)} =
    \mathrm{Outside\ Radiation\ (W/m^2)}
    -
    \frac{
    \mathrm{Screen\ Lower\ Radiation\ Limit\ (\%)}
    }{
    \mathrm{Screen\ Upper\ Radiation\ Limit\ (\%)}
    }
    -
    \mathrm{Screen\ Lower\ Radiation\ Limit\ (\%)}
    """)
    st.markdown("""
    **Step 4:** Compute radiation at crop level (after screens)
    """)
    st.latex(r"""
    \mathrm{Radiation\ (Crop\ Level)} =
    \mathrm{Radiation\ (Under\ Roof)}
    \times
    \left(1 - \mathrm{Screen\ 1\ Shade\ (\%)}\right)
    \left(\mathrm{Screen\ 1\ Position}\right)
    \times
    \left(1 - \mathrm{Screen\ 2\ Shade\ (\%)}\right)
    \left(\mathrm{Screen\ 2\ Position}\right)
    """)

    st.subheader("Dimmable vs Non-Dimmable Usage")
    st.markdown("With dimmable lights, both the DLI and photoperiod targets are strict. Target hourly light intensity (Solar + AL) is calculated per day, by dividing the" \
    "remaining DLI between the entire range of the photoperiod.")
    st.markdown("Non-dimmable lights are designed to be the max. intensity needed for the darkest days (ie. winter). During summer, turning the lights on to meet DLI can result" \
    "in very high total light intensities if not coordinated with sunlight.")

    st.markdown("**Summer**")
    st.image("Summer_Demo.jpg", width=2000)

    st.markdown("**Winter**")
    st.image("Winter_Demo.jpg", width=2000)

