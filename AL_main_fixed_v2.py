
import io
import streamlit as st
import info_page_v2

from growlights_v4 import AL_intensity_needed, AL_intensity_matrix, LED_usage, LED_dimmable_usage, plot_avgDLI, barplot_avgDLI, ScreenParams, compute_radiation_after_screen
from alma_helpers_v2 import call_crop_lightSetpoints, clear_results, _normalize_columns, format_weather_from_alma_workbook, format_weather_from_ksgclimatedata, load_weather

months = ("Jan", "Feb", "Mar", "Apr", "May", "June", "July", "Aug", "Sept", "Oct", "Nov", "Dec")

### Changes from v5 ###
# - AL_Intensity is determined in a first stage calculation using DLI and photoperiod
# - Two usage calculation methods:
#       METHOD 1: Traditional AlMA (strict DLI, shorten photoperiod, lights On/Off)
#       METHOD 2: Dimmable (strict DLI, strict photoperiod, lights dimmable)

# - Other pages updated for main_v6
#       info_page -> info_page_v2
#       alma_helpers -> alma_helpers_v2
#       growlights_fixed_v2 -> growlights_v4




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
    "STRAWBERRY",
    "LETTUCE, baby leaf",
    "LETTUCE, teen leaf (direct seeding)",
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

    # system = st.radio(":red[**Choose system**]", ["LED", "Hybrid (LED + HPS)"], index=0, key="system", on_change=lambda: st.session_state.pop("results", None))

    uploaded = st.file_uploader(":red[**Upload weather data (Excel file)**] (https://ksgclimatedata.streamlit.app/)", type=["xlsx"])

    # Select Crop and Retreive Crop Data
    st.header("Step 1: Enter Crop Specifications")
    
    crop_name = st.selectbox(":red[**Select Crop**]", crop_list)
    reference, variety, day_max_temp,  night_max_temp, DLI_min_molm2, DLI_max_molm2, photoperiod = call_crop_lightSetpoints(crop_name)
    
    st.caption("If data is available, crop setpoints will populate with crop selection")
    photoperiod = st.number_input("Photoperiod (h)", value=photoperiod)

    st.caption("Lamp intensity will be calculated for each DLI and displayed in a table of percentiles.")
    dli_min = st.number_input("Minimum DLI (mol/m2/day)", value=DLI_min_molm2)
    dli_op = st.number_input(":red[**Optimal DLI (mol/m2/day)**]")
    dli_max = st.number_input("Maximum DLI (mol/m²/day)", value=DLI_max_molm2)

    st.caption("Artificial lighting will not be allowed for outside temperatures higher than these setpoints.")
    day_temp_setpoint = st.number_input("Day temp setpoint (°C)", value=day_max_temp)
    night_temp_setpoint = st.number_input("Night temp setpoint (°C)", value=night_max_temp)

    # ---------- Step 2: Determining the AL Intensity ---------- #

    with st.form("intensity", clear_on_submit=False):
        st.header("Step 2: Determine AL Intensity")
        st.caption("Using DLI and photoperiod, required lamp intensity is calculated. From the results, select an intensity to use in the next section of the calculator.")

        st.caption("Artificial lighting will not be allowed before this hour (24:00)")
        start = st.number_input("Start hour", min_value=0, max_value=23, value=5, step=1)
        st.caption("Artificial lighting will not be allowed for outside radiation above this Radiation setpoint:")
        rad_setpoint = st.number_input("Radiation setpoint (W/m²)", min_value=0.0, value=400.0, step=10.0, format="%.0f")
        st.caption("Optional: month window where AL is disabled (Excel L3..M3). Set to 0 to disable.")
        al_off_start_month = st.number_input("AL off start month", min_value=0, max_value=12, value=0, step=1)
        al_off_end_month = st.number_input("AL off end month", min_value=0, max_value=12, value=0, step=1)

        trans_roof = st.number_input("Roof transmission (0-1)", min_value=0.0, max_value=1.0, value=0.8, step=0.01)
        nr_screens = st.number_input("Number of screens", min_value=0, max_value=2, value=2, step=1)
        Tout_influence = st.number_input("Force Screen 2 closed at Temp (C)", value=-1.0, step=0.5, format="%.1f")
        use_temp_influence_screen2 = st.checkbox("Use Tout influence for Screen 2 (force closed when T_out < Tout_influence)", value=True)

        st.subheader("Screen 1")
        screen_1_shading_pct = st.number_input(":red[**Screen 1 shading (%)**]", min_value=0.0, max_value=100.0, value=13.0, step=1.0, format="%.0f")
        screen_1_lower_limit = st.number_input("Screen 1 lower radiation limit (W/m²)", min_value=0.0, value=450.0, step=10.0, format="%.0f")
        screen_1_upper_limit = st.number_input("Screen 1 upper radiation limit (W/m²)", min_value=0.0, value=550.0, step=10.0, format="%.0f")

        st.subheader("Screen 2")
        screen_2_shading_pct = st.number_input(":red[**Screen 2 shading (%)**]", min_value=0.0, max_value=100.0, value=20.0, step=1.0, format="%.0f")
        screen_2_lower_limit = st.number_input("Screen 2 lower radiation limit (W/m²)", min_value=0.0, value=550.0, step=10.0, format="%.0f")
        screen_2_upper_limit = st.number_input("Screen 2 upper radiation limit (W/m²)", min_value=0.0, value=600.0, step=10.0, format="%.0f")

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
            weather_addIntensity_maxDLI
        )

        st.dataframe(intensity_table, hide_index=True)

    # ---------- Step 3: AlMA Calculator - Monthly Usage ---------- #
    
    st.header("Step 3: Calculate Monthly Usage")
    system = st.radio("Select Lighting System:", ["LED (On/Off, Fixed DLI, Variable Photoperiod)", "LED (Dimmable, Fixed DLI & Photoperiod)"])

    if system == "LED (On/Off, Fixed DLI, Variable Photoperiod)":
        with st.form("LED_monthly_usage", clear_on_submit=False):
            st.caption("Enter your chosen target intensity (unmol/m2/s). AlMA will calculate monthly usage. Photoperiod may be shorter than selected value if lights reach DLI before the photoperiod is up.")

            dli_target = st.number_input(":red[**Target DLI (mol/m²/day)**]", format="%.0f")
            al_intensity = st.number_input(":red[**AL intensity (µmol/m²/s)**]", min_value=0.0, step=10.0, format="%.0f")
            led_eff = st.number_input("LED efficiency (µmol/J)", min_value=0.01, value=3.6, step=0.1, format="%.1f")

            run_AlMA = st.form_submit_button("Calculate")
    
    elif system == "LED (Dimmable, Fixed DLI & Photoperiod)":
        with st.form("LED_dimmable_monthly_usage", clear_on_submit=False):
            st.caption("Enter your chosen DLI target. Photoperiod remains the same as input above. Hourly electrical consumption is based on intensity needed rather than lamp maximum.")
            dli_target = st.number_input(":red[**Target DLI (mol/m²/day)**]", format="%.0f")
            led_eff = st.number_input("LED efficiency (µmol/J)", min_value=0.01, value=3.6, step=0.1, format="%.1f")
            run_AlMA = st.form_submit_button("Calculate")

    if run_AlMA:
        
        weather = load_weather(uploaded)

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
    info_page_v2.render()

