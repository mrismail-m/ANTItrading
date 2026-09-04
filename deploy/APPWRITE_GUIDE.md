# ☁️ Deploying ANTItrading on Appwrite Cloud Functions

Appwrite is an active partner in the **GitHub Student Developer Pack**, offering **Appwrite Cloud Pro credits** for students.

Appwrite Functions provides a fast, managed serverless environment with **built-in Cron Schedules**, eliminating all local server maintenance and queue delays.

---

## 🛠️ Architecture: Stateless Function + Git-Backed Persistence

Because Appwrite serverless containers are stateless:
1. On each scheduled execution (minute 15 of every hour), the function pulls the latest state from your GitHub repository via `GITHUB_TOKEN`.
2. It evaluates live Binance market data, news sentiment, and the **BTC Macro Flush Circuit Breaker**.
3. It dispatches your Discord notifications.
4. It automatically commits and pushes updated `state/` files back to GitHub (`[skip ci]`).

---

## 🚀 Step 1: Claim Your Appwrite Student Benefit
1. Go to your [GitHub Student Developer Pack](https://education.github.com/pack/offers).
2. Claim the **Appwrite Cloud Pro** offer.
3. Sign in to [cloud.appwrite.io](https://cloud.appwrite.io/).

---

## 🔑 Step 2: Ensure You Have a GitHub Token (PAT)
To allow Appwrite to push updated portfolio state back to GitHub:
1. In GitHub -> **Settings** -> **Developer settings** -> **Personal access tokens** -> **Tokens (classic)**.
2. Generate a token with the ☑️ **`repo`** scope.
3. Copy your `ghp_...` token.

---

## ⚡ Step 3: Create the Appwrite Function

1. In your Appwrite Cloud project, click **Functions** on the left menu.
2. Click **Create function** -> choose **Connect with GitHub**.
3. Authorize Appwrite and select repository: **`mrismail-m/ANTItrading`**.
4. Configure the function settings:
   * **Function Name:** `antitrader`
   * **Runtime:** `Python 3.11` (or `Python 3.10`)
   * **Root Directory:** `./`
   * **Entrypoint:** `main.py`
   * **Build Commands:** `apk add --no-cache git && pip install -r requirements.txt`
5. Configure the **Schedule (Cron)**:
   * **Schedule:** `15 * * * *` *(Runs at minute 15 of every hour, 24 times a day)*
   * **Timeout:** `900` seconds (Maximum 15 minutes)
6. Add **Environment Variables**:
   * `GITHUB_TOKEN` = `ghp_yourTokenHere...`
   * `GITHUB_REPO` = `mrismail-m/ANTItrading`
   * `DISCORD_WEBHOOK_URL` = `https://discord.com/api/webhooks/...`
7. Click **Create** or **Deploy**. Appwrite will build the Python container and install all dependencies.

---

## 🧪 Step 4: Test & Verify

### 1. Manual Execution:
In the Appwrite Console:
1. Go to **Functions** -> **antitrader**.
2. Click **Execute now** (select `GET` or `POST`).
3. Click the execution entry to view real-time execution logs.

You will see:
```
🚀 ANTItrading Appwrite Function Triggered.
📥 Pulling latest state from GitHub...
🧠 Executing live trading pass...
✅ Pass completed! Equity: $10,075.69 USD | Cash: $6,613.94 USD
💾 Committing and pushing state updates to GitHub...
✅ Successfully pushed state updates to GitHub.
```

### 2. Scheduled Runs:
Appwrite's built-in scheduler will automatically trigger the function at **minute 15 of every hour**, completely serverless and 24/7.
