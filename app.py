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
    page_title="QUANT_PARLAY_ENGINE_V25", 
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

# --- CALLBACKS (The Safe Way) ---
def update_main_data():
    if st.session_state.get("editor_widget") is not None:
        st.session_state.input_data = st.session_state["editor_widget"]

def update_portfolio_data():
    if st.session_state.get("portfolio_editor") is not None:
        edited_df = st.session_state["portfolio_editor"]
        for index, row in edited_df.iterrows():
            if index < len(st.session_state.generated_parlays):
                st.session_state.generated_parlays[index]['BET?'] = row['BET?']
                new_wager = row['MY_WAGER']
                st.session_state.generated_parlays[index]['MY_WAGER'] = new_wager
                
                # Recalc Logic
                dec_odds = st.session_state.generated_parlays[index]['ODDS']
                prob = st.session_state.generated_parlays[index]['PROB'] / 100
                new_payout = (dec_odds * new_wager) - new_wager
                new_ev = (prob * new_payout) - ((1 - prob) * new_wager)
                
                st.session_state.generated_parlays[index]['PAYOUT'] = new_payout
                st.session_state.generated_parlays[index]['EV'] = new_ev

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
    st.session_state.bet_history = pd.DataFrame(columns=["Date", "Legs", "Odds", "Wager", "Payout", "Result", "Profit"])

# --- SIDEBAR ---
with st.sidebar:
    st.title("/// SYSTEM_CONTROLS")
    
    with st.expander("⚖️ FAIR_VALUE_CALC"):
        fv_odds_1 = st.number_input("Side A Odds", value=-110, step=5)
        fv_odds_2 = st.number_input("Side B Odds", value=-110, step=5)
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
    api_key = st.text_input("API_KEY", type="password")
    sport_select = st.selectbox("MARKET", ["americanfootball_nfl", "basketball_nba", "icehockey_nhl", "basketball_ncaab"])
    
    if st.button("📡 PULL_FANDUEL_LINES"):
        if not api_key:
            st.error("MISSING_API_KEY")
        else:
            with st.spinner("FETCHING..."):
                fetched = fetch_fanduel_odds(api_key, sport_select)
                if fetched:
                    st.session_state.input_data = pd.concat([st.session_state.input_data, pd.DataFrame(fetched)], ignore_index=True)
                    st.session_state.input_data.drop_duplicates(subset=['Leg Name'], keep='last', inplace=True)
                    st.success(f"ADDED {len(fetched)} LINES")
                    st.rerun()

    st.markdown("---")
    st.markdown("### > DATA_PERSISTENCE")
    
    # Save Buttons
    if isinstance(st.session_state.input_data, pd.DataFrame):
        csv_input = st.session_state.input_data.to_csv(index=False).encode('utf-8')
        st.download_button("💾 SAVE_INPUTS", csv_input, "parlay_inputs.csv", "text/csv")
    
    if isinstance(st.session_state.bet_history, pd.DataFrame):
        csv_hist = st.session_state.bet_history.to_csv(index=False).encode('utf-8')
        st.download_button("💾 SAVE_HISTORY", csv_hist, "bet_ledger.csv", "text/csv")

    # Load Inputs
    uploaded_file = st.file_uploader("📂 LOAD_INPUTS", type=["csv"])
    if uploaded_file is not None:
        try:
            loaded_df = pd.read_csv(uploaded
