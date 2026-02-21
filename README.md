# fxlens 📡
**FX Carry × Volatility Dashboard**

Real-time scatter chart and table showing carry (interest rate differential vs USD)
and 1-month realised volatility for 18 currencies, with historical carry/vol ratios
across 1Y, 3Y, 5Y, and 10Y horizons.

---

## Architecture

```
fetch_data.py   →   data/fx_data.db   →   app.py (Streamlit)
    ↑
scheduler.py (or GitHub Actions cron)
```

**Data sources (all free):**
| Data | Source | API Key? |
|---|---|---|
| Policy rates (carry input) | FRED API (St. Louis Fed) | Yes — free |
| Spot rates + history (vol) | exchangerate.host | No |
| GCC spot rates | Hardcoded (pegged) | N/A |

---

## Setup — Local

### 1. Clone and install

```bash
git clone https://github.com/YOUR_USERNAME/fxlens.git
cd fxlens
pip install -r requirements.txt
```

### 2. Get a free FRED API key

Go to: https://fred.stlouisfed.org/docs/api/api_key.html
Takes 30 seconds. Paste the key into your environment:

```bash
export FRED_API_KEY="your_key_here"

# Or create a .env file:
echo 'FRED_API_KEY=your_key_here' > .env
```

### 3. Fetch data for the first time

```bash
python fetch_data.py
```

You'll see live output as it pulls rates and computes vol. Takes ~30 seconds.

### 4. Run the dashboard

```bash
streamlit run app.py
```

Opens at http://localhost:8501

### 5. Keep data fresh (pick one)

**Option A — Background scheduler (simple):**
```bash
python scheduler.py   # runs every 6 hours, keeps going until you stop it
```

**Option B — Cron job (recommended for always-on machines):**
```bash
crontab -e
# Add this line:
0 */6 * * * cd /path/to/fxlens && FRED_API_KEY=xxx python fetch_data.py >> logs/fetch.log 2>&1
```

---

## Deploy — Streamlit Cloud (free, public URL)

This gets you a public URL anyone can visit, for free.

### 1. Push to GitHub

```bash
git init
git add .
git commit -m "initial commit"
git remote add origin https://github.com/YOUR_USERNAME/fxlens.git
git push -u origin main
```

### 2. Deploy on Streamlit Cloud

1. Go to **https://share.streamlit.io**
2. Click **New app**
3. Connect your GitHub repo
4. Set **Main file path** to `app.py`
5. Click **Advanced settings → Secrets** and add:
   ```
   FRED_API_KEY = "your_fred_api_key_here"
   ```
6. Click **Deploy**

Your app is now live at `https://your-app-name.streamlit.app` 🎉

### 3. Auto-update data with GitHub Actions (free)

Add your FRED key to GitHub Secrets:
- Repo → Settings → Secrets and variables → Actions → New repository secret
- Name: `FRED_API_KEY`, Value: your key

The workflow in `.github/workflows/fetch.yml` will then:
- Fetch new data every 6 hours automatically
- Commit the updated `data/fx_data.db` back to the repo
- Streamlit Cloud picks up the new data on next page load

**Total cost: $0.**

---

## Alternative: Deploy on Railway or Render

For a more persistent deployment (runs 24/7, no sleep):

**Railway (free tier, ~$5/mo for always-on):**
```bash
# Install Railway CLI
npm install -g @railway/cli
railway login
railway new
railway up
railway variables set FRED_API_KEY=your_key
```

Set start command to: `streamlit run app.py --server.port $PORT --server.address 0.0.0.0`

---

## File Structure

```
fxlens/
├── app.py              # Streamlit dashboard
├── fetch_data.py       # Data fetcher (FRED + exchangerate.host)
├── scheduler.py        # Background refresh loop
├── requirements.txt    # Python dependencies
├── .gitignore
├── .streamlit/
│   └── secrets.toml    # Local secrets (never commit this)
├── .github/
│   └── workflows/
│       └── fetch.yml   # GitHub Actions auto-fetch cron
├── data/
│   └── fx_data.db      # SQLite database (auto-created)
└── logs/               # Fetch logs (auto-created)
```

---

## Updating Historical Carry/Vol

The `hist_1y`, `hist_3y`, `hist_5y`, `hist_10y` figures in `fetch_data.py`
are manually curated estimates based on central bank rate archives and
historical vol data. To update them with precise figures, pull historical
rates from FRED for each currency and historical realised vol from a
provider like Polygon.io or Bloomberg, then recompute averages per period.

---

## Currency Coverage

| Group | Currencies |
|---|---|
| G10 | EUR, JPY, GBP, CHF, AUD, NZD, CAD |
| Europe | NOK, DKK, PLN |
| EM | MXN |
| GCC (USD-pegged) | SAR, AED, OMR, KWD, QAR, BHD |
