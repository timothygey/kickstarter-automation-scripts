#!/usr/bin/env python3
"""
Kickstarter Pledge Availability Monitor & Auto-Clicker
=======================================================
Monitors the "Custom Weapon Designer" ($500) tier on a Kickstarter
pledge page. Triggers when:
  - The total available slots changes from 40 to any other number
    (e.g., "0 of 40 available" -> "X of 50 available")
  - The "Pledge $500" button appears and becomes clickable

When either condition is met, it automatically:
  1. Clicks "Pledge $500"
  2. Clicks the black "Continue" button
  3. Clicks the "Confirm changes" button

Supports scheduled start — opens the browser early for login, then
waits until the exact scheduled time to begin polling.

Requirements:
    pip install selenium webdriver-manager

Usage (immediate start):
    python kickstarter_monitor_500.py --now

Usage (scheduled start — default: 2026-04-03 00:59:55 SGT):
    python kickstarter_monitor_500.py

Usage (custom scheduled start):
    python kickstarter_monitor_500.py --schedule "2026-04-03 00:59:55"
"""

import time
import re
import sys
import subprocess
import argparse
import threading
import smtplib
from email.mime.text import MIMEText
from datetime import datetime, timedelta

try:
    import selenium
    from selenium import webdriver
    from selenium.webdriver.chrome.options import Options
    from selenium.webdriver.common.by import By
    from selenium.webdriver.support.ui import WebDriverWait
    from selenium.webdriver.support import expected_conditions as EC
    from selenium.common.exceptions import (
        NoSuchElementException,
        TimeoutException,
        StaleElementReferenceException,
        WebDriverException,
    )
    SELENIUM_MAJOR = int(selenium.__version__.split(".")[0])
    if SELENIUM_MAJOR >= 4:
        from selenium.webdriver.chrome.service import Service
    else:
        Service = None
except ImportError:
    print("=" * 60)
    print("ERROR: Selenium is not installed.")
    print("Install with: pip install selenium webdriver-manager")
    print("=" * 60)
    sys.exit(1)

try:
    from webdriver_manager.chrome import ChromeDriverManager
except ImportError:
    ChromeDriverManager = None


# ============================================================
# CONFIG
# ============================================================

TARGET_URL = "https://www.kickstarter.com/projects/artix/adventurequest-worlds-infinity/pledge/edit"

# Tier name to scope selectors to
TARGET_TIER_NAME = "Custom Weapon Designer"

# Pledge button text
TARGET_PLEDGE_TEXT = "Pledge $500"

# The known total slot count to watch — trigger when this changes
KNOWN_TOTAL_SLOTS = 50

# How often to refresh and check (in seconds)
POLL_INTERVAL = 7

# Play a sound alert on change
PLAY_SOUND_ALERT = True

# Default scheduled start time (local timezone, e.g. SGT)
# Set to None for immediate start by default
# Format: "YYYY-MM-DD HH:MM:SS"
DEFAULT_SCHEDULE = "2026-04-03 00:59:55"

# How many minutes before the scheduled time to open the browser for login
BROWSER_OPEN_MINUTES_EARLY = 5

# Email notification settings (for Cloudflare detection alerts)
EMAIL_ENABLED = True
EMAIL_FROM = "<insert your gmail>"
EMAIL_TO = "<insert your gmail>"
EMAIL_APP_PASSWORD = "jsrt bwfz orjh dson"
EMAIL_SMTP_SERVER = "smtp.gmail.com"
EMAIL_SMTP_PORT = 587

# ============================================================


def log(msg):
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{ts}] {msg}")


def send_email_alert(subject, body):
    """Send an email notification via Gmail SMTP. Tries SSL (465) first, then TLS (587)."""
    if not EMAIL_ENABLED:
        return
    try:
        msg = MIMEText(body)
        msg["Subject"] = subject
        msg["From"] = EMAIL_FROM
        msg["To"] = EMAIL_TO

        # Try SSL first (port 465) — more reliable on Windows
        try:
            with smtplib.SMTP_SSL(EMAIL_SMTP_SERVER, 465, timeout=10) as server:
                server.login(EMAIL_FROM, EMAIL_APP_PASSWORD)
                server.sendmail(EMAIL_FROM, EMAIL_TO, msg.as_string())
            log(f"📧 Email alert sent to {EMAIL_TO} (via SSL)")
            return
        except Exception as e1:
            log(f"   SSL attempt failed: {e1}")

        # Fallback: TLS (port 587)
        try:
            with smtplib.SMTP(EMAIL_SMTP_SERVER, EMAIL_SMTP_PORT, timeout=10) as server:
                server.ehlo()
                server.starttls()
                server.ehlo()
                server.login(EMAIL_FROM, EMAIL_APP_PASSWORD)
                server.sendmail(EMAIL_FROM, EMAIL_TO, msg.as_string())
            log(f"📧 Email alert sent to {EMAIL_TO} (via TLS)")
            return
        except Exception as e2:
            log(f"   TLS attempt failed: {e2}")

        log(f"⚠️  Could not send email via either SSL or TLS")
    except Exception as e:
        log(f"⚠️  Failed to send email: {e}")


def is_cloudflare_challenge(driver):
    """
    Detect if the current page is a Cloudflare security verification page.
    Returns True if the Cloudflare challenge is detected.
    """
    try:
        page_source = driver.page_source.lower()
        indicators = [
            "performing security verification",
            "verify you are human",
            "cloudflare",
            "just a moment",
            "cf-challenge",
            "turnstile",
        ]
        matches = sum(1 for ind in indicators if ind in page_source)
        return matches >= 2
    except Exception:
        return False


def handle_cloudflare_challenge(driver, script_name="$500"):
    """
    Handle Cloudflare challenge: pause refreshing, alert user, send email,
    and wait until the challenge is resolved. Sends a second email when resolved
    with start/end times and duration.
    """
    start_time = datetime.now()
    start_str = start_time.strftime("%Y-%m-%d %H:%M:%S")

    log("")
    log("🛡️" * 20)
    log("🛡️  CLOUDFLARE SECURITY CHALLENGE DETECTED!")
    log("🛡️  The script has PAUSED refreshing.")
    log("🛡️  Please solve the 'Verify you are human' checkbox in the browser.")
    log("🛡️  The script will resume automatically once you pass the check.")
    log("🛡️" * 20)

    if PLAY_SOUND_ALERT:
        for _ in range(5):
            play_alert()
            time.sleep(0.3)

    # Send encounter email notification
    send_email_alert(
        subject=f"⚠️ Kickstarter Monitor ({script_name}) — Cloudflare Challenge ENCOUNTERED!",
        body=(
            f"Your Kickstarter monitor script for the {script_name} tier has encountered "
            f"a Cloudflare security verification page.\n\n"
            f"Start Time: {start_str} SGT\n\n"
            f"ACTION REQUIRED: Go to your computer and solve the 'Verify you are human' "
            f"checkbox in the Chrome browser window.\n\n"
            f"The script is paused and will resume automatically once you pass the check."
        ),
    )

    # Wait until the challenge is resolved
    while is_cloudflare_challenge(driver):
        time.sleep(2)

    end_time = datetime.now()
    end_str = end_time.strftime("%Y-%m-%d %H:%M:%S")
    duration = end_time - start_time
    duration_secs = int(duration.total_seconds())
    duration_mins = duration_secs // 60
    duration_remaining_secs = duration_secs % 60

    log(f"✅ Cloudflare challenge resolved! Resuming monitoring... (took {duration_mins}m {duration_remaining_secs}s)")
    if PLAY_SOUND_ALERT:
        play_alert()

    # Send resolved email notification
    send_email_alert(
        subject=f"✅ Kickstarter Monitor ({script_name}) — Cloudflare Challenge RESOLVED!",
        body=(
            f"Your Kickstarter monitor script for the {script_name} tier has successfully "
            f"passed the Cloudflare security verification and resumed monitoring.\n\n"
            f"Start Time:  {start_str} SGT\n"
            f"End Time:    {end_str} SGT\n"
            f"Duration:    {duration_mins} min {duration_remaining_secs} sec\n\n"
            f"The script is now actively monitoring again."
        ),
    )

    time.sleep(2)  # Brief pause to let the real page load


def play_alert():
    try:
        if sys.platform == "linux":
            subprocess.Popen(
                ["paplay", "/usr/share/sounds/freedesktop/stereo/complete.oga"],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            )
        elif sys.platform == "darwin":
            subprocess.Popen(["afplay", "/System/Library/Sounds/Glass.aiff"])
        else:
            import winsound
            winsound.Beep(1000, 500)
    except Exception:
        print("\a" * 5)


def play_success_alert():
    """Play a distinct celebratory sound for successful pledge."""
    try:
        if sys.platform == "linux":
            subprocess.Popen(
                ["paplay", "/usr/share/sounds/freedesktop/stereo/complete.oga"],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            )
        elif sys.platform == "darwin":
            subprocess.Popen(["afplay", "/System/Library/Sounds/Hero.aiff"])
        else:
            import winsound
            # Celebratory ascending melody
            for freq in [523, 659, 784, 1047, 1319]:
                winsound.Beep(freq, 200)
            time.sleep(0.1)
            for freq in [1319, 1568, 2093]:
                winsound.Beep(freq, 300)
    except Exception:
        print("\a" * 10)


def create_driver():
    opts = Options()
    opts.add_argument("--start-maximized")
    opts.add_argument("--disable-blink-features=AutomationControlled")
    opts.add_experimental_option("excludeSwitches", ["enable-automation"])
    opts.add_experimental_option("useAutomationExtension", False)

    try:
        if ChromeDriverManager and Service:
            svc = Service(ChromeDriverManager().install())
            driver = webdriver.Chrome(service=svc, options=opts)
        elif ChromeDriverManager:
            driver_path = ChromeDriverManager().install()
            driver = webdriver.Chrome(executable_path=driver_path, options=opts)
        else:
            driver = webdriver.Chrome(options=opts)
    except WebDriverException as e:
        log(f"Could not start Chrome: {e}")
        sys.exit(1)

    driver.execute_script(
        "Object.defineProperty(navigator, 'webdriver', {get: () => undefined})"
    )
    return driver


def parse_availability(text):
    """
    Parse text like '0 of 40 available' -> (available=0, total=40).
    Returns (available, total) or None.
    """
    m = re.search(r"(\d+)\s+of\s+(\d+)\s+available", text, re.IGNORECASE)
    if m:
        return int(m.group(1)), int(m.group(2))
    return None


def find_tier_container(driver):
    """
    Find the parent container element that holds the 'Custom Weapon Designer' tier.
    Looks for the <h4> with the tier name and walks up to find the tier card container.
    Returns the container WebElement or None.
    """
    try:
        headings = driver.find_elements(
            By.XPATH,
            f"//h4[contains(text(), '{TARGET_TIER_NAME}')]"
        )
        for h4 in headings:
            parent = h4
            for _ in range(10):
                try:
                    parent = parent.find_element(By.XPATH, "..")
                    badges = parent.find_elements(By.TAG_NAME, "kds-badge")
                    if badges:
                        return parent
                except (NoSuchElementException, StaleElementReferenceException):
                    break
    except (StaleElementReferenceException, NoSuchElementException):
        pass
    return None


def check_availability_change(driver):
    """
    Look for the availability text WITHIN the 'Custom Weapon Designer' tier only.
    Finds the <kds-badge> inside that tier's container.

    Returns:
        (changed: bool, available: int|None, total: int|None, raw_text: str|None)
    """
    try:
        tier = find_tier_container(driver)
        if tier:
            badges = tier.find_elements(By.TAG_NAME, "kds-badge")
            for badge in badges:
                text = badge.text.strip()
                parsed = parse_availability(text)
                if parsed is not None:
                    available, total = parsed
                    changed = (total != KNOWN_TOTAL_SLOTS)
                    return changed, available, total, text

        # Fallback: look for kds-badge near the tier name using XPath
        elements = driver.find_elements(
            By.XPATH,
            f"//h4[contains(text(), '{TARGET_TIER_NAME}')]"
            "/ancestor::*[.//kds-badge[contains(., 'available')]]"
            "//kds-badge[contains(., 'available')]"
        )
        for el in elements:
            text = el.text.strip()
            parsed = parse_availability(text)
            if parsed is not None:
                available, total = parsed
                changed = (total != KNOWN_TOTAL_SLOTS)
                return changed, available, total, text

    except (StaleElementReferenceException, NoSuchElementException):
        pass
    return False, None, None, None


def check_pledge_button(driver):
    """
    Check if the 'Pledge $500' button is present and clickable
    WITHIN the 'Custom Weapon Designer' tier container.
    Returns the WebElement if found and clickable, else None.
    """
    try:
        tier = find_tier_container(driver)
        if tier:
            buttons = tier.find_elements(
                By.XPATH,
                f".//button[contains(., '{TARGET_PLEDGE_TEXT}')]"
            )
            for btn in buttons:
                if btn.is_displayed() and btn.is_enabled():
                    return btn

        # Fallback: find button near the tier name
        xpaths = [
            f"//h4[contains(text(), '{TARGET_TIER_NAME}')]"
            f"/ancestor::*[.//button[contains(., '{TARGET_PLEDGE_TEXT}')]]"
            f"//button[contains(., '{TARGET_PLEDGE_TEXT}')]",
            f"//button[normalize-space()='{TARGET_PLEDGE_TEXT}']",
        ]
        for xp in xpaths:
            buttons = driver.find_elements(By.XPATH, xp)
            for btn in buttons:
                if btn.is_displayed() and btn.is_enabled():
                    return btn

    except (StaleElementReferenceException, NoSuchElementException):
        pass
    return None


def click_element(driver, element, label):
    """
    Click an element using standard click, falling back to JS click.
    Returns True on success.
    """
    try:
        driver.execute_script(
            "arguments[0].scrollIntoView({behavior:'instant',block:'center'});",
            element,
        )
        element.click()
        log(f"✅ Clicked '{label}'!")
        return True
    except Exception as e:
        log(f"Standard click failed for '{label}': {e}")
        try:
            driver.execute_script("arguments[0].click();", element)
            log(f"✅ Clicked '{label}' (JS fallback)!")
            return True
        except Exception as e2:
            log(f"❌ JS click also failed for '{label}': {e2}")
            return False


def find_continue_button(driver, timeout=15):
    """
    Find the black 'Continue' button on the page.
    Waits up to `timeout` seconds for it to appear.
    Returns the WebElement or None.
    """
    xpaths = [
        "//button[contains(text(), 'Continue')]",
        "//button[normalize-space()='Continue']",
        "//a[normalize-space()='Continue']",
        "//button[.//span[contains(text(), 'Continue')]]",
        "//input[@type='submit' and @value='Continue']",
        "//button[contains(@class, 'dark') and contains(., 'Continue')]",
        "//button[contains(@class, 'black') and contains(., 'Continue')]",
        "//button[contains(@class, 'primary') and contains(., 'Continue')]",
    ]

    end_time = time.time() + timeout
    while time.time() < end_time:
        for xp in xpaths:
            try:
                buttons = driver.find_elements(By.XPATH, xp)
                for btn in buttons:
                    if btn.is_displayed() and btn.is_enabled():
                        return btn
            except (StaleElementReferenceException, NoSuchElementException):
                continue
        time.sleep(0.05)

    return None


def find_confirm_changes_button(driver, timeout=15):
    """
    Find the 'Confirm changes' button on the page.
    Waits up to `timeout` seconds for it to appear.
    Returns the WebElement or None.
    """
    xpaths = [
        "//button[contains(text(), 'Confirm changes')]",
        "//button[normalize-space()='Confirm changes']",
        "//a[contains(text(), 'Confirm changes')]",
        "//button[.//span[contains(text(), 'Confirm changes')]]",
        "//button[contains(text(), 'Confirm Changes')]",
        "//button[normalize-space()='Confirm Changes']",
        "//input[@type='submit' and contains(@value, 'Confirm')]",
        "//button[contains(., 'Confirm') and contains(., 'change')]",
    ]

    end_time = time.time() + timeout
    while time.time() < end_time:
        for xp in xpaths:
            try:
                buttons = driver.find_elements(By.XPATH, xp)
                for btn in buttons:
                    if btn.is_displayed() and btn.is_enabled():
                        return btn
            except (StaleElementReferenceException, NoSuchElementException):
                continue
        time.sleep(0.05)

    return None


def dismiss_error_popup(driver):
    """
    Detect and dismiss any error popup/dialog/modal by clicking its close "X" button.
    Uses generic selectors that cover common popup close button patterns,
    including Kickstarter's kds- component library.

    Returns True if an error popup was found and dismissed, False otherwise.
    """
    close_xpaths = [
        # Kickstarter kds- components
        "//kds-dialog//button[contains(@aria-label, 'close') or contains(@aria-label, 'Close')]",
        "//kds-dialog//button[contains(@class, 'close')]",
        "//kds-dialog//button[contains(., '×')]",
        "//kds-dialog//button[contains(., '✕')]",
        # Generic dialog/modal close buttons
        "//dialog//button[contains(@aria-label, 'close') or contains(@aria-label, 'Close')]",
        "//dialog//button[contains(@class, 'close')]",
        "//*[@role='dialog']//button[contains(@aria-label, 'close') or contains(@aria-label, 'Close')]",
        "//*[@role='dialog']//button[contains(@class, 'close')]",
        "//*[@role='alertdialog']//button[contains(@aria-label, 'close') or contains(@aria-label, 'Close')]",
        # Modals with overlay
        "//*[contains(@class, 'modal')]//button[contains(@class, 'close')]",
        "//*[contains(@class, 'modal')]//button[contains(@aria-label, 'close')]",
        "//*[contains(@class, 'popup')]//button[contains(@class, 'close')]",
        "//*[contains(@class, 'toast')]//button[contains(@class, 'close')]",
        # Buttons near "Error" text
        "//*[contains(text(), 'Error')]/ancestor::*[position() <= 5]//button",
        "//*[contains(text(), 'error')]/ancestor::*[position() <= 5]//button",
        # Generic X / × close buttons (visible ones)
        "//button[normalize-space()='×']",
        "//button[normalize-space()='✕']",
        "//button[normalize-space()='X']",
        "//button[normalize-space()='x']",
        "//button[@aria-label='Close']",
        "//button[@aria-label='close']",
        "//button[@aria-label='Dismiss']",
        "//button[@aria-label='dismiss']",
        # SVG close icons inside buttons
        "//button[.//svg[contains(@class, 'close')]]",
        "//button[.//svg][@aria-label='Close']",
    ]

    try:
        for xp in close_xpaths:
            buttons = driver.find_elements(By.XPATH, xp)
            for btn in buttons:
                try:
                    if btn.is_displayed() and btn.is_enabled():
                        log(f"   Found popup close button: '{btn.text.strip() or btn.get_attribute('aria-label') or 'X'}'")
                        driver.execute_script("arguments[0].click();", btn)
                        log("   ✅ Dismissed error popup!")
                        return True
                except (StaleElementReferenceException, NoSuchElementException):
                    continue
    except Exception as e:
        log(f"   Error while trying to dismiss popup: {e}")

    return False


def execute_pledge_flow(driver):
    """
    Execute the full pledge flow:
      Step 1: Click "Pledge $500"
      Step 2: Click "Continue" (only if Step 1 succeeded)
      Step 3: Click "Confirm changes" (only if Step 2 succeeded)
              With guardband: if error popup appears, dismiss and retry up to 3 times.

    Returns True if all steps completed successfully.
    """
    # ---- Step 1: Click pledge button ----
    log("─" * 40)
    log(f"Step 1/3: Looking for '{TARGET_PLEDGE_TEXT}' button...")

    pledge_btn = check_pledge_button(driver)
    if not pledge_btn:
        log(f"❌ Could not find '{TARGET_PLEDGE_TEXT}' button.")
        return False

    if not click_element(driver, pledge_btn, TARGET_PLEDGE_TEXT):
        log(f"❌ Failed to click '{TARGET_PLEDGE_TEXT}'.")
        return False

    if PLAY_SOUND_ALERT:
        play_alert()

    # ---- Step 2: Click "Continue" ----
    log("─" * 40)
    log("Step 2/3: Waiting for 'Continue' button...")

    continue_btn = find_continue_button(driver, timeout=15)
    if not continue_btn:
        log("❌ Could not find 'Continue' button within 15 seconds.")
        log("   You may need to click it manually in the browser.")
        return False

    if not click_element(driver, continue_btn, "Continue"):
        log("❌ Failed to click 'Continue'.")
        return False

    if PLAY_SOUND_ALERT:
        play_alert()

    # ---- Step 3: Click "Confirm changes" (with retry on error popup) ----
    max_confirm_attempts = 3
    for attempt in range(1, max_confirm_attempts + 1):
        log("─" * 40)
        log(f"Step 3/3: Waiting for 'Confirm changes' button... (attempt {attempt}/{max_confirm_attempts})")

        confirm_btn = find_confirm_changes_button(driver, timeout=15)
        if not confirm_btn:
            log("❌ Could not find 'Confirm changes' button within 15 seconds.")
            log("   You may need to click it manually in the browser.")
            return False

        if not click_element(driver, confirm_btn, "Confirm changes"):
            log("❌ Failed to click 'Confirm changes'.")
            return False

        # Wait a moment to see if an error popup appears
        time.sleep(2)

        # Check for error popup and dismiss it
        error_dismissed = dismiss_error_popup(driver)
        if error_dismissed:
            log(f"⚠️  Error popup detected and dismissed (attempt {attempt}). Retrying 'Confirm changes'...")
            time.sleep(1)
            continue  # Retry clicking "Confirm changes"
        else:
            # No error popup — success!
            break

    success_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    if PLAY_SOUND_ALERT:
        for _ in range(3):
            play_success_alert()
            time.sleep(0.5)

    log("─" * 40)
    log("🎉🎉🎉 ALL STEPS COMPLETED SUCCESSFULLY! 🎉🎉🎉")
    log(f"   {TARGET_PLEDGE_TEXT} → Continue → Confirm changes")
    log(f"   Completed at: {success_time} SGT")
    log("─" * 40)

    # Send congratulatory email
    send_email_alert(
        subject=f"🎉 Kickstarter Monitor — Successfully Pledged $500!",
        body=(
            f"Congratulations! Your Kickstarter monitor script has successfully "
            f"completed the pledge flow!\n\n"
            f"Tier:      {TARGET_TIER_NAME}\n"
            f"Amount:    $500\n"
            f"Completed: {success_time} SGT\n"
            f"Flow:      {TARGET_PLEDGE_TEXT} → Continue → Confirm changes\n\n"
            f"All 3 steps were executed successfully. Please verify the pledge "
            f"in your Kickstarter account."
        ),
    )

    return True


def wait_until_schedule(schedule_time_str):
    """
    Wait until the scheduled time. Shows a countdown in the terminal.
    Returns the parsed schedule datetime.
    """
    try:
        schedule_dt = datetime.strptime(schedule_time_str, "%Y-%m-%d %H:%M:%S")
    except ValueError:
        log(f"ERROR: Invalid schedule format '{schedule_time_str}'")
        log("Expected format: YYYY-MM-DD HH:MM:SS  (e.g., 2026-04-03 00:59:55)")
        sys.exit(1)

    now = datetime.now()

    if schedule_dt <= now:
        log(f"Scheduled time {schedule_time_str} is in the past — starting immediately!")
        return schedule_dt

    log(f"⏰ Scheduled to start monitoring at: {schedule_time_str}")
    log(f"   Current time:  {now.strftime('%Y-%m-%d %H:%M:%S')}")
    wait_seconds = (schedule_dt - now).total_seconds()
    log(f"   Waiting:       {wait_seconds:.0f} seconds ({wait_seconds/60:.1f} minutes)")
    log("")

    while True:
        now = datetime.now()
        remaining = (schedule_dt - now).total_seconds()

        if remaining <= 0:
            log("")
            log("⏰ SCHEDULED TIME REACHED — Starting monitoring NOW!")
            play_alert()
            return schedule_dt

        hours = int(remaining // 3600)
        mins = int((remaining % 3600) // 60)
        secs = int(remaining % 60)

        sys.stdout.write(
            f"\r   ⏳ Countdown: {hours:02d}:{mins:02d}:{secs:02d} remaining "
            f"(starts at {schedule_time_str})    "
        )
        sys.stdout.flush()

        if remaining > 60:
            time.sleep(1)
        elif remaining > 5:
            time.sleep(0.5)
        else:
            time.sleep(0.1)


def monitor(schedule_time=None):
    log("=" * 60)
    log("Kickstarter Pledge Monitor")
    log(f"Tier: {TARGET_TIER_NAME} — $500")
    log("=" * 60)
    log(f"URL:            {TARGET_URL}")
    log(f"Watching for:   total slots ≠ {KNOWN_TOTAL_SLOTS}")
    log(f"                OR '{TARGET_PLEDGE_TEXT}' button appears")
    log(f"Poll interval:  {POLL_INTERVAL}s")
    log(f"Auto-flow:      {TARGET_PLEDGE_TEXT} → Continue → Confirm changes")

    if schedule_time:
        log(f"Scheduled start: {schedule_time} (local time)")
    else:
        log(f"Start mode:     Immediate (manual)")

    log("=" * 60)

    # --- Handle scheduled start: open browser early for login ---
    if schedule_time:
        try:
            schedule_dt = datetime.strptime(schedule_time, "%Y-%m-%d %H:%M:%S")
        except ValueError:
            log(f"ERROR: Invalid schedule format '{schedule_time}'")
            sys.exit(1)

        now = datetime.now()
        browser_open_time = schedule_dt - timedelta(minutes=BROWSER_OPEN_MINUTES_EARLY)

        if now < browser_open_time:
            secs_until_browser = (browser_open_time - now).total_seconds()
            log(f"Browser will open at: {browser_open_time.strftime('%Y-%m-%d %H:%M:%S')} "
                f"({BROWSER_OPEN_MINUTES_EARLY} min before scheduled start)")
            log(f"Waiting {secs_until_browser:.0f}s to open browser...\n")

            while datetime.now() < browser_open_time:
                remaining = (browser_open_time - datetime.now()).total_seconds()
                hours = int(remaining // 3600)
                mins = int((remaining % 3600) // 60)
                secs = int(remaining % 60)
                sys.stdout.write(
                    f"\r   ⏳ Browser opens in: {hours:02d}:{mins:02d}:{secs:02d}    "
                )
                sys.stdout.flush()
                time.sleep(1)
            print()

    # --- Open browser ---
    log("Starting Chrome browser...")
    driver = create_driver()

    try:
        log(f"Navigating to: {TARGET_URL}")
        driver.get(TARGET_URL)

        print()
        print("=" * 60)
        print(" 1. Log into Kickstarter in the browser window.")
        print(" 2. Make sure you're on the pledge/edit page.")
        if schedule_time:
            print(f" 3. The script will auto-start monitoring at {schedule_time}.")
            print("    You can also press ENTER to skip the wait.")
        else:
            print(" 3. Come back here and press ENTER to start monitoring.")
        print("=" * 60)

        if schedule_time:
            enter_pressed = threading.Event()

            def wait_for_enter():
                input()
                enter_pressed.set()

            t = threading.Thread(target=wait_for_enter, daemon=True)
            t.start()

            print(f" Press ENTER to start immediately, or wait for {schedule_time}...")
            print()

            wait_until_schedule(schedule_time)

            if not enter_pressed.is_set():
                log("Scheduled time reached — starting automatically!")
        else:
            input(" Press ENTER when ready... ")

        print()

        # --- Navigate to the page and do initial read ---
        log("Refreshing page to begin monitoring...")
        driver.get(TARGET_URL)
        time.sleep(3)

        _, avail, total, raw = check_availability_change(driver)
        if raw:
            log(f"Initial state: {raw}")
        else:
            log("Could not read availability yet — will keep trying.")

        # Check if pledge button is already there
        if check_pledge_button(driver):
            log(f"⚠️  '{TARGET_PLEDGE_TEXT}' button is ALREADY visible!")
            log("Executing full pledge flow...")
            if execute_pledge_flow(driver):
                input("Press ENTER to close the browser... ")
                return
            else:
                log("Flow did not complete fully — check the browser.")
                input("Press ENTER to close the browser... ")
                return
        else:
            log(f"'{TARGET_PLEDGE_TEXT}' button is NOT visible (tier fully claimed).")

        log("")
        log(f"🔍 Monitoring started — refreshing every {POLL_INTERVAL}s …")
        log("   Press Ctrl+C to stop.\n")

        check_num = 0

        while True:
            time.sleep(POLL_INTERVAL)
            check_num += 1

            try:
                driver.refresh()

                # Wait for page content to be ready
                try:
                    WebDriverWait(driver, 3).until(
                        lambda d: (
                            d.find_elements(By.XPATH, "//*[contains(text(),'available')]")
                            or d.find_elements(By.XPATH, "//button[contains(., 'Pledge')]")
                        )
                    )
                except TimeoutException:
                    pass

                # --- Check for Cloudflare challenge ---
                if is_cloudflare_challenge(driver):
                    handle_cloudflare_challenge(driver, script_name="$500")
                    continue  # Skip this cycle and re-check after resolution

                # --- Condition 1: total slots changed from 50 ---
                changed, avail, total, raw = check_availability_change(driver)

                if changed and total is not None:
                    log("")
                    log("=" * 60)
                    log(f"🚨 TOTAL SLOTS CHANGED!  Was {KNOWN_TOTAL_SLOTS}, now {total}")
                    log(f"   Current: {raw}")
                    log("=" * 60)

                    if PLAY_SOUND_ALERT:
                        play_alert()

                    if execute_pledge_flow(driver):
                        input("Press ENTER to close the browser... ")
                        return
                    else:
                        log("Flow did not complete fully — check the browser.")
                        input("Press ENTER to close the browser... ")
                        return

                # --- Condition 2: Pledge button appeared ---
                pledge_btn = check_pledge_button(driver)
                if pledge_btn:
                    log("")
                    log("=" * 60)
                    log(f"🚨 '{TARGET_PLEDGE_TEXT}' BUTTON IS NOW AVAILABLE!")
                    log("=" * 60)

                    if PLAY_SOUND_ALERT:
                        play_alert()

                    if execute_pledge_flow(driver):
                        input("Press ENTER to close the browser... ")
                        return
                    else:
                        log("Flow did not complete fully — check the browser.")
                        input("Press ENTER to close the browser... ")
                        return

                # --- Status output ---
                if raw:
                    if check_num % 24 == 0:
                        log(f"[#{check_num}] No change — {raw}")
                    else:
                        sys.stdout.write(
                            f"\r[#{check_num}] {raw} — "
                            f"{datetime.now().strftime('%H:%M:%S')}    "
                        )
                        sys.stdout.flush()
                else:
                    if check_num % 24 == 0:
                        log(f"[#{check_num}] Could not read availability text")

            except StaleElementReferenceException:
                continue
            except WebDriverException as e:
                if "disconnected" in str(e).lower() or "no such window" in str(e).lower():
                    log("Browser window closed. Exiting.")
                    return
                log(f"WebDriver error: {e}")
                time.sleep(3)

    except KeyboardInterrupt:
        log("\nStopped by user (Ctrl+C).")
    finally:
        try:
            driver.quit()
        except Exception:
            pass
        log("Browser closed. Goodbye!")


def main():
    parser = argparse.ArgumentParser(
        description="Kickstarter Pledge Monitor — Custom Weapon Designer ($500)"
    )
    parser.add_argument(
        "--schedule",
        type=str,
        default=None,
        help='Start monitoring at a specific time (local timezone). '
             'Format: "YYYY-MM-DD HH:MM:SS". '
             'Example: "2026-04-03 00:59:55"'
    )
    parser.add_argument(
        "--now",
        action="store_true",
        help="Start monitoring immediately (ignore DEFAULT_SCHEDULE in config)"
    )

    args = parser.parse_args()

    if args.now:
        schedule = None
    elif args.schedule:
        schedule = args.schedule
    elif DEFAULT_SCHEDULE:
        schedule = DEFAULT_SCHEDULE
    else:
        schedule = None

    monitor(schedule_time=schedule)


if __name__ == "__main__":
    main()
