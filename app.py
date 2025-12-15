import streamlit as st
import pandas as pd
import itertools
import numpy as np
import altair as alt
import requests
import random
import uuid # For generating unique keys
from datetime import datetime

# --- PAGE CONFIG ---
st.set_page_config(
    page_title="QUANT_PARLAY_ENGINE_V26", 
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
    # Only update if the widget exists in session state
    if st.session_state.get(st.session_state.main_editor_key) is not None:
        st.session_state.input_data = st.session_state[st.session_state.main_editor_key]

def update_portfolio_data():
    key = st.session_state.portfolio_editor_key
    if st.session_state.get(key) is not None:
        edited_df = st.session_state[key]
        for index, row in edited_df.iterrows():
            if index < len(st.session_state.generated_parlays):
                st.session_state.generated_parlays[index]['BET?'] = row['BET?']
                
                # Update Wager Logic
                new_wager = row['MY_WAGER']
                st.session_state.generated_parlays[index]['MY_WAGER'] = new_wager
                
                # Recalc Stats
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

# Dynamic Keys for Widgets (This forces refresh on load/clear)
if 'main_editor_key' not in st.session_state:
    st.session_state.main_editor_key = str(uuid.uuid4())

if 'portfolio_editor_key' not in st.session_state:
    st.session_state.portfolio_editor_key = str(uuid.uuid4())
    
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
                    # Force Refresh
                    st.session_state.main_editor_key = str(uuid.uuid4())
                    st.success(f"ADDED {len(fetched)} LINES")
                    st.rerun()

    st.markdown("---")
    st.markdown("### > DATA_PERSISTENCE")
    
    if isinstance(st.session_state.input_data, pd.DataFrame):
        csv_input = st.session_state.input_data.to_csv(index=False).encode('utf-8')
        st.download_button("💾 SAVE_INPUTS", csv_input, "parlay_inputs.csv", "text/csv")
    
    if isinstance(st.session_state.bet_history, pd.DataFrame):
        csv_hist = st.session_state.bet_history.to_csv(index=False).encode('utf-8')
        st.download_button("💾 SAVE_HISTORY", csv_hist, "bet_ledger.csv", "text/csv")

    uploaded_file = st.file_uploader("📂 LOAD_INPUTS", type=["csv"])
    if uploaded_file is not None:
        try:
            loaded_df = pd.read_csv(uploaded_file)
            
            # Sanitizer
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

            st.session_state.input_data = loaded_df
            
            # --- FORCE WIDGET REFRESH (THE FIX) ---
            st.session_state.main_editor_key = str(uuid.uuid4())
            
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
    if st.button("🗑️ CLEAR_ALL"):
        st.session_state.input_data = pd.DataFrame(columns=["Active", "Excl Group", "Link Group", "Leg Name", "Odds", "Conf (1-10)"])
        st.session_state.generated_parlays = []
        # FORCE REFRESH
        st.session_state.main_editor_key = str(uuid.uuid4())
        st.session_state.portfolio_editor_key = str(uuid.uuid4())
        st.rerun()

    st.markdown("### > BANKROLL")
    bankroll = st.number_input("TOTAL_BANKROLL", 100.0, 1000000.0, 1000.0)
    kelly_fraction = st.slider("KELLY_FRACT", 0.1, 1.0, 0.25)
    
    st.markdown("### > WAGER_SETTINGS")
    auto_fill_kelly = st.checkbox("AUTO_FILL_KELLY", value=False)
    default_unit = st.number_input("DEFAULT_UNIT ($)", value=1.0, step=1.0)

    st.markdown("### > CORRELATION")
    sgp_mode = st.checkbox("SGP_BOOST", value=True)
    correlation_boost = st.slider("BOOST_PCT", 0, 50, 15)

    st.markdown("### > SPECS")
    min_legs = st.number_input("MIN_LEGS", 2, 12, 3)
    max_legs = st.number_input("MAX_LEGS", 2, 15, 4)

    st.markdown("### > FILTERS")
    target_min_odds = st.number_input("MIN_ODDS", 100, 100000, 100)
    target_max_odds = st.number_input("MAX_ODDS", 100, 500000, 10000)
    min_ev_filter = st.checkbox("FILTER_NEG_EV", value=True)
    max_combos = st.number_input("MAX_ITER", 1, 1000000, 5000, 100)

# --- MAIN APP ---
st.title("> QUANT_PARLAY_ENGINE_V26")
tab_build, tab_scenarios, tab_hedge, tab_analysis, tab_ledger = st.tabs(["🏗️ BUILDER", "🧪 SCENARIOS", "🛡️ HEDGE", "📊 ANALYSIS", "📜 LEDGER"])

# --- BUILDER TAB ---
with tab_build:
    with st.expander("➕ OPEN_PROP_BUILDER"):
        c1, c2, c3, c4, c5 = st.columns([2, 1, 1, 1, 1])
        with c1: new_prop_name = st.text_input("PROP_NAME")
        with c2: new_excl = st.text_input("⛔ EXCL_ID")
        with c3: new_link = st.text_input("🔗 LINK_ID")
        with c4: new_odds = st.number_input("ODDS", -110, step=10)
        with c5: new_conf = st.slider("CONF", 1, 10, 5)
        if st.button("ADD_PROP"):
            new_row = {"Active": True, "Excl Group": new_excl, "Link Group": new_link, "Leg Name": new_prop_name, "Odds": new_odds, "Conf (1-10)": new_conf}
            st.session_state.input_data = pd.concat([st.session_state.input_data, pd.DataFrame([new_row])], ignore_index=True)
            # Force Refresh
            st.session_state.main_editor_key = str(uuid.uuid4())
            st.success("ADDED")
            st.rerun()

    if st.button("👯 CLONE_SELECTED"):
        df = st.session_state.input_data.copy()
        clones = df[df['Active'] == True]
        if not clones.empty:
            st.session_state.input_data = pd.concat([df, clones], ignore_index=True)
            st.session_state.main_editor_key = str(uuid.uuid4())
            st.success(f"CLONED {len(clones)}")
            st.rerun()

    # Safety check
    if not isinstance(st.session_state.input_data, pd.DataFrame):
         st.session_state.input_data = pd.DataFrame(columns=["Active", "Excl Group", "Link Group", "Leg Name", "Odds", "Conf (1-10)"])

    # --- MAIN TABLE (DYNAMIC KEY) ---
    st.data_editor(
        st.session_state.input_data, 
        column_config={
            "Active": st.column_config.CheckboxColumn("USE?", width="small"),
            "Excl Group": st.column_config.TextColumn("⛔ EXCL", width="small"),
            "Link Group": st.column_config.TextColumn("🔗 LINK", width="small"),
            "Leg Name": st.column_config.TextColumn("LEG_ID"),
            "Odds": st.column_config.NumberColumn("ODDS"),
            "Conf (1-10)": st.column_config.NumberColumn("CONF", min_value=1, max_value=10)
        },
        num_rows="dynamic", 
        width="stretch", 
        key=st.session_state.main_editor_key, # <--- The Magic Key
        on_change=update_main_data  
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
            stop = False
            min_dec, max_dec = american_to_decimal(target_min_odds), american_to_decimal(target_max_odds)

            with st.spinner("PROCESSING..."):
                for r in range(min_legs, max_legs + 1):
                    if stop: break
                    for combo in itertools.combinations(legs_list, r):
                        excl = [str(x['Excl Group']) for x in combo if str(x['Excl Group']).strip()]
                        if len(excl) != len(set(excl)): continue

                        is_corr = False
                        if sgp_mode:
                            links = [str(x['Link Group']) for x in combo if str(x['Link Group']).strip()]
                            if len(links) != len(set(links)): is_corr = True
                        
                        combo_count += 1
                        if combo_count > max_combos: stop = True; break

                        dec_total = np.prod([x['Decimal'] for x in combo])
                        if not (min_dec <= dec_total <= max_dec): continue

                        raw_prob = np.prod([x['Est Win %']/100 for x in combo])
                        final_prob = min(0.99, raw_prob * (1 + (correlation_boost/100) if is_corr else 1))

                        kelly_rec = bankroll * kelly_criterion(dec_total, final_prob * 100, kelly_fraction)
                        my_wager = kelly_rec if auto_fill_kelly else default_unit
                        
                        if min_ev_filter and kelly_rec <= 0: continue
                        
                        payout = (dec_total * my_wager) - my_wager
                        ev = (final_prob * payout) - ((1 - final_prob) * my_wager)

                        valid_parlays.append({
                            "BET?": False,
                            "LEGS": [l['Leg Name'] for l in combo],
                            "ODDS": dec_total,
                            "PROB": final_prob * 100,
                            "KELLY_REC": kelly_rec,
                            "MY_WAGER": my_wager,
                            "PAYOUT": payout,
                            "EV": ev,
                            "RAW_LEGS_DATA": combo,
                            "BOOST": "🚀" if is_corr else ""
                        })
            st.session_state.generated_parlays = valid_parlays
            # New Results Table needs refresh too
            st.session_state.portfolio_editor_key = str(uuid.uuid4())
            st.rerun()

    # --- RESULTS DISPLAY ---
    if len(st.session_state.generated_parlays) > 0:
        st.divider()
        st.markdown("### 📋 GENERATED_PORTFOLIO")
        
        results_df = pd.DataFrame(st.session_state.generated_parlays)
        display_df = results_df.copy()
        display_df['LEGS'] = display_df['LEGS'].apply(lambda x: " + ".join(x))
        
        st.data_editor(
            display_df,
            column_config={
                "BET?": st.column_config.CheckboxColumn("PLACED?", help="Check to mark as placed"),
                "LEGS": st.column_config.TextColumn("PARLAY LEGS", width="large"),
                "KELLY_REC": st.column_config.NumberColumn("KELLY", format="$%.2f", disabled=True),
                "MY_WAGER": st.column_config.NumberColumn("WAGER", format="$%.2f", min_value=0.0),
                "PAYOUT": st.column_config.NumberColumn("PAYOUT", format="$%.2f", disabled=True),
                "EV": st.column_config.NumberColumn("EV", format="$%.2f", disabled=True),
                "ODDS": st.column_config.NumberColumn("DEC", format="%.2f", disabled=True),
                "PROB": st.column_config.NumberColumn("WIN %", format="%.1f%%", disabled=True),
                "RAW_LEGS_DATA": None 
            },
            hide_index=True, width="stretch", 
            key=st.session_state.portfolio_editor_key, 
            on_change=update_portfolio_data 
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

        # Copy Section
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
        
        # Safe Manual Check (Ledger doesn't use callbacks)
        if not hist.equals(st.session_state.bet_history):
            updated_history = hist.copy()
            for i, r in updated_history.iterrows():
                if r['Result'] == 'Won': updated_history.at[i, 'Profit'] = r['Payout']
                elif r['Result'] == 'Lost': updated_history.at[i, 'Profit'] = -r['Wager']
                else: updated_history.at[i, 'Profit'] = 0.0
            
            st.session_state.bet_history = updated_history
            st.rerun()
        
        tot_wag = st.session_state.bet_history['Wager'].sum()
        tot_prof = st.session_state.bet_history['Profit'].sum()
        c1, c2 = st.columns(2)
        c1.metric("VOL", format_money(tot_wag))
        c2.metric("PROFIT", format_money(tot_prof))
