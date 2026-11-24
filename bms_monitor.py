#!/usr/bin/env python3
"""
BookMyShow Ticket Availability Monitor Agent
--------------------------------------------
Monitors specific theatres and screens on BookMyShow continuously,
bypassing WAF/Cloudflare bot challenges using TLS fingerprint emulation,
and sends instant push alerts to Telegram/Discord when tickets open.
"""

import os
import sys
import time
import json
import argparse
import datetime
from pathlib import Path
from curl_cffi import requests

# Base paths
BASE_DIR = Path(__file__).resolve().parent
CONFIG_PATH = BASE_DIR / "config.json"
STATE_PATH = BASE_DIR / "last_state.json"

def load_config():
    if not CONFIG_PATH.exists():
        print(f"[!] Error: config.json not found at {CONFIG_PATH}")
        sys.exit(1)
    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        return json.load(f)

def load_state():
    if STATE_PATH.exists():
        try:
            with open(STATE_PATH, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {}
    return {}

def save_state(state):
    with open(STATE_PATH, "w", encoding="utf-8") as f:
        json.dump(state, f, indent=2)

def send_telegram_alert(token, chat_id, message, booking_url=None):
    """Sends a formatted push notification via Telegram Bot API."""
    if not token or not chat_id:
        print("[*] Telegram credentials not configured. Skipping Telegram notification.")
        return False
    
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = {
        "chat_id": chat_id,
        "text": message,
        "parse_mode": "HTML",
        "disable_web_page_preview": False
    }
    
    if booking_url:
        payload["reply_markup"] = {
            "inline_keyboard": [
                [
                    {"text": "🎟 Open BookMyShow & Book Now", "url": booking_url}
                ]
            ]
        }
        
    try:
        res = requests.post(url, json=payload, timeout=10)
        if res.status_code == 200:
            print("[+] Telegram alert delivered successfully.")
            return True
        else:
            print(f"[-] Telegram error: HTTP {res.status_code} - {res.text}")
            return False
    except Exception as e:
        print(f"[-] Telegram request failed: {e}")
        return False

def send_discord_alert(webhook_url, message, booking_url=None):
    """Sends a formatted push notification via Discord Webhook."""
    if not webhook_url:
        return False
    
    content = message
    if booking_url:
        content += f"\n\n**Direct Link:** {booking_url}"
        
    payload = {"content": content}
    try:
        res = requests.post(webhook_url, json=payload, timeout=10)
        return res.status_code in (200, 204)
    except Exception as e:
        print(f"[-] Discord request failed: {e}")
        return False

def notify(message, booking_url=None):
    """Dispatches notifications across all configured channels."""
    tg_token = os.environ.get("TELEGRAM_BOT_TOKEN")
    tg_chat_id = os.environ.get("TELEGRAM_CHAT_ID")
    discord_webhook = os.environ.get("DISCORD_WEBHOOK_URL")
    
    tg_sent = send_telegram_alert(tg_token, tg_chat_id, message, booking_url)
    dc_sent = send_discord_alert(discord_webhook, message, booking_url)
    
    if not tg_sent and not dc_sent:
        print("\n" + "="*50)
        print("ALERT (No external webhook configured):")
        print(message)
        if booking_url:
            print(f"Booking URL: {booking_url}")
        print("="*50 + "\n")

def fetch_venue_showtimes(venue_code, venue_slug, date_code):
    """
    Fetches the BookMyShow showtimes page using Chrome TLS impersonation
    to avoid Cloudflare/Akamai bot challenge blocks.
    """
    url = f"https://in.bookmyshow.com/buytickets/{venue_slug}/cinema-hyd-{venue_code}-MT/{date_code}"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
    }
    
    try:
        r = requests.get(url, headers=headers, impersonate="chrome", timeout=15)
        if r.status_code != 200:
            return {"error": f"HTTP {r.status_code}", "url": url}
        
        idx = r.text.find("window.__INITIAL_STATE__")
        if idx == -1:
            return {"error": "INITIAL_STATE not found", "url": url}
            
        sub = r.text[idx + len("window.__INITIAL_STATE__ ="):].strip()
        obj, _ = json.JSONDecoder().raw_decode(sub)
        
        queries = obj.get("venueShowtimesFunctionalApi", {}).get("queries", {})
        events_found = []
        for qk, qv in queries.items():
            if "getShowtimesByVenue" in qk:
                data = qv.get("data", {})
                event_list = data.get("showDetailsTransformed", {}).get("Event", [])
                for ev in event_list:
                    title = ev.get("EventTitle", "")
                    for child in ev.get("ChildEvents", []):
                        dim = child.get("EventDimension", "")
                        child_name = child.get("EventName", "")
                        shows = []
                        for st in child.get("ShowTimes", []):
                            avail_status = str(st.get("AvailStatus", "0"))
                            # BMS statuses: 0 = not open / sold out, 1 = available, 4 = bestseller/filling fast
                            is_open = avail_status not in ("0", "")
                            
                            shows.append({
                                "time": st.get("ShowTime"),
                                "screen": st.get("ScreenName"),
                                "attr": st.get("Attributes"),
                                "avail_status": avail_status,
                                "is_open": is_open,
                                "categories": [
                                    {
                                        "name": cat.get("PriceDesc"),
                                        "price": cat.get("CurPrice"),
                                        "avail": str(cat.get("AvailStatus", "0"))
                                    }
                                    for cat in st.get("Categories", [])
                                ]
                            })
                            
                        events_found.append({
                            "movie": title,
                            "name": child_name,
                            "dimension": dim,
                            "shows": shows
                        })
                        
        return {"url": url, "events": events_found}
    except Exception as e:
        return {"error": str(e), "url": url}

def check_tickets(config):
    """
    Scans BookMyShow for target movie and venues, detects open tickets or
    new Dolby Cinema shows, and triggers notifications.
    """
    movie_name = config["movie"]["name"].lower()
    target_dates = config.get("target_dates", [])
    venues = config.get("venues", [])
    preferred_keywords = [k.lower() for k in config.get("preferred_keywords", [])]
    
    current_state = load_state()
    new_alerts = []
    
    now_str = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"\n[{now_str}] Starting BookMyShow availability scan...")
    
    for venue in venues:
        v_name = venue["name"]
        v_code = venue["code"]
        v_slug = venue["slug"]
        is_primary = venue.get("is_primary", False)
        
        print(f"\n-> Checking Venue: {v_name} ({v_code})")
        
        for date_code in target_dates:
            res = fetch_venue_showtimes(v_code, v_slug, date_code)
            if "error" in res:
                print(f"   [!] Date {date_code}: Error fetching ({res['error']})")
                continue
                
            events = res.get("events", [])
            matching_events = [e for e in events if movie_name in e["movie"].lower()]
            
            if not matching_events:
                print(f"   [-] Date {date_code}: '{config['movie']['name']}' not listed yet.")
                continue
                
            for ev in matching_events:
                dim = ev.get("dimension", "")
                child_name = ev.get("name", "")
                shows = ev.get("shows", [])
                
                # Check for preferred keywords (Dolby Cinema, Screen 1, etc.)
                is_preferred_screen = any(
                    kw in dim.lower() or kw in child_name.lower() or any(kw in s["screen"].lower() or kw in s["attr"].lower() for s in shows)
                    for kw in preferred_keywords
                )
                
                # Filter shows that are open for booking
                open_shows = [s for s in shows if s["is_open"]]
                
                state_key = f"{v_code}_{date_code}_{child_name}"
                last_status = current_state.get(state_key, {})
                last_open_count = last_status.get("open_count", 0)
                
                print(f"   [+] Date {date_code} | {child_name}")
                print(f"       Total Shows: {len(shows)} | Open for Booking: {len(open_shows)} | Preferred Match: {is_preferred_screen}")
                
                # Trigger criteria:
                # 1. Any show has opened for booking (open_shows > 0) AND count increased from last check
                # 2. Or if primary venue (ALLU Cinemas) newly added a Dolby Cinema screen
                tickets_just_opened = len(open_shows) > 0 and len(open_shows) > last_open_count
                new_screen_added = state_key not in current_state and is_preferred_screen and len(shows) > 0
                
                if tickets_just_opened or new_screen_added:
                    # Format show details
                    show_lines = []
                    for s in shows:
                        status_emoji = "🟢 OPEN" if s["is_open"] else "🔴 LOCKED / SOLD OUT"
                        show_lines.append(f"  • <b>{s['time']}</b> - {s['screen']} ({s['attr']}) → {status_emoji}")
                    
                    shows_text = "\n".join(show_lines)
                    
                    header_title = "🚨 <b>TICKETS OPENED FOR BOOKING!</b> 🚨" if len(open_shows) > 0 else "📢 <b>NEW DOLBY SHOWTIMES LISTED!</b> 📢"
                    
                    # Parse date to human readable
                    try:
                        dt = datetime.datetime.strptime(date_code, "%Y%m%d")
                        human_date = dt.strftime("%A, %d %B %Y")
                    except Exception:
                        human_date = date_code
                        
                    msg = (
                        f"{header_title}\n\n"
                        f"🎬 <b>Movie:</b> {config['movie']['name']}\n"
                        f"🏛 <b>Cinema:</b> {v_name}\n"
                        f"📅 <b>Date:</b> {human_date}\n"
                        f"🔊 <b>Format / Screen:</b> {child_name}\n\n"
                        f"⏰ <b>Showtimes:</b>\n{shows_text}\n\n"
                        f"⚡ <i>Book immediately before seats fill up!</i>"
                    )
                    
                    new_alerts.append({
                        "message": msg,
                        "url": res["url"],
                        "venue": v_name,
                        "date": human_date
                    })
                    
                # Update state
                current_state[state_key] = {
                    "total_shows": len(shows),
                    "open_count": len(open_shows),
                    "last_checked": now_str
                }
                
    save_state(current_state)
    
    # Send all detected alerts
    if new_alerts:
        print(f"\n[⚡] Triggering {len(new_alerts)} alert notification(s)...")
        for alert in new_alerts:
            notify(alert["message"], alert["url"])
    else:
        print("\n[✓] Check completed. No newly opened tickets or changes detected.")

def send_test_message(config):
    print("[*] Dispatching test notification to verify communication channels...")
    sample_url = f"https://in.bookmyshow.com/buytickets/{config['venues'][0]['slug']}/cinema-hyd-{config['venues'][0]['code']}-MT/{config['target_dates'][0]}"
    msg = (
        "🤖 <b>BookMyShow Agent Online & Active</b>\n\n"
        f"Watching for: <b>{config['movie']['name']}</b>\n"
        f"Venue: <b>{config['venues'][0]['name']}</b>\n"
        f"Screen Target: <b>Dolby Cinema / Screen 1</b>\n"
        "Check Interval: <b>Every 20 Minutes</b>\n\n"
        "✅ Notifications are connected. You will receive an instant alert with a direct booking link as soon as tickets open!"
    )
    notify(msg, sample_url)

def main():
    parser = argparse.ArgumentParser(description="BookMyShow Ticket Monitor Agent")
    parser.add_argument("--once", action="store_true", help="Run once and exit (for Cron / GitHub Actions)")
    parser.add_argument("--daemon", action="store_true", help="Run continuously in a loop")
    parser.add_argument("--interval", type=int, default=20, help="Check interval in minutes (default: 20)")
    parser.add_argument("--test-notify", action="store_true", help="Send a test notification to verify setup")
    args = parser.parse_args()

    config = load_config()

    if args.test_notify:
        send_test_message(config)
        return

    if args.daemon:
        interval_secs = args.interval * 60
        print(f"[*] Starting BMS Agent in daemon mode. Checking every {args.interval} minutes...")
        while True:
            try:
                check_tickets(config)
            except Exception as e:
                print(f"[!] Unexpected error in scan cycle: {e}")
            print(f"[*] Sleeping for {args.interval} minutes. Next run at {(datetime.datetime.now() + datetime.timedelta(seconds=interval_secs)).strftime('%H:%M:%S')}...")
            time.sleep(interval_secs)
    else:
        # Default behavior: run once (ideal for GitHub Actions & serverless crons)
        check_tickets(config)

if __name__ == "__main__":
    main()
