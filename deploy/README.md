# ☁️ Hosting ANTItrading on Oracle Cloud Infrastructure (Always Free Tier)

Oracle Cloud Infrastructure (OCI) provides a generous **Always Free Tier** that **never expires**. This allows you to run ANTItrading 24/7 on a dedicated Linux VPS with exact-minute timing precision, zero queue latency, and persistent disk storage.

---

## 📋 Free Resources Allocated by Oracle Cloud
Under the Always Free Tier, you are entitled to:
* **Option A (Simplest):** Up to 2 AMD-based Compute VMs (`VM.Standard.E2.1.Micro`, 1 OCPU, 1 GB RAM each) for life.
* **Option B (Powerful):** Up to 4 OCPUs and 24 GB RAM on Arm-based Ampere A1 Compute instances (can be 1 single VM or divided).
* **Storage:** 200 GB total block volume storage.

---

## 🚀 Step 1: Create Your Free Oracle Cloud Instance

1. **Sign Up:** Go to [oracle.com/cloud/free/](https://www.oracle.com/cloud/free/) and register for an Always Free account.
2. **Open the Console:** Go to **Menu ☰** -> **Compute** -> **Instances**.
3. **Click "Create Instance"**:
   * **Name:** `antitrader-vps`
   * **Image and Shape:**
     * **Image:** `Canonical Ubuntu 24.04` (or `Ubuntu 22.04 Minimal`)
     * **Shape:**
       * *Either* **VM.Standard.E2.1.Micro** (Always Free Eligible AMD)
       * *Or* **VM.Standard.A1.Flex** (Ampere ARM, 1-2 OCPUs, 4-6 GB RAM — Always Free Eligible)
   * **Networking:**
     * Select "Create new Virtual Cloud Network (VCN)" and "Create new public subnet".
     * Make sure **"Assign a public IPv4 address"** is set to **Yes**.
   * **Add SSH Keys:**
     * Choose **"Generate a key pair for me"** and save both the **Private Key** (`.key`) and **Public Key** (`.pub`) to your computer.
     * *(Or paste your existing public SSH key from your local machine).*
   * **Boot Volume:** Leave as default (50 GB).
4. **Click "Create"** and wait ~60 seconds until the instance state turns green (**RUNNING**).
5. **Note the Public IP Address** from the instance details page.

---

## 🔑 Step 2: Connect via SSH

On your local machine (Linux/macOS terminal or Windows PowerShell), connect using your saved private key:

```bash
# Secure private key file permissions (Linux / macOS)
chmod 400 /path/to/your-oracle-key.key

# SSH into the server (default username is 'ubuntu')
ssh -i /path/to/your-oracle-key.key ubuntu@<YOUR_ORACLE_PUBLIC_IP>
```

---

## ⚡ Step 3: Run the 1-Step Provisioning Script

Once logged into your Oracle VPS, run the turnkey setup script directly from GitHub:

```bash
curl -fsSL https://raw.githubusercontent.com/mrismail-m/ANTItrading/main/deploy/setup_oracle_vps.sh | sudo bash
```

*(Alternatively, if you prefer cloning first manually:)*
```bash
git clone https://github.com/mrismail-m/ANTItrading.git /opt/ANTItrading
cd /opt/ANTItrading
sudo bash deploy/setup_oracle_vps.sh
```

### What this script configures automatically:
* Installs Python 3, venv, pip, git, and logrotate.
* Clones/updates the repository in `/opt/ANTItrading`.
* Builds an isolated Python virtual environment (`venv`) with all dependencies (`requests`, `pandas`, `ta`, etc.).
* Sets up an hourly **systemd timer** (`antitrader.timer`) running at minute 15 of every hour with high precision.
* Configures automatic log rotation at `/var/log/antitrader.log` so the disk never fills up.

---

## ⚙️ Step 4: Configure Webhooks & Environment Variables

Edit the environment file on your server to set your Discord notification webhook:

```bash
nano /opt/ANTItrading/.env
```

Paste your webhook URL:
```env
DISCORD_WEBHOOK_URL=https://discord.com/api/webhooks/...
```
Save and exit (`Ctrl + O`, `Enter`, `Ctrl + X`).

---

## 🔄 Step 5: (Optional) Allow VPS to Push State Commits to GitHub

If you want the Oracle VPS to automatically commit and push state updates back to your GitHub repository:

1. On the Oracle VPS, generate a dedicated SSH deploy key:
   ```bash
   ssh-keygen -t ed25519 -C "oracle-antitrader" -f ~/.ssh/id_ed25519 -N ""
   cat ~/.ssh/id_ed25519.pub
   ```
2. Copy the output.
3. Open your GitHub Repository in your browser:
   * **Settings** -> **Deploy Keys** -> **Add deploy key**.
   * **Title:** `Oracle VPS Deploy Key`.
   * **Key:** Paste the public key.
   * **Check:** ☑️ **"Allow write access"**.
   * Click **Add key**.
4. On the Oracle VPS, change the git origin from HTTPS to SSH:
   ```bash
   cd /opt/ANTItrading
   git remote set-url origin git@github.com:mrismail-m/ANTItrading.git
   ```

Now every hourly pass executed by the VPS will automatically commit its results and push them to your GitHub repository!

---

## 🛠️ Useful Management Commands

| Action | Command |
| :--- | :--- |
| **Check timer schedule & next run** | `systemctl list-timers antitrader.timer` |
| **Trigger an immediate manual pass** | `sudo systemctl start antitrader.service` |
| **Watch live paper-trading execution** | `tail -f /var/log/antitrader.log` |
| **View systemd execution status** | `sudo systemctl status antitrader.service` |
| **View journalctl logs** | `sudo journalctl -u antitrader.service -n 50 -f` |
| **Stop hourly automation** | `sudo systemctl stop antitrader.timer && sudo systemctl disable antitrader.timer` |
| **Restart hourly automation** | `sudo systemctl restart antitrader.timer` |
