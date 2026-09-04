# 🟣 Deploying ANTItrading to Heroku (with Student Credits)

Heroku provides **$13/month in platform credits for 12 months** via the **GitHub Student Developer Pack**. 

Because a Heroku **Basic Dyno is only $7/month** (or Eco Dyno pool for $5/month), your entire ANTItrading 24/7 background worker will be **100% free** under your student credits.

---

## ⚠️ The Ephemeral Filesystem Solution
Heroku dynos reboot at least once every 24 hours (daily dyno cycling), resetting the local filesystem.

To prevent losing your portfolio state (`state/portfolio.json`, `state/trade_log.csv`, etc.), our Heroku worker uses **Git-backed persistence**:
* Every time a pass runs, it pulls the latest state from GitHub using a `GITHUB_TOKEN`.
* After computing decisions and updating portfolio files, it commits and pushes `state/` back to your GitHub repository automatically (`[skip ci]`).
* Your state is permanently preserved on GitHub, surviving all restarts and re-deployments!

---

## 🚀 Step 1: Claim Your Heroku Student Credit
1. Go to your [GitHub Student Developer Pack](https://education.github.com/pack/offers).
2. Claim the **Heroku $13/month offer** and apply it to your Heroku account.

---

## 🔑 Step 2: Generate a GitHub Personal Access Token (PAT)
To allow your Heroku dyno to push state updates back to your repository:
1. In GitHub, click your profile picture (top right) -> **Settings**.
2. Scroll down to the bottom left -> **Developer Settings** -> **Personal access tokens** -> **Tokens (classic)**.
3. Click **Generate new token** -> **Generate new token (classic)**.
   * **Note:** `ANTItrading Heroku Bot`
   * **Expiration:** 90 days or No expiration
   * **Scopes:** Check ☑️ **`repo`** (Full control of private/public repositories).
4. Click **Generate token** and copy the `ghp_...` token string.

---

## 🛠️ Step 3: Create & Configure the Heroku App

### Option A: Using the Heroku Web Dashboard (No CLI needed)
1. Go to [dashboard.heroku.com](https://dashboard.heroku.com/) and click **New** -> **Create new app** (e.g., `antitrader-bot`).
2. Go to **Settings** -> **Config Vars** -> **Reveal Config Vars**, and add these keys:
   * `GITHUB_TOKEN` = `ghp_yourCopiedTokenHere...`
   * `GITHUB_REPO` = `mrismail-m/ANTItrading`
   * `DISCORD_WEBHOOK_URL` = `https://discord.com/api/webhooks/...`
   * `SCHEDULE_MINUTE` = `15` *(Runs hourly at minute 15)*
3. Go to the **Deploy** tab:
   * Deployment method: Click **GitHub**.
   * Connect to your GitHub repository: `mrismail-m/ANTItrading`.
   * Under **Manual deploy**, select branch `main` and click **Deploy Branch**.
4. Go to the **Resources** tab:
   * Turn **ON** the `worker` dyno (`python3 deploy/heroku_worker.py`).
   * Turn **OFF** any `web` dyno if present.

---

### Option B: Using the Heroku CLI (Fast terminal setup)

If you have the Heroku CLI installed (`sudo snap install --classic heroku` or `brew install heroku`):

```bash
# 1. Login to Heroku
heroku login

# 2. Create the app
heroku create antitrader-bot

# 3. Configure your secrets
heroku config:set GITHUB_TOKEN="ghp_yourCopiedTokenHere..."
heroku config:set GITHUB_REPO="mrismail-m/ANTItrading"
heroku config:set DISCORD_WEBHOOK_URL="https://discord.com/api/webhooks/..."
heroku config:set SCHEDULE_MINUTE="15"

# 4. Deploy your code
git push heroku main

# 5. Enable the 24/7 background worker
heroku ps:scale worker=1
```

---

## 📊 Step 4: Monitor & Verify

### View Live Execution Logs:
In the Heroku Web Dashboard, click **More** -> **View logs**, or run:
```bash
heroku logs --tail --dyno worker
```

### Trigger an Instant One-Off Pass:
You can manually test a pass anytime without waiting for the next hour:
```bash
heroku run bash deploy/heroku_run.sh
```

---

## 💰 Monthly Credit Breakdown
* **Monthly Student Credit:** $13.00 USD
* **Basic Dyno Cost (24/7 continuous worker):** $7.00 USD
* **Remaining Credit:** **+$6.00 USD surplus every month**
* **Total Cost to You:** **$0.00**
