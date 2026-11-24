# 🎬 BookMyShow Ticket Availability Monitor Agent

An automated cloud agent that continuously monitors **BookMyShow (Hyderabad Region)** for **Avengers: Doomsday (Dec 17, 2026)** at **ALLU Cinemas: Kokapet (Dolby Cinema)** and **AAA Cinemas: Ameerpet**.

It runs **every 20 minutes in the cloud**, completely independent of your laptop (runs 24/7 even when your laptop is turned off), and sends an **instant push notification to your phone via Telegram** with a direct booking button the second tickets open.

---

## ⚡ Key Highlights

- **Bypasses Anti-Bot & Cloudflare Protection:** Uses `curl_cffi` with browser TLS fingerprint impersonation (`impersonate="chrome"`), preventing the `403 Forbidden` WAF challenges BookMyShow applies to standard bots.
- **Targets Specific Screens:** Specifically filters for **ALLU Cinemas Dolby Cinema** (`ALUC`), Screen 1, and Atmos formats.
- **Zero-Cost 24/7 Cloud Execution:** Configured with GitHub Actions cron runner so you never need to keep your laptop awake.
- **Instant Mobile Alerts:** Delivers alerts via Telegram Bot directly to your smartphone with sound and direct BookMyShow booking URLs.

---

## 📱 Step 1: Set Up Your Telegram Notification Bot (Takes 1 Minute)

1. Open **Telegram** on your phone or desktop.
2. Search for `@BotFather` and click **Start**.
3. Send the command: `/newbot`.
4. Give your bot a name (e.g., `MyBMSAlertBot`) and a username ending in `bot` (e.g., `allu_cinemas_alert_bot`).
5. Copy the **HTTP API Token** provided by BotFather (this is your `TELEGRAM_BOT_TOKEN`).
6. Click the link to open your newly created bot, and press **Start** (or send any text message like `/start`).
7. Search for `@userinfobot` on Telegram and click Start. It will reply with your numeric **Id** (this is your `TELEGRAM_CHAT_ID`).

---

## ☁️ Step 2: Run 24/7 in the Cloud (Works when Laptop is OFF)

To make it run every 20 minutes **without your laptop being turned on**, use GitHub Actions:

1. Create a new repository on [GitHub](https://github.com/new) (e.g., `bms-ticket-alert`).
2. Push this folder to your GitHub repo:
   ```bash
   cd bms-ticket-agent
   git init
   git add .
   git commit -m "Initialize BMS Monitor Agent"
   git branch -M main
   git remote add origin https://github.com/<YOUR_USERNAME>/bms-ticket-alert.git
   git push -u origin main
   ```
3. In your GitHub repository:
   - Navigate to **Settings** → **Secrets and variables** → **Actions**.
   - Under **Repository secrets**, click **New repository secret**:
     - Name: `TELEGRAM_BOT_TOKEN` | Value: *(Your bot token from Step 1)*
     - Name: `TELEGRAM_CHAT_ID` | Value: *(Your chat ID from Step 1)*
4. Go to the **Actions** tab in GitHub:
   - You will see the **"BookMyShow 20-Min Ticket Monitor"** workflow.
   - Click **Run workflow** once manually to verify it executes cleanly.
5. **Done!** GitHub will now automatically run the agent every 20 minutes on their cloud infrastructure. When tickets open, your phone will buzz immediately!

---

## 💻 Optional: Running Locally on your Laptop

If you ever want to run it on your machine:

1. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```
2. Test Telegram connection:
   ```bash
   set TELEGRAM_BOT_TOKEN=your_token
   set TELEGRAM_CHAT_ID=your_id
   python bms_monitor.py --test-notify
   ```
3. Run once:
   ```bash
   python bms_monitor.py --once
   ```
4. Run continuously as a background loop:
   ```bash
   python bms_monitor.py --daemon --interval 20
   ```

---

## ⚙️ Configuration Reference (`config.json`)

You can edit `config.json` at any time to add new dates, cinemas, or movie codes:
- **`movie.event_code`**: `ET00526320` (*Avengers: Doomsday*)
- **`venues`**:
  - `ALUC`: *ALLU Cinemas: Kokapet* (Hyderabad's flagship Dolby Cinema screen)
  - `ACAS`: *AAA Cinemas: Ameerpet*
- **`target_dates`**: `["20261217", "20261218", "20261219", "20261220"]`
- **`preferred_keywords`**: `["DOLBY CINEMA", "DOLBY", "ATMOS", "SCREEN 1", "SCREEN 2"]`
