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
    page_title="QUANT_PARLAY_ENGINE_V23", 
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

# --- CALLBACKS ---
def update_main_data():
    if st.session_state["editor_widget"] is not None:
        st.session_state.input_data = st.session_state["editor_widget"]

def update_portfolio_data():
    if st.session_state["portfolio_editor"] is not None:
        edited_df = st.session_state["portfolio_editor"]
        for index, row in edited_df.iterrows():
            if index < len(st.session_state.generated_parlays):
                st.session_state.generated_parlays[index]['BET?'] = row['BET?']
                new_wager = row['MY_WAGER']
                st.session_state.generated_parlays[index]['MY_WAGER'] = new_wager
                
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
    
    if isinstance(st.session_state.input_data, pd.DataFrame):
        csv_input = st.session_state.input_data.to_csv(index=False).encode('utf-8')
        st.download_button("💾 SAVE_INPUTS (CSV)", csv_input, "parlay_inputs.csv", "text/csv")
    
    if isinstance(st.session_state.bet_history, pd.DataFrame):
        csv_hist = st.session_state.bet_history.to_csv(index=False).encode('utf-8')
        st.download_button("💾 SAVE_HISTORY (CSV)", csv_hist, "bet_ledger.csv", "text/csv")

       uploaded_file = st.file_uploader("📂 LOAD_INPUTS", type=["csv"])
    if uploaded_file is not None:
        try:
            loaded_df = pd.read_csv(uploaded_file)
            
            # --- DATA SANITIZER ---
            if "Link Group" not in loaded_df.columns: loaded_df["Link Group"] = ""
            if "Excl Group" not in loaded_df.columns and "Group" in loaded_df.columns:
                loaded_df.rename(columns={"Group": "Excl Group"}, inplace=True)
            
            loaded_df["Link Group"] = loaded_df["Link Group"].fillna("").astype(str)
            loaded_df["Excl Group"] = loaded_df["Excl Group"].fillna("").astype(str)
            loaded_df["Leg Name"] = loaded_df["Leg Name"].fillna("Unknown").astype(str)
            
            if "Active" in loaded_df.columns:
                loaded_df["Active"] = loaded_df["Active"].astype(bool)
            else:
                loaded_df["Active"] = True
                
            loaded_df["Odds"] = pd.to_numeric(loaded_df["Odds"], errors='coerce').fillna(-110)
            loaded_df["Conf (1-10)"] = pd.to_numeric(loaded_df["Conf (1-10)"], errors='coerce').fillna(5)
            # ----------------------

            # 1. UPDATE THE DATA
            st.session_state.input_data = loaded_df
            
            # 2. FORCE RESET THE WIDGET (The Magic Fix)
            if "editor_widget" in st.session_state:
                del st.session_state["editor_widget"]

            st.success("DATABASE_RESTORED")
            st.rerun()
        except Exception as e: st.error(f"ERROR: {e}")


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
    
    st.markdown("### > WAGER_SETTINGS")
    auto_fill_kelly = st.checkbox("AUTO_FILL_KELLY_WAGER", value=False, help="If checked, 'My Wager' equals Kelly Rec. If unchecked, uses Default Unit.")
    default_unit = st.number_input("DEFAULT_UNIT ($)", value=1.0, step=1.0)

    st.markdown("### > CORRELATION")
    sgp_mode = st.checkbox("ENABLE_SGP_BOOST", value=True)
    correlation_boost = st.slider("BOOST_PCT", 0, 50, 15)

    st.markdown("### > PARLAY_SPECS")
    min_legs = st.number_input("MIN_LEGS", 2, 12, 3)
    max_legs = st.number_input("MAX_LEGS", 2, 15, 4)

    st.markdown("### > FILTERS")
    target_min_odds = st.number_input("MIN_ODDS (+)", 100, 100000, 100)
    target_max_odds = st.number_input("MAX_ODDS (+)", 100, 500000, 10000)
    min_ev_filter = st.checkbox("FILTER_NEG_EV", value=True)
    max_combos = st.number_input("MAX_ITERATIONS", min_value=1, max_value=1000000, value=5000, step=100)

# --- MAIN APP LAYOUT ---
st.title("> QUANT_PARLAY_ENGINE_V23")

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

    # --- MAIN TABLE (SAFETY CHECKED) ---
    if not isinstance(st.session_state.input_data, pd.DataFrame):
         st.session_state.input_data = pd.DataFrame(columns=["Active", "Excl Group", "Link Group", "Leg Name", "Odds", "Conf (1-10)"])

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
        num_rows="dynamic", width="stretch", key="editor_widget", on_change=update_main_data  
    )

    if not st.session_state.input_data.empty:
        df = st.session_state.input_data.copy()
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
                        
                        # Wager Logic
                        my_wager = kelly_rec = bankroll * kelly_pct
                        if not auto_fill_kelly:
                            my_wager = default_unit
                        
                        if min_ev_filter and kelly_rec <= 0: continue
                        
                        payout = (dec_total * my_wager) - my_wager
                        ev = (final_win_prob * payout) - ((1 - final_win_prob) * my_wager)

                        valid_parlays.append({
                            "BET?": False,
                            "LEGS": [l['Leg Name'] for l in combo],
                            "ODDS": dec_total,
                            "PROB": final_win_prob * 100,
                            "KELLY_REC": kelly_rec,
                            "MY_WAGER": my_wager,
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
                "KELLY_REC": st.column_config.NumberColumn("KELLY (REC)", format="$%.2f", disabled=True),
                "MY_WAGER": st.column_config.NumberColumn("MY WAGER ($)", format="$%.2f", min_value=0.0),
                "PAYOUT": st.column_config.NumberColumn("PAYOUT ($)", format="$%.2f", disabled=True),
                "EV": st.column_config.NumberColumn("EV ($)", format="$%.2f", disabled=True),
                "ODDS": st.column_config.NumberColumn("DEC ODDS", format="%.2f", disabled=True),
                "PROB": st.column_config.NumberColumn("WIN %", format="%.1f%%", disabled=True),
                "RAW_LEGS_DATA": None 
            },
            hide_index=True, width="stretch", key="portfolio_editor", on_change=update_portfolio_data 
        )

        st.write("")
        if st.button("💾 COMMIT_PLACED_TO_LEDGER"):
            placed = [p for p in st.session_state.generated_parlays if p['BET?']]
            if placed:
                rows = []
                today = datetime.now().strftime("%Y-%m-%d")
                for p in placed:
                    rows.append({
                        "Date": today, "Legs": " + ".join(p['LEGS']), "Odds": round(p['ODDS'], 2),
                        "Wager": round(p['MY_WAGER'], 2), "Payout": round(p['PAYOUT'], 2),
                        "Result": "Pending", "Profit": 0.0
                    })
                st.session_state.bet_history = pd.concat([st.session_state.bet_history, pd.DataFrame(rows)], ignore_index=True)
                st.success(f"COMMITTED {len(placed)}")
            else: st.warning("NO BETS SELECTED")

        active = [p for p in st.session_state.generated_parlays if p['BET?']]
        if active:
            st.divider()
            for i, p in enumerate(active):
                c1, c2 = st.columns([5, 1])
                with c1: st.code(f"{' + '.join(p['LEGS'])}\n(Odds: {p['ODDS']:.2f}) | Wager: {format_money(p['MY_WAGER'])}")
                with c2: st.caption(f"#{i+1}")
            
            risk = sum(p['MY_WAGER'] for p in active)
            ev = sum(p['EV'] for p in active)
            st.divider()
            c1, c2 = st.columns(2)
            c1.metric("TOTAL RISK", format_money(risk))
            c2.metric("TOTAL EV", format_money(ev))

# --- SCENARIOS ---
with tab_scenarios:
    st.header("🧪 SCENARIO_STRESS_TESTER")
    active = [p for p in st.session_state.generated_parlays if p.get('BET?', False)]
    if not active: st.warning("NO PLACED BETS.")
    else:
        legs = set()
        for p in active:
            for l in p['RAW_LEGS_DATA']: legs.add(l['Leg Name'])
        sorted_legs = sorted(list(legs))
        
        st.markdown("#### SET OUTCOMES:")
        cols = st.columns(3)
        state = {}
        for i, l in enumerate(sorted_legs):
            with cols[i%3]: state[l] = st.radio(f"{l}", ["Pending", "WIN", "LOSS"], index=0, key=f"s_{i}", horizontal=True)

        if st.button("RUN SCENARIO"):
            pnl, won, lost, pend = 0, 0, 0, 0
            for p in active:
                status = "WIN"
                for l in p['RAW_LEGS_DATA']:
                    s = state[l['Leg Name']]
                    if s == "LOSS": status = "LOSS"; break
                    elif s == "Pending": status = "PENDING"
                
                if status == "WIN": pnl += p['PAYOUT']; won += 1
                elif status == "LOSS": pnl -= p['MY_WAGER']; lost += 1
                else: pend += 1
            
            st.divider()
            c1, c2, c3 = st.columns(3)
            c1.metric("P&L", format_money(pnl), delta="Profit" if pnl>0 else "Loss")
            c2.metric("W/L", f"{won}/{lost}")
            c3.metric("PENDING", f"{pend}")

# --- HEDGE ---
with tab_hedge:
    st.header("🛡️ EXIT_STRATEGY")
    c1, c2 = st.columns(2)
    with c1: 
        pay = st.number_input("Potential Payout ($)", 1000.0)
        wag = st.number_input("Original Cost ($)", 50.0)
    with c2: 
        ho = st.number_input("Opponent Odds", 150)
        hd = american_to_decimal(ho)
        st.metric("Dec Odds", f"{hd:.2f}")
    
    if st.button("CALC"):
        hedge = pay / hd
        prof = pay - hedge - wag
        c1, c2 = st.columns(2)
        c1.metric("HEDGE BET", format_money(hedge))
        c2.metric("LOCKED PROFIT", format_money(prof))

# --- ANALYSIS ---
with tab_analysis:
    if isinstance(st.session_state.input_data, pd.DataFrame) and not st.session_state.input_data.empty:
        df = st.session_state.input_data[st.session_state.input_data['Active']==True].copy()
        if not df.empty:
            df['Imp'] = (1/df['Odds'].apply(american_to_decimal))*100
            df['My'] = df['Conf (1-10)']*10
            c = alt.Chart(df).mark_circle(size=100).encode(x='Imp', y='My', tooltip=['Leg Name'])
            l = alt.Chart(pd.DataFrame({'x':[0,100], 'y':[0,100]})).mark_line(color='grey', strokeDash=[5,5]).encode(x='x', y='y')
            st.altair_chart((c+l).interactive(), use_container_width=True)

    active = [p for p in st.session_state.generated_parlays if p.get('BET?', False)]
    if active:
        if st.button("RUN SIM (1000)"):
            sims = []
            ulegs = {}
            for p in active:
                for l in p['RAW_LEGS_DATA']: ulegs[l['Leg Name']] = l['Est Win %']/100
            
            for _ in range(1000):
                outcome = {k: random.random() < v for k,v in ulegs.items()}
                prof = 0
                for p in active:
                    if all(outcome[l['Leg Name']] for l in p['RAW_LEGS_DATA']): prof += p['PAYOUT']
                    else: prof -= p['MY_WAGER']
                sims.append(prof)
            
            chart = alt.Chart(pd.DataFrame(sims, columns=['P'])).mark_bar().encode(alt.X("P", bin=True), y='count()')
            st.altair_chart(chart, use_container_width=True)

# --- LEDGER ---
with tab_ledger:
    st.header("📜 LEDGER")
    if not st.session_state.bet_history.empty:
        hist = st.data_editor(st.session_state.bet_history, num_rows="dynamic", width="stretch")
        # Update Logic
        for i, r in hist.iterrows():
            if r['Result'] == 'Won': hist.at[i, 'Profit'] = r['Payout']
            elif r['Result'] == 'Lost': hist.at[i, 'Profit'] = -r['Wager']
            else: hist.at[i, 'Profit'] = 0.0
        
        st.session_state.bet_history = hist
        
        tot_wag = hist['Wager'].sum()
        tot_prof = hist['Profit'].sum()
        c1, c2 = st.columns(2)
        c1.metric("VOL", format_money(tot_wag))
        c2.metric("PROFIT", format_money(tot_prof))
