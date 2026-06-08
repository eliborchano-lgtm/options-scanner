import streamlit as st
import yfinance as yf
import pandas as pd
from datetime import datetime, timedelta
import time
import concurrent.futures

st.set_page_config(page_title="Sector Options Scanner", layout="wide", page_icon="🌐")

# --- חלוקה לסקטורים (מבוסס על הרשימה שלך) ---
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


def process_ticker(ticker, min_ratio, min_premium, max_expiry_date):
    results = []
    try:
        tk = yf.Ticker(ticker)
        try:
            current_price = tk.info.get('regularMarketPrice', tk.history(period="1d")['Close'].iloc[-1])
        except:
            current_price = 0

        expirations = tk.options
        if not expirations:
            return results

        near_term_expiries = [exp for exp in expirations if datetime.strptime(exp, '%Y-%m-%d') <= max_expiry_date]

        for expiry in near_term_expiries[:2]:
            opt_chain = tk.option_chain(expiry)
            for opt_type, chain in [("Call", opt_chain.calls), ("Put", opt_chain.puts)]:
                chain = chain.fillna(0)
                active_strikes = chain[chain['openInterest'] > 0]

                for index, row in active_strikes.iterrows():
                    vol = row['volume']
                    oi = row['openInterest']
                    last_price = row['lastPrice']
                    strike = row['strike']

                    ratio = round(vol / oi, 2) if oi > 0 else 0
                    premium_traded = vol * last_price * 100

                    if ratio >= min_ratio and premium_traded >= min_premium:
                        iv = round(row['impliedVolatility'] * 100, 2)
                        is_otm = (opt_type == "Call" and strike > current_price) or (
                                    opt_type == "Put" and strike < current_price)
                        score = premium_traded * ratio
                        if is_otm: score *= 1.5

                        results.append({
                            "סימול": ticker,
                            "סוג חוזה": "🟢 Call" if opt_type == "Call" else "🔴 Put",
                            "סטרייק": strike,
                            "פקיעה": expiry,
                            "אגרסיביות": "🔥 OTM" if is_otm else "🛡️ ITM",
                            "פרמיה ($)": premium_traded,
                            "יחס Vol/OI": ratio,
                            "מחיר חוזה": last_price,
                            "IV (%)": iv,
                            "_score": score
                        })
    except Exception:
        pass
    return results


@st.cache_data(ttl=60)
def get_top_flow(tickers, min_ratio, min_premium):
    max_expiry_date = datetime.today() + timedelta(days=30)
    all_results = []

    with concurrent.futures.ThreadPoolExecutor(max_workers=20) as executor:
        futures = [executor.submit(process_ticker, t, min_ratio, min_premium, max_expiry_date) for t in tickers]
        for future in concurrent.futures.as_completed(futures):
            res = future.result()
            if res:
                all_results.extend(res)

    df = pd.DataFrame(all_results)
    if not df.empty:
        df = df.sort_values(by="_score", ascending=False).reset_index(drop=True).head(15)
        df['פרמיה ($)'] = df['פרמיה ($)'].apply(lambda x: f"${x:,.0f}")
        df = df.drop(columns=["_score"])
    return df


st.title("🌐 סורק אופציות מבוסס סקטורים")

with st.sidebar:
    st.header("⚙️ בחירת מיקוד")
    selected_sector = st.selectbox("בחר סקטור לסריקה:", list(SECTORS.keys()))

    st.divider()
    min_premium_input = st.number_input("מינימום דולרים (Premium):", 10000, 1000000, 50000, 10000)
    min_ratio_input = st.slider("יחס Vol/OI מינימלי:", 1.0, 10.0, 3.0, 0.5)
    auto_refresh = st.checkbox("רענון אוטומטי (כל 60 שניות)")

if st.button("🚀 הפעל סריקה") or auto_refresh:
    # שליפת המניות הרלוונטיות מהמילון שבנינו
    ticker_list = [x.strip().upper() for x in SECTORS[selected_sector].split(",") if x.strip()]

    with st.spinner(f"סורק את סקטור {selected_sector}..."):
        df_top = get_top_flow(ticker_list, min_ratio_input, min_premium_input)

    if not df_top.empty:
        st.success(f"✅ **החוזים החמים ביותר בסקטור {selected_sector}:**")


        def style_rows(row):
            if "Call" in row['סוג חוזה']:
                return ['background-color: rgba(0, 255, 0, 0.1)'] * len(row)
            else:
                return ['background-color: rgba(255, 0, 0, 0.1)'] * len(row)


        st.dataframe(df_top.style.apply(style_rows, axis=1), width="stretch")
    else:
        st.info("לא נמצאו פקודות חריגות בסקטור זה כרגע.")

if auto_refresh:
    time.sleep(60)
    st.rerun()