# Portfolio Manager - Deployment Guide

This guide shows how to deploy your Quantitative Portfolio Manager on Render.com or PythonAnywhere.

---

## 🎯 Quick Start (Render.com - RECOMMENDED)

Render.com is recommended because:
- ✅ Unlimited storage (no space errors)
- ✅ Automatic sleep/wake for web app
- ✅ Free cron jobs for daily emails
- ✅ No need for 24/7 uptime (perfect for your usage)

---

## Section 1: Render.com Deployment

### Prerequisites
- GitHub repository with your code
- Google Cloud Project with Sheets API enabled
- Gmail App Password for email notifications

### Step 1: Push Code to GitHub
```bash
cd portfolio_g

# Initialize git if not done
git init
git add .
git commit -m "Portfolio manager deployment"

# Create repository on GitHub, then:
git remote add origin https://github.com/YOUR_USERNAME/portfolio_g.git
git push -u origin main
```

### Step 2: Sign Up / Log In at Render.com
1. Go to [https://render.com](https://render.com)
2. Sign up with GitHub (free account)

### Step 3: Deploy Web Service
1. Click "New +" → "Web Service"
2. Connect your GitHub repository
3. Configure:
   - **Service Name**: `portfolio-web`
   - **Environment**: Python 3
   - **Build Command**: `pip install -r requirements.txt`
   - **Start Command**: `streamlit run app.py --server.port=$PORT --server.enableCORS=false`

### Step 4: Deploy Worker (Daily Scheduler)
1. Click "New +" → "Background Worker"
2. Connect your GitHub repository
3. Configure:
   - **Service Name**: `portfolio-worker`
   - **Environment**: Python 3
   - **Build Command**: `pip install -r requirements.txt`
   - **Start Command**: `python main.py --daily`

### Step 5: Add Environment Variables
In Render dashboard, add these environment variables:
| Key | Value |
|-----|-------|
| `GOOGLE_SHEET_ID` | Your Google Sheet ID |
| `EMAIL_SENDER` | you@gmail.com |
| `EMAIL_PASSWORD` | Your Gmail App Password (16 chars) |
| `SCREEN_MODE` | tickertape |

### Step 6: Set Cron Triggers
Add these cron triggers in Worker settings:
| Schedule | Command |
|----------|---------|
| 0 2 * * * (Daily at 8 AM IST) | `python main.py --daily` |
| 0 3 * * 6 (Saturday at 8:30 AM IST) | `python main.py --weekly` |
| 0 3 1-7 * 6 (Monthly on 1st Sat) | `python main.py --monthly` |

---

## Section 2: PythonAnywhere Deployment (Alternative)

### Prerequisites
- PythonAnywhere account (free tier works fine)
- GitHub repository with your code

### Step 1: Create Account & Push Code
Go to [https://www.pythonanywhere.com/](https://www.pythonanywhere.com/) and sign up.

Push your code or upload via File Editor.

### Step 2: Install Dependencies (Avoid Space Error)
```bash
# Use --user flag to install without venv
pip install --user -r requirements.txt

# Or install smaller packages first:
pip install --user gspread google-auth python-dotenv requests
pip install --user pandas numpy ta pyxirr yfinance plotly streamlit apscheduler
```

### Step 3: Create .env File
```bash
cd ~/portfolio_g
echo "GOOGLE_SHEET_ID=your_sheet_id" > .env
echo "EMAIL_SENDER=you@gmail.com" >> .env
echo "EMAIL_PASSWORD=your_app_password" >> .env
```

### Step 4: Configure Web App
1. Go to "Web" tab → Add a new web app (Python 3.11)
2. Set WSGI file:
```python
from streamlit.web import cli as stcli
import sys

sys.argv = ['streamlit', 'run', '/home/YOUR_USERNAME/portfolio_g/app.py', '--server.port=5000']
stcli.main()
```

### Step 5: Set Up Cron Jobs
| Schedule | Command |
|----------|---------|
| Mon-Fri 8:00 AM | `python main.py --daily` |
| Sat 9:00 AM | `python main.py --weekly` |
| 1st Sat 9:00 AM | `python main.py --monthly` |

---

## Section 3: Environment Variables

### For Render.com
Set in dashboard → Environment tab:
```bash
GOOGLE_SHEET_ID=your_actual_google_sheet_id
EMAIL_SENDER=you@gmail.com
EMAIL_PASSWORD=your_16_char_app_password
SCREEN_MODE=tickertape
```

### For PythonAnywhere
Create `.env` file:
```bash
GOOGLE_SHEET_ID=your_actual_google_sheet_id
EMAIL_SENDER=you@gmail.com
EMAIL_PASSWORD=your_16_char_app_password
```

---

## Section 4: Verification

### Test Web App
- Visit your Render.com domain (e.g., `portfolio-web.onrender.com`)
- Should load instantly and sleep when idle

### Test Daily Email
```bash
# On PythonAnywhere:
python main.py --test

# Or run manually from dashboard
```

### Test Google Sheets Connection
- Check Holdings tab loads in dashboard
- Verify portfolio value displays

---

## Section 5: Troubleshooting

| Issue | Solution |
|-------|----------|
| Space error on PythonAnywhere | Use `pip install --user -r requirements.txt` |
| Email not sending | Verify Gmail App Password |
| Web app sleeps | That's normal - click to wake up |
| Cron not triggering | Check Render cron trigger settings |

---

## Section 6: Costs

### Render.com (Free Tier)
- ✅ Unlimited storage
- ✅ 750 hours/month active time (your app sleeps when idle)
- ✅ Free cron jobs
- ⚠️ Web app wakes on first request

### PythonAnywhere (Free Tier)
- ✅ 512MB RAM
- ✅ Cron jobs available
- ⚠️ Limited storage (may need `--user` flag)

---

## Section 7: My Recommendation

**Use Render.com** because:
1. Your usage pattern (5 min/day) matches perfectly
2. No space constraints
3. Automatic sleep saves resources
4. Simple deployment process
5. Free cron jobs for daily notifications

Just follow **Section 1** above and you're good to go!
