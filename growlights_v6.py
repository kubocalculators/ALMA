
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Literal, Tuple

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt

@dataclass
class ScreenParams:
    # Greenhouse cover
    trans_roof: float = 0.8
    u_roof: float = 6.9
    u_leak: float = 0.7
    Tout_influence: float = -1.0
    nr_screens: int = 2

    # Screen 1
    screen_1_shading_pct: float = 13.0
    screen_1_energy_pct: float = 47.0
    screen_1_lower_limit: float = 450.0
    screen_1_upper_limit: float = 550.0

    # Screen 2
    screen_2_shading_pct: float = 20.0
    screen_2_energy_pct: float = 47.0
    screen_2_lower_limit: float = 550.0
    screen_2_upper_limit: float = 600.0

# Updates included in v6
# - change method of calculating daily AL intensity
# - removed temperature (hot) check to disallow AL when outside temp > day setpoint (it was messing with daily AL intensity calc)

# -------------------------
# Crop Level Radiation (Glass & Screens)
# -------------------------

def compute_radiation_after_screen(
    I_global: pd.Series | np.ndarray,
    T_out: pd.Series | np.ndarray,
    p: ScreenParams,
    temp_screen2: Literal[0, 1] = 0,
) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    """
    Vectorized implementation of your screening logic.

    Returns:
      Isun_after_screen (W/m2),
      total_U (W/m2K),
      Screen1_pos (0..1),
      Screen2_pos (0..1),
      force_by_temp (0..1)

    Notes:
    - Matches the logic you provided (roof transmission, then screen positions based on
      radiation thresholds and Tout_influence).
    - If nr_screens == 0: only roof + leak, no screens.
    - If nr_screens == 1: only Screen1.
    """
    I_global = np.asarray(I_global, dtype=float)
    T_out = np.asarray(T_out, dtype=float)

    # Roof transmission
    Isun_afterroof = I_global * float(p.trans_roof)

    # Screen 1 position
    cond1 = (I_global < 15) | (T_out < float(p.Tout_influence))
    Screen1_pos = np.where(cond1, 1.0, np.clip(
        (I_global - float(p.screen_1_lower_limit)) / (float(p.screen_1_upper_limit) - float(p.screen_1_lower_limit)),
        0.0, 1.0
    ))

    if int(p.nr_screens) <= 0:
        Isun_after = Isun_afterroof
        total_U = np.full_like(Isun_after, float(p.u_roof) + float(p.u_leak), dtype=float)
        Screen2_pos = np.zeros_like(Isun_after, dtype=float)
        return Isun_after, total_U, Screen1_pos, Screen2_pos

    # Apply screen 1 effects
    Isun_afterscreen1 = Isun_afterroof * (1.0 - (float(p.screen_1_shading_pct) / 100.0) * Screen1_pos)
    Uroof1 = float(p.u_roof) * (1.0 - (float(p.screen_1_energy_pct) / 100.0) * Screen1_pos)

    if int(p.nr_screens) == 1:
        Isun_after = Isun_afterscreen1
        total_U = Uroof1 + float(p.u_leak)
        Screen2_pos = np.zeros_like(Isun_after, dtype=float)
        return Isun_after, total_U, Screen1_pos, Screen2_pos

    # Screen 2 position (uses Isun_afterscreen1 in the threshold)
    force_by_temp = (T_out < float(p.Tout_influence)) if temp_screen2 else False
    cond2 = (Isun_afterscreen1 == 0) | (force_by_temp)
    Screen2_pos = np.where(cond2, 1.0, np.clip(
        (Isun_afterscreen1 - float(p.screen_2_lower_limit)) / (float(p.screen_2_upper_limit) - float(p.screen_2_lower_limit)),
        0.0, 1.0
    ))

    # Apply screen 2
    Isun_afterscreen2 = Isun_afterscreen1 * (1.0 - (float(p.screen_2_shading_pct) / 100.0) * Screen2_pos)
    Uroof2 = Uroof1 * (1.0 - (float(p.screen_2_energy_pct) / 100.0) * Screen2_pos)

    total_U = Uroof2 + float(p.u_leak)
    return Isun_afterscreen2, total_U, Screen1_pos, Screen2_pos

# -------------------------
# Utilities
# -------------------------

def _month_block_mask(month: pd.Series, off_start: int, off_end: int) -> pd.Series:
    """
    Excel's month influence:
      IF(AND(Month>=off_start, Month<=off_end), "No", "Yes")
    If off_start/off_end are 0/None -> not blocked.
    """
    if off_start is None or off_end is None or off_start == 0 or off_end == 0:
        return pd.Series(False, index=month.index)
    # handles both normal ranges (5..8) and wrap-around (e.g., 11..2)
    if off_start <= off_end:
        return (month >= off_start) & (month <= off_end)
    else:
        return (month >= off_start) | (month <= off_end)

def _validate_weather_df(weather: pd.DataFrame) -> pd.DataFrame:
    required = ["Year", "Month", "Day", "Hour", "Temp", "Isun"]
    missing = [c for c in required if c not in weather.columns]
    if missing:
        raise KeyError(f"Weather dataframe missing required columns: {missing}")
    out = weather.copy()

    # Coerce dtypes (keep it robust for Streamlit uploads)
    out["Year"] = pd.to_numeric(out["Year"], errors="coerce").astype("Int32")
    out["Month"] = pd.to_numeric(out["Month"], errors="coerce").astype("Int16")
    out["Day"] = pd.to_numeric(out["Day"], errors="coerce").astype("Int16")
    out["Hour"] = pd.to_numeric(out["Hour"], errors="coerce").astype("Int16")
    out["Temp"] = pd.to_numeric(out["Temp"], errors="coerce")
    out["Isun"] = pd.to_numeric(out["Isun"], errors="coerce").fillna(0.0)

    if out[["Year", "Month", "Day", "Hour"]].isna().any().any():
        # Some exports include header/preamble rows; drop them.
        out = out.dropna(subset=["Year", "Month", "Day", "Hour"]).copy()
    out["Temp"] = out["Temp"].ffill().bfill()

    # Sort like Excel (important for cumulative hour allocation)
    out = out.sort_values(["Year", "Month", "Day", "Hour"]).reset_index(drop=True)
    return out

def _par_umol_per_m2_per_s(isun_after_screen_wm2: pd.Series, par_fraction: float = 0.5, umol_per_w: float = 4.6) -> pd.Series:
    # Excel: Isun * 0.5 * 4.6 * 3600 / 1e6
    return isun_after_screen_wm2 * par_fraction * umol_per_w

def daily_al_intensity(day_data, dli_target):
    """
    Computes the daily intensity target

    If Natural DLI > Target DLI, a minimum target is returned (to reach photoperiod)
    Otherwise, a daily AL intensity target is determined that will reach DLI target by using all hours labeled "AL ON" (ie. using the whole photoperiod)

    """
    # --- Confirm all columns needed in day_data are present
    required = ["AL_Possible", "Solar_Intensity"]                       # AL_Possible = 1 (on) or 0 (off)   Solar_Intensity (post screen, PAR, umol/m2/s)
    missing = [c for c in required if c not in day_data.columns]
    if missing:
        raise KeyError(f"Day_data missing required columns: {missing}")
    df = day_data.copy()

    # --- Check if Natural DLI > Target DLI ---
    min_target = 100                                        # umol/m2/s         # Minimum light intensity, to extend photoperiod
    dli_natural = df["Solar_Intensity"].sum() *3600 /1e6    # mol/m2/d
    if dli_natural > dli_target:
        return min_target
    
    # --- Calculate AL Intensity needed to meet DLI target in photoperiod
    dli_solar_AL_OFF = df.loc[df["AL_Possible"] == 0, "Solar_Intensity"].sum() *3600 /1e6       # Add up solar radiation for hours where AL are OFF
    dli_remaining = dli_target - dli_solar_AL_OFF                                               # Calculate remaining DLI to gather from AL only & AL+sun hours
    
    hours_needing_AL = df["AL_Possible"].sum()                                                  # Since AL_Possible == 1 when AL are "on" summing the row will give the # of hours AL are on
    daily_intensity_target = dli_remaining/hours_needing_AL /3600 *1e6

    return daily_intensity_target


# -------------------------
# Lamp Intensity
# -------------------------

def AL_intensity_needed(
    weather: pd.DataFrame,
    start: int = 5,
    photoperiod: int = 16,          # h
    rad_setpoint: float = 400,      # W/m2
    day_temp_setpoint: float = 24,
    al_off_start_month: int = 0,
    al_off_end_month: int = 0,
    dli_target: float = 30,         # mol/m2/d
):

    w = _validate_weather_df(weather)

    # --- Step 1: Mark hours where AL are allowed to be ON
    window_ok = (w["Hour"] >= start) & ((start + photoperiod) > w["Hour"])              # J: photoperiod window
    sr_ok = w["Isun"] < rad_setpoint                                                        # K: SR influence (Yes if Isun < rad_setpoint)
    
    # TODO: remove this line if we remove the temp check
    # temp_ok = ~((w["Temp"] > day_temp_setpoint) & (w["Isun"] > 0))                          # L: Temp influence (Yes unless Temp>setpoint AND Isun>0)
    month_blocked = _month_block_mask(w["Month"], al_off_start_month, al_off_end_month)     # M: month influence
    month_ok = ~month_blocked
    # w["AL_Possible"] = window_ok & sr_ok & temp_ok & month_ok                     # TODO: remove this line if we remove the temp check
    w["AL_Possible"] = window_ok & sr_ok & month_ok
    # --- Step 2: Calculate required AL to reach target DLI & photoperiod
    w["Solar_Intensity"] = _par_umol_per_m2_per_s(w["Isun"])        # umol/m2/s          # Pull solar radiation from the weather dataframe (will be crop-level, conversion done before this function)

    # --- Step 3: Iteratively determine daily intensity target to ensure DLI and photoperiod are reached simultaneously
    key = ["Year", "Month", "Day"]
    w["IntensityTarget_daily"] = 0                                                          # Initialize the daily target column

    for _, day_data in w.groupby(key):
        # day_data is a DataFrame containing all columns for just one day
        
        # Compute the daily intensity target based on solar radiation and targets (DLI & photoperiod)
        daily_target = daily_al_intensity(day_data, dli_target)

        # Store daily target in w DataFrame
        #    Force the column to be a float type so it can accept numeric targets
        w["IntensityTarget_daily"] = w["IntensityTarget_daily"].astype(float)
        w.loc[day_data.index, "IntensityTarget_daily"] = daily_target
    
    # Calculate the hourly AL Intensity needed to reach each daily intensity target
        w["AL_Intensity"] = (w["IntensityTarget_daily"] - w["Solar_Intensity"]).clip(lower=0).where(w["AL_Possible"], 0.0)

    return w

def AL_intensity_matrix(w_min,w_op,w_max, col: str = "AL_Intensity"):
    
    out = pd.DataFrame([{
        "Min DLI":     pd.to_numeric(w_min[col], errors="coerce").max(),
        "Optimal DLI": pd.to_numeric(w_op[col],  errors="coerce").max(),
        "Max DLI":     pd.to_numeric(w_max[col], errors="coerce").max(),
    }]).round(1)

    # convert to strings and append units
    unit = " umol/m2/s"
    out = out.astype(str) + unit

    return out

# -------------------------
# LED-Only
# -------------------------

def LED_dimmable_usage(weather, dli_target, led_eff):
    # Aggregate data into daily and monthly dataframes
    key = ["Year", "Month", "Day"]

    # Confirm the hourly AL Intensity data is in the weather dataframe
    missing = "AL_Intensity" not in weather.columns
    if missing:
        raise KeyError(f"Complete Step 2: Determine AL Intensity")
    w = weather.copy()

    w["Solar_PAR_hourly"] = w["Solar_Intensity"] *3600 /1000000             # mol/m2/h              # Convert per s to per h

    # Calculate the gap between the target DLI and what the sun provides
    w["Natural DLI"] = w.groupby(key)["Solar_PAR_hourly"].transform("sum")
    par_needed = (dli_target - w["Natural DLI"]).clip(lower=0.0)

    # Overwite hourly AL intensity to 0 if additional light is not required to meet DLI target
    w["AL_Intensity"] = w["AL_Intensity"].where(par_needed > 0, 0.0)
    w["AL_PAR_hourly"] = w["AL_Intensity"] *3600 /1000000                   # mol/m2/h              # Convert per s to per h
    
    # Calculate hourly electricity usage (using selected efficiency)
    w["Elec_hourly_kWh_m2"] = w["AL_Intensity"] / led_eff / 1000.0          # umol/m2/s x J/umol x kW/1000W = kW/m2 (consumption rate for each hour -> kWh)

    daily = (
        w.groupby(key, as_index=False)
        .agg(
            **{
                "Natural DLI": ("Solar_PAR_hourly", "sum"),
                "AL DLI": ("AL_PAR_hourly", "sum"),
                "Elec (kWh/m2)": ("Elec_hourly_kWh_m2", "sum"),
            }
        )
    )

    daily["DLI Total"] = daily["Natural DLI"] + daily["AL DLI"]

    monthly = (
        daily.groupby("Month", as_index=False)
        .agg(
            **{
                "DLI Solar": ("Natural DLI", "mean"),
                "DLI AL": ("AL DLI", "mean"),
                "DLI Total Stdev": ("DLI Total", "std"),
                "Elec Cons (kWh/m2)": ("Elec (kWh/m2)", "sum"),
            }
        )
    )

    return monthly, w

def LED_usage(
    weather: pd.DataFrame,
    dli_target: float = 30,
    al_intensity: float = 200,      # umol/m2/s
    led_eff: float = 3.6,           # umol/J
) -> pd.DataFrame:
    
    # Confirm weather has all needed columns... ie. AL_intensity_needed has been run
    missing = "AL_Possible" not in weather.columns
    if missing:
        raise KeyError(f"Complete Step 2: Determine AL Intensity")
    w = weather.copy()

    # Determine Natural DLI (daily)
    w["PAR_Canopy_molm2h"] = w["Isun"] * 0.5 * 4.6 * 3600 / 1e6                 # Converts solar radiation (after roof and screens) from W/m2 to mol/m2/h
    key = ["Year", "Month", "Day"]
    w["Natural_DLI"] = w.groupby(key)["PAR_Canopy_molm2h"].transform("sum")     # Computes the daily sum (DLI) of light from the sun (no lamps yet)

    # Determine how many hours of AL is needed to reach DLI (photoperiod is flexible)
    w["Max_AL_Hours"] = w.groupby(key)["AL_Possible"].transform("sum").astype(float)                # This will be the daily count of how many hours AL is allowed to be on
    par_needed = (dli_target - w["Natural_DLI"]).clip(lower=0.0)
    hours_needed_float = par_needed * 1000000 / (al_intensity * 3600)                               # Based on the selected DLI, this is how many hours of AL is needed to reach the DLI target
    w["Actual_AL_Hours_Float"] = np.minimum(hours_needed_float, w["Max_AL_Hours"]).clip(lower=0.0)  # Take the minimum, either max allowed, or what's needed to reach the target
    # cap_hours_int = np.floor(w["Actual_AL_Hours_Float"] + 1e-12).astype(int)                        # Rounds down to the nearest whole number
    cap_hours_int = np.ceil(w["Actual_AL_Hours_Float"] - 1e-12).astype(int)                        # Rounds up to the nearest whole number

    # cumulative allowed hours within each day
    allowed_cum = w["AL_Possible"].astype(int).groupby([w[c] for c in key]).cumsum()
    w["AL_On"] = (w["AL_Possible"]) & (allowed_cum <= cap_hours_int)

    # DLI from AL + electricity (hourly then daily like Excel)
    w["maxAL_PAR_hourly"] = np.where(w["AL_On"], al_intensity * 3600.0 / 1_000_000.0, 0.0)     # mol/m2/h
    w["Elec_hourly_kWh_m2"] = np.where(w["AL_On"], al_intensity / led_eff / 1000.0, 0.0)        # umol/m2/s x J/umol x kW/1000W

    daily = (
        w.groupby(key, as_index=False)
        .agg(
            **{
                "Natural DLI": ("PAR_Canopy_molm2h", "sum"),
                "AL Hours (int)": ("AL_On", "sum"),
                "AL DLI": ("maxAL_PAR_hourly", "sum"),
                "Elec (kWh/m2)": ("Elec_hourly_kWh_m2", "sum"),
            }
        )
    )
    # The lambda above isn't supported in agg this way on older pandas; compute explicitly to be safe:
    daily["DLI Total"] = daily["Natural DLI"] + daily["AL DLI"]

    monthly = (
        daily.groupby("Month", as_index=False)
        .agg(
            **{
                "DLI Solar": ("Natural DLI", "mean"),
                "DLI AL": ("AL DLI", "mean"),
                "DLI Total Stdev": ("DLI Total", "std"),
                "Elec Cons (kWh/m2)": ("Elec (kWh/m2)", "sum"),
                "Avg AL Hours (h/d)": ("AL Hours (int)", "mean"),
            }
        )
    )

    return monthly, w

# -------------------------
# Hybrid (LED & HPS)
# -------------------------



# -------------------------
# Plotting
# -------------------------

def plot_avgDLI(monthly: pd.DataFrame, months, savepath: Optional[str] = "AverageDLI_hill.png"):
    fig, ax = plt.subplots()
    ax.stackplot(months, monthly["DLI Solar"], monthly["DLI AL"], labels=["DLI Solar", "DLI AL"], alpha=0.7)
    ax.legend(loc="upper left")
    ax.set_xticks([])
    ax.set_ylabel("Average DLI (mol/m2/d)")

    table_data = [
        [f"{val:.1f}" for val in monthly["DLI Solar"]],
        [f"{val:.1f}" for val in monthly["DLI AL"]],
    ]
    ax.table = plt.table(cellText=table_data, rowLabels=["DLI Solar", "DLI AL"], colLabels=months, loc="bottom", cellLoc="center")

    if savepath:
        fig.savefig(savepath, dpi=300)
    return fig

def barplot_avgDLI(monthly: pd.DataFrame, months, savepath: Optional[str] = "AverageDLI_bar.png"):
    fig, ax = plt.subplots()
    ax.bar(months, monthly["DLI Solar"], label="DLI Solar", alpha=0.7)
    ax.bar(months, monthly["DLI AL"], bottom=monthly["DLI Solar"], label="DLI AL", alpha=0.7)
    total = monthly["DLI Solar"] + monthly["DLI AL"]
    ax.errorbar(range(len(months)), total, yerr=monthly["DLI Total Stdev"], fmt="none", capsize=5)
    ax.legend(loc="upper left")
    ax.set_xticks([])
    ax.set_ylabel("Average DLI (mol/m2/d)")

    table_data = [
        [f"{val:.1f}" for val in monthly["DLI Solar"]],
        [f"{val:.1f}" for val in monthly["DLI AL"]],
    ]
    ax.table = plt.table(cellText=table_data, rowLabels=["DLI Solar", "DLI AL"], colLabels=months, loc="bottom", cellLoc="center")

    if savepath:
        fig.savefig(savepath, dpi=300)
    return fig
