import sqlite3
from datetime import datetime, date
from pathlib import Path
import re

import numpy as np
import pandas as pd
import streamlit as st

APP_TITLE = "Options Flow Research Desk"
DB_PATH = Path("options_flow.db")
WATCHLIST = ["SPY", "QQQ", "IWM", "NVDA", "TSLA", "META", "AAPL", "AMD", "AMZN", "MSFT", "GOOGL", "NFLX"]

st.set_page_config(page_title=APP_TITLE, page_icon="📈", layout="wide")

# ---------- Persistence ----------
def db():
    con = sqlite3.connect(DB_PATH, check_same_thread=False)
    con.execute("""
        CREATE TABLE IF NOT EXISTS observations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            imported_at TEXT NOT NULL,
            source TEXT NOT NULL,
            source_timestamp TEXT,
            symbol TEXT,
            option_type TEXT,
            expiration TEXT,
            strike REAL,
            last REAL,
            bid REAL,
            ask REAL,
            volume REAL,
            open_interest REAL,
            vol_oi REAL,
            premium REAL,
            sentiment TEXT,
            raw_json TEXT
        )
    """)
    con.execute("""
        CREATE TABLE IF NOT EXISTS paper_ideas (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            created_at TEXT NOT NULL,
            symbol TEXT,
            option_type TEXT,
            expiration TEXT,
            strike REAL,
            entry_premium REAL,
            thesis TEXT,
            horizon TEXT,
            status TEXT DEFAULT 'Open',
            exit_premium REAL,
            notes TEXT
        )
    """)
    con.commit()
    return con

CON = db()

# ---------- Import normalization ----------
ALIASES = {
    "symbol": ["symbol", "underlying", "ticker", "stock"],
    "option_type": ["type", "option type", "put/call", "call/put", "right"],
    "expiration": ["expiration", "expiry", "expiration date", "exp date", "exp"],
    "strike": ["strike", "strike price"],
    "last": ["last", "last price", "price", "option price"],
    "bid": ["bid"],
    "ask": ["ask", "offer"],
    "volume": ["volume", "vol", "option volume"],
    "open_interest": ["open interest", "open_interest", "oi", "open int"],
    "vol_oi": ["vol/oi", "volume/open interest", "volume / open interest", "vol oi", "volume to open interest"],
    "premium": ["premium", "dollar volume", "total premium"],
    "sentiment": ["sentiment", "direction", "bull/bear", "bullish/bearish"],
    "contract": ["contract", "option symbol", "occ symbol"]
}

def clean_col(value):
    return re.sub(r"\s+", " ", str(value).strip().lower().replace("_", " "))

def normalize_csv(df):
    out = pd.DataFrame()
    lookup = {clean_col(c): c for c in df.columns}
    for target, names in ALIASES.items():
        source = next((lookup[clean_col(n)] for n in names if clean_col(n) in lookup), None)
        if source is not None:
            out[target] = df[source]
    if "symbol" not in out.columns and "contract" in out.columns:
        out["symbol"] = out["contract"].astype(str).str.extract(r"^([A-Z]{1,6})")[0]
    if "option_type" in out.columns:
        out["option_type"] = out["option_type"].astype(str).str.upper().replace({"CALL":"CALL", "PUT":"PUT", "C":"CALL", "P":"PUT"})
    for col in ["strike", "last", "bid", "ask", "volume", "open_interest", "vol_oi", "premium"]:
        if col in out.columns:
            out[col] = pd.to_numeric(out[col].astype(str).str.replace(r"[$,]", "", regex=True), errors="coerce")
    if "vol_oi" not in out.columns and {"volume", "open_interest"}.issubset(out.columns):
        out["vol_oi"] = out["volume"] / out["open_interest"].replace(0, np.nan)
    if "premium" not in out.columns and {"last", "volume"}.issubset(out.columns):
        out["premium"] = out["last"] * out["volume"] * 100
    for col in ["symbol", "option_type", "expiration", "sentiment"]:
        if col not in out.columns:
            out[col] = ""
        out[col] = out[col].fillna("").astype(str).str.strip()
    return out

def score_row(row, horizon):
    # Transparent heuristic score; deliberately not a probability or trade recommendation.
    score = 0
    vol_oi = row.get("vol_oi", np.nan)
    volume = row.get("volume", np.nan)
    premium = row.get("premium", np.nan)
    sentiment = str(row.get("sentiment", "")).lower()
    if pd.notna(vol_oi):
        score += 25 if vol_oi >= 3 else 18 if vol_oi >= 2 else 10 if vol_oi >= 1.25 else 0
    if pd.notna(volume):
        score += 15 if volume >= 5000 else 10 if volume >= 2000 else 5 if volume >= 500 else 0
    if pd.notna(premium):
        score += 20 if premium >= 1_000_000 else 15 if premium >= 500_000 else 10 if premium >= 100_000 else 5 if premium >= 25_000 else 0
    if "bull" in sentiment or "bear" in sentiment:
        score += 10
    exp = str(row.get("expiration", ""))
    try:
        dte = (pd.to_datetime(exp).date() - date.today()).days
        if horizon == "Intraday" and 0 <= dte <= 1:
            score += 20
        elif horizon == "Swing" and 2 <= dte <= 14:
            score += 15
        elif horizon == "Swing" and 15 <= dte <= 45:
            score += 10
    except Exception:
        pass
    return min(score, 100)

def load_observations():
    return pd.read_sql_query("SELECT * FROM observations ORDER BY id DESC", CON)

def money(x):
    return "—" if pd.isna(x) else f"${x:,.0f}"

# ---------- Header ----------
st.title("📈 Options Flow Research Desk")
st.caption("Barchart-first research • delayed/manual observations • paper tracking only")
st.warning("Data is not real-time. Barchart reports options data delayed approximately 25–30 minutes. Scores are experimental screening heuristics—not trading signals.")

with st.sidebar:
    st.header("Research filters")
    universe = st.radio("Universe", ["Entire imported market", "Starter watchlist"], index=0)
    horizon = st.selectbox("Research horizon", ["Intraday", "Swing"], index=0)
    min_score = st.slider("Minimum experimental score", 0, 100, 25, 5)
    st.divider()
    st.caption("Starter watchlist")
    st.write(", ".join(WATCHLIST))
    st.caption("Database: local SQLite. Export records regularly if deployed to ephemeral hosting.")

tab_scan, tab_import, tab_tracker, tab_method = st.tabs(["Market Scanner", "Import Barchart CSV", "Paper Tracker", "Method & Data Quality"])

# ---------- Import ----------
with tab_import:
    st.subheader("Import Barchart Unusual Options Activity")
    st.markdown("Download the displayed table from [Barchart Unusual Options Activity](https://www.barchart.com/options/unusual-activity), then upload the CSV here.")
    uploaded = st.file_uploader("Upload Barchart CSV", type=["csv"])
    source_time = st.text_input("Source report timestamp (optional)", placeholder="e.g. 2026-11-09 10:15 ET")
    if uploaded is not None:
        try:
            raw = pd.read_csv(uploaded)
            normalized = normalize_csv(raw)
            st.write("Detected columns:", ", ".join(normalized.columns))
            st.dataframe(normalized.head(20), use_container_width=True)
            required = ["symbol", "volume"]
            missing = [c for c in required if c not in normalized.columns]
            if missing:
                st.error("Required fields not detected: " + ", ".join(missing) + ". This CSV may use an unsupported layout.")
            else:
                st.caption(f"{len(normalized)} rows ready to import. Verify the preview before saving.")
                if st.button("Save imported observations", type="primary"):
                    now = datetime.now().isoformat(timespec="seconds")
                    saved = 0
                    for _, r in normalized.iterrows():
                        vals = [
                            now, "Barchart CSV", source_time, r.get("symbol",""), r.get("option_type",""),
                            r.get("expiration",""), r.get("strike",None), r.get("last",None), r.get("bid",None),
                            r.get("ask",None), r.get("volume",None), r.get("open_interest",None),
                            r.get("vol_oi",None), r.get("premium",None), r.get("sentiment",""),
                            r.to_json(date_format="iso")
                        ]
                        CON.execute("""INSERT INTO observations
                        (imported_at,source,source_timestamp,symbol,option_type,expiration,strike,last,bid,ask,volume,open_interest,vol_oi,premium,sentiment,raw_json)
                        VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""", vals)
                        saved += 1
                    CON.commit()
                    st.success(f"Saved {saved} observations.")
        except Exception as e:
            st.error(f"Could not read this CSV: {e}")

    st.divider()
    st.subheader("Manual contract entry")
    with st.form("manual_entry"):
        c1, c2, c3 = st.columns(3)
        symbol = c1.text_input("Underlying symbol", "SPY").upper().strip()
        opt_type = c2.selectbox("Call or put", ["CALL", "PUT"])
        exp = c3.date_input("Expiration", value=date.today())
        c4, c5, c6 = st.columns(3)
        strike = c4.number_input("Strike", min_value=0.0, value=600.0, step=1.0)
        last = c5.number_input("Option last price", min_value=0.0, value=1.0, step=0.05)
        vol = c6.number_input("Volume", min_value=0, value=1000, step=100)
        c7, c8, c9 = st.columns(3)
        oi = c7.number_input("Open interest", min_value=0, value=500, step=100)
        sentiment = c8.selectbox("Barchart sentiment flag", ["Not recorded", "Bullish", "Bearish"])
        bid = c9.number_input("Bid (optional)", min_value=0.0, value=0.0, step=0.05)
        submitted = st.form_submit_button("Save manual observation")
        if submitted:
            voloi = vol / oi if oi else None
            prem = last * vol * 100
            CON.execute("""INSERT INTO observations
            (imported_at,source,source_timestamp,symbol,option_type,expiration,strike,last,bid,ask,volume,open_interest,vol_oi,premium,sentiment,raw_json)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (datetime.now().isoformat(timespec="seconds"),"Manual entry","",symbol,opt_type,str(exp),strike,last,bid,None,vol,oi,voloi,prem,sentiment,"{}"))
            CON.commit()
            st.success("Observation saved.")

# ---------- Scanner ----------
with tab_scan:
    st.subheader("Unusual activity scanner")
    df = load_observations()
    if df.empty:
        st.info("No observations yet. Upload a Barchart CSV or add a manual contract in the Import tab. A small sample file is available in the repository.")
    else:
        if universe == "Starter watchlist":
            df = df[df["symbol"].str.upper().isin(WATCHLIST)]
        if not df.empty:
            df["research_score"] = df.apply(lambda r: score_row(r, horizon), axis=1)
            df = df[df["research_score"] >= min_score].copy()
            df = df.sort_values(["research_score", "premium"], ascending=False, na_position="last")
            m1,m2,m3,m4 = st.columns(4)
            m1.metric("Observations", f"{len(df):,}")
            m2.metric("Symbols", df["symbol"].nunique())
            m3.metric("Highest score", int(df["research_score"].max()) if len(df) else "—")
            m4.metric("Imported premium", money(df["premium"].sum(min_count=1)))
            show_cols = [c for c in ["symbol","option_type","expiration","strike","last","volume","open_interest","vol_oi","premium","sentiment","research_score","source_timestamp"] if c in df.columns]
            st.dataframe(df[show_cols], use_container_width=True, hide_index=True)
            st.download_button("Download filtered observations", df[show_cols].to_csv(index=False), "options_scanner_export.csv", "text/csv")
            st.caption("Premium is estimated gross premium (last price × volume × 100) when not supplied by the source. It is not net buying, opening flow, or directional capital.")
        else:
            st.info("No observations match the current universe and score filters.")

# ---------- Tracker ----------
with tab_tracker:
    st.subheader("Paper idea tracker")
    st.caption("Log a research idea here; this does not place an order.")
    with st.form("paper_idea"):
        a,b,c = st.columns(3)
        p_symbol = a.text_input("Underlying", "SPY").upper().strip()
        p_type = b.selectbox("Option type", ["CALL","PUT"])
        p_exp = c.date_input("Expiration date", key="paper_exp")
        d,e,f = st.columns(3)
        p_strike = d.number_input("Strike price", min_value=0.0, value=600.0, key="paper_strike")
        p_entry = e.number_input("Paper entry premium", min_value=0.0, value=1.0, step=0.05, key="paper_entry")
        p_horizon = f.selectbox("Horizon", ["Intraday","Swing"])
        thesis = st.text_area("Why is this worth tracking?")
        if st.form_submit_button("Add paper idea"):
            CON.execute("""INSERT INTO paper_ideas(created_at,symbol,option_type,expiration,strike,entry_premium,thesis,horizon)
            VALUES (?,?,?,?,?,?,?,?)""", (datetime.now().isoformat(timespec="seconds"),p_symbol,p_type,str(p_exp),p_strike,p_entry,thesis,p_horizon))
            CON.commit()
            st.success("Paper idea added.")
    ideas = pd.read_sql_query("SELECT * FROM paper_ideas ORDER BY id DESC", CON)
    if not ideas.empty:
        st.dataframe(ideas, use_container_width=True, hide_index=True)
        st.download_button("Export paper ideas CSV", ideas.to_csv(index=False), "paper_ideas.csv", "text/csv")
        st.markdown("**Update an idea's outcome**")
        selected_id = st.selectbox("Idea ID", ideas["id"].tolist())
        selected = ideas[ideas["id"] == selected_id].iloc[0]
        with st.form("update_idea"):
            status = st.selectbox("Status", ["Open","Win","Loss","Expired","Closed"])
            exit_price = st.number_input("Exit premium (optional)", min_value=0.0, value=float(selected["exit_premium"] or 0.0))
            notes = st.text_area("Outcome notes", value=str(selected["notes"] or ""))
            if st.form_submit_button("Update outcome"):
                CON.execute("UPDATE paper_ideas SET status=?,exit_premium=?,notes=? WHERE id=?",
                            (status, exit_price if exit_price > 0 else None, notes, int(selected_id)))
                CON.commit()
                st.success("Outcome updated. Refresh the page to see the latest values.")

# ---------- Method ----------
with tab_method:
    st.subheader("How to interpret the scanner")
    st.markdown("""
    **Experimental scoring only.** The initial 0–100 score rewards:
    - Higher volume/open-interest ratio.
    - Higher contract volume.
    - Larger estimated or source-reported premium.
    - Presence of a Barchart sentiment label.
    - Expiration fit for the selected research horizon.

    **Not included yet:** intraday relative-volume baselines, repeated trade prints, reliable trade-level bid/ask classification, underlying price/volume confirmation, Greeks-based positioning, or historical backtesting. The CSV summary page does not provide a complete options time-and-sales tape.

    **Critical caveats**
    - Call does not automatically mean bullish; put does not automatically mean bearish.
    - High volume does not prove opening activity.
    - Volume/open interest compares today's cumulative volume with open interest, generally a prior-session figure.
    - A large estimated premium does not reveal whether buyers or sellers initiated the trade.
    - Delayed data is unsuitable for precise intraday execution decisions.
    """)
    st.markdown("**Source:** [Barchart Unusual Options Activity](https://www.barchart.com/options/unusual-activity)")
    st.markdown("**Current build:** Barchart CSV/manual input only. No scraping, API key, broker connection, or order routing.")
