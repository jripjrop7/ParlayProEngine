import streamlit as st
import pandas as pd
import itertools
import numpy as np
import altair as alt
import requests
import random

# --- PAGE CONFIG ---
st.set_page_config(
    page_title="QUANT_PARLAY_ENGINE_V16", 
    layout="wide",
    initial_sidebar_state="expanded"
)

# --- CUSTOM CSS ---
st.markdown("""
<style>
    @import url('https://fonts.googleapis.com/css2?family=Source+Code+Pro:wght@400;600&display=swap');
    
    html, body, [class*="css"]  {
        font-family: 'Source Code Pro', 'Courier New', monospace !important;
        background-color: #0e1117; 
        color: #e0e0e0;
    }
    h1, h2, h3 { color: #00ff41 !important; font-weight: 600; letter-spacing: -1px; }
    .stTextInput input, .stNumberInput input, .stSelectbox div[data-baseweb="select"] {
        background-color: #1a1c24 !important; color: #00ff41 !important; border: 1px solid #333;
    }
    div[data-testid="stDataFrame"] { background-color: #1a1c24; border: 1px solid #333; }
    div.stButton > button {
        background-color: #0e1117; color: #00ff41; border: 1px solid #00ff41; border-radius: 0px;
        transition: all 0.3s ease;
    }
    div.stButton > button:hover {
        background-color: #00ff41; color: #000000; box-shadow: 0 0 10px #00ff41;
    }
    section[data-testid="stSidebar"] { background-color: #111; border-right: 1px solid #333; }
    
    /* Tabs Styling */
    .stTabs [data-baseweb="tab-list"] { gap: 10px; }
    .stTabs [data-baseweb="tab"] {
        background-color: #1a1c24; border: 1px solid #333; color: #00ff41; border-radius: 4px;
    }
    .stTabs [aria-selected="true"] {
        background-color: #00ff41 !important; color: #000 !important;
    }
</style>
""", unsafe_allow_html=True)

# --- HELPER FUNCTIONS ---
def american_to_decimal(odds):
    try:
        odds = float(odds)
        if odds >= 100: return (odds / 100) + 1
        elif odds <= -100: return (100 / abs(odds)) + 1
        return 1.0
    except: return 1.0

def format_money(val):
    return f"${val:,.2f}"

def kelly_criterion(decimal_odds, win_prob_percent, fractional_kelly=0.25):
    if decimal_odds <= 1: return 0.0
    b = decimal_odds - 1
    p = win_prob_percent / 100
    q = 1 - p
    kelly_perc = (b * p - q) / b
    return max(0, kelly_perc * fractional_kelly)

def fetch_fanduel_odds(api_key, sport_key):
    url = f'https://api.the-odds-api.com/v4/sports/{sport_key}/odds'
    params = {
        'apiKey': api_key,
        'regions': 'us',
        'markets': 'h2h', 
        'bookmakers': 'fanduel',
        'oddsFormat': 'american'
    }
    try:
        response = requests.get(url, params=params)
        response.raise_for_status()
        data = response.json()
        new_legs = []
        for game in data:
            game_group_id = game['id'][-5:] 
            for bookmaker in game['bookmakers']:
                if bookmaker['key'] == 'fanduel':
                    for market in bookmaker['markets']:
                        if market['key'] == 'h2h':
                            for outcome in market['outcomes']:
                                leg_name = f"{outcome['name']} (ML)"
                                price = outcome['price']
                                new_legs.append({
                                    "Active": True,
                                    "Excl Group": game_group_id,
                                    "Link Group": "",
                                    "Leg Name": leg_name,
                                    "Odds": price,
                                    "Conf (1-10)": 5 
                                })
        return new_legs
    except Exception as e:
        st.error(f"API Error: {e}")
        return []

# --- INITIALIZE STATE ---
if 'input_data' not in st.session_state:
    st.session_state.input_data = pd.DataFrame([
        {"Active": True, "Excl Group": "A", "Link Group": "KC", "Leg Name": "KC Chiefs ML", "Odds": -200, "Conf (1-10)": 8},
        {"Active": True, "Excl Group": "A", "Link Group": "", "Leg Name": "KC Chiefs -3", "Odds": -110, "Conf (1-10)": 7},
        {"Active": True, "Excl Group": "", "Link Group": "KC", "Leg Name": "Mahomes 2+ TD", "Odds": -150, "Conf (1-10)": 9},
    ])
    
if 'generated_parlays' not in st.session_state:
    st.session_state.generated_parlays = []
    
if 'portfolio_state' not in st.session_state:
    st.session_state.portfolio_state = pd.DataFrame()

# --- SIDEBAR ---
with st.sidebar:
    st.title("/// SYSTEM_CONTROLS")
    
    st.markdown("### > LIVE_DATA_FEED")
    api_key = st.text_input("API_KEY (The Odds API)", type="password")
    sport_select = st.selectbox("TARGET_MARKET", 
        ["americanfootball_nfl", "basketball_nba", "icehockey_nhl", "basketball_ncaab"]
    )
    
    if st.button("📡 PULL_FANDUEL_LINES (APPEND)"):
        if not api_key:
            st.error("MISSING_API_KEY")
        else:
            with st.spinner("FETCHING_LIVE_ODDS..."):
                fetched_data = fetch_fanduel_odds(api_key, sport_select)
                if fetched_data:
                    new_df = pd.DataFrame(fetched_data)
                    st.session_state.input_data = pd.concat([st.session_state.input_data, new_df], ignore_index=True)
                    st.session_state.input_data.drop_duplicates(subset=['Leg Name'], keep='last', inplace=True)
                    st.success(f"ADDED {len(fetched_data)} NEW LINES")
                    st.rerun()

    st.markdown("---")
    st.markdown("### > DATA_PERSISTENCE")
    
    csv = st.session_state.input_data.to_csv(index=False).encode('utf-8')
    st.download_button(
        label="💾 DOWNLOAD_DATABASE (CSV)",
        data=csv,
        file_name="parlay_master_list.csv",
        mime="text/csv",
    )

    uploaded_file = st.file_uploader("📂 LOAD_DATABASE", type=["csv"])
    if uploaded_file is not None:
        try:
            loaded_df = pd.read_csv(uploaded_file)
            if "Link Group" not in loaded_df.columns: loaded_df["Link Group"] = ""
            if "Excl Group" not in loaded_df.columns and "Group" in loaded_df.columns:
                loaded_df.rename(columns={"Group": "Excl Group"}, inplace=True)
            st.session_state.input_data = loaded_df
            st.success("DATABASE_RESTORED")
            st.rerun()
        except Exception as e:
            st.error(f"ERROR: {e}")

    st.markdown("---")
    if st.button("🗑️ CLEAR_ALL_DATA"):
        st.session_state.input_data = pd.DataFrame(columns=["Active", "Excl Group", "Link Group", "Leg Name", "Odds", "Conf (1-10)"])
        st.session_state.generated_parlays = []
        st.rerun()

    st.markdown("### > BANKROLL_LOGIC")
    bankroll = st.number_input("TOTAL_BANKROLL ($)", 100.0, 1000000.0, 1000.0)
    kelly_fraction = st.slider("KELLY_FRACT", 0.1, 1.0, 0.25)
    
    st.markdown("### > CORRELATION_MATRIX")
    sgp_mode = st.checkbox("ENABLE_CORRELATION_BOOST", value=True)
    correlation_boost = st.slider("LINK_BOOST_PCT (%)", 0, 50, 15)

    st.markdown("### > PARLAY_SPECS")
    min_legs = st.number_input("MIN_LEGS", 2, 12, 3)
    max_legs = st.number_input("MAX_LEGS", 2, 15, 4)

    st.markdown("### > FILTERS")
    target_min_odds = st.number_input("MIN_ODDS (+)", 100, 100000, 100)
    target_max_odds = st.number_input("MAX_ODDS (+)", 100, 500000, 10000)
    min_ev_filter = st.checkbox("FILTER_NEG_EV", value=True)
    max_combos = st.select_slider("MAX_ITERATIONS", options=[1000, 5000, 10000], value=5000)

# --- MAIN APP LAYOUT ---
st.title("> QUANT_PARLAY_ENGINE_V16")

# --- TABS SYSTEM ---
tab_build, tab_scenarios, tab_hedge, tab_analysis = st.tabs(["🏗️ BUILDER", "🧪 SCENARIOS", "🛡️ HEDGE_CALC", "📊 ANALYSIS"])

# ==========================================
# TAB 1: BUILDER
# ==========================================
with tab_build:
    with st.expander("➕ OPEN_PROP_BUILDER (Click to Add Custom Bets)"):
        st.markdown("`>> MANUAL_OVERRIDE_PROTOCOL`")
        c1, c2, c3, c4, c5 = st.columns([2, 1, 1, 1, 1])
        
        with c1: new_prop_name = st.text_input("PROP_NAME", placeholder="e.g. LeBron Over 25.5 Pts")
        with c2: new_excl_group = st.text_input("⛔ EXCL_ID", placeholder="Conflict ID")
        with c3: new_link_group = st.text_input("🔗 LINK_ID", placeholder="Correlation ID")
        with c4: new_prop_odds = st.number_input("ODDS (AMER)", value=-110, step=10)
        with c5: new_prop_conf = st.slider("CONFIDENCE", 1, 10, 5)
            
        if st.button("ADD_PROP_TO_TABLE"):
            if new_prop_name:
                new_row = {
                    "Active": True, "Excl Group": new_excl_group, "Link Group": new_link_group,
                    "Leg Name": new_prop_name, "Odds": new_prop_odds, "Conf (1-10)": new_prop_conf
                }
                st.session_state.input_data = pd.concat([st.session_state.input_data, pd.DataFrame([new_row])], ignore_index=True)
                st.success(f"ADDED: {new_prop_name}")
                st.rerun()

    col_clone, col_spacer = st.columns([1, 4])
    with col_clone:
        if st.button("👯 CLONE_SELECTED_ROWS"):
            df = st.session_state.input_data.copy()
            rows_to_clone = df[df['Active'] == True]
            if not rows_to_clone.empty:
                st.session_state.input_data = pd.concat([df, rows_to_clone], ignore_index=True)
                st.success(f"CLONED {len(rows_to_clone)} ROWS")
                st.rerun()

    edited_df = st.data_editor(
        st.session_state.input_data, 
        column_config={
            "Active": st.column_config.CheckboxColumn("USE?", width="small"),
            "Excl Group": st.column_config.TextColumn("⛔ EXCL", width="small"),
            "Link Group": st.column_config.TextColumn("🔗 LINK", width="small"),
            "Leg Name": st.column_config.TextColumn("LEG_ID"),
            "Odds": st.column_config.NumberColumn("ODDS"),
            "Conf (1-10)": st.column_config.NumberColumn("CONF", min_value=1, max_value=10)
        },
        num_rows="dynamic", use_container_width=True, key="editor_widget" 
    )

    st.session_state.input_data = edited_df

    if not edited_df.empty:
        df = edited_df.copy()
        active_df = df[df["Active"] == True].copy()
        active_df['Decimal'] = active_df['Odds'].apply(american_to_decimal)
        active_df['Est Win %'] = active_df['Conf (1-10)'] * 10 
    else:
        st.info("TABLE_EMPTY")
        st.stop()

    st.write("") 
    if st.button(">>> GENERATE_OPTIMIZED_HEDGE"):
        if active_df.empty:
            st.error("NO_ACTIVE_LEGS")
        else:
            legs_list = active_df.to_dict('records')
            valid_parlays = []
            combo_count = 0
            stop_execution = False
            min_dec = american_to_decimal(target_min_odds)
            max_dec = american_to_decimal(target_max_odds)

            with st.spinner(f"PROCESSING {len(legs_list)} ACTIVE LEGS..."):
                for r in range(min_legs, max_legs + 1):
                    if stop_execution: break
                    for combo in itertools.combinations(legs_list, r):
                        excl_groups = [str(x['Excl Group']) for x in combo if str(x['Excl Group']).strip()]
                        if len(excl_groups) != len(set(excl_groups)): continue

                        is_correlated = False
                        if sgp_mode:
                            link_groups = [str(x['Link Group']) for x in combo if str(x['Link Group']).strip()]
                            if len(link_groups) != len(set(link_groups)): is_correlated = True
                        
                        combo_count += 1
                        if combo_count > max_combos: stop_execution = True; break

                        dec_total = np.prod([x['Decimal'] for x in combo])
                        if not (min_dec <= dec_total <= max_dec): continue

                        raw_win_prob = np.prod([x['Est Win %']/100 for x in combo])
                        final_win_prob = min(0.99, raw_win_prob * (1 + (correlation_boost/100) if is_correlated else 1))

                        kelly_pct = kelly_criterion(dec_total, final_win_prob * 100, kelly_fraction)
                        wager = bankroll * kelly_pct
                        if min_ev_filter and wager <= 0: continue
                        
                        payout = (dec_total * wager) - wager
                        ev = (final_win_prob * payout) - ((1 - final_win_prob) * wager)

                        valid_parlays.append({
                            "BET?": True, # DEFAULT ALL TO TRUE
                            "LEGS": [l['Leg Name'] for l in combo],
                            "ODDS": dec_total,
                            "PROB": final_win_prob * 100,
                            "WAGER": wager,
                            "PAYOUT": payout,
                            "EV": ev,
                            "RAW_LEGS_DATA": combo,
                            "BOOST": "🚀" if is_correlated else ""
                        })
            
            st.session_state.generated_parlays = valid_parlays
            st.rerun()

    # --- RESULTS DISPLAY (NOW EDITABLE) ---
    if len(st.session_state.generated_parlays) > 0:
        st.divider()
        st.markdown("### 📋 GENERATED_PORTFOLIO (Check box to include in Analysis)")
        
        # Convert list to DF
        results_df = pd.DataFrame(st.session_state.generated_parlays)
        
        # We need to sort it initially, but if we just sort the DF, it might mess up the editor state
        # So we usually just display it.
        
        # Prepare for Editor
        display_df = results_df.copy()
        display_df['LEGS'] = display_df['LEGS'].apply(lambda x: " + ".join(x))
        
        # EDITABLE DATAFRAME FOR SELECTION
        portfolio_edits = st.data_editor(
            display_df,
            column_config={
                "BET?": st.column_config.CheckboxColumn("PLACED?", help="Only checked rows are used in Scenarios/Sims"),
                "LEGS": st.column_config.TextColumn("PARLAY LEGS", width="large"),
                "WAGER": st.column_config.NumberColumn("KELLY ($)", format="$%.2f"),
                "PAYOUT": st.column_config.NumberColumn("PAYOUT ($)", format="$%.2f"),
                "EV": st.column_config.NumberColumn("EV ($)", format="$%.2f"),
                "ODDS": st.column_config.NumberColumn("DEC ODDS", format="%.2f"),
                "PROB": st.column_config.NumberColumn("WIN %", format="%.1f%%"),
                "RAW_LEGS_DATA": None # Hide raw data
            },
            hide_index=True,
            use_container_width=True,
            key="portfolio_editor"
        )
        
        # SYNC SELECTION BACK TO STATE
        # We iterate through the original list and update the "BET?" status based on the editor
        # Note: data_editor returns a new DF. We must map it back.
        # Simplest way: The index of display_df matches st.session_state.generated_parlays
        
        # Update the master list 'BET?' status based on the editor
        for index, row in portfolio_edits.iterrows():
            st.session_state.generated_parlays[index]['BET?'] = row['BET?']

        # Total Stats (Only counting Checked rows)
        active_portfolio = [p for p in st.session_state.generated_parlays if p['BET?']]
        total_risk = sum(p['WAGER'] for p in active_portfolio)
        total_ev = sum(p['EV'] for p in active_portfolio)
        
        st.caption(f"ACTIVE PORTFOLIO: {len(active_portfolio)} Tickets Selected")
        c1, c2 = st.columns(2)
        c1.metric("TOTAL_RISK (Active)", format_money(total_risk))
        c2.metric("TOTAL_EV (Active)", format_money(total_ev))

# ==========================================
# TAB 2: SCENARIOS
# ==========================================
with tab_scenarios:
    st.header("🧪 SCENARIO_STRESS_TESTER")
    st.caption("Only analyzes tickets marked as 'PLACED?' in the Builder tab.")
