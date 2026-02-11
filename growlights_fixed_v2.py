
"""
growlights.py

Excel-faithful translation of the "AL calc" logic from:
  AlMA4.5_2016-2026 - Northstar- 21012026.xlsx

Key differences vs older version:
- Adds month-off window (AL month influence) exactly like Excel.
- Uses the same PAR conversion used in the workbook: PAR(mol/m2/h) = Isun_after_screen * 0.5 * 4.6 * 3600 / 1e6
  (i.e., no extra 0.8*(1-shade) unless you explicitly ask for it).
- Implements hourly allocation of AL hours (Excel uses a cumulative counter -> effectively FLOOR(actual_hours_float)).
- Hybrid decision logic matches the workbook's IFS() rules.

Inputs:
weather dataframe must contain columns:
  Year, Month, Day, Hour, Temp, Isun
Where Isun is "Radiation after screen (W/m2)" (same as Excel column G).

Returns:
monthly dataframe aggregated by Month (1..12).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Literal, Tuple

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt




# -------------------------
# Cover & Screens model (to reproduce Excel 'Radiation after screen')
# -------------------------

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
    out["Temp"] = out["Temp"].fillna(method="ffill").fillna(method="bfill")

    # Sort like Excel (important for cumulative hour allocation)
    out = out.sort_values(["Year", "Month", "Day", "Hour"]).reset_index(drop=True)
    return out


def _par_mol_per_m2_per_h(isun_after_screen_wm2: pd.Series, par_fraction: float = 0.5, umol_per_w: float = 4.6) -> pd.Series:
    # Excel: Isun * 0.5 * 4.6 * 3600 / 1e6
    return isun_after_screen_wm2 * par_fraction * umol_per_w * 3600.0 / 1_000_000.0


# -------------------------
# LED-only (Excel: system="LED" or "HPS" is handled similarly, but this function is LED)
# -------------------------

def LED_usage(
    weather: pd.DataFrame,
    *,
    start: int = 5,
    photoperiod: int = 16,
    rad_setpoint: float = 400,
    gh_temp_setpoint: float = 24,
    dli_target: float = 30,
    al_intensity: float = 200,   # umol/m2/s
    led_eff: float = 3.6,        # umol/J
    al_off_start_month: int = 0,
    al_off_end_month: int = 0,
) -> pd.DataFrame:
    """
    Matches the workbook's LED/HPS modes for DLI + electricity.
    - AL allowed only within photoperiod window
    - Off when Isun >= rad_setpoint
    - Off when (Temp > gh_temp_setpoint AND Isun > 0)
    - Off when Month within [al_off_start_month, al_off_end_month]
    - Hourly allocation uses a cumulative counter -> ON for the first FLOOR(actual_hours_float) allowed hours.
    """
    w = _validate_weather_df(weather)

    # Step 1: PAR from sun at canopy (mol/m2/h)
    w["PAR_Canopy"] = _par_mol_per_m2_per_h(w["Isun"])

    # Daily solar DLI (mol/m2/d)
    key = ["Year", "Month", "Day"]
    w["Natural_DLI"] = w.groupby(key)["PAR_Canopy"].transform("sum")

    # Step 2: AL on possibility flags (Excel columns J..N)
    # J: photoperiod window
    # Excel condition: AND(Hour >= start, start+photoperiod+1 > Hour)
    window_ok = (w["Hour"] >= start) & ((start + photoperiod + 1) > w["Hour"])

    # K: SR influence (Yes if Isun < rad_setpoint)
    sr_ok = w["Isun"] < rad_setpoint

    # L: Temp influence (Yes unless Temp>setpoint AND Isun>0)
    temp_ok = ~((w["Temp"] > gh_temp_setpoint) & (w["Isun"] > 0))

    # M: month influence
    month_blocked = _month_block_mask(w["Month"], al_off_start_month, al_off_end_month)
    month_ok = ~month_blocked

    w["AL_Possible"] = window_ok & sr_ok & temp_ok & month_ok

    # Max AL hours per day (Excel O)
    w["Max_AL_Hours"] = w.groupby(key)["AL_Possible"].transform("sum").astype(float)

    # Step 3: Actual hours needed (Excel R) - float hours, capped by Max_AL_Hours
    par_needed = (dli_target - w["Natural_DLI"]).clip(lower=0.0)
    hours_needed_float = par_needed * 1_000_000.0 / (al_intensity * 3600.0)
    # Excel uses R in the MIN() inside the cumulative counter, which results in integer hours ON = floor(R)
    w["Actual_AL_Hours_Float"] = np.minimum(hours_needed_float, w["Max_AL_Hours"]).clip(lower=0.0)

    # Hourly allocation using Excel-style cumulative counter:
    # S_t = IF(OR(P=0, N="No"),0, IF(AND(N="Yes", S_prev+1<=MIN(O,R)), S_prev+1, S_prev))
    # => delta_on = 1 for the first floor(min(O,R)) allowed hours, else 0
    cap_hours_int = np.floor(w["Actual_AL_Hours_Float"] + 1e-12).astype(int)

    # cumulative allowed hours within each day
    allowed_cum = w["AL_Possible"].astype(int).groupby([w[c] for c in key]).cumsum()
    w["AL_On"] = (w["AL_Possible"]) & (allowed_cum <= cap_hours_int)

    # Step 4: DLI from AL + electricity (hourly then daily like Excel)
    w["AL_PAR_hourly"] = np.where(w["AL_On"], al_intensity * 3600.0 / 1_000_000.0, 0.0)  # mol/m2/h
    w["Elec_hourly_kWh_m2"] = np.where(w["AL_On"], al_intensity / led_eff / 1000.0, 0.0)

    daily = (
        w.groupby(key, as_index=False)
        .agg(
            **{
                "Natural DLI": ("PAR_Canopy", "sum"),
                "AL Hours (int)": ("AL_On", "sum"),
                "AL DLI": ("AL_PAR_hourly", "sum"),
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
                "Avg Daily Elec (kWh/m2/d)": ("Elec (kWh/m2)", "mean"),
                "Avg AL Hours (h/d)": ("AL Hours (int)", "mean"),
            }
        )
    )

    return monthly


# -------------------------
# Hybrid (LED + HPS) — Excel-faithful
# -------------------------

def Hybrid_usage(
    weather: pd.DataFrame,
    *,
    start: int = 5,
    photoperiod: int = 16,
    rad_setpoint: float = 400,
    day_temp_setpoint: float = 24,
    night_temp_setpoint: float = 16,
    dli_target: float = 30,
    al_intensity_target: float = 200,   # Q3 in Excel (target total PPFD)
    led_ppfd: float = 100,              # S3 in Excel for Hybrid (typically 0.5*Q3)
    hps_ppfd: float = 100,              # T3 in Excel for Hybrid (typically 0.5*Q3)
    led_eff: float = 3.6,               # U3
    hps_eff: float = 1.8,               # V3
    al_off_start_month: int = 0,
    al_off_end_month: int = 0,
) -> pd.DataFrame:
    """
    Implements the workbook's "Hybrid" mode decisions:
    - Hourly AL allocation based on AL_Possible and FLOOR(actual_hours_float)
    - Decision 1 (U): if AL_On then (Temp < setpoint ? HPS : LED) else None
      where setpoint is night/day depending on Isun==0
    - Decision 2 (Y): if D1 None -> None
      if D1 HPS and PPFD_D1 < target -> LED
      if D1 LED and PPFD_D1 < target and Temp < setpoint -> HPS
      else None
    """
    w = _validate_weather_df(weather)

    # Sun PAR at canopy
    w["PAR_Canopy"] = _par_mol_per_m2_per_h(w["Isun"])
    key = ["Year", "Month", "Day"]
    w["Natural_DLI"] = w.groupby(key)["PAR_Canopy"].transform("sum")

    # AL possible (same as LED)
    window_ok = (w["Hour"] >= start) & ((start + photoperiod + 1) > w["Hour"])
    sr_ok = w["Isun"] < rad_setpoint
    # For Hybrid, workbook uses day/night setpoint in Decision1, but AL_Possible temp influence in sheet is based on W3 (day setpoint) and Isun>0.
    # We'll follow the sheet's temp influence logic from column L: AND(Tout > day_setpoint, Isun>0) => No
    temp_ok = ~((w["Temp"] > day_temp_setpoint) & (w["Isun"] > 0))
    month_blocked = _month_block_mask(w["Month"], al_off_start_month, al_off_end_month)
    month_ok = ~month_blocked
    w["AL_Possible"] = window_ok & sr_ok & temp_ok & month_ok

    w["Max_AL_Hours"] = w.groupby(key)["AL_Possible"].transform("sum").astype(float)

    par_needed = (dli_target - w["Natural_DLI"]).clip(lower=0.0)
    hours_needed_float = par_needed * 1_000_000.0 / (al_intensity_target * 3600.0)
    w["Actual_AL_Hours_Float"] = np.minimum(hours_needed_float, w["Max_AL_Hours"]).clip(lower=0.0)
    cap_hours_int = np.floor(w["Actual_AL_Hours_Float"] + 1e-12).astype(int)

    allowed_cum = w["AL_Possible"].astype(int).groupby([w[c] for c in key]).cumsum()
    w["AL_On"] = w["AL_Possible"] & (allowed_cum <= cap_hours_int)

    # Decision 1 (U): pick HPS/LED based on temp vs setpoint (night if Isun==0)
    is_night = w["Isun"] == 0
    setpoint = np.where(is_night, night_temp_setpoint, day_temp_setpoint)
    w["Light1"] = np.where(
        ~w["AL_On"],
        "None",
        np.where(w["Temp"] < setpoint, "HPS", "LED")
    )

    # PPFD produced by Light1 this hour (W in Excel) – depends on light type, and only if AL_On
    w["Light1_PPFD"] = np.where(
        w["Light1"] == "HPS", hps_ppfd,
        np.where(w["Light1"] == "LED", led_ppfd, 0.0)
    )
    w["Light1_PPFD"] = np.where(w["AL_On"], w["Light1_PPFD"], 0.0)

    # Decision 2 (Y): see Excel formula
    need_more = w["Light1_PPFD"] < al_intensity_target
    temp_ok_for_hps = w["Temp"] < setpoint

    w["Light2"] = "None"
    w.loc[(w["Light1"] == "HPS") & need_more, "Light2"] = "LED"
    w.loc[(w["Light1"] == "LED") & need_more & temp_ok_for_hps, "Light2"] = "HPS"

    w["Light2_PPFD"] = np.where(
        w["Light2"] == "HPS", hps_ppfd,
        np.where(w["Light2"] == "LED", led_ppfd, 0.0)
    )
    w["Light2_PPFD"] = np.where(w["AL_On"], w["Light2_PPFD"], 0.0)

    # PAR + electricity per hour for each light (match Excel: PPFD * 3600 / 1e6 ; Elec = PPFD/eff/1000)
    def ppfd_to_par(ppfd):
        return ppfd * 3600.0 / 1_000_000.0  # mol/m2/h

    w["Light1_PAR"] = ppfd_to_par(w["Light1_PPFD"])
    w["Light2_PAR"] = ppfd_to_par(w["Light2_PPFD"])

    w["Light1_Elec_kWh_m2"] = np.where(
        w["Light1"] == "HPS", w["Light1_PPFD"] / hps_eff / 1000.0,
        np.where(w["Light1"] == "LED", w["Light1_PPFD"] / led_eff / 1000.0, 0.0)
    )
    w["Light2_Elec_kWh_m2"] = np.where(
        w["Light2"] == "HPS", w["Light2_PPFD"] / hps_eff / 1000.0,
        np.where(w["Light2"] == "LED", w["Light2_PPFD"] / led_eff / 1000.0, 0.0)
    )

    w["AL_PAR_hourly"] = w["Light1_PAR"] + w["Light2_PAR"]
    w["Elec_hourly_kWh_m2"] = w["Light1_Elec_kWh_m2"] + w["Light2_Elec_kWh_m2"]
    w["DLI_total_hourly"] = w["PAR_Canopy"] + w["AL_PAR_hourly"]

    daily = (
        w.groupby(key, as_index=False)
        .agg(
            **{
                "Natural DLI": ("PAR_Canopy", "sum"),
                "AL DLI": ("AL_PAR_hourly", "sum"),
                "DLI Total": ("DLI_total_hourly", "sum"),
                "Elec (kWh/m2)": ("Elec_hourly_kWh_m2", "sum"),
            }
        )
    )

    monthly = (
        daily.groupby("Month", as_index=False)
        .agg(
            **{
                "DLI Solar": ("Natural DLI", "mean"),
                "DLI AL": ("AL DLI", "mean"),
                "DLI Total Stdev": ("DLI Total", "std"),
                "Elec Cons (kWh/m2)": ("Elec (kWh/m2)", "mean"),  # Excel takes mean of monthly elec across years
                "Avg Daily Elec (kWh/m2/d)": ("Elec (kWh/m2)", "mean"),
            }
        )
    )

    return monthly


# -------------------------
# Plotting (kept compatible with your Streamlit)
# -------------------------

def plot_avgDLI(monthly: pd.DataFrame, months, savepath: Optional[str] = "AverageDLI_hybrid.png"):
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


def barplot_avgDLI(monthly: pd.DataFrame, months, savepath: Optional[str] = "AverageDLI.png"):
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