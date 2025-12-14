import streamlit as st
import pandas as pd
import itertools
import numpy as np
import altair as alt
import requests
import random
from datetime import datetime

# --- PAGE CONFIG ---
st.set_page_config(
    page_title="QUANT_PARLAY_ENGINE_V20", 
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

# --- CALLBACK FUNCTIONS (THE FIX FOR DOUBLE CLICK) ---
def update_main_data():
    # Syncs the editor state back to the permanent session state immediately on change
    st.session_state.input_data = st.session_state["editor_widget"]

def update_portfolio_data():
    # Updates the 'BET?' status in the generated parlays list immediately
    edits = st.session_state["portfolio_editor"]
    # Reconstruct the updates
    # The data_editor returns the full dataframe in the state key
    # We iterate and update our master list
    # Note: st.session_state["portfolio_editor"] is a DataFrame containing the edited data
    edited_df = st.session_state["portfolio_editor"]
    
    # We map the 'BET?' column back to our list of dictionaries
    for index, row in edited_df.iterrows():
        if index < len(st.session_state.generated_parlays):
            st.session_state.generated_parlays[index]['BET?'] = row['BET?']

# --- INITIALIZE STATE ---
if 'input_data' not in st.session_state:
    st.session_state.input_data = pd.DataFrame([
        {"Active": True, "Excl Group": "A", "Link Group": "KC", "Leg Name": "KC Chiefs ML", "Odds": -200, "Conf (1-10)": 8},
        {"Active": True, "Excl Group": "A", "Link Group": "", "Leg Name": "KC Chiefs -3", "Odds": -110, "Conf (1-10)": 7},
        {"Active": True, "Excl Group": "", "Link Group": "KC", "Leg Name": "Mahomes 2+ TD", "Odds": -150, "Conf (1-10)": 9},
    ])
    
if 'generated_parlays' not in st.session_state:
    st.session_state.generated_parlays = []
    
if 'bet_history' not in st.session_state:
    st.session_state.bet_history = pd.DataFrame(columns=[
        "Date", "Legs", "Odds", "Wager", "Payout", "Result", "Profit"
    ])

# --- SIDEBAR ---
with st.sidebar:
    st.title("/// SYSTEM_CONTROLS")
    
    with st.expander("⚖️ FAIR_VALUE_CALC (Vig Remover)"):
        fv_odds_1 = st.number_input("Side A Odds (e.g. -110)", value=-110, step=5)
        fv_odds_2 = st.number_input("Side B Odds (e.g. -110)", value=-110, step=5)
        if st.button("CALC_TRUE_PROB"):
            dec1 = american_to_decimal(fv_odds_1)
            dec2 = american_to_decimal(fv_odds_2)
            imp1 = (1/dec1)
            imp2 = (1/dec2)
            total_imp = imp1 + imp2 
            true_prob1 = (imp1 / total_imp) * 100
            st.metric("Side A True Win %", f"{true_prob1:.1f}%")

    st.markdown("---")
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
    
    csv_input = st.session_state.input_data.to_csv(index=False).encode('utf-8')
    st.download_button("💾 SAVE_INPUTS (CSV)", csv_input, "parlay_inputs.csv", "text/csv")
    csv_hist = st.session_state.bet_history.to_csv(index=False).encode('utf-8')
    st.download_button("💾 SAVE_HISTORY (CSV)", csv_hist, "bet_ledger.csv", "text/csv")

    uploaded_file = st.file_uploader("📂 LOAD_INPUTS", type=["csv"])
    if uploaded_file is not None:
        try:
            loaded_df = pd.read_csv(uploaded_file)
            if "Link Group" not in loaded_df.columns: loaded_df["Link Group"] = ""
            if "Excl Group" not in loaded_df.columns and "Group" in loaded_df.columns:
                loaded_df.rename(columns={"Group": "Excl Group"}, inplace=True)
            st.session_state.input_data = loaded_df
            st.success("DATABASE_RESTORED")
            st.rerun()
        except Exception as e: st.error(f"ERROR: {e}")

    uploaded_hist = st.file_uploader("📂 LOAD_HISTORY", type=["csv"])
    if uploaded_hist is not None:
        try:
            st.session_state.bet_history = pd.read_csv(uploaded_hist)
            st.success("LEDGER RESTORED")
            st.rerun()
        except: pass

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
    max_combos = st.number_input("MAX_ITERATIONS", min_value=1, max_value=1000000, value=5000, step=100)

# --- MAIN APP LAYOUT ---
st.title("> QUANT_PARLAY_ENGINE_V20")

# --- TABS SYSTEM ---
tab_build, tab_scenarios, tab_hedge, tab_analysis, tab_ledger = st.tabs([
    "🏗️ BUILDER", "🧪 SCENARIOS", "🛡️ HEDGE_CALC", "📊 ANALYSIS", "📜 LEDGER"
])

# ==========================================
# TAB 1: BUILDER
# ==========================================
with tab_build:
    with st.expander("➕ OPEN_PROP_BUILDER (Click to Add Custom Bets)"):
        st.markdown("`>> MANUAL_OVERRIDE_PROTOCOL`")
        c1, c2, c3, c4, c5 = st.columns([2, 1, 1, 1, 1])
        with c1: new_
