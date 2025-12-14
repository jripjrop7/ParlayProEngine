import streamlit as st
import pandas as pd
import itertools
import numpy as np
import altair as alt
import requests
import random

# --- PAGE CONFIG ---
st.set_page_config(
    page_title="QUANT_PARLAY_ENGINE_V10.1", 
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
                                    "Group": game_group_id,
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
        {"Active": True, "Group": "", "Leg Name": "Manual Entry 1", "Odds": -110, "Conf (1-10)": 5},
    ])
    
if 'generated_parlays' not in st.session_state:
    st.session_state.generated_parlays = []

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
            required_cols = ["Active", "Group", "Leg Name", "Odds", "Conf (1-10)"]
            if all(col in loaded_df.columns for col in required_cols):
                st.session_state.input_data = loaded_df
                st.success("DATABASE_RESTORED")
                st.rerun()
            else:
                st.error("ERROR: INVALID_CSV_FORMAT")
        except Exception as e:
            st.error(f"ERROR: {e}")

    st.markdown("---")
    if st.button("🗑️ CLEAR_ALL_DATA"):
        st.session_state.input_data = pd.DataFrame(columns=["Active", "Group", "Leg Name", "Odds", "Conf (1-10)"])
        st.session_state.generated_parlays = []
        st.rerun()

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
st.title("> QUANT_PARLAY_ENGINE_V10.1")

# --- PROP BUILDER ---
st.subheader("1.0 // DATA_ENTRY")

with st.expander("➕ OPEN_PROP_BUILDER (Click to Add Custom Bets)"):
    st.markdown("`>> MANUAL_OVERRIDE_PROTOCOL`")
    c1, c2, c3, c4 = st.columns([3, 1, 1, 1])
    
    with c1:
        new_prop_name = st.text_input("PROP_NAME", placeholder="e.g. LeBron Over 25.5 Pts")
    with c2:
        new_prop_group = st.text_input("GROUP_ID", placeholder="Optional (Conflict)")
    with c3:
        new_prop_odds = st.number_input("ODDS (AMER)", value=-110, step=10)
    with c4:
        new_prop_conf = st.slider("CONFIDENCE", 1, 10, 5)

    # --- ALPHA HUNTER VISUALIZER (NEW) ---
if not st.session_state.input_data.empty:
    with st.expander("📈 MARKET_ANALYSIS (Alpha Hunter)"):
        # Prepare data for plotting
        plot_data = st.session_state.input_data.copy()
        plot_data['Active'] = plot_data['Active'].astype(bool)
        plot_data = plot_data[plot_data['Active'] == True]
        
        if not plot_data.empty:
            # Calculate metrics
            plot_data['Decimal'] = plot_data['Odds'].apply(american_to_decimal)
            plot_data['Implied_Prob'] = (1 / plot_data['Decimal']) * 100
            plot_data['My_Prob'] = plot_data['Conf (1-10)'] * 10
            plot_data['Edge'] = plot_data['My_Prob'] - plot_data['Implied_Prob']
            plot_data['Color'] = plot_data['Edge'].apply(lambda x: '#00ff41' if x > 0 else '#ff4b4b')
            
            # The Chart
            c = alt.Chart(plot_data).mark_circle(size=100).encode(
                x=alt.X('Implied_Prob', title='Bookmaker Implied Probability (%)', scale=alt.Scale(domain=[0, 100])),
                y=alt.Y('My_Prob', title='My Confidence (%)', scale=alt.Scale(domain=[0, 100])),
                color=alt.Color('Color', scale=None),
                tooltip=['Leg Name', 'Odds', 'Edge']
            ).properties(
                title="Your Edge vs. The Bookie",
                height=300,
                background='transparent'
            )
            
            # The Break-Even Line (x=y)
            line = alt.Chart(pd.DataFrame({'x': [0, 100], 'y': [0, 100]})).mark_line(
                color='#666', strokeDash=[5, 5]
            ).encode(x='x', y='y')
            
            st.altair_chart((c + line).interactive(), use_container_width=True)
            st.caption("DOTS ABOVE DOTTED LINE = +EV (Good Bets). DOTS BELOW = -EV (Bad Bets).")

    if st.button("ADD_PROP_TO_TABLE"):
        if new_prop_name:
            new_row = {
                "Active": True,
                "Group": new_prop_group, 
                "Leg Name": new_prop_name, 
                "Odds": new_prop_odds, 
                "Conf (1-10)": new_prop_conf
            }
            st.session_state.input_data = pd.concat([
                st.session_state.input_data, 
                pd.DataFrame([new_row])
            ], ignore_index=True)
            st.success(f"ADDED: {new_prop_name}")
            st.rerun()
        else:
            st.warning("ERROR: NAME_REQUIRED")

# --- CLONE TOOL ---
col_clone, col_spacer = st.columns([1, 4])
with col_clone:
    if st.button("👯 CLONE_SELECTED_ROWS"):
        df = st.session_state.input_data.copy()
        rows_to_clone = df[df['Active'] == True]
        if not rows_to_clone.empty:
            st.session_state.input_data = pd.concat([df, rows_to_clone], ignore_index=True)
            st.success(f"CLONED {len(rows_to_clone)} ROWS")
            st.rerun()
        else:
            st.warning("NO_SELECTION")

# --- MAIN TABLE ---
edited_df = st.data_editor(
    st.session_state.input_data, 
    column_config={
        "Active": st.column_config.CheckboxColumn("USE?", help="Check to include (or Clone)", width="small"),
        "Group": st.column_config.TextColumn("GRP_ID", width="small", help="Conflict Group"),
        "Leg Name": st.column_config.TextColumn("LEG_ID"),
        "Odds": st.column_config.NumberColumn("ODDS"),
        "Conf (1-10)": st.column_config.NumberColumn("CONF", min_value=1, max_value=10)
    },
    num_rows="dynamic", 
    use_container_width=True,
    key="editor_widget" 
)

st.session_state.input_data = edited_df

if not edited_df.empty:
    df = edited_df.copy()
    active_df = df[df["Active"] == True].copy()
    
    # --- CALCULATION LOGIC RESTORED ---
    active_df['Decimal'] = active_df['Odds'].apply(american_to_decimal)
    active_df['Est Win %'] = active_df['Conf (1-10)'] * 10 
    # ----------------------------------
else:
    st.info("TABLE_EMPTY")
    st.stop()

# --- EXECUTION BUTTON ---
st.write("") 
if st.button(">>> GENERATE_OPTIMIZED_HEDGE"):
    
    if active_df.empty:
        st.error("NO_ACTIVE_LEGS: Please select at least one leg.")
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
                        "EV": ev,
                        "RAW_LEGS_DATA": combo 
                    })
        
        st.session_state.generated_parlays = valid_parlays
        st.rerun()

# --- DISPLAY LOGIC ---
if len(st.session_state.generated_parlays) > 0:
    st.divider()
    results = pd.DataFrame(st.session_state.generated_parlays)
    
    col1, col2 = st.columns([2, 1])
    with col1:
        st.markdown("`>> STRATEGY_TABLE`")
        sort_by = st.selectbox("SORT_BY", ["EV", "WAGER", "PAYOUT", "PROB"], label_visibility="collapsed")
        results_sorted = results.sort_values(by=sort_by, ascending=False)
        
        display = results_sorted.copy()
        display['LEGS'] = display['LEGS'].apply(lambda x: " + ".join(x))
        display['WAGER'] = display['WAGER'].apply(format_money)
        display['PAYOUT'] = display['PAYOUT'].apply(format_money)
        display['EV'] = display['EV'].apply(format_money)
        display['ODDS'] = display['ODDS'].apply(lambda x: f"{x:.2f}x")
        display['PROB'] = display['PROB'].apply(lambda x: f"{x:.1f}%")
        
        st.dataframe(display.drop(columns=['RAW_LEGS_DATA']), use_container_width=True, hide_index=True)

    with col2:
        st.metric("TOTAL_RISK", format_money(results['WAGER'].sum()))
        st.metric("TOTAL_EXP_VALUE", format_money(results['EV'].sum()))
        
        st.divider()
        st.subheader("3.0 // RISK_SIM")
        
        if st.button("🔮 RUN_1000_SIMULATIONS"):
            parlays = st.session_state.generated_parlays
            sim_profits = []
            
            unique_legs = {}
            for p in parlays:
                for leg in p['RAW_LEGS_DATA']:
                    unique_legs[leg['Leg Name']] = leg['Est Win %'] / 100.0

            with st.spinner("SIMULATING..."):
                for _ in range(1000):
                    leg_outcomes = {name: random.random() < prob for name, prob in unique_legs.items()}
                    run_profit = 0
                    for p in parlays:
                        wager = p['WAGER']
                        all_hit = all(leg_outcomes[leg['Leg Name']] for leg in p['RAW_LEGS_DATA'])
                        if all_hit: run_profit += p['PAYOUT']
                        else: run_profit -= wager
                    sim_profits.append(run_profit)

            c1, c2, c3 = st.columns(3)
            c1.metric("WORST", format_money(min(sim_profits)))
            c2.metric("AVG", format_money(np.mean(sim_profits)))
            c3.metric("BEST", format_money(max(sim_profits)))
            
            sim_df = pd.DataFrame(sim_profits, columns=['Profit'])
            chart = alt.Chart(sim_df).mark_bar(color='#00ff41').encode(
                alt.X("Profit", bin=alt.Bin(maxbins=30)), y='count()'
            ).properties(background='transparent').configure_axis(
                labelColor='#e0e0e0', titleColor='#00ff41'
            )
            st.altair_chart(chart, use_container_width=True)
            
            profitable = len([x for x in sim_profits if x > 0])
            st.caption(f"WIN_PROB: {(profitable/1000)*100:.1f}%")
