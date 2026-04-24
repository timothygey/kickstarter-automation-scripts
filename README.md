# kickstarter-automation-scripts
Kickstarter Pledge Availability Monitor &amp; Auto-Clicker
# Kickstarter Auto-Pledge Monitor

Automated Selenium scripts that monitor a Kickstarter reward tier and auto-pledge the moment a slot opens up.
(assisted by Claude Opus-4-6)
---

## What This Project Does

These scripts watch the **AdventureQuest Worlds Infinity** Kickstarter project (by Artix) for specific reward tiers. They repeatedly refresh the pledge page, check whether a slot is available (or a "Pledge" button has appeared), and then automatically complete the 3-step pledge flow: **Pledge → Continue → Confirm**. Two scripts are production-ready monitors for limited-slot tiers; the other two are safe test scripts that target unlimited-slot tiers so you can verify the flow without risk.

---

## The Scripts

### 1. `kickstarter_monitor.py` — Production Monitor ($1,500 Tier)

Monitors the **"Custom Armor Set Designer"** tier at **$1,500** (30 limited slots). This is the full-featured production script with Cloudflare detection, error popup handling with 3× retry, scheduled start, email alerts, and sound alerts. Polls every 7 seconds. Note: the tier name is hardcoded in XPath strings rather than a config variable.

### 2. `kickstarter_monitor_500.py` — Production Monitor ($500 Tier)

Monitors the **"Custom Weapon Designer"** tier at **$500** (50 limited slots). Functionally identical to the $1,500 script but with a cleaner design — uses `TARGET_TIER_NAME` and `TARGET_PLEDGE_TEXT` config variables instead of hardcoded strings. Polls every 7 seconds.

### 3. `kickstarter_monitor_test250.py` — Test Script ($250 Tier)

Targets the **"Immortalized Founder"** tier at **$250** (unlimited slots). A simplified version of the production scripts — no slot monitoring, no Cloudflare handling, no error popup dismissal, no retry logic. Use this to safely test the auto-click flow. Polls every 2 seconds. Starts immediately (no scheduled start).

### 4. `kickstarter_monitor_test400.py` — Test Script ($400 Tier)

Targets the **"Benevolent Founder"** tier at **$400** (unlimited slots). Structurally identical to the $250 test script, just pointed at a different tier. Polls every 2 seconds. Starts immediately.

---

## How It Works

1. **Parse command-line arguments** — Choose `--now` (run immediately), `--schedule "YYYY-MM-DD HH:MM:SS"` (custom time), or fall back to the default schedule.
2. **Wait for schedule** — If a start time is set, the script waits until 5 minutes before that time, then opens the browser.
3. **Launch Chrome** — Opens a Chrome browser with anti-detection settings so Kickstarter doesn't flag it as automated.
4. **Navigate to pledge page** — Goes to the Kickstarter pledge/edit URL. You log in manually at this point.
5. **Wait to begin** — Either counts down to the scheduled time (you can press ENTER to skip the wait in production scripts) or waits for you to press ENTER.
6. **Refresh & read initial state** — Takes a baseline reading of the page.
7. **Polling loop** — Every 7 seconds (production) or 2 seconds (test):
   - Refreshes the page
   - *(Production only)* Checks for Cloudflare challenge — pauses and emails you if detected
   - *(Production only)* Checks if slot count has changed — triggers pledge if so
   - Checks if a "Pledge $X" button appeared — triggers pledge if so
   - Logs status to the terminal
8. **Auto-pledge** — When triggered, executes the 3-step flow:
   - Click **"Pledge $X"**
   - Click **"Continue"**
   - Click **"Confirm changes"** (production scripts retry up to 3× if an error popup appears)
9. **Success notification** — Sends an email and plays a celebration sound.

---

## Key Features

- **Slot count monitoring** (production) — Detects changes in "X of Y available" text, not just button appearance
- **Cloudflare challenge detection** — Scans page source for CAPTCHA indicators; pauses monitoring and sends an email alert so you can solve it manually
- **Error popup dismissal** — Handles unexpected popups/modals using ~22 different XPath selectors with 3× retry (production only)
- **Anti-bot-detection** — Disables automation flags, removes `navigator.webdriver`, hides Chrome automation indicators
- **Scheduled start** — Set a future start time; the browser opens 5 minutes early so you can log in
- **ENTER-to-skip** — Press ENTER at any time during the countdown to start monitoring immediately (production scripts, via threading)
- **Email alerts** — Gmail SMTP notifications (SSL port 465 with TLS port 587 fallback) for Cloudflare events and successful pledges
- **Sound alerts** — Cross-platform audio notifications for key events
- **JavaScript click fallback** — If a normal Selenium click fails, falls back to `driver.execute_script()` click

---

## Quick Comparison Table

| Feature | `kickstarter_monitor.py` | `kickstarter_monitor_500.py` | `kickstarter_monitor_test250.py` | `kickstarter_monitor_test400.py` |
|---|---|---|---|---|
| **Type** | Production | Production | Test | Test |
| **Tier** | Custom Armor Set Designer | Custom Weapon Designer | Immortalized Founder | Benevolent Founder |
| **Price** | $1,500 | $500 | $250 | $400 |
| **Slots** | 30 (limited) | 50 (limited) | Unlimited | Unlimited |
| **Poll interval** | 7s | 7s | 2s | 2s |
| **Default schedule** | 2026-04-03 00:59:55 | 2026-04-03 00:59:55 | None (immediate) | None (immediate) |
| **Slot monitoring** | ✅ | ✅ | ❌ | ❌ |
| **Cloudflare handling** | ✅ | ✅ | ❌ | ❌ |
| **Error popup retry** | ✅ (3×) | ✅ (3×) | ❌ | ❌ |
| **Email alerts** | ✅ | ✅ | ✅ | ✅ |
| **Sound alerts** | ✅ | ✅ | ✅ | ✅ |
| **Tier name config** | Hardcoded in XPaths | `TARGET_TIER_NAME` variable | Hardcoded | Hardcoded |
| **Lines of code** | ~978 | ~971 | ~628 | ~625 |

---

## Usage

### Step 1 — Create and activate a virtual environment first

> ⚠️ **Do not skip this step.** Running `pip install` without an active venv installs packages into your **global system Python**, polluting it for all other projects on your machine.

```powershell
# Navigate to the project folder
cd C:\Users\timmy\Desktop\Coding\kickstarter-automation-scripts

# Create a venv
python -m venv venv

# Activate it (Windows PowerShell)
.\venv\Scripts\Activate.ps1

# You should see (venv) in your prompt before proceeding
```

> **First-time PowerShell users:** If you get a script execution error, open PowerShell as Administrator and run once:
> ```powershell
> Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser
> ```
> Then activate again.

### Step 2 — Install dependencies

```bash
python -m pip install selenium webdriver-manager
python -m pip show selenium
```

### Run a production monitor

```bash
# Use default schedule (2026-04-03 00:59:55)
python kickstarter_monitor.py

# Start immediately
python kickstarter_monitor.py --now

# Custom schedule
python kickstarter_monitor.py --schedule "2026-04-05 12:00:00"
```

```bash
# $500 tier — same options
python kickstarter_monitor_500.py --now
```

### Run a test script

```bash
# $250 test — starts immediately, no schedule needed
python kickstarter_monitor_test250.py

# $400 test
python kickstarter_monitor_test400.py
```

> **Tip:** Use the test scripts first to verify the pledge flow works end-to-end before relying on the production monitors.
> Only play around with SCROLL_INTERVAL, set it at a min of 3 seconds.

---

## Dependencies

| Package | Purpose |
|---|---|
| `selenium` | Browser automation (drives Chrome) |
| `webdriver-manager` | Auto-downloads the correct ChromeDriver for your Chrome version |

```bash
python -m pip install selenium webdriver-manager
```

---

## Security Note

⚠️ The production scripts contain a **hardcoded Gmail App Password in plaintext**. If you share or version-control these files, that password is exposed. Consider moving it to an environment variable:

```python
import os
EMAIL_PASSWORD = os.environ.get("GMAIL_APP_PASSWORD")
```

Then set it in your shell before running:

```bash
export GMAIL_APP_PASSWORD="your-app-password-here"
python kickstarter_monitor.py --now
```
