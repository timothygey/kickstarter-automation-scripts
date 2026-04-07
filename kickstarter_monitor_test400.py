#!/usr/bin/env python3
"""
Kickstarter Pledge Test Script — Benevolent Founder ($400)
=============================================================
TEST version of kickstarter_monitor.py adapted for the "Benevolent Founder"
($400) tier. This tier has unlimited slots, so the "Pledge $400" button is
always visible. Used to test the full click flow:

  1. Click "Pledge $400"
  2. Click "Continue"
  3. Click "Confirm changes"

Requirements:
    pip install selenium webdriver-manager

Usage:
    python kickstarter_monitor_test400.py --now
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
TARGET_TIER_NAME = "Benevolent Founder"

# Pledge button text
TARGET_PLEDGE_TEXT = "Pledge $400"

# How often to refresh and check (in seconds)
POLL_INTERVAL = 2

# Play a sound alert on change
PLAY_SOUND_ALERT = True

# Default scheduled start time — set to None for immediate start
DEFAULT_SCHEDULE = None

# How many minutes before the scheduled time to open the browser for login
BROWSER_OPEN_MINUTES_EARLY = 5

# Email notification settings
EMAIL_ENABLED = True
EMAIL_FROM = "tim13aq3dmain@gmail.com"
EMAIL_TO = "tim13aq3dmain@gmail.com"
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

        try:
            with smtplib.SMTP_SSL(EMAIL_SMTP_SERVER, 465, timeout=10) as server:
                server.login(EMAIL_FROM, EMAIL_APP_PASSWORD)
                server.sendmail(EMAIL_FROM, EMAIL_TO, msg.as_string())
            log(f"📧 Email alert sent to {EMAIL_TO} (via SSL)")
            return
        except Exception as e1:
            log(f"   SSL attempt failed: {e1}")

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


def find_tier_container(driver):
    """
    Find the parent container element that holds the 'Benevolent Founder' tier.
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
                    buttons = parent.find_elements(
                        By.XPATH,
                        f".//button[contains(., '{TARGET_PLEDGE_TEXT}')]"
                    )
                    if buttons:
                        return parent
                except (NoSuchElementException, StaleElementReferenceException):
                    break
    except (StaleElementReferenceException, NoSuchElementException):
        pass
    return None


def check_pledge_button(driver):
    """
    Check if the 'Pledge $400' button is present and clickable
    WITHIN the 'Benevolent Founder' tier container.
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


def execute_pledge_flow(driver):
    """
    Execute the full pledge flow:
      Step 1: Click "Pledge $400"
      Step 2: Click "Continue" (only if Step 1 succeeded)
      Step 3: Click "Confirm changes" (only if Step 2 succeeded)

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

    # ---- Step 3: Click "Confirm changes" ----
    log("─" * 40)
    log("Step 3/3: Waiting for 'Confirm changes' button...")

    confirm_btn = find_confirm_changes_button(driver, timeout=15)
    if not confirm_btn:
        log("❌ Could not find 'Confirm changes' button within 15 seconds.")
        log("   You may need to click it manually in the browser.")
        return False

    if not click_element(driver, confirm_btn, "Confirm changes"):
        log("❌ Failed to click 'Confirm changes'.")
        return False

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

    send_email_alert(
        subject=f"🎉 Kickstarter Monitor — Successfully Pledged $400!",
        body=(
            f"Congratulations! Your Kickstarter monitor script has successfully "
            f"completed the pledge flow!\n\n"
            f"Tier:      {TARGET_TIER_NAME}\n"
            f"Amount:    $400\n"
            f"Completed: {success_time} SGT\n"
            f"Flow:      {TARGET_PLEDGE_TEXT} → Continue → Confirm changes\n\n"
            f"All 3 steps were executed successfully. Please verify the pledge "
            f"in your Kickstarter account."
        ),
    )

    return True


def monitor(schedule_time=None):
    log("=" * 60)
    log("Kickstarter Pledge Monitor (TEST)")
    log(f"Tier: {TARGET_TIER_NAME} — $400")
    log("=" * 60)
    log(f"URL:            {TARGET_URL}")
    log(f"Looking for:    '{TARGET_PLEDGE_TEXT}' button")
    log(f"Poll interval:  {POLL_INTERVAL}s")
    log(f"Auto-flow:      {TARGET_PLEDGE_TEXT} → Continue → Confirm changes")

    if schedule_time:
        log(f"Scheduled start: {schedule_time} (local time)")
    else:
        log(f"Start mode:     Immediate (manual)")

    log("=" * 60)

    # --- Handle scheduled start ---
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
        print(" 3. Come back here and press ENTER to start.")
        print("=" * 60)
        input(" Press ENTER when ready... ")
        print()

        # --- Navigate to the page and do initial read ---
        log("Refreshing page to begin...")
        driver.get(TARGET_URL)
        time.sleep(3)

        # Check if pledge button is already there
        pledge_btn = check_pledge_button(driver)
        if pledge_btn:
            log(f"✅ '{TARGET_PLEDGE_TEXT}' button found!")
            log("Executing full pledge flow...")
            if execute_pledge_flow(driver):
                input("Press ENTER to close the browser... ")
                return
            else:
                log("Flow did not complete fully — check the browser.")
                input("Press ENTER to close the browser... ")
                return
        else:
            log(f"'{TARGET_PLEDGE_TEXT}' button NOT found.")
            log("Starting monitoring loop — will check every 2s...")

        log("")
        log(f"🔍 Monitoring started — refreshing every {POLL_INTERVAL}s …")
        log("   Press Ctrl+C to stop.\n")

        check_num = 0

        while True:
            time.sleep(POLL_INTERVAL)
            check_num += 1

            try:
                driver.refresh()

                try:
                    WebDriverWait(driver, 3).until(
                        lambda d: d.find_elements(
                            By.XPATH,
                            f"//h4[contains(text(), '{TARGET_TIER_NAME}')]"
                        )
                    )
                except TimeoutException:
                    pass

                # Check if pledge button appeared
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

                # Status output
                if check_num % 24 == 0:
                    log(f"[#{check_num}] No '{TARGET_PLEDGE_TEXT}' button yet")
                else:
                    sys.stdout.write(
                        f"\r[#{check_num}] Waiting for '{TARGET_PLEDGE_TEXT}' — "
                        f"{datetime.now().strftime('%H:%M:%S')}    "
                    )
                    sys.stdout.flush()

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
        description="Kickstarter Pledge Test — Benevolent Founder ($400)"
    )
    parser.add_argument(
        "--schedule",
        type=str,
        default=None,
        help='Start at a specific time. Format: "YYYY-MM-DD HH:MM:SS"'
    )
    parser.add_argument(
        "--now",
        action="store_true",
        help="Start immediately"
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
