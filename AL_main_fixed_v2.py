import io
import pandas as pd
import streamlit as st
import info_page

from growlights_fixed_v2 import LED_usage, Hybrid_usage, plot_avgDLI, barplot_avgDLI, ScreenParams, compute_radiation_after_screen

months = ("Jan", "Feb", "Mar", "Apr", "May", "June", "July", "Aug", "Sept", "Oct", "Nov", "Dec")

### Changes from v3 ###
# - Units stated for Roof transmission changed from W/m2/K to %
# - Added information page showing the hourly decisions to turn lights on/off
# - Limited decimal places displayed to match allowed step sizes
# - Commented out the U-value inputs and requirements to the calcualtion. It complicates the input and is not considered in the output.
# - Added pdf download button for crop data
# - Re-arranged inputs for LED/Hybrid inputs to be at the top (I thought it was clearer to have target AL intensity closer to target DLI)

# --- Default U-value data as placeholders in case if we choose to use the energy data and re-include the inputs
default_u_roof = 6.90
default_u_leak = 0.70
default_scr1_energy = 47
default_scr2_energy = 47

# ---------- Help Functions ---------- #

def clear_results():
    for k in ("results", "error"):
        st.session_state.pop(k, None)

def _normalize_columns(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df.columns = [str(c).strip().replace("\u00a0", " ") for c in df.columns]
    return df

def format_weather_from_alma_workbook(raw_data: pd.DataFrame) -> pd.DataFrame:
    """
    Reads the 'AL calc' sheet structure from the provided AlMA workbook.

    Required columns (as in your file):
      Year, Month , Day , Hour, Tout, Radiation after screen
    """
    raw = _normalize_columns(raw_data)

    # tolerate the trailing spaces Excel has in headers
    def pick(*cands):
        for c in cands:
            if c in raw.columns:
                return c
        return None

    c_year = pick("Year")
    c_month = pick("Month", "Month ")
    c_day = pick("Day", "Day ")
    c_hour = pick("Hour")
    c_temp = pick("Tout", "Temperature (C)")
    c_isun = pick("Radiation after screen", "Radiation after screen ", "Solar Radiation (W/m²)")

    missing = [name for name, col in {
        "Year": c_year, "Month": c_month, "Day": c_day, "Hour": c_hour, "Temp": c_temp, "Isun": c_isun
    }.items() if col is None]
    if missing:
        raise KeyError(f"Could not find required columns in uploaded file: {missing}")

    weather = pd.DataFrame({
        "Year": pd.to_numeric(raw[c_year], errors="coerce"),
        "Month": pd.to_numeric(raw[c_month], errors="coerce"),
        "Day": pd.to_numeric(raw[c_day], errors="coerce"),
        "Hour": pd.to_numeric(raw[c_hour], errors="coerce"),
        "Temp": pd.to_numeric(raw[c_temp], errors="coerce"),
        "Isun": pd.to_numeric(raw[c_isun], errors="coerce"),
    })

    weather["I_global"] = weather["Isun"]

    weather = weather.dropna(subset=["Year", "Month", "Day", "Hour"])
    return weather

def format_weather_from_ksgclimatedata(raw_data: pd.DataFrame) -> pd.DataFrame:
    """
    Original ksgclimatedata export format.
    """
    raw = _normalize_columns(raw_data)

    required = ["Local Time", "Temperature (C)", "Solar Radiation (W/m²)"]
    missing = [c for c in required if c not in raw.columns]
    if missing:
        raise KeyError(f"Missing required columns: {missing}")

    dt = pd.to_datetime(raw["Local Time"], errors="coerce", utc=False)
    if dt.isna().any():
        raise ValueError("Some 'Local Time' values could not be parsed as datetimes.")

    clean_data = pd.DataFrame({
        "Year": dt.dt.year.astype("int16"),
        "Month": dt.dt.month.astype("int8"),
        "Day": dt.dt.day.astype("int8"),
        "Hour": dt.dt.hour.astype("int8"),
        "Temp": pd.to_numeric(raw["Temperature (C)"], errors="coerce"),
        "Isun": pd.to_numeric(raw["Solar Radiation (W/m²)"], errors="coerce"),
    })
    return clean_data

def load_weather(uploaded) -> pd.DataFrame:
    """
    Auto-detect the uploaded Excel format:
    - If sheet 'AL calc' exists -> use that (AlMA workbook)
    - Else assume ksgclimatedata single-sheet export
    """
    xls = pd.ExcelFile(uploaded)
    if "AL calc" in xls.sheet_names:
        raw = pd.read_excel(xls, sheet_name="AL calc", header=4)  # row 5 in Excel
        return format_weather_from_alma_workbook(raw)
    else:
        raw = pd.read_excel(xls, header=0)
        return format_weather_from_ksgclimatedata(raw)

# ---------- Sidebar for Info ---------- #

st.sidebar.title("Navigation")

page = st.sidebar.radio("Go to:", ["Calculator","Info"], index=0)

if page == "Calculator":
    # ---------- Main Page ---------- #

    st.title("Grow Lights - Average DLI")

    system = st.radio("Choose system", ["LED", "Hybrid (LED + HPS)"], index=0, key="system", on_change=lambda: st.session_state.pop("results", None))

    with st.form("controls", clear_on_submit=False):
        uploaded = st.file_uploader("Upload weather Excel (https://ksgclimatedata.streamlit.app/)", type=["xlsx"])

        st.header("Crop / Project Parameters")

        with open("Productsheets.pdf", "rb") as f:
            st.download_button(
                "Open Crop Data PDF",
                f,
                file_name="Productsheets.pdf",
                mime="application/pdf"
            )    

        start = st.number_input("Start hour", min_value=0, max_value=23, value=5, step=1)
        photoperiod = st.number_input("Photoperiod (h)", min_value=1, max_value=24, value=16, step=1)

        rad_setpoint = st.number_input("Radiation setpoint (W/m²)", min_value=0.0, value=400.0, step=10.0, format="%.0f")
        dli_target = st.number_input("Target DLI (mol/m²/day)", min_value=0.0, value=30.0, step=0.5, format="%.1f")

        st.caption("Optional: month window where AL is disabled (Excel L3..M3). Set to 0 to disable.")
        al_off_start_month = st.number_input("AL off start month", min_value=0, max_value=12, value=0, step=1)
        al_off_end_month = st.number_input("AL off end month", min_value=0, max_value=12, value=0, step=1)

        if system == "LED":
            st.header("LED-only parameters")
            gh_temp_setpoint = st.number_input("GH temperature setpoint (°C)", min_value=-30.0, max_value=60.0, value=24.0, step=0.5, format="%.1f")
            al_intensity = st.number_input("AL intensity (µmol/m²/s)", min_value=0.0, value=200.0, step=10.0, format="%.0f")
            led_eff = st.number_input("LED efficacy (µmol/J)", min_value=0.01, value=3.6, step=0.1, format="%.1f")
        else:
            st.header("Hybrid parameters")
            day_temp_setpoint = st.number_input("Day temp setpoint (°C)", min_value=-30.0, max_value=60.0, value=24.0, step=0.5)
            night_temp_setpoint = st.number_input("Night temp setpoint (°C)", min_value=-30.0, max_value=60.0, value=16.0, step=0.5)
            al_intensity_target = st.number_input("Target total AL intensity (µmol/m²/s)", min_value=0.0, value=200.0, step=10.0)
            led_ppfd = st.number_input("LED PPFD (µmol/m²/s)", min_value=0.0, value=100.0, step=10.0)
            hps_ppfd = st.number_input("HPS PPFD (µmol/m²/s)", min_value=0.0, value=100.0, step=10.0)
            led_eff = st.number_input("LED efficacy (µmol/J)", min_value=0.01, value=3.6, step=0.1)
            hps_eff = st.number_input("HPS efficacy (µmol/J)", min_value=0.01, value=1.8, step=0.1)

        st.header("Greenhouse Cover & Screen Specifications")
        use_screen_model = st.checkbox(
            "Compute Radiation after screen from direct solar radiation",
            value=True,
            help="If checked, the app will compute 'Isun' using the roof + screen settings below. If unchecked, it will use the 'Isun' column as provided by the file."
        )

        trans_roof = st.number_input("Roof transmission (0-1)", min_value=0.0, max_value=1.0, value=0.8, step=0.01)
        # u_roof = st.number_input("U roof (W/m²/k)", min_value=0.0, value=6.9, step=0.1)
        # u_leak = st.number_input("U leak (W/m²/K)", min_value=0.0, value=0.7, step=0.1)
        nr_screens = st.number_input("Number of screens", min_value=0, max_value=2, value=2, step=1)
        Tout_influence = st.number_input("Force Screen 2 closed at Temp (C)", value=-1.0, step=0.5, format="%.1f")

        st.subheader("Screen 1")
        screen_1_shading_pct = st.number_input("Screen 1 shading (%)", min_value=0.0, max_value=100.0, value=13.0, step=1.0, format="%.0f")
        # screen_1_energy_pct = st.number_input("Screen 1 energy saving (%)", min_value=0.0, max_value=100.0, value=47.0, step=1.0)
        screen_1_lower_limit = st.number_input("Screen 1 lower radiation limit (W/m²)", min_value=0.0, value=450.0, step=10.0, format="%.0f")
        screen_1_upper_limit = st.number_input("Screen 1 upper radiation limit (W/m²)", min_value=0.0, value=550.0, step=10.0, format="%.0f")

        st.subheader("Screen 2")
        screen_2_shading_pct = st.number_input("Screen 2 shading (%)", min_value=0.0, max_value=100.0, value=20.0, step=1.0, format="%.0f")
        # screen_2_energy_pct = st.number_input("Screen 2 energy saving (%)", min_value=0.0, max_value=100.0, value=47.0, step=1.0)
        screen_2_lower_limit = st.number_input("Screen 2 lower radiation limit (W/m²)", min_value=0.0, value=550.0, step=10.0, format="%.0f")
        screen_2_upper_limit = st.number_input("Screen 2 upper radiation limit (W/m²)", min_value=0.0, value=600.0, step=10.0, format="%.0f")
        use_temp_influence_screen2 = st.checkbox("Use Tout influence for Screen 2 (force closed when T_out < Tout_influence)", value=True)

        run = st.form_submit_button("Calculate")

    # ---------- Run Calculations ---------- #

    if run:
        try:
            if uploaded is None:
                st.warning("Please upload an Excel file.")
                st.stop()

            weather = load_weather(uploaded)


            st.success(f"✅ Loaded {len(weather):,} hourly rows")

            # Optionally recompute 'Isun' (Radiation after screen) from global radiation using roof + screens
            if use_screen_model:
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
                Isun_after, total_U, s1pos, s2pos = compute_radiation_after_screen(weather["Isun"], weather["Temp"], sp, temp_screen2=1 if use_temp_influence_screen2 else 0)
                weather = weather.copy()
                weather["Isun"] = Isun_after
                weather["U_total"] = total_U
                weather["Screen1_pos"] = s1pos
                weather["Screen2_pos"] = s2pos
                st.info("Using computed 'Isun' (Radiation after screen) based on the cover/screen settings.")

            if system == "LED":
                monthly = LED_usage(
                    weather,
                    start=int(start),
                    photoperiod=int(photoperiod),
                    rad_setpoint=float(rad_setpoint),
                    gh_temp_setpoint=float(gh_temp_setpoint),
                    dli_target=float(dli_target),
                    al_intensity=float(al_intensity),
                    led_eff=float(led_eff),
                    al_off_start_month=int(al_off_start_month),
                    al_off_end_month=int(al_off_end_month),
                )
            else:
                monthly = Hybrid_usage(
                    weather,
                    start=int(start),
                    photoperiod=int(photoperiod),
                    rad_setpoint=float(rad_setpoint),
                    day_temp_setpoint=float(day_temp_setpoint),
                    night_temp_setpoint=float(night_temp_setpoint),
                    dli_target=float(dli_target),
                    al_intensity_target=float(al_intensity_target),
                    led_ppfd=float(led_ppfd),
                    hps_ppfd=float(hps_ppfd),
                    led_eff=float(led_eff),
                    hps_eff=float(hps_eff),
                    al_off_start_month=int(al_off_start_month),
                    al_off_end_month=int(al_off_end_month),
                )

            fig1 = plot_avgDLI(monthly, months)
            fig2 = barplot_avgDLI(monthly, months)

            st.session_state["results"] = {"system": system, "monthly": monthly, "fig1": fig1, "fig2": fig2}

        except Exception as e:
            st.session_state["error"] = str(e)

    if st.button("Reset", type="secondary"):
        clear_results()
        st.rerun()

elif page == "Info":
    info_page.render()


# ---------- Display Output ---------- #

if "error" in st.session_state:
    st.error(f"Something went wrong: {st.session_state['error']}")

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
        width="stretch"
    )

    st.download_button(
        "Download monthly averages (CSV)",
        data=res["monthly"].to_csv(index=False).encode("utf-8"),
        file_name="Monthly_DLI.csv",
        mime="text/csv",
        key="csv"
    )


