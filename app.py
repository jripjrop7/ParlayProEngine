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
    page_title="QUANT_PARLAY_ENGINE_V19", 
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
    
if 'bet_history' not in st.session_state:
    # Structure for the Ledger
    st.session_state.bet_history = pd.DataFrame(columns=[
        "Date", "Legs", "Odds", "Wager", "Payout", "Result", "Profit"
    ])

# --- SIDEBAR ---
with st.sidebar:
    st.title("/// SYSTEM_CONTROLS")
    
    # --- FAIR VALUE CALCULATOR (NEW) ---
    with st.expander("⚖️ FAIR_VALUE_CALC (Vig Remover)"):
        fv_odds_1 = st.number_input("Side A Odds (e.g. -110)", value=-110, step=5)
        fv_odds_2 = st.number_input("Side B Odds (e.g. -110)", value=-110, step=5)
        if st.button("CALC_TRUE_PROB"):
            dec1 = american_to_decimal(fv_odds_1)
            dec2 = american_to_decimal(fv_odds_2)
            imp1 = (1/dec1)
            imp2 = (1/dec2)
            total_imp = imp1 + imp2 # Will be > 100% due to vig
            true_prob1 = (imp1 / total_imp) * 100
            st.metric("Side A True Win %", f"{true_prob1:.1f}%")
            st.caption(f"Use this % for Confidence.")

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
    
    # SAVE/LOAD INPUTS
    csv_input = st.session_state.input_data.to_csv(index=False).encode('utf-8')
    st.download_button("💾 SAVE_INPUTS (CSV)", csv_input, "parlay_inputs.csv", "text/csv")
    
    # SAVE/LOAD HISTORY
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

    # NEW: Load History
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
st.title("> QUANT_PARLAY_ENGINE_V19")

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
        with c1: new_prop_name = st.text_input("PROP_NAME", placeholder="e.g. LeBron Over 25.5 Pts")
        with c2: new_excl_group = st.text_input("⛔ EXCL_ID", placeholder="Conflict ID")
        with c3: new_link_group = st.text_input("🔗 LINK_ID", placeholder="Correlation ID")
        with c4: new_prop_odds = st.number_input("ODDS (AMER)", value=-110, step=10)
        with c5: new_prop_conf = st.slider("CONFIDENCE", 1, 10, 5)
        if st.button("ADD_PROP_TO_TABLE"):
            if new_prop_name:
                new_row = {"Active": True, "Excl Group": new_excl_group, "Link Group": new_link_group,
                    "Leg Name": new_prop_name, "Odds": new_prop_odds, "Conf (1-10)": new_prop_conf}
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
        if active_df.empty: st.error("NO_ACTIVE_LEGS")
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
                            "BET?": False,
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

    # --- RESULTS ---
    if len(st.session_state.generated_parlays) > 0:
        st.divider()
        st.markdown("### 📋 GENERATED_PORTFOLIO")
        results_df = pd.DataFrame(st.session_state.generated_parlays)
        display_df = results_df.copy()
        display_df['LEGS'] = display_df['LEGS'].apply(lambda x: " + ".join(x))
        
        portfolio_edits = st.data_editor(
            display_df,
            column_config={
                "BET?": st.column_config.CheckboxColumn("PLACED?", help="Check to mark as placed"),
                "LEGS": st.column_config.TextColumn("PARLAY LEGS", width="large"),
                "WAGER": st.column_config.NumberColumn("KELLY ($)", format="$%.2f"),
                "PAYOUT": st.column_config.NumberColumn("PAYOUT ($)", format="$%.2f"),
                "EV": st.column_config.NumberColumn("EV ($)", format="$%.2f"),
                "ODDS": st.column_config.NumberColumn("DEC ODDS", format="%.2f"),
                "PROB": st.column_config.NumberColumn("WIN %", format="%.1f%%"),
                "RAW_LEGS_DATA": None 
            },
            hide_index=True, use_container_width=True, key="portfolio_editor"
        )
        for index, row in portfolio_edits.iterrows(): st.session_state.generated_parlays[index]['BET?'] = row['BET?']

        # COMMIT TO LEDGER BUTTON
        st.write("")
        col_commit, col_space = st.columns([1, 4])
        with col_commit:
            if st.button("💾 COMMIT_PLACED_TO_LEDGER"):
                placed_bets = [p for p in st.session_state.generated_parlays if p['BET?']]
                if placed_bets:
                    new_history_rows = []
                    today_str = datetime.now().strftime("%Y-%m-%d")
                    for p in placed_bets:
                        new_history_rows.append({
                            "Date": today_str,
                            "Legs": " + ".join(p['LEGS']),
                            "Odds": round(p['ODDS'], 2),
                            "Wager": round(p['WAGER'], 2),
                            "Payout": round(p['PAYOUT'], 2),
                            "Result": "Pending", # Default status
                            "Profit": 0.0
                        })
                    
                    st.session_state.bet_history = pd.concat([st.session_state.bet_history, pd.DataFrame(new_history_rows)], ignore_index=True)
                    st.success(f"COMMITTED {len(placed_bets)} BETS TO LEDGER")
                else:
                    st.warning("NO 'PLACED?' BETS SELECTED")

        # COPY TOOLS
        st.divider()
        st.subheader("📋 COPY_TO_SPORTSBOOK (Placed Only)")
        active_portfolio = [p for p in st.session_state.generated_parlays if p['BET?']]
        if not active_portfolio: st.info("Check 'PLACED?' to view tickets.")
        else:
            for i, p in enumerate(active_portfolio):
                leg_str = " + ".join(p['LEGS'])
                copy_str = f"{leg_str}\n(Odds: {p['ODDS']:.2f}) | Wager: {format_money(p['WAGER'])}"
                c1, c2 = st.columns([5, 1])
                with c1: st.code(copy_str, language="text")
                with c2: st.caption(f"Ticket #{i+1}")

        total_risk = sum(p['WAGER'] for p in active_portfolio)
        total_ev = sum(p['EV'] for p in active_portfolio)
        st.divider()
        c1, c2 = st.columns(2)
        c1.metric("TOTAL_RISK (Placed Only)", format_money(total_risk))
        c2.metric("TOTAL_EV (Placed Only)", format_money(total_ev))

# ==========================================
# TAB 2: SCENARIOS
# ==========================================
with tab_scenarios:
    st.header("🧪 SCENARIO_STRESS_TESTER")
    active_parlays = [p for p in st.session_state.generated_parlays if p.get('BET?', False)]
    if len(active_parlays) == 0: st.warning("NO ACTIVE BETS SELECTED.")
    else:
        unique_legs_set = set()
        for p in active_parlays:
            for leg in p['RAW_LEGS_DATA']: unique_legs_set.add(leg['Leg Name'])
        unique_legs_list = sorted(list(unique_legs_set))
        st.markdown("#### SET OUTCOMES:")
        col_list = st.columns(3)
        scenario_state = {}
        for i, leg in enumerate(unique_legs_list):
            with col_list[i % 3]:
                status = st.radio(f"{leg}", ["Pending", "WIN ✅", "LOSS ❌"], index=0, key=f"scen_{i}", horizontal=True)
                scenario_state[leg] = status

        if st.button("RUN_SCENARIO_ANALYSIS"):
            simulated_pnl = 0
            tickets_won = 0
            tickets_lost = 0
            tickets_pending = 0
            for p in active_parlays:
                wager = p['WAGER']
                payout = p['PAYOUT']
                ticket_status = "WIN"
                for leg in p['RAW_LEGS_DATA']:
                    s = scenario_state[leg['Leg Name']]
                    if s == "LOSS ❌": ticket_status = "LOSS"; break
                    elif s == "Pending": ticket_status = "PENDING"
                if ticket_status == "WIN": simulated_pnl += payout; tickets_won += 1
                elif ticket_status == "LOSS": simulated_pnl -= wager; tickets_lost += 1
                else: tickets_pending += 1
            st.divider()
            c_s1, c_s2, c_s3 = st.columns(3)
            c_s1.metric("PROJECTED_P&L", format_money(simulated_pnl), delta="Profit" if simulated_pnl > 0 else "Loss")
            c_s2.metric("TICKETS_WON/LOST", f"{tickets_won} / {tickets_lost}")
            c_s3.metric("TICKETS_STILL_ALIVE", f"{tickets_pending}")

# ==========================================
# TAB 3: HEDGE CALC
# ==========================================
with tab_hedge:
    st.header("🛡️ EXIT_STRATEGY")
    col_h1, col_h2 = st.columns(2)
    with col_h1:
        current_payout = st.number_input("Potential Payout ($)", value=1000.0)
        current_wager = st.number_input("Original Cost ($)", value=50.0)
    with col_h2:
        hedge_odds = st.number_input("Opponent Odds (ML)", value=150)
        hedge_decimal = american_to_decimal(hedge_odds)
        st.metric("Decimal Odds", f"{hedge_decimal:.2f}")
    st.divider()
    optimal_hedge = current_payout / hedge_decimal
    guaranteed_profit = current_payout - optimal_hedge - current_wager
    if st.button("CALC_HEDGE"):
        c1, c2 = st.columns(2)
        c1.metric("BET_ON_OPPONENT", format_money(optimal_hedge))
        c2.metric("LOCKED_PROFIT", format_money(guaranteed_profit), delta="Risk Free")

# ==========================================
# TAB 4: ANALYSIS
# ==========================================
with tab_analysis:
    st.header("📊 MARKET_INTELLIGENCE")
    if not st.session_state.input_data.empty:
        with st.expander("📈 INPUT_ANALYSIS (Alpha Hunter)"):
            plot_data = st.session_state.input_data.copy()
            plot_data = plot_data[plot_data['Active'] == True]
            if not plot_data.empty:
                plot_data['Decimal'] = plot_data['Odds'].apply(american_to_decimal)
                plot_data['Implied_Prob'] = (1 / plot_data['Decimal']) * 100
                plot_data['My_Prob'] = plot_data['Conf (1-10)'] * 10
                plot_data['Edge'] = plot_data['My_Prob'] - plot_data['Implied_Prob']
                plot_data['Color'] = plot_data['Edge'].apply(lambda x: '#00ff41' if x > 0 else '#ff4b4b')
                c = alt.Chart(plot_data).mark_circle(size=100).encode(
                    x=alt.X('Implied_Prob', title='Implied Prob (%)'), y=alt.Y('My_Prob', title='My Conf (%)'),
                    color=alt.Color('Color', scale=None), tooltip=['Leg Name', 'Odds', 'Edge']
                )
                line = alt.Chart(pd.DataFrame({'x': [0, 100], 'y': [0, 100]})).mark_line(color='#666', strokeDash=[5, 5]).encode(x='x', y='y')
                st.altair_chart((c + line).interactive(), use_container_width=True)

    active_parlays = [p for p in st.session_state.generated_parlays if p.get('BET?', False)]
    if len(active_parlays) > 0:
        st.divider()
        st.subheader(f"🔮 MONTE_CARLO (Simulating {len(active_parlays)} Active Tickets)")
        if st.button("RUN_SIM (1000 Runs)"):
            sim_profits = []
            unique_legs = {}
            for p in active_parlays:
                for leg in p['RAW_LEGS_DATA']: unique_legs[leg['Leg Name']] = leg['Est Win %'] / 100.0
            for _ in range(1000):
                leg_outcomes = {name: random.random() < prob for name, prob in unique_legs.items()}
                run_profit = 0
                for p in active_parlays:
                    if all(leg_outcomes[leg['Leg Name']] for leg in p['RAW_LEGS_DATA']): run_profit += p['PAYOUT']
                    else: run_profit -= p['WAGER']
                sim_profits.append(run_profit)
            sim_df = pd.DataFrame(sim_profits, columns=['Profit'])
            chart = alt.Chart(sim_df).mark_bar(color='#00ff41').encode(
                alt.X("Profit", bin=alt.Bin(maxbins=30)), y='count()'
            ).properties(background='transparent').configure_axis(labelColor='#e0e0e0', titleColor='#00ff41')
            st.altair_chart(chart, use_container_width=True)
            st.metric("AVG_PROFIT", format_money(np.mean(sim_profits)))

# ==========================================
# TAB 5: LEDGER (NEW)
# ==========================================
with tab_ledger:
    st.header("📜 BET_TRACKING_LEDGER")
    
    if st.session_state.bet_history.empty:
        st.info("No bets in history yet. Go to Builder and click 'COMMIT_PLACED_TO_LEDGER'.")
    else:
        # Display Editable History
        st.caption("Mark your bets as 'Won' or 'Lost' to update P&L.")
        
        history_editor = st.data_editor(
            st.session_state.bet_history,
            column_config={
                "Date": st.column_config.TextColumn("Date", disabled=True),
                "Legs": st.column_config.TextColumn("Ticket Legs", disabled=True, width="large"),
                "Odds": st.column_config.NumberColumn("Odds", disabled=True),
                "Wager": st.column_config.NumberColumn("Wager", format="$%.2f", disabled=True),
                "Payout": st.column_config.NumberColumn("Pot. Payout", format="$%.2f", disabled=True),
                "Result": st.column_config.SelectboxColumn("Status", options=["Pending", "Won", "Lost"], required=True),
                "Profit": st.column_config.NumberColumn("P&L", format="$%.2f", disabled=True)
            },
            hide_index=True,
            use_container_width=True,
            num_rows="dynamic" # Allow deletion
        )
        
        # Calculate Logic
        updated_history = history_editor.copy()
        
        # Auto-Calc Profit based on Status
        for i, row in updated_history.iterrows():
            if row['Result'] == 'Won':
                updated_history.at[i, 'Profit'] = row['Payout'] # Profit is net payout usually, but here displayed as full return? 
                # Actually Payout usually includes stake. Let's assume Payout = Total Return.
                # Profit = Payout - Wager
                updated_history.at[i, 'Profit'] = row['Payout'] # Net logic below
            elif row['Result'] == 'Lost':
                updated_history.at[i, 'Profit'] = -row['Wager']
            else:
                updated_history.at[i, 'Profit'] = 0.0

        st.session_state.bet_history = updated_history
        
        # SUMMARY METRICS
        total_wagered = updated_history['Wager'].sum()
        total_profit = updated_history['Profit'].sum()
        roi = (total_profit / total_wagered * 100) if total_wagered > 0 else 0.0
        
        st.divider()
        m1, m2, m3 = st.columns(3)
        m1.metric("TOTAL_VOLUME", format_money(total_wagered))
        m2.metric("NET_PROFIT", format_money(total_profit), delta_color="normal")
        m3.metric("ROI %", f"{roi:.2f}%", delta=f"{roi:.2f}%")
        
        # P&L CHART
        if not updated_history.empty:
            st.subheader("Performance Chart")
            # Create a running total
            chart_data = updated_history.copy()
            chart_data['Cumulative'] = chart_data['Profit'].cumsum()
            chart_data['Index'] = range(1, len(chart_data) + 1)
            
            chart = alt.Chart(chart_data).mark_line(point=True, color='#00ff41').encode(
                x=alt.X('Index', title='Bet Count'),
                y=alt.Y('Cumulative', title='Total Profit ($)')
            ).properties(background='transparent').configure_axis(labelColor='#e0e0e0', titleColor='#00ff41')
            st.altair_chart(chart, use_container_width=True)
