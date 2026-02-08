import time
import sqlite3
from datetime import datetime, timezone, timedelta

import requests
import pandas as pd
import streamlit as st
import matplotlib.pyplot as plt

# =========================
# CONFIG
# =========================
DEFAULT_SITE = "09429100"  # USGS: Colorado River Below Palo Verde Dam
USGS_IV_URL = "https://waterservices.usgs.gov/nwis/iv/"
OPEN_METEO_URL = "https://api.open-meteo.com/v1/forecast"
DB_PATH = "levels.sqlite"

# Shaggy Tree coordinates
LAT = 33.891584
LON = -114.524107

# USGS parameter codes
PARAM_GAGE_HEIGHT = "00065"  # ft
PARAM_WATER_TEMP = "00010"   # °C

# =========================
# HELPERS
# =========================
def c_to_f(c): return (c * 9 / 5) + 32 if c is not None else None
def mps_to_mph(mps): return mps * 2.23694 if mps is not None else None
def fmt(v, d=2): return "N/A" if v is None else f"{v:.{d}f}"

# =========================
# DATABASE
# =========================
def init_db():
    with sqlite3.connect(DB_PATH) as con:
        con.execute("""
            CREATE TABLE IF NOT EXISTS readings (
                id INTEGER PRIMARY KEY,
                ts_utc TEXT,
                gage_height_ft REAL,
                water_temp_c REAL,
                air_temp_c REAL,
                wind_mph REAL
            )
        """)

def store_row(ts, gh, wt, at, wind):
    with sqlite3.connect(DB_PATH) as con:
        con.execute(
            "INSERT INTO readings VALUES (NULL, ?, ?, ?, ?, ?)",
            (ts, gh, wt, at, wind)
        )

def load_last_24h():
    since = datetime.now(timezone.utc) - timedelta(hours=24)
    with sqlite3.connect(DB_PATH) as con:
        df = pd.read_sql(
            "SELECT * FROM readings WHERE ts_utc >= ? ORDER BY ts_utc",
            con,
            params=(since.isoformat(),)
        )
    if not df.empty:
        df["ts_utc"] = pd.to_datetime(df["ts_utc"], utc=True)
    return df

# =========================
# DATA FETCH
# =========================
def fetch_usgs():
    params = {
        "format": "json",
        "sites": DEFAULT_SITE,
        "parameterCd": f"{PARAM_GAGE_HEIGHT},{PARAM_WATER_TEMP}"
    }
    r = requests.get(USGS_IV_URL, params=params, timeout=20)
    r.raise_for_status()
    js = r.json()

    gh = wt = ts = None
    for s in js["value"]["timeSeries"]:
        code = s["variable"]["variableCode"][0]["value"]
        val = s["values"][0]["value"][-1]
        ts = val["dateTime"]
        if code == PARAM_GAGE_HEIGHT:
            gh = float(val["value"])
        if code == PARAM_WATER_TEMP:
            wt = float(val["value"])
    return ts, gh, wt

def fetch_weather():
    params = {
        "latitude": LAT,
        "longitude": LON,
        "current": "temperature_2m,wind_speed_10m",
        "timezone": "UTC"
    }
    r = requests.get(OPEN_METEO_URL, params=params, timeout=20)
    r.raise_for_status()
    cur = r.json()["current"]
    return cur["time"], cur["temperature_2m"], mps_to_mph(cur["wind_speed_10m"])

# =========================
# APP START
# =========================
st.set_page_config(page_title="Shaggy Tree River Watch", layout="wide")
init_db()

# =========================
# STYLES
# =========================
st.markdown("""
<style>
.title { font-size:36px; font-weight:800; }
.subtitle { opacity:0.8; margin-bottom:20px; }
.section { font-size:22px; font-weight:700; margin-top:30px; }
.card { padding:18px; border-radius:16px; border:1px solid rgba(255,255,255,.15); }
.value { font-size:28px; font-weight:800; }
.label { font-size:13px; opacity:0.85; }
</style>
""", unsafe_allow_html=True)

# =========================
# HEADER
# =========================
st.markdown('<div class="title">Shaggy Tree River Watch</div>', unsafe_allow_html=True)
st.markdown(
    '<div class="subtitle">Live Colorado River & weather conditions near Shaggy Tree · Units: ft · °F · mph</div>',
    unsafe_allow_html=True
)

# =========================
# FETCH LIVE
# =========================
try:
    ts_r, gh, wt = fetch_usgs()
    ts_w, at, wind = fetch_weather()
    ts = ts_r or ts_w
except Exception as e:
    st.error(f"Data fetch error: {e}")
    st.stop()

# =========================
# CURRENT CONDITIONS
# =========================
st.markdown('<div class="section">Current Conditions</div>', unsafe_allow_html=True)

c1, c2, c3, c4 = st.columns(4)
with c1:
    st.markdown(f'<div class="card"><div class="label">River Level</div><div class="value">{fmt(gh)} ft</div></div>', unsafe_allow_html=True)
with c2:
    st.markdown(f'<div class="card"><div class="label">Water Temp</div><div class="value">{fmt(c_to_f(wt),1)} °F</div></div>', unsafe_allow_html=True)
with c3:
    st.markdown(f'<div class="card"><div class="label">Air Temp</div><div class="value">{fmt(c_to_f(at),1)} °F</div></div>', unsafe_allow_html=True)
with c4:
    st.markdown(f'<div class="card"><div class="label">Wind</div><div class="value">{fmt(wind,1)} mph</div></div>', unsafe_allow_html=True)

st.caption(f"Last updated (UTC): {ts}")

# =========================
# STORE SNAPSHOT BUTTON
# =========================
if st.button("Fetch & store latest now"):
    store_row(ts, gh, wt, at, wind)
    st.success("Snapshot stored.")

# =========================
# LAST 24 HOURS
# =========================
st.markdown('<div class="section">Last 24 Hours</div>', unsafe_allow_html=True)
df = load_last_24h()

if df.empty:
    st.info("No stored data yet. Click 'Fetch & store latest now' a few times.")
else:
    def plot(col, label):
        if df[col].notna().any():
            fig = plt.figure()
            plt.plot(df["ts_utc"], df[col])
            plt.ylabel(label)
            plt.xlabel("Time (UTC)")
            st.pyplot(fig)

    plot("gage_height_ft", "River Level (ft)")
    plot("water_temp_c", "Water Temp (°C)")
    plot("air_temp_c", "Air Temp (°C)")
    plot("wind_mph", "Wind (mph)")

    with st.expander("View raw data"):
        st.dataframe(df, use_container_width=True)
