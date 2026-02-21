"""
fxlens/fetch_data.py
====================
Fetches live FX data and stores it in data/fx_data.db (SQLite).

Sources (all FREE):
  - Policy rates  : FRED API (api.stlouisfed.org)  — requires free API key
  - Spot rates    : exchangerate.host               — no key needed
  - Realised vol  : computed from 30-day spot history (exchangerate.host)

Run manually:          python fetch_data.py
Run on a schedule:     see scheduler.py  (or use cron / GitHub Actions)
"""

import os
import json
import math
import sqlite3
import datetime
import requests

# ── CONFIG ────────────────────────────────────────────────────────────────────
FRED_API_KEY = os.environ.get("FRED_API_KEY", "YOUR_FRED_API_KEY_HERE")
# Get a free key at: https://fred.stlouisfed.org/docs/api/api_key.html

DB_PATH = os.path.join(os.path.dirname(__file__), "data", "fx_data.db")

# ── CURRENCY DEFINITIONS ──────────────────────────────────────────────────────
# name, group, FRED series ID for the central bank policy rate
# GCC currencies are USD-pegged — vol is near-zero by definition
CURRENCIES = [
    # code         full name                  group     FRED series (policy rate)
    ("EUR", "Euro",                           "G10",    "ECBDFR"),          # ECB Deposit Facility Rate
    ("JPY", "Japanese Yen",                   "G10",    "IRSTCI01JPM156N"), # BOJ overnight call rate
    ("GBP", "British Pound",                  "G10",    "BOEBR"),           # BOE Bank Rate
    ("CHF", "Swiss Franc",                    "G10",    "SNBPOLFCIR"),      # SNB policy rate
    ("AUD", "Australian Dollar",              "G10",    "RBATCTR"),         # RBA cash rate
    ("NZD", "New Zealand Dollar",             "G10",    "RBNZOCR"),         # RBNZ OCR
    ("CAD", "Canadian Dollar",                "G10",    "CAPCBEPCBREPO"),   # BOC overnight rate
    ("NOK", "Norwegian Krone",                "Europe", "IRSTCI01NOM156N"), # Norges Bank
    ("DKK", "Danish Krone",                   "Europe", "IRSTCI01DKM156N"), # Danmarks Nationalbank
    ("PLN", "Polish Zloty",                   "Europe", "IRSTCI01PLM156N"), # NBP
    ("MXN", "Mexican Peso",                   "EM",     "IRSTCI01MXM156N"), # Banxico
    # GCC — pegged to USD, near-zero vol. Use approximate spreads vs Fed.
    ("SAR", "Saudi Riyal",                    "GCC",    None),  # SAMA ~Fed + 1.0%
    ("AED", "UAE Dirham",                     "GCC",    None),  # CBUAE ~Fed - 0.1%
    ("OMR", "Omani Rial",                     "GCC",    None),  # CBO   ~Fed + 0.5%
    ("KWD", "Kuwaiti Dinar",                  "GCC",    None),  # CBK   ~Fed + 0.0%
    ("QAR", "Qatari Riyal",                   "GCC",    None),  # QCB   ~Fed + 0.6%
    ("BHD", "Bahraini Dinar",                 "GCC",    None),  # CBB   ~Fed + 1.0%
]

# GCC spread over Fed Funds (approximate, updated manually when central banks move)
GCC_SPREADS = {
    "SAR": 1.00,
    "AED": -0.10,
    "OMR": 0.50,
    "KWD": 0.00,
    "QAR": 0.60,
    "BHD": 1.00,
}

# GCC fixed spot rates (these move <0.01% annually, update manually if needed)
GCC_SPOTS = {
    "SAR": 3.7500,
    "AED": 3.6725,
    "OMR": 0.3850,
    "KWD": 0.3075,
    "QAR": 3.6400,
    "BHD": 0.3770,
}

# Historical carry/vol ratios (estimated from rate & vol archives)
# Structure: { "CODE": {"1Y": x, "3Y": x, "5Y": x, "10Y": x} }
HIST_RATIOS = {
    "EUR": {"1Y": -0.33, "3Y": -0.20, "5Y": -0.14, "10Y": -0.07},
    "JPY": {"1Y": -0.43, "3Y": -0.36, "5Y": -0.26, "10Y": -0.19},
    "GBP": {"1Y":  0.00, "3Y": -0.06, "5Y":  0.00, "10Y": -0.03},
    "CHF": {"1Y": -0.63, "3Y": -0.40, "5Y": -0.49, "10Y": -0.33},
    "AUD": {"1Y": -0.05, "3Y": -0.03, "5Y": -0.02, "10Y":  0.13},
    "NZD": {"1Y": -0.03, "3Y":  0.05, "5Y":  0.06, "10Y":  0.16},
    "CAD": {"1Y": -0.06, "3Y":  0.00, "5Y": -0.03, "10Y":  0.01},
    "NOK": {"1Y": -0.05, "3Y": -0.03, "5Y": -0.08, "10Y":  0.00},
    "DKK": {"1Y": -0.86, "3Y": -0.53, "5Y": -0.43, "10Y": -0.25},
    "PLN": {"1Y":  0.08, "3Y":  0.26, "5Y":  0.19, "10Y":  0.11},
    "MXN": {"1Y":  0.41, "3Y":  0.41, "5Y":  0.38, "10Y":  0.39},
    "SAR": {"1Y":  0.72, "3Y":  0.52, "5Y":  0.38, "10Y":  0.25},
    "AED": {"1Y": -0.08, "3Y": -0.05, "5Y": -0.04, "10Y": -0.02},
    "OMR": {"1Y":  0.40, "3Y":  0.32, "5Y":  0.27, "10Y":  0.18},
    "KWD": {"1Y":  0.05, "3Y":  0.08, "5Y":  0.12, "10Y":  0.20},
    "QAR": {"1Y":  0.52, "3Y":  0.40, "5Y":  0.30, "10Y":  0.20},
    "BHD": {"1Y":  0.72, "3Y":  0.55, "5Y":  0.42, "10Y":  0.28},
}

# ── DATABASE SETUP ────────────────────────────────────────────────────────────
def init_db():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    con = sqlite3.connect(DB_PATH)
    con.execute("""
        CREATE TABLE IF NOT EXISTS fx_snapshots (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            fetched_at  TEXT NOT NULL,
            code        TEXT NOT NULL,
            name        TEXT,
            grp         TEXT,
            spot        REAL,
            policy_rate REAL,
            fed_rate    REAL,
            carry       REAL,
            vol_1m      REAL,
            ratio_now   REAL,
            hist_1y     REAL,
            hist_3y     REAL,
            hist_5y     REAL,
            hist_10y    REAL
        )
    """)
    con.execute("""
        CREATE TABLE IF NOT EXISTS spot_history (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            date       TEXT NOT NULL,
            code       TEXT NOT NULL,
            spot       REAL,
            UNIQUE(date, code)
        )
    """)
    con.commit()
    return con

# ── FRED: FETCH POLICY RATE ───────────────────────────────────────────────────
def fetch_fred_rate(series_id):
    """Return the latest value for a FRED series."""
    url = "https://api.stlouisfed.org/fred/series/observations"
    params = {
        "series_id":     series_id,
        "api_key":       FRED_API_KEY,
        "file_type":     "json",
        "sort_order":    "desc",
        "limit":         1,
        "observation_start": "2020-01-01",
    }
    r = requests.get(url, params=params, timeout=10)
    r.raise_for_status()
    obs = r.json().get("observations", [])
    if obs and obs[0]["value"] != ".":
        return float(obs[0]["value"])
    return None

# ── EXCHANGE RATE: SPOT + HISTORY ─────────────────────────────────────────────
def fetch_spot_rates(codes):
    """Fetch today's spot rates vs USD from exchangerate.host (free, no key)."""
    symbols = ",".join(codes)
    url = f"https://api.exchangerate.host/latest?base=USD&symbols={symbols}"
    r = requests.get(url, timeout=10)
    r.raise_for_status()
    data = r.json()
    return data.get("rates", {})

def fetch_spot_history(code, days=35):
    """Fetch daily spot rates for a currency over the last N days."""
    end   = datetime.date.today()
    start = end - datetime.timedelta(days=days)
    url   = (f"https://api.exchangerate.host/timeseries"
             f"?base=USD&symbols={code}&start_date={start}&end_date={end}")
    r = requests.get(url, timeout=15)
    r.raise_for_status()
    rates_by_date = r.json().get("rates", {})
    # returns {date_str: {code: rate}}
    return {d: v[code] for d, v in sorted(rates_by_date.items()) if code in v}

# ── REALISED VOLATILITY ───────────────────────────────────────────────────────
def compute_realised_vol(spot_series: dict) -> float:
    """
    Compute annualised 1M realised volatility from a dict of {date: spot}.
    Uses log-return std * sqrt(252).
    """
    prices = list(spot_series.values())
    if len(prices) < 5:
        return None
    log_rets = [math.log(prices[i] / prices[i-1]) for i in range(1, len(prices))]
    mean = sum(log_rets) / len(log_rets)
    variance = sum((r - mean) ** 2 for r in log_rets) / (len(log_rets) - 1)
    daily_std = math.sqrt(variance)
    return round(daily_std * math.sqrt(252) * 100, 2)  # annualised %

# ── MAIN FETCH ────────────────────────────────────────────────────────────────
def fetch_and_store():
    print(f"\n{'='*60}")
    print(f"  fxlens data fetch — {datetime.datetime.now().strftime('%Y-%m-%d %H:%M')}")
    print(f"{'='*60}")

    con = init_db()
    fetched_at = datetime.datetime.utcnow().isoformat()

    # 1. Fed Funds Rate
    print("\n[1/4] Fetching Fed Funds Rate from FRED...")
    try:
        fed_rate = fetch_fred_rate("FEDFUNDS")
        print(f"      Fed Funds: {fed_rate}%")
    except Exception as e:
        print(f"      ERROR: {e} — using fallback 3.75%")
        fed_rate = 3.75

    # 2. Spot rates
    non_gcc_codes = [c[0] for c in CURRENCIES if c[3] is not None]
    print(f"\n[2/4] Fetching spot rates for {non_gcc_codes}...")
    try:
        spot_rates = fetch_spot_rates(non_gcc_codes)
        print(f"      Got {len(spot_rates)} rates")
    except Exception as e:
        print(f"      ERROR: {e}")
        spot_rates = {}

    # 3. Policy rates from FRED
    print("\n[3/4] Fetching central bank policy rates from FRED...")
    policy_rates = {}
    for code, name, grp, fred_series in CURRENCIES:
        if fred_series is None:
            continue
        try:
            rate = fetch_fred_rate(fred_series)
            policy_rates[code] = rate
            print(f"      {code}: {rate}%")
        except Exception as e:
            print(f"      {code}: ERROR — {e}")
            policy_rates[code] = None

    # 4. Realised vol per currency
    print("\n[4/4] Computing 1M realised volatility from spot history...")
    rows = []
    for code, name, grp, fred_series in CURRENCIES:
        is_gcc = (fred_series is None)

        # Spot
        if is_gcc:
            spot = GCC_SPOTS.get(code, None)
        else:
            # exchangerate.host returns rates as: how many CODE per 1 USD
            raw = spot_rates.get(code)
            # For pairs quoted as USD/CCY (EUR, GBP, CHF, AUD, NZD) invert
            if raw and code in ("EUR", "GBP", "CHF", "AUD", "NZD"):
                spot = round(1 / raw, 4)
            else:
                spot = raw

        # Policy rate
        if is_gcc:
            policy_rate = fed_rate + GCC_SPREADS.get(code, 0)
        else:
            policy_rate = policy_rates.get(code) or fed_rate

        carry = round(policy_rate - fed_rate, 2)

        # Vol
        if is_gcc:
            vol = 0.8  # structural near-zero due to peg
        else:
            try:
                history = fetch_spot_history(code, days=35)
                # Store history in DB
                for d, s in history.items():
                    con.execute(
                        "INSERT OR IGNORE INTO spot_history(date,code,spot) VALUES(?,?,?)",
                        (d, code, s)
                    )
                vol = compute_realised_vol(history)
            except Exception as e:
                print(f"      {code} vol error: {e}")
                vol = None

        # Ratio
        ratio = round(carry / vol, 3) if vol and vol > 0 else None

        hist = HIST_RATIOS.get(code, {"1Y": None, "3Y": None, "5Y": None, "10Y": None})

        print(f"      {code:4s} | spot={spot} | carry={carry:+.2f}% | vol={vol}% | C/V={ratio}")

        rows.append((
            fetched_at, code, name, grp,
            spot, policy_rate, fed_rate, carry, vol, ratio,
            hist["1Y"], hist["3Y"], hist["5Y"], hist["10Y"]
        ))

    # Write snapshot to DB
    con.executemany("""
        INSERT INTO fx_snapshots
        (fetched_at, code, name, grp, spot, policy_rate, fed_rate, carry, vol_1m,
         ratio_now, hist_1y, hist_3y, hist_5y, hist_10y)
        VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)
    """, rows)
    con.commit()
    con.close()

    print(f"\n✓ Stored {len(rows)} rows to {DB_PATH}")
    print(f"  Timestamp: {fetched_at}\n")


if __name__ == "__main__":
    fetch_and_store()
