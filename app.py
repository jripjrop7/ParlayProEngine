import streamlit as st
import pandas as pd
import itertools
import numpy as np
import altair as alt
import requests

# --- PAGE CONFIG ---
st.set_page_config(
    page_title="QUANT_PARLAY_ENGINE_V3", 
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

def decimal_to_american(decimal):
    if decimal >= 2:
        return int((decimal - 1) * 100)
    elif decimal > 1:
        return int(-100 / (decimal - 1))
    return -100

def format_money(val):
    return f"${val:,.2f}"

def kelly_criterion(decimal_odds, win_prob_percent, fractional_kelly=0.25):
    if decimal_odds <= 1: return 0.0
    b = decimal_odds - 1
    p = win_prob_percent / 100
    q = 1 - p
    kelly_perc = (b * p - q) / b
    return max(0, kelly_perc * fractional_kelly)

# --- API LOGIC ---
def fetch_fanduel_odds(api_key, sport_key):
    # Fetch data from The Odds API
    url = f'https://api.the-odds-api.com/v4/sports/{sport_key}/odds'
    params = {
        'apiKey': api_key,
        'regions': 'us',
        'markets': 'h2h', # Head to head (Moneyline)
        'bookmakers': 'fanduel',
        'oddsFormat': 'american'
    }
    
    try:
        response = requests.get(url, params=params)
        response.raise_for_status()
        data = response.json()
        
        new_legs = []
        
        for game in data:
            # We use the Game ID as the "Group" so you can't bet both sides
            game_group_id = game['id'][-5:] 
            
            # Find FanDuel odds
            for bookmaker in game['bookmakers']:
                if bookmaker['key'] == 'fanduel':
                    for market in bookmaker['markets']:
                        if market['key'] == 'h2h':
                            for outcome in market['outcomes']:
                                leg_name = f"{outcome['name']} (ML)"
                                price = outcome['price']
                                
                                new_legs.append({
                                    "Group": game_group_id,
                                    "Leg Name": leg_name,
                                    "Odds": price,
                                    "Conf (1-10)": 5 # Default neutral confidence
                                })
        return new_legs
    except Exception as e:
        st.error(f"API Error: {e}")
        return []

# --- SIDEBAR ---
with st.sidebar:
    st.title("/// SYSTEM_CONTROLS")
    
    st.markdown("### > LIVE_DATA_FEED")
    api_key = st.text_input("API_KEY (The Odds API)", type="password")
    sport_select = st.selectbox("TARGET_MARKET", 
        ["americanfootball_nfl", "basketball_nba", "icehockey_nhl", "basketball_ncaab"]
    )
    
    if st.button("📡 PULL_FANDUEL_LINES"):
        if not api_key:
            st.error("MISSING_API_KEY")
        else:
            with st.spinner("FETCHING_LIVE_ODDS..."):
                fetched_data = fetch_fanduel_odds(api_key, sport_select)
                if fetched_data:
                    # Update session state with new data
                    st.session_state.input_data = pd.DataFrame(fetched_data)
                    st.success(f"SUCCESS: LOADED {len(fetched_data)} LINES")
                    st.rerun()

    st.markdown("---")
    st.markdown("### > BANKROLL")
    bankroll = st.number_input("TOTAL_BANKROLL ($)", 100.0, 1000000.0, 1000.0)
    kelly_fraction = st.slider("KELLY_FRACT", 0.1, 1.0, 0.25)
    
    st.markdown("### > PARLAY_SPECS")
    min_legs = st.number_input("MIN_LEGS", 2, 12, 3)
    max_legs = st.number_input("MAX_LEGS", 2, 15, 4)

    st.markdown("### > FILTERS")
    target_min_odds = st.number_input("MIN_ODDS (+)", 100, 100000, 100)
    target_max_odds = st.number_input("MAX_ODDS (+)", 100, 500000, 10000)
    min_ev_filter = st.checkbox("FILTER_NEG_EV", value=True)
    max_combos = st.select_slider("MAX_ITERATIONS", options=[1000, 5000, 10000], value=5000)

# --- MAIN APP ---
st.title("> QUANT_PARLAY_ENGINE_V3")

# Initialize Session State
if 'input_data' not in st.session_state:
    st.session_state.input_data = pd.DataFrame([
        {"Group": "", "Leg Name": "Manual Entry 1", "Odds": -110, "Conf (1-10)": 5},
    ])

# DATA EDITOR
st.subheader("1.0 // DATA_ENTRY")

edited_df = st.data_editor(
    st.session_state.input_data, 
    column_config={
        "Group": st.column_config.TextColumn("GRP_ID", width="small", help="Conflict Group"),
        "Leg Name": st.column_config.TextColumn("LEG_ID"),
        "Odds": st.column_config.NumberColumn("ODDS"),
        "Conf (1-10)": st.column_config.NumberColumn("CONF", min_value=1, max_value=10)
    },
    num_rows="dynamic", 
    use_container_width=True
)

if not edited_df.empty:
    df = edited_df.copy()
    df['Decimal'] = df['Odds'].apply(american_to_decimal)
    df['Est Win %'] = df['Conf (1-10)'] * 10 
else:
    st.stop()

# EXECUTION
st.write("") 
if st.button(">>> GENERATE_OPTIMIZED_HEDGE"):
    
    legs_list = df.to_dict('records')
    valid_parlays = []
    combo_count = 0
    stop_execution = False
    min_dec = american_to_decimal(target_min_odds)
    max_dec = american_to_decimal(target_max_odds)

    with st.spinner("PROCESSING_MATRIX..."):
        for r in range(min_legs, max_legs + 1):
            if stop_execution: break
            
            for combo in itertools.combinations(legs_list, r):
                # Conflict Check (Group ID)
                groups = [str(x['Group']) for x in combo if str(x['Group']).strip()]
                if len(groups) != len(set(groups)): continue 
                
                combo_count += 1
                if combo_count > max_combos:
                    stop_execution = True
                    break

                dec_total = np.prod([x['Decimal'] for x in combo])
                if not (min_dec <= dec_total <= max_dec): continue

                win_prob = np.prod([x['Est Win %']/100 for x in combo])
                kelly_pct = kelly_criterion(dec_total, win_prob * 100, kelly_fraction)
                wager = bankroll * kelly_pct
                
                if min_ev_filter and wager <= 0: continue
                
                payout = (dec_total * wager) - wager
                ev = (win_prob * payout) - ((1 - win_prob) * wager)

                valid_parlays.append({
                    "LEGS": [l['Leg Name'] for l in combo],
                    "ODDS": dec_total,
                    "PROB": win_prob * 100,
                    "WAGER": wager,
                    "PAYOUT": payout,
                    "EV": ev
                })

    # OUTPUT
    st.divider()
    if not valid_parlays:
        st.error("NO_VALID_STRATEGIES_FOUND")
    else:
        results = pd.DataFrame(valid_parlays)
        col1, col2 = st.columns([2, 1])
        
        with col1:
            st.markdown("`>> STRATEGY_TABLE`")
            sort_by = st.selectbox("SORT_BY", ["EV", "WAGER", "PAYOUT", "PROB"], label_visibility="collapsed")
            results = results.sort_values(by=sort_by, ascending=False)
            
            display = results.copy()
            display['LEGS'] = display['LEGS'].apply(lambda x: " + ".join(x))
            display['WAGER'] = display['WAGER'].apply(format_money)
            display['PAYOUT'] = display['PAYOUT'].apply(format_money)
            display['EV'] = display['EV'].apply(format_money)
            display['ODDS'] = display['ODDS'].apply(lambda x: f"{x:.2f}x")
            display['PROB'] = display['PROB'].apply(lambda x: f"{x:.1f}%")
            
            st.dataframe(display, use_container_width=True, hide_index=True)
            
        with col2:
            st.markdown("`>> EXPOSURE_MAP`")
            flat_legs = [leg for sub in results['LEGS'] for leg in sub]
            counts = pd.Series(flat_legs).value_counts().reset_index()
            counts.columns = ['LEG', 'COUNT']
            
            c = alt.Chart(counts).mark_bar(color='#00ff41').encode(
                x='COUNT', y=alt.Y('LEG', sort='-x')
            ).configure_view(strokeWidth=0).properties(background='transparent')
            st.altair_chart(c, use_container_width=True)
            
            st.metric("TOTAL_RISK", format_money(results['WAGER'].sum()))
            st.metric("TOTAL_EXP_VALUE", format_money(results['EV'].sum()))
    section[data-testid="stSidebar"] { background-color: #111; border-right: 1px solid #333; }
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
    """
    Calculates % of bankroll to wager.
    Uses Quarter Kelly (0.25) by default for safety.
    """
    if decimal_odds <= 1: return 0.0
    b = decimal_odds - 1
    p = win_prob_percent / 100
    q = 1 - p
    
    kelly_perc = (b * p - q) / b
    return max(0, kelly_perc * fractional_kelly)

# --- SIDEBAR: CONTROLS ---
with st.sidebar:
    st.title("/// SYSTEM_CONTROLS")
    
    st.markdown("### > BANKROLL_MGMT")
    bankroll = st.number_input("TOTAL_BANKROLL ($)", 100.0, 1000000.0, 1000.0)
    kelly_fraction = st.slider("KELLY_AGGRESSION", 0.1, 1.0, 0.25, help="1.0 = Full Kelly (High Risk), 0.25 = Quarter Kelly (Safe)")
    
    st.markdown("---")
    st.markdown("### > STRUCTURE")
    min_legs = st.number_input("MIN_LEGS", 2, 12, 3)
    max_legs = st.number_input("MAX_LEGS", 2, 15, 4)

    st.markdown("---")
    st.markdown("### > FILTERS")
    target_min_odds = st.number_input("MIN_ODDS (+)", 100, 100000, 100)
    target_max_odds = st.number_input("MAX_ODDS (+)", 100, 500000, 10000)
    min_ev_filter = st.checkbox("FILTER_NEGATIVE_EV", value=True)
    
    st.markdown("---")
    max_combos = st.select_slider("MAX_ITERATIONS", options=[1000, 5000, 10000, 50000], value=5000)

# --- MAIN INTERFACE ---
st.title("> PARLAY_OPTIMIZER_V2.0")
st.markdown("`STATUS: ONLINE` | `MODULES: KELLY_CRITERION, CONFLICT_DETECTION`")

# --- STEP 1: INPUT ---
st.subheader("1.0 // DATA_ENTRY")

# Initialize Session State for Data if not exists
if 'input_data' not in st.session_state:
    st.session_state.input_data = pd.DataFrame([
        {"Group": "", "Leg Name": "KC Chiefs -3", "Odds": -200, "Conf (1-10)": 9},
        {"Group": "", "Leg Name": "KC Chiefs -7", "Odds": +100, "Conf (1-10)": 7},
        {"Group": "", "Leg Name": "LAL Lakers ML", "Odds": -110, "Conf (1-10)": 6},
        {"Group": "", "Leg Name": "LAL Lakers -5", "Odds": +150, "Conf (1-10)": 5},
        {"Group": "C", "Leg Name": "Over 220.5", "Odds": -110, "Conf (1-10)": 5},
        {"Group": "C", "Leg Name": "Under 220.5", "Odds": -110, "Conf (1-10)": 5},
    ])

# AUTO CONFLICT BUTTON
col_tools1, col_tools2 = st.columns([1, 4])
with col_tools1:
    if st.button("🪄 AUTO_DETECT_CONFLICTS"):
        # Logic: Extract first word of Leg Name. If matches, assign same Group ID.
        df_logic = st.session_state.input_data.copy()
        for i in range(len(df_logic)):
            # Get first word (e.g. "KC" or "Lakers")
            name_curr = str(df_logic.at[i, "Leg Name"]).strip()
            first_word = name_curr.split(' ')[0] if ' ' in name_curr else name_curr
            
            # If Group is empty, assign the first word as Group ID
            if not df_logic.at[i, "Group"]:
                df_logic.at[i, "Group"] = first_word.upper()
        
        st.session_state.input_data = df_logic
        st.rerun()

column_config = {
    "Group": st.column_config.TextColumn("GRP_ID", help="Conflict Group", width="small"),
    "Leg Name": st.column_config.TextColumn("LEG_ID"),
    "Odds": st.column_config.NumberColumn("AMER_ODDS"),
    "Conf (1-10)": st.column_config.NumberColumn("CONF_LVL", min_value=1, max_value=10)
}

edited_df = st.data_editor(
    st.session_state.input_data, 
    column_config=column_config,
    num_rows="dynamic", 
    use_container_width=True,
    key="data_editor"
)

# Sync edits back to session state
st.session_state.input_data = edited_df

# Logic Processing
if not edited_df.empty:
    df = edited_df.copy()
    df['Decimal'] = df['Odds'].apply(american_to_decimal)
    df['Est Win %'] = df['Conf (1-10)'] * 10 
else:
    st.stop()

# --- STEP 2: EXECUTION ---
st.write("") 
if st.button(">>> INITIALIZE_GENERATION_SEQUENCE"):
    
    legs_list = df.to_dict('records')
    valid_parlays = []
    combo_count = 0
    stop_execution = False

    min_dec_target = american_to_decimal(target_min_odds)
    max_dec_target = american_to_decimal(target_max_odds)

    with st.spinner("CALCULATING_OPTIMAL_PATH..."):
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
                    st.warning(f"LIMIT_REACHED: Displaying first {max_combos} results.")
                    break

                decimal_total = np.prod([leg['Decimal'] for leg in combo])
                
                # Odds Filter
                if not (min_dec_target <= decimal_total <= max_dec_target):
                    continue

                avg_conf = np.mean([leg['Conf (1-10)'] for leg in combo])
                est_win_prob = np.prod([leg['Est Win %']/100 for leg in combo])
                
                # --- KELLY CALCULATION ---
                # We calculate Kelly % based on total odds and total probability
                kelly_pct = kelly_criterion(decimal_total, est_win_prob * 100, kelly_fraction)
                rec_wager = bankroll * kelly_pct
                
                # If Kelly suggests $0 (negative edge), and filter is on, skip it
                if min_ev_filter and rec_wager <= 0:
                    continue
                
                # Fallback: If Kelly is 0 but user wants to see it, show $0.00
                payout = (decimal_total * rec_wager) - rec_wager
                ev = (est_win_prob * payout) - ((1 - est_win_prob) * rec_wager)

                valid_parlays.append({
                    "LEGS": [l['Leg Name'] for l in combo], 
                    "ODDS": decimal_total,
                    "WIN_%": est_win_prob * 100,
                    "KELLY_BET": rec_wager,
                    "PAYOUT": payout,
                    "EV": ev
                })

    # --- STEP 3: OUTPUT ---
    st.divider()
    st.subheader("2.0 // STRATEGY_OUTPUT")
    
    results_df = pd.DataFrame(valid_parlays)

    if results_df.empty:
        st.error("NO_OPPORTUNITIES_FOUND: Try adjusting filters or increasing confidence.")
    else:
        col1, col2 = st.columns([2, 1])
        
        with col1:
            st.markdown("`>> SORTING_PROTOCOL`")
            sort_col = st.selectbox("", ["EV", "KELLY_BET", "PAYOUT", "WIN_%"], label_visibility="collapsed")
            
            results_df = results_df.sort_values(by=sort_col, ascending=False)
            
            # Format for display
            display_df = results_df.copy()
            display_df['LEGS'] = display_df['LEGS'].apply(lambda x: " + ".join(x))
            display_df['KELLY_BET'] = display_df['KELLY_BET'].apply(format_money)
            display_df['PAYOUT'] = display_df['PAYOUT'].apply(format_money)
            display_df['EV'] = display_df['EV'].apply(format_money)
            display_df['ODDS'] = display_df['ODDS'].apply(lambda x: f"{x:.2f}x")
            display_df['WIN_%'] = display_df['WIN_%'].apply(lambda x: f"{x:.1f}%")
            
            st.dataframe(
                display_df[['LEGS', 'ODDS', 'WIN_%', 'KELLY_BET', 'PAYOUT', 'EV']], 
                use_container_width=True, 
                hide_index=True
            )

        with col2:
            st.markdown("`>> EXPOSURE_ANALYSIS`")
            
            all_legs = [leg for sublist in results_df['LEGS'] for leg in sublist]
            counts = pd.Series(all_legs).value_counts().reset_index()
            counts.columns = ['LEG_ID', 'FREQ']
            
            c = alt.Chart(counts).mark_bar(color='#00ff41').encode(
                x='FREQ', 
                y=alt.Y('LEG_ID', sort='-x'),
                tooltip=['LEG_ID', 'FREQ']
            ).configure_axis(
                labelColor='#e0e0e0',
                titleColor='#00ff41'
            ).configure_view(strokeWidth=0).properties(background='transparent')
            
            st.altair_chart(c, use_container_width=True)
            
            total_wagered = results_df['KELLY_BET'].sum()
            st.metric("TOTAL_CAPITAL_AT_RISK", format_money(total_wagered))
            st.metric("PORTFOLIO_EV", format_money(results_df['EV'].sum()))
