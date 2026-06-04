import streamlit as st
import pandas as pd
import matplotlib.pyplot as plt


### HELPERS ###
months = ("Jan", "Feb", "Mar", "Apr", "May", "June", "July", "Aug", "Sept", "Oct", "Nov", "Dec")

def _screen_check_prepare_hourly(weather: pd.DataFrame, trans_roof: float) -> pd.DataFrame:
    """Prepare hourly solar DLI data for the simple screen check page.

    Input: hourly weather
    Output: that same hourly weather, but added columns: Month (int), _day (date object), and PAR_mol_m2_h (float)
    
    Upload weather data from ksgclimatedata to keep correct formatting

    Conversion W/m² → mol PAR/m²/h matches growlights_v6.py line 315:
      mol/m²/h = W/m² × 0.5 × 4.6 × 3600 / 1e6
    """
    df = weather.copy()

    # Alert if there are any missing columns
    required = ["Local Time", "Temperature (C)", "Relative Humidity (%)", "Solar Radiation (W/m²)"]
    missing = [c for c in required if c not in df.columns]
    if missing:
        raise ValueError(f"Missing required columns: {missing}")

    # Add column for formatted Date/Time
    df["timestamp"] = pd.to_datetime(df["Local Time"])

    # Convert raw solar radiation into crop level PAR
    isun_raw = pd.to_numeric(df["Solar Radiation (W/m²)"], errors="coerce").clip(lower=0)
    #      Apply trans_roof here.
    isun_wm2 = isun_raw * float(trans_roof)
    #      W/m² → mol PAR/m²/h  (consistent with growlights_v6.py)
    df["PAR_mol_m2_h"] = isun_wm2 * 0.5 * 4.6 * 3600 / 1_000_000

    return df

def _calculate_monthly_dli_stats(hourly: pd.DataFrame, shade_1_pct: float = 0.0, shade_2_pct: float = 0.0) -> pd.DataFrame:
    """
    Input: hourly climate data, scr 1 shade, scr 2, shade
    Output: table with two columns (timestamp and DLI) for each day in the 10 year data

    The PAR data coming in the hourly dataframe already includes roof transmission (calculation in _screen_check_prepare_hourly)
    """
    
    # Step 1: Collpase to day level

    multiplier = (1 - float(shade_1_pct) / 100) * (1 - float(shade_2_pct) / 100)
    df = hourly.copy()
    df["DLI"] = df["PAR_mol_m2_h"] * multiplier
    
    daily = (
        df.groupby(df["timestamp"].dt.date, dropna=True)["DLI"]
        .sum()
        .reset_index(name="DLI")
    )
    daily["timestamp"] = pd.to_datetime(daily["timestamp"])
    daily["Month"] = daily["timestamp"].dt.month

    # Step 2: Define functions for the monthly stats
    
    def _top10(s: pd.Series) -> float:
        q = s.quantile(0.90)
        return s[s >= q].mean()

    def _bottom10(s: pd.Series) -> float:
        q = s.quantile(0.10)
        return s[s <= q].mean()

    # Step 3: Group by month and calculate benchmarks

    out = (
        daily.groupby("Month")["DLI"]
        .agg(
            Average_DLI="mean",
            Minimum_DLI="min",
            Maximum_DLI="max",
            Bottom_10pct_mean_DLI=_bottom10,
            Top_10pct_mean_DLI=_top10,
        )
        .reset_index()
    )

    out["Month name"] = out["Month"].map(lambda m: months[int(m) - 1] if pd.notna(m) and 1 <= int(m) <= 12 else str(m))

    return out[["Month", "Month name", "Average_DLI", "Minimum_DLI", "Maximum_DLI", "Bottom_10pct_mean_DLI", "Top_10pct_mean_DLI"]]

def _plot_screen_check_compare(
    stats_shaded: pd.DataFrame, 
    stats_no_screens: pd.DataFrame, 
    dli_target: float = None
):
    """Plots a 3-way monthly comparison: No Screens vs. Shaded vs. Target DLI."""
    
    fig, ax = plt.subplots(figsize=(10, 5))
    
    # 1. Plot Baseline (No Screens) - typically a dashed or lighter line
    ax.plot(
        stats_no_screens["Month name"], 
        stats_no_screens["Top_10pct_mean_DLI"], 
        marker="o", 
        linestyle="--",
        color="gray",
        linewidth=2, 
        label="No Screens (Top 10% Bright Days)"
    )
    
    # 2. Plot Strategy (With Screens Applied) - solid, high-contrast line
    ax.plot(
        stats_shaded["Month name"], 
        stats_shaded["Top_10pct_mean_DLI"], 
        marker="s", 
        color="#1f77b4", # Clean blue
        linewidth=2.5, 
        label="Screens Active (Top 10% Bright Days)"
    )
    
    # 3. Plot the Target DLI Goal Line
    if dli_target is not None and dli_target > 0:
        ax.axhline(
            dli_target, 
            color="red", 
            linestyle="-.", 
            linewidth=1.5, 
            label=f"Target Crop DLI ({dli_target:.0f})"
        )
    
    # Formatting
    ax.set_xlabel("Month")
    ax.set_ylabel("DLI (mol/m²/day)")
    ax.tick_params(axis="x", rotation=45)
    ax.grid(True, alpha=0.3, linestyle=":")
    ax.legend(loc="upper right")
    
    fig.tight_layout()
    return fig

### PAGE RENDER ###

def render():
    st.title("Screen Selection Tool")

    # ------------------------------------------------------------------ #
    #  Upload
    # ------------------------------------------------------------------ #
    uploaded_screen = st.file_uploader(
        ":red[**Upload weather data (Excel file)**]",
        type=["xlsx"],
        key="screen_check_upload",
    )
    if uploaded_screen is not None:
        weather_df = pd.read_excel(uploaded_screen)
    else:
        st.warning("Upload weather data to activate the tool.")
        st.stop()

    system = st.radio("Screen System:", ["Two Screens (Energy & Shade)","One Screen (Energy/Shade) or Two Screens (Energy/Shade & Blackout)"], index=0)
    
    if system == "Two Screens (Energy & Shade)":
        st.subheader("Select Screen 1")
        st.markdown("If the greenhouse is an **Ultra-Clima greenhouse**, start with high energy savings, low shade. If the greenhouse is a **Conventional Venlo**, " \
        "energy savings will be limited due to reliance on ventilation.")

        type = st.selectbox("Greenhouse Type:", ["Ultra-Clima","Conventional Venlo"])
        st.markdown("**Screen 1 (Initial) Suggestion:**")
        if type == "Ultra-Clima":
            st.info("SF10 Diffuse - FR, 47% Energy-Savings, 15% Shade")
        elif type == "Conventional Venlo":
            st.info("KSG to advise scr1 for conventional Venlo.")

        st.subheader("Select Screen 2")

        st.markdown("**Step 1:** Set the DLI target:")
        st.caption("Use the maximum suggested DLI from the crop. See Crop Data PDF or main 'Calculator' tab.")
        target_dli = st.number_input("*Max DLI*:", value=30.0, step=1.0)

        st.markdown("**Step 2:** Set screen 1 shade level based on the suggestion in Step 1.")
        scr1_shade = st.slider("*Screen 1 (Shading %):*", min_value=0, max_value=100, value=15, step=1)

        st.markdown("**Step 3:** Adjust screen 2 shade level until the highest DLIs are contained to the DLI target when both screens are shut.")
        scr2_shade = st.slider("*Screen 2 (Shading %):*", min_value=0, max_value=100, value=20, step=1)

        # Process the weather data by grouping into daily sums, then monthly stats
        hourly_processed = _screen_check_prepare_hourly(weather_df, trans_roof=0.8)
        stats_shaded = _calculate_monthly_dli_stats(hourly_processed, scr1_shade, scr2_shade)
        stats_no_screens = _calculate_monthly_dli_stats(hourly_processed, 0, 0)

        # Plot comparison
        fig_top = _plot_screen_check_compare(
            stats_shaded, 
            stats_no_screens, 
            dli_target=target_dli
        )
        st.pyplot(fig_top, use_container_width=True)
        plt.close(fig_top)
        

    elif system == "One Screen (Energy/Shade) or Two Screens (Energy/Shade & Blackout)":

        st.markdown("**Step 1:** Set the DLI target:")
        st.caption("Use the maximum suggested DLI from the crop. See Crop Data PDF or main 'Calculator' tab.")
        target_dli = st.number_input("*Max DLI*:", value=30.0, step=1.0)

        st.markdown("**Step 2:** Adjust the screen level to meet the DLI target.")
        st.caption("If using the PAR Perfect strategy with an upper blackout screen, then assume the summer months " \
        "are kept within the DLI target.")
        scr_shade = st.slider("*Screen (Shading %):*", min_value=0, max_value=100, value=15, step=1)

        # Process the weather data by grouping into daily sums, then monthly stats
        hourly_processed = _screen_check_prepare_hourly(weather_df, trans_roof=0.8)
        stats_shaded = _calculate_monthly_dli_stats(hourly_processed, scr_shade, 0)
        stats_no_screens = _calculate_monthly_dli_stats(hourly_processed, 0, 0)

        # Plot comparison
        fig_top = _plot_screen_check_compare(
            stats_shaded, 
            stats_no_screens, 
            dli_target=target_dli
        )
        st.pyplot(fig_top, use_container_width=True)
        plt.close(fig_top)

    st.title("Common Screens")
    screen_df = pd.read_excel("Screen_database.xlsx")
    st.dataframe(screen_df, hide_index=True)