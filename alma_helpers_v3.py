

import pandas as pd
import numpy as np
import streamlit as st

# Update since v1
# - call_crop_lightSetpoints now returns DLI min and max rather than calculating an average
# - load_weather removes days that are less than 24 h long (missing data)
# - (v2.1) add update_crop function which will keep climate parameters as session_state variables

def call_crop_lightSetpoints(crop_name):
    
    crop_df = pd.read_excel("CropData.xlsx")

    # Raise an error if the file has been changed and therefore cannot be referenced
    required = [
        "Crop",
        "Day_Temp_Max (degC)",
        "Night_Temp_Max (deg C)",
        "Daylength_Optimal (h)",
        "DLI_min (mol/m2)",
        "DLI_max (mol/m2)",
        "DLI_optimal (mol/m2)"
        ]
    missing = [c for c in required if c not in crop_df.columns]
    if missing:
        raise ValueError(f"Missing required columns: {missing}")

    # Select the row matching the crop
    crop_df = crop_df.set_index("Crop")
    row = crop_df.loc[crop_name]

    # Function that returns None if the Excel database is missing that data
    def nan_to_default(x, default=0.0):
        return default if pd.isna(x) else x
    
    # Retrieve values from that row
    day_max_temp = nan_to_default(row["Day_Temp_Max (degC)"])
    night_max_temp = nan_to_default(row["Night_Temp_Max (deg C)"])
    photoperiod = nan_to_default(row["Daylength_Optimal (h)"])
    DLI_min_molm2 = nan_to_default(row["DLI_min (mol/m2)"])
    DLI_max_molm2 = nan_to_default(row["DLI_max (mol/m2)"])
    DLI_op_molm2 = nan_to_default(row["DLI_optimal (mol/m2)"])

    return day_max_temp, night_max_temp, DLI_min_molm2, DLI_max_molm2, photoperiod, DLI_op_molm2

def update_crop():
    (
        day_max_temp,
        night_max_temp,
        DLI_min_molm2,
        DLI_max_molm2,
        photoperiod,
        DLI_op_molm2,
    ) = call_crop_lightSetpoints(st.session_state.crop_name)

    st.session_state.photoperiod = photoperiod
    st.session_state.dli_min_val = DLI_min_molm2
    st.session_state.dli_op_val = DLI_op_molm2
    st.session_state.dli_max_val = DLI_max_molm2
    st.session_state.day_max_temp = day_max_temp
    st.session_state.night_max_temp = night_max_temp

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
        df = format_weather_from_alma_workbook(raw)
    else:
        raw = pd.read_excel(xls, header=0)
        df = format_weather_from_ksgclimatedata(raw)

    # Remove incomplete days
    key = ["Year", "Month", "Day"]
    df = df.groupby(key).filter(lambda x: len(x) == 24)

    return df

