import streamlit as st
import yfinance as yf
import pandas as pd
from datetime import datetime, timedelta
import time
import concurrent.futures

st.set_page_config(page_title="Algorithmic Options Scoring", layout="wide", page_icon="🧠")

SECTORS = {
    "כל המניות (סריקה מלאה)": "CLSK, VIX, SLV, UMAC, RDW, LUNR, ASTS, RKLB, AVAV, BA, ONDS, FTAI, TSLA, EOSE, QUBT, SMR, RGTI, CIFR, CORZ, NNE, ALGM, VIAV, IONQ, OKLO, IREN, HUT, DELL, PATH, S, ZETA, TTD, TOST, VRNS, TDC, DT, RBLX, TEM, ESTC, NOW, CRWV, DUOL, SEZL, CSCO, ZS, BABA, PLTR, RDDT, SNOW, ORCL, NBIS, NET, DDOG, ADBE, PANW, MDB, GOOGL, MSFT, APP, META, CRWD, IMSR, CRML, UEC, UUUU, USAR, MP, CMC, SQM, CCJ, LEU, HIMS, NVO, MRNA, UNH, LLY, MARA, BMNR, HOOD, CRCL, MSTR, APLD, STM, INTC, VST, AAOI, GLW, MRVL, NVDA, CRDO, QCOM, IBM, AMZN, FSLR, AAPL, VRT, ALAB, CLS, GOOG, AVGO, AMD, WDC, MU, SNDK, ASML, FLNC, ENPH, SEDG, NEE, OKE, CEG, GEV, ASPI, RKT, SOFI, GLXY, PYPL, AFRM, UBER, ADM, EL, DLTR, AEHR, DECK, ARES, LULU, TJX, NVT, MOD, JPM, AEIS, TER, AMAT",
    "Space & Defense": "UMAC, RDW, LUNR, ASTS, RKLB, AVAV, BA, ONDS, FTAI, TSLA",
    "Data Centers & Nuclear": "EOSE, QUBT, SMR, CLSK, RGTI, CIFR, CORZ, NNE, ALGM, VIAV, IONQ, OKLO, IREN, HUT, DELL",
    "Software & Cloud": "PATH, S, ZETA, TTD, TOST, VRNS, TDC, DT, RBLX, TEM, ESTC, NOW, CRWV, DUOL, SEZL, CSCO, ZS, BABA, PLTR, RDDT, SNOW, ORCL, NBIS, NET, DDOG, ADBE, PANW, MDB, GOOGL, MSFT, APP, META, CRWD",
    "Materials & Uranium": "IMSR, CRML, UEC, UUUU, USAR, MP, CMC, SQM, CCJ, LEU",
    "Health & Pharma": "HIMS, NVO, MRNA, UNH, LLY",
    "Crypto & Miners": "MARA, BMNR, HOOD, CRCL, MSTR, CLSK, IREN, HUT, CORZ, CIFR",
    "Semiconductors & AI": "APLD, STM, INTC, VST, AAOI, GLW, MRVL, NVDA, CRDO, QCOM, IBM, AMZN, FSLR, AAPL, VRT, ALAB, CLS, GOOG, AVGO, AMD, WDC, MU, SNDK, ASML",
    "Energy": "FLNC, ENPH, SEDG, NEE, OKE, CEG, GEV"
}

# --- מנוע הניקוד האלגוריתמי (מעודכן ל-OTM בלבד) ---
def calculate_trade_score(premium, ratio, pcr, opt_type, dte, dist_pct):
    score = 0
    
    # 1. Premium Weight (35%) - משקל מוגדל לכסף גדול
    if premium >= 500000: score += 35
    elif premium >= 250000: score += 25
    elif premium >= 100000: score += 15
    else: score += 5
        
    # 2. Vol/OI Anomaly Weight (30%) - חשיבות עליונה להפתעה
    if ratio >= 10: score += 30
    elif ratio >= 5: score += 20
    elif ratio >= 3: score += 10
    else: score += 5
        
    # 3. Sentiment Alignment (20%)
    if opt_type == "Call" and pcr < 0.7: score += 20
    elif opt_type == "Put" and pcr > 1.2: score += 20
    elif (opt_type == "Call" and pcr > 1.0) or (opt_type == "Put" and pcr < 0.8): score -= 15
        
    # 4. Urgency / DTE (15%)
    if dte <= 7: score += 15
    elif dte <= 14: score += 10
    else: score += 5
        
    return max(0, min(100, score))

def process_ticker(ticker, min_ratio, min_premium, max_expiry_date):
    results = []
    try:
        tk = yf.Ticker(ticker)
        try: current_price = tk.info.get('regularMarketPrice', tk.history(period="1d")['Close'].iloc[-1])
        except: current_price = 0
            
        expirations = tk.options
        if not expirations: return results
        near_term_expiries = [exp for exp in expirations if datetime.strptime(exp, '%Y-%m-%d') <= max_expiry_date]
        
        for expiry in near_term_expiries[:2]:
            opt_chain = tk.option_chain(expiry)
            
            total_calls_vol = opt_chain.calls['volume'].sum() if not opt_chain.calls.empty else 0
            total_puts_vol = opt_chain.puts['volume'].sum() if not opt_chain.puts.empty else 0
            pcr = round(total_puts_vol / total_calls_vol, 2) if total_calls_vol > 0 else 0
            
            dte = (datetime.strptime(expiry, '%Y-%m-%d') - datetime.now()).days
            if dte < 0: dte = 0
            
            for opt_type, chain in [("Call", opt_chain.calls), ("Put", opt_chain.puts)]:
                chain = chain.fillna(0)
                active_strikes = chain[chain['openInterest'] > 0]
                
                for index, row in active_strikes.iterrows():
                    strike = row['strike']
                    
                    # === חומת האש: סינון ITM לחלוטין ===
                    # אנחנו מאפשרים רק OTM או על הכסף בדיוק (ATM)
                    if opt_type == "Call" and strike < current_price: continue # מתעלם מקולים בתוך הכסף
                    if opt_type == "Put" and strike > current_price: continue # מתעלם מפוטים בתוך הכסף
                    
                    vol, oi, last_price = row['volume'], row['openInterest'], row['lastPrice']
                    ratio = round(vol / oi, 2) if oi > 0 else 0
                    premium_traded = vol * last_price * 100 
                    
                    if ratio >= min_ratio and premium_traded >= min_premium:
                        iv = round(row['impliedVolatility'] * 100, 2)
                        dist_pct = round(abs(strike - current_price) / current_price * 100, 1) if current_price else 0
                        
                        final_score = calculate_trade_score(premium_traded, ratio, pcr, opt_type, dte, dist_pct)
                        
                        if final_score >= 60:
                            if final_score >= 85: grade = f"A+ 🔥 ({final_score}/100)"
                            elif final_score >= 75: grade = f"A 🟢 ({final_score}/100)"
                            else: grade = f"B 🟡 ({final_score}/100)"
                                
                            results.append({
                                "דירוג אלגוריתמי": grade,
                                "סימול": ticker,
                                "סוג": "🟢 Call" if opt_type == "Call" else "🔴 Put",
                                "סטרייק": strike,
                                "פקיעה": expiry,
                                "מרחק מהמחיר": f"{dist_pct}%",
                                "פרמיה ($)": premium_traded,
                                "יחס Vol/OI": ratio,
                                "PCR": pcr,
                                "IV (%)": iv,
                                "_raw_score": final_score
                            })
    except Exception: pass
    return results

@st.cache_data(ttl=60)
def get_scored_flow(tickers, min_ratio, min_premium):
    max_expiry_date = datetime.today() + timedelta(days=30)
    all_results = []
    
    with concurrent.futures.ThreadPoolExecutor(max_workers=20) as executor:
        futures = [executor.submit(process_ticker, t, min_ratio, min_premium, max_expiry_date) for t in tickers]
        for future in concurrent.futures.as_completed(futures):
            res = future.result()
            if res: all_results.extend(res)
                
    df = pd.DataFrame(all_results)
    if not df.empty:
        df = df.sort_values(by="_raw_score", ascending=False).reset_index(drop=True).head(15)
        df['פרמיה ($)'] = df['פרמיה ($)'].apply(lambda x: f"${x:,.0f}")
        df = df.drop(columns=["_raw_score"])
    return df

st.title("🎯 Pure OTM Scoring Engine")
st.markdown("מנוע אגרסיבי לאיתור פריצות: **כל אופציות ה-ITM (הגנות/תחליפי מניה) מסוננות החוצה לחלוטין ברמת הקוד.** המערכת מציגה ומדרגת אך ורק הימורים כיווניים מחוץ לכסף (OTM) עם תזרים הון חריג.")

with st.sidebar:
    st.header("⚙️ הגדרות מנוע")
    selected_sector = st.selectbox("בחר סקטור:", list(SECTORS.keys()))
    st.divider()
    min_premium_input = st.number_input("רצפת פרמיה ($):", 10000, 1000000, 50000, 10000)
    min_ratio_input = st.slider("יחס Vol/OI מינימלי:", 1.0, 10.0, 3.0, 0.5)
    auto_refresh = st.checkbox("רענון אוטומטי (כל 60 שניות)")

if st.button("🚀 הפעל סריקת פריצות (OTM בלבד)") or auto_refresh:
    ticker_list = [x.strip().upper() for x in SECTORS[selected_sector].split(",") if x.strip()]
    
    with st.spinner(f"סורק פוזיציות OTM בלבד לסקטור {selected_sector}..."):
        df_top = get_scored_flow(ticker_list, min_ratio_input, min_premium_input)
    
    if not df_top.empty:
        st.success(f"✅ **העסקאות האגרסיביות ביותר (OTM Only):**")
        def style_rows(row):
            if "A+" in row['דירוג אלגוריתמי']: return ['background-color: rgba(255, 215, 0, 0.15)'] * len(row)
            elif "Call" in row['סוג']: return ['background-color: rgba(0, 255, 0, 0.05)'] * len(row)
            else: return ['background-color: rgba(255, 0, 0, 0.05)'] * len(row)
        st.dataframe(df_top.style.apply(style_rows, axis=1), width="stretch")
    else:
        st.info("לא נמצאו פקודות אגרסיביות מספיק (OTM) שקיבלו ציון עובר בסקטור זה.")

if auto_refresh:
    time.sleep(60)
    st.rerun()
