import streamlit as st
import pandas as pd
import itertools
import numpy as np
import altair as alt

# --- PAGE CONFIG ---
st.set_page_config(
    page_title="QUANT_PARLAY_ENGINE_V1", 
    layout="wide",
    initial_sidebar_state="expanded"
)

# --- CUSTOM CSS FOR TERMINAL UI ---
# This block injects the "Slick Coder" look
st.markdown("""
<style>
    /* GLOBAL FONTS & BACKGROUND */
    @import url('https://fonts.googleapis.com/css2?family=Source+Code+Pro:wght@400;600&display=swap');
    
    html, body, [class*="css"]  {
        font-family: 'Source Code Pro', 'Courier New', monospace !important;
        background-color: #0e1117; 
        color: #e0e0e0;
    }

    /* HEADERS */
    h1, h2, h3 {
        color: #00ff41 !important; /* Matrix Green Accents */
        font-weight: 600;
        letter-spacing: -1px;
    }
    
    /* INPUT FIELDS */
    .stTextInput input, .stNumberInput input {
        background-color: #1a1c24 !important;
        color: #00ff41 !important;
        border: 1px solid #333;
    }

    /* DATAFRAME/TABLE STYLING */
    div[data-testid="stDataFrame"] {
        background-color: #1a1c24;
        border: 1px solid #333;
    }

    /* BUTTONS */
    div.stButton > button {
        background-color: #0e1117;
        color: #00ff41;
        border: 1px solid #00ff41;
        border-radius: 0px; /* Square edges for technical look */
        transition: all 0.3s ease;
    }
    div.stButton > button:hover {
        background-color: #00ff41;
        color: #000000;
        box-shadow: 0 0 10px #00ff41;
    }

    /* SIDEBAR */
    section[data-testid="stSidebar"] {
        background-color: #111;
        border-right: 1px solid #333;
    }
    
    /* ALERTS */
    .stAlert {
        background-color: #1a1c24;
        color: #e0e0e0;
        border: 1px solid #444;
    }
</style>
""", unsafe_allow_html=True)

# --- HELPER FUNCTIONS ---
def american_to_decimal(odds):
    try:
        odds = float(odds)
        if odds >= 100:
            return (odds / 100) + 1
        elif odds <= -100:
            return (100 / abs(odds)) + 1
        return 1.0
    except:
        return 1.0

def format_money(val):
    return f"${val:,.2f}"

# --- SIDEBAR: CONTROLS ---
with st.sidebar:
    st.title("/// SYSTEM_CONTROLS")
    
    st.markdown("### > STRUCTURE")
    min_legs = st.number_input("MIN_LEGS", 2, 12, 3)
    max_legs = st.number_input("MAX_LEGS", 2, 15, 4)
    unit_size = st.number_input("UNIT_SIZE ($)", 1.0, 5000.0, 10.0)

    st.markdown("---")
    
    st.markdown("### > FILTERS")
    target_min_odds = st.number_input("MIN_ODDS (+)", 100, 100000, 100)
    target_max_odds = st.number_input("MAX_ODDS (+)", 100, 500000, 10000)
    min_ev_filter = st.checkbox("FILTER_NEGATIVE_EV", value=False)
    
    st.markdown("---")
    st.markdown("### > SAFETY_LIMITS")
    max_combos = st.select_slider(
        "MAX_ITERATIONS", 
        options=[1000, 5000, 10000, 50000, 100000],
        value=5000
    )

# --- MAIN INTERFACE ---
st.title("> PARLAY_OPTIMIZER_V1.0")
st.markdown("`STATUS: READY` | `MODE: HEDGING`")

# --- STEP 1: INPUT ---
st.subheader("1.0 // DATA_ENTRY")

default_data = pd.DataFrame([
    {"Group": "A", "Leg Name": "KC_CHIEFS_ALT_LINE -3", "Odds": -200, "Conf (1-10)": 9},
    {"Group": "A", "Leg Name": "KC_CHIEFS_Spread -7", "Odds": +100, "Conf (1-10)": 7},
    {"Group": "A", "Leg Name": "KC_CHIEFS_ALT_LINE -10", "Odds": +180, "Conf (1-10)": 4},
    {"Group": "B", "Leg Name": "LAL_LAKERS_ML", "Odds": -110, "Conf (1-10)": 6},
    {"Group": "C", "Leg Name": "TOTAL_OVER 220.5", "Odds": -110, "Conf (1-10)": 5},
    {"Group": "C", "Leg Name": "TOTAL_UNDER 220.5", "Odds": -110, "Conf (1-10)": 5},
    {"Group": "D", "Leg Name": "PROP_BARKLEY_TD", "Odds": +120, "Conf (1-10)": 8},
])

column_config = {
    "Group": st.column_config.TextColumn("GRP_ID", help="Conflict Group", width="small"),
    "Leg Name": st.column_config.TextColumn("LEG_ID"),
    "Odds": st.column_config.NumberColumn("AMER_ODDS"),
    "Conf (1-10)": st.column_config.NumberColumn("CONF_LVL", min_value=1, max_value=10)
}

edited_df = st.data_editor(
    default_data, 
    column_config=column_config,
    num_rows="dynamic", 
    use_container_width=True
)

# Logic Processing
if not edited_df.empty:
    df = edited_df.copy()
    df['Decimal'] = df['Odds'].apply(american_to_decimal)
    df['Est Win %'] = df['Conf (1-10)'] * 10 
else:
    st.stop()

# --- STEP 2: EXECUTION ---
st.write("") # Spacer
if st.button(">>> INITIALIZE_GENERATION_SEQUENCE"):
    
    legs_list = df.to_dict('records')
    valid_parlays = []
    combo_count = 0
    stop_execution = False

    min_dec_target = american_to_decimal(target_min_odds)
    max_dec_target = american_to_decimal(target_max_odds)

    with st.spinner("PROCESSING_PERMUTATIONS..."):
        for r in range(min_legs, max_legs + 1):
            if stop_execution: break
            
            combinations = itertools.combinations(legs_list, r)
            
            for combo in combinations:
                # Conflict Check
                groups = [item['Group'] for item in combo if item['Group'] and str(item['Group']).strip() != '']
                if len(groups) != len(set(groups)):
                    continue 
                
                combo_count += 1
                if combo_count > max_combos:
                    stop_execution = True
                    st.warning(f"Warning: Iteration limit ({max_combos}) reached. Displaying partial results.")
                    break

                decimal_total = np.prod([leg['Decimal'] for leg in combo])
                
                # Odds Range Filter
                if not (min_dec_target <= decimal_total <= max_dec_target):
                    continue

                avg_conf = np.mean([leg['Conf (1-10)'] for leg in combo])
                est_win_prob = np.prod([leg['Est Win %']/100 for leg in combo])
                
                payout = (decimal_total * unit_size) - unit_size
                ev = (est_win_prob * payout) - ((1 - est_win_prob) * unit_size)

                if min_ev_filter and ev < 0:
                    continue

                valid_parlays.append({
                    "LEGS": [l['Leg Name'] for l in combo], 
                    "COUNT": r,
                    "ODDS": decimal_total,
                    "CONF": round(avg_conf, 1),
                    "PAYOUT": payout,
                    "EV": ev
                })

    # --- STEP 3: OUTPUT ---
    st.divider()
    st.subheader("2.0 // OUTPUT_LOG")
    
    results_df = pd.DataFrame(valid_parlays)

    if results_df.empty:
        st.error("ERROR: NO_VALID_COMBINATIONS_FOUND.")
    else:
        col1, col2 = st.columns([2, 1])
        
        with col1:
            st.markdown("`>> SORTING_PROTOCOL`")
            sort_col = st.selectbox("", ["EV", "CONF", "PAYOUT", "ODDS"], label_visibility="collapsed")
            ascending_order = False 
            
            results_df = results_df.sort_values(by=sort_col, ascending=ascending_order)
            
            # Format for display
            display_df = results_df.copy()
            display_df['LEGS'] = display_df['LEGS'].apply(lambda x: " + ".join(x))
            display_df['PAYOUT'] = display_df['PAYOUT'].apply(format_money)
            display_df['EV'] = display_df['EV'].apply(format_money)
            display_df['ODDS'] = display_df['ODDS'].apply(lambda x: f"{x:.2f}")
            
            st.dataframe(display_df, use_container_width=True, hide_index=True)

        with col2:
            st.markdown("`>> EXPOSURE_HEATMAP`")
            
            all_legs = [leg for sublist in results_df['LEGS'] for leg in sublist]
            counts = pd.Series(all_legs).value_counts().reset_index()
            counts.columns = ['LEG_ID', 'FREQ']
            
            # Custom Green Theme Chart
            c = alt.Chart(counts).mark_bar(color='#00ff41').encode(
                x='FREQ', 
                y=alt.Y('LEG_ID', sort='-x'),
                tooltip=['LEG_ID', 'FREQ']
            ).configure_axis(
                labelColor='#e0e0e0',
                titleColor='#00ff41'
            ).configure_view(
                strokeWidth=0
            ).properties(background='transparent')
            
            st.altair_chart(c, use_container_width=True)
            
            st.metric("TOTAL_TICKETS", len(results_df))
            st.metric("EST_MAX_RETURN", format_money(results_df['PAYOUT'].max() if not results_df.empty else 0))

