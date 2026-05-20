

import io
import streamlit as st
import pandas as pd
import info_page_v3

from growlights_v6 import AL_intensity_needed, AL_intensity_matrix, LED_usage, LED_dimmable_usage, plot_avgDLI, barplot_avgDLI, ScreenParams, compute_radiation_after_screen
from alma_helpers_v3 import update_crop, clear_results, load_weather

months = ("Jan", "Feb", "Mar", "Apr", "May", "June", "July", "Aug", "Sept", "Oct", "Nov", "Dec")

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


# --- Default U-value data as placeholders in case if we choose to use the energy data and re-include the inputs
default_u_roof = 6.90
default_u_leak = 0.70
default_scr1_energy = 47
default_scr2_energy = 47

crop_list = [
    "TOMATO ON THE VINE, large",
    "CHERRY TOMATO",
    "BEEF TOMATO",
    "CUCUMBER - LONG ENGLISH, high wire",
    "CUCUMBER - LONG ENGLISH, traditional",
    "CUCUMBER - SNACK/MINI, high wire",
    "CUCUMBER - SNACK/MINI, traditional",
    "ROSES",
    "STRAWBERRY - EVERBEARING",
    "STRAWBERRY - JUNE BEARING",
    "LETTUCE, baby leaf",
    "LETTUCE, baby/teen leaf (direct seeding)",
    "LETTUCE, teen leaf (transplanted)",
    "LETTUCE, whole head (medium)",
    "LETTUCE, whole head (large)",
    "SWEET POINT PEPPER",
    "BELL PEPPER"
]

# ---------- Sidebar for Info ---------- #

st.set_page_config(layout="centered")

st.sidebar.title("Navigation")

page = st.sidebar.radio("Go to:", ["Calculator","Info"], index=0)
with st.sidebar:
    with open("Productsheets.pdf", "rb") as f:
        st.download_button(
            "Open Crop Data PDF",
            f,
            file_name="Productsheets.pdf",
            mime="application/pdf"
        )

if page == "Calculator":
    # ---------- Main Page ---------- #

    st.title("Grow Lights - Monthly DLI")

    uploaded = st.file_uploader(":red[**Upload weather data (Excel file)**] (https://ksgclimatedata.streamlit.app/)", type=["xlsx"])

    # Select Crop and Retreive Crop Data
    st.header("Step 1: Enter Crop Specifications")
    
    crop_name = st.selectbox(":red[**Select Crop**]", crop_list, key="crop_name", on_change=update_crop)
    # This avoids an error (missing key) when app first starts since update_crop runs "on change"
    if "photoperiod" not in st.session_state:
        update_crop()

    st.caption("If data is available, crop setpoints will populate with crop selection")
    photoperiod = st.number_input("Photoperiod (h)", key="photoperiod")

    st.caption("Lamp intensity will be calculated for each DLI and displayed in a table of percentiles.")
    dli_min = st.number_input("Minimum DLI (mol/m2/day)", key="dli_min_val")
    dli_op = st.number_input("Optimal DLI (mol/m2/day)", key="dli_op_val")
    dli_max = st.number_input("Maximum DLI (mol/m²/day)", key="dli_max_val")

    # No longer functional
    with st.expander("Default Settings (Optional to Adjust): Day/Night Temperature Setpoints", expanded=False):
        st.caption("Artificial lighting will not be allowed for outside temperatures higher than these setpoints.")
        day_temp_setpoint = st.number_input("Day temp setpoint (°C)", key="day_max_temp")
        night_temp_setpoint = st.number_input("Night temp setpoint (°C)", key="night_max_temp")

    # ---------- Step 2: Determining the AL Intensity ---------- #

    with st.form("intensity", clear_on_submit=False):
        st.header("Step 2: Determine AL Intensity")
        st.caption("Using DLI and photoperiod, required lamp intensity is calculated. From the results, select an intensity to use in the next section of the calculator.")

        st.caption("Optional: month window where growlights are disabled (Excel L3..M3). Jan = 1, Feb = 2, etc. Set to 0 to disable.")
        al_off_start_month = st.number_input("Blackout start month", min_value=0, max_value=12, value=0, step=1)
        al_off_end_month = st.number_input("Blackout end month", min_value=0, max_value=12, value=0, step=1)

        with st.expander("Default Settings (Optional to Adjust)", expanded=False):
            st.caption("Artificial lighting will not be allowed before this hour (24:00)")
            start = st.number_input("Start hour", min_value=0, max_value=23, value=5, step=1)
            st.caption("Artificial lighting will not be allowed for outside radiation above this Radiation setpoint:")
            rad_setpoint = st.number_input("Radiation setpoint (W/m²)", min_value=0.0, value=400.0, step=10.0, format="%.0f")

            trans_roof = st.number_input("Roof transmission (0-1)", min_value=0.0, max_value=1.0, value=0.8, step=0.01)
            nr_screens = st.number_input("Number of screens", min_value=0, max_value=2, value=2, step=1)
            Tout_influence = st.number_input("Force Screens closed at Temp (C)", value=-1.0, step=0.5, format="%.1f")
            use_temp_influence_screen2 = st.checkbox("Use Tout influence for Screen 2 as well (force closed when T_out < Tout_influence)", value=False)

        st.caption("For common screen shading percentages, see the Info tab.")
        screen_1_shading_pct = st.number_input(":red[**Screen 1 shading (%)**]", min_value=0.0, max_value=100.0, value=13.0, step=1.0, format="%.0f", key="scr1_shade")
        screen_2_shading_pct = st.number_input(":red[**Screen 2 shading (%)**]", min_value=0.0, max_value=100.0, value=20.0, step=1.0, format="%.0f", key="scr2_shade")

        with st.expander("Default Settings (Optional to Adjust): Lower/Upper radiation limits for screen position control", expanded=False):
            screen_1_lower_limit = st.number_input("Screen 1 lower radiation limit (W/m²)", min_value=0.0, value=600.0, step=10.0, format="%.0f")
            screen_1_upper_limit = st.number_input("Screen 1 upper radiation limit (W/m²)", min_value=0.0, value=700.0, step=10.0, format="%.0f")
            screen_2_lower_limit = st.number_input("Screen 2 lower radiation limit (W/m²)", min_value=0.0, value=750.0, step=10.0, format="%.0f")
            screen_2_upper_limit = st.number_input("Screen 2 upper radiation limit (W/m²)", min_value=0.0, value=850.0, step=10.0, format="%.0f")

        run_intensity = st.form_submit_button("Calculate")

    if run_intensity:
        if uploaded is None:
            st.warning("Please upload an Excel file.")
            st.stop()

        weather = load_weather(uploaded)
        st.success(f"✅ Weather data loaded {len(weather):,} hourly rows")

        # Screen Parameters
        sp = ScreenParams(
                    trans_roof=float(trans_roof),
                    u_roof=default_u_roof,
                    u_leak=default_u_leak,
                    Tout_influence=float(Tout_influence),
                    nr_screens=int(nr_screens),
                    screen_1_shading_pct=float(screen_1_shading_pct),
                    screen_1_energy_pct=default_scr1_energy,
                    screen_1_lower_limit=float(screen_1_lower_limit),
                    screen_1_upper_limit=float(screen_1_upper_limit),
                    screen_2_shading_pct=float(screen_2_shading_pct),
                    screen_2_energy_pct=default_scr2_energy,
                    screen_2_lower_limit=float(screen_2_lower_limit),
                    screen_2_upper_limit=float(screen_2_upper_limit),
                )

        # Calculation 1 - Compute radiation after the glass and screen
        Isun_after, total_U, s1pos, s2pos = compute_radiation_after_screen(weather["Isun"], weather["Temp"], sp, temp_screen2=1 if use_temp_influence_screen2 else 0)
        weather = weather.copy()
        weather["Isun"] = Isun_after

        # Calculation 2 - Compute AL Intensities
        weather_addIntensity_minDLI = AL_intensity_needed(weather, start, photoperiod, rad_setpoint, day_temp_setpoint, al_off_start_month, al_off_end_month, dli_min)
        weather_addIntensity_optimalDLI = AL_intensity_needed(weather, start, photoperiod, rad_setpoint, day_temp_setpoint, al_off_start_month, al_off_end_month, dli_op)
        weather_addIntensity_maxDLI = AL_intensity_needed(weather, start, photoperiod, rad_setpoint, day_temp_setpoint, al_off_start_month, al_off_end_month, dli_max)

        # Calculation 3 - Generate and display AL Intensity Table
      
        intensity_table = AL_intensity_matrix(
            weather_addIntensity_minDLI,
            weather_addIntensity_optimalDLI,
            weather_addIntensity_maxDLI,
        )
        intensity_table.columns = [
            f"Min ({dli_min} mol/m2/day)",
            f"Optimal ({dli_op} mol/m2/day)",
            f"Max ({dli_max} mol/m2/day)"
        ]

        # Save results to session state to keep from clearing / re-uploading in Step 3
        st.session_state["intensity_results"] = intensity_table
        st.session_state["weather_data"] = weather

    # Display results (persistent)
    if "intensity_results" in st.session_state:
        st.dataframe(st.session_state["intensity_results"], hide_index=True)

    # ---------- Step 3: AlMA Calculator - Monthly Usage ---------- #
    
    st.header("Step 3: Calculate Monthly Usage")
    system = st.radio("Select Lighting System:", ["LED (On/Off, Fixed DLI, Variable Photoperiod)", "LED (Dimmable, Fixed DLI & Photoperiod)"])

    if system == "LED (On/Off, Fixed DLI, Variable Photoperiod)":
        with st.form("LED_monthly_usage", clear_on_submit=False):
            st.caption("Enter your chosen target intensity (unmol/m2/s). AlMA will calculate monthly usage. Photoperiod may be shorter than selected value if lights reach DLI before the photoperiod is up.")

            dli_target = st.number_input(":red[**Target DLI (mol/m²/day)**]", format="%.0f", key="selected_dli")
            al_intensity = st.number_input(":red[**AL intensity (µmol/m²/s)**]", min_value=0.0, step=10.0, format="%.0f", key="selected_intensity")
            led_eff = st.number_input("LED efficiency (µmol/J)", min_value=0.01, value=3.6, step=0.1, format="%.1f")

            run_AlMA = st.form_submit_button("Calculate")
    
    elif system == "LED (Dimmable, Fixed DLI & Photoperiod)":
        with st.form("LED_dimmable_monthly_usage", clear_on_submit=False):
            st.caption("Enter your chosen DLI target. Photoperiod remains the same as input above. Hourly electrical consumption is based on intensity needed rather than lamp maximum.")
            dli_target = st.number_input(":red[**Target DLI (mol/m²/day)**]", format="%.0f", key="selected_dli")
            led_eff = st.number_input("LED efficiency (µmol/J)", min_value=0.01, value=3.6, step=0.1, format="%.1f", key="selected_efficiency")
            run_AlMA = st.form_submit_button("Calculate")

    if run_AlMA:

        if "weather_data" in st.session_state:
            weather = st.session_state["weather_data"]
        else:
            if uploaded is not None:
                weather = load_weather(uploaded)
            else:
                st.error("Please upload weather data and run Step 2 first.")
                st.stop()

        # Screen Parameters
        sp = ScreenParams(
                    trans_roof=float(trans_roof),
                    u_roof=default_u_roof,
                    u_leak=default_u_leak,
                    Tout_influence=float(Tout_influence),
                    nr_screens=int(nr_screens),
                    screen_1_shading_pct=float(screen_1_shading_pct),
                    screen_1_energy_pct=default_scr1_energy,
                    screen_1_lower_limit=float(screen_1_lower_limit),
                    screen_1_upper_limit=float(screen_1_upper_limit),
                    screen_2_shading_pct=float(screen_2_shading_pct),
                    screen_2_energy_pct=default_scr2_energy,
                    screen_2_lower_limit=float(screen_2_lower_limit),
                    screen_2_upper_limit=float(screen_2_upper_limit),
                )

        # Calculation 1 - Compute radiation after the glass and screen
        Isun_after, total_U, s1pos, s2pos = compute_radiation_after_screen(weather["Isun"], weather["Temp"], sp, temp_screen2=1 if use_temp_influence_screen2 else 0)
        weather = weather.copy()
        weather["Isun"] = Isun_after

        # Calculation 2 - Calculate monthly usage
            # LED
        if system == "LED (On/Off, Fixed DLI, Variable Photoperiod)":
            weather_addIntensity = AL_intensity_needed(weather, start, photoperiod, rad_setpoint, day_temp_setpoint, al_off_start_month, al_off_end_month, dli_target)
            monthly, weather_complete = LED_usage(weather_addIntensity, dli_target, al_intensity, led_eff)

            # LED (Dimmable)
        elif system == "LED (Dimmable, Fixed DLI & Photoperiod)":
            weather_addIntensity = AL_intensity_needed(weather, start, photoperiod, rad_setpoint, day_temp_setpoint, al_off_start_month, al_off_end_month, dli_target)
            monthly, weather_complete = LED_dimmable_usage(weather_addIntensity, dli_target, led_eff)
        

        fig1 = plot_avgDLI(monthly, months)
        fig2 = barplot_avgDLI(monthly, months)

        st.session_state["results"] = {
            "monthly": monthly,
            "fig1": fig1,
            "fig2": fig2,
            "hourly_data": weather_complete
            }
        
        if "results" in st.session_state:
            res = st.session_state["results"]

        # Plot graph outputs
        st.pyplot(res["fig1"],  use_container_width=True)
        buf1 = io.BytesIO()
        res["fig1"].savefig(buf1, format="png", dpi=300, bbox_inches="tight")
        st.download_button(
            "Download chart (PNG)",
            data=buf1.getvalue(),
            file_name="AverageDLI.png",
            mime="image/png",
            key="png"
        )

        st.pyplot(res["fig2"],  use_container_width=True)
        buf2 = io.BytesIO()
        res["fig2"].savefig(buf2, format="png", dpi=300, bbox_inches="tight")
        st.download_button(
            "Download chart (PNG)",
            data=buf2.getvalue(),
            file_name="AverageDLI_barplot.png",
            mime="image/png",
            key="bar"
        )

        # Monthly Data
        st.dataframe(
            res["monthly"].style.format({
                "DLI Solar": "{:.1f}",
                "DLI AL": "{:.1f}",
                "Elec Cons (kWh/m2)": "{:.2f}",
                "Avg Daily Elec (kWh/m2/d)": "{:.2f}",
                "Avg AL Hours (h/d)": "{:.2f}",
            }),
            width="stretch",
            hide_index=True
        )

        st.download_button(
            "Download monthly averages (CSV)",
            data=res["monthly"].to_csv(index=False).encode("utf-8"),
            file_name="Monthly_DLI.csv",
            mime="text/csv",
            key="csv_monthly"
        )

        # Summary of Inputs
        summary_data = {
            "Parameter": [
                "Target DLI",
                "Target Intensity",
                "Photoperiod",
                "Screen 1 Shading",
                "Screen 2 Shading"
            ],
            "Value": [
                f"{st.session_state.selected_dli} mol/m²/day",
                f"{st.session_state.get('selected_intensity', 'variable')} µmol/m²/s",
                f"{st.session_state.photoperiod} h",
                f"{st.session_state.scr1_shade}%",
                f"{st.session_state.scr2_shade}%"
            ]
        }
        summary_df = pd.DataFrame(summary_data)
        summary_df.set_index("Parameter", inplace=True)
        st.subheader("Input Summary")
        st.table(summary_df)

        st.download_button(
            "Download complete hourly data (CSV)",
            data=res["hourly_data"].to_csv(index=False).encode("utf-8"),
            file_name="Hourly_data.csv",
            mime="text/csv",
            key="csv_hourly"
        )

    if st.button("Reset", type="secondary"):
        clear_results()
        st.rerun()

elif page == "Info":
    info_page_v3.render()
