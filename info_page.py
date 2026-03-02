"""
If the user selects "info" in the side bar, the following inforamtion will be displayed
"""

import streamlit as st

def render():

    st.title("How This Calculator Works")

    st.markdown("""

    From the hourly climate data, this calculator makes hourly decisions of whether to put the lights on or off and if it is a hybrid system, whether to use the LED or HPS lights first.  \n
    **See below how the input variables contribute to these hourly decisions.**

    """)

    st.image("HourlyDecisionChart_AlMA.png")

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
    
    st.subheader("Target DLI & Target AL Intensity")

    st.markdown("""
    The Target Artificial Light Intensity is used to determine how many hours per day artifical lights will need to be on to meet the Target DLI.  \n
    For hybrid systems, the target AL Intensity is called **"Target total AL intensity"**. For LED-only systems, it is called just **"AL Intensity"**.
    """)
    st.latex(r"""
    \mathrm{PAR\ Needed\ (mol/m2/day)}=
    \mathrm{Target\ DLI\ (mol/m2/day)}-
    \mathrm{Natural\ DLI\ (mol/m2/day)}
    """)
    st.latex(r"""
    \mathrm{Hours\ Needed\ (h)} =
    \mathrm{PAR\ Needed\ (mol/m2/day)}
    \times
    \mathrm{Target\ AL\ Intensity\ (umol/m2/s)}
    \times{1000000umol/mol}
    \times{h/3600s}
    """)
    st.markdown("""
    The number of hours required to meet the target DLI is compared to the number of hours AL is allowed to be one by Step 1 Checkpoint. The lower threshold is taken as the maximum
    and a cumulative counter disallows artificial lighting when the daily maximum has been reached.
    """)

