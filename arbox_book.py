"""
Arbox auto-booking script.
Books tomorrow's class if it matches a preconfigured schedule.

Usage:
    python arbox_book.py              # Book tomorrow's matching classes now
    python arbox_book.py --dry-run    # Show what would be booked without booking

Configuration via environment variables (or .env file):
    ARBOX_EMAIL        – Arbox account email
    ARBOX_PASSWORD     – Arbox account password
    CLASS_NAME_PREFIX  – Default class name prefix (e.g. "WOD"). Can be overridden per class entry.
    CLASSES            – JSON list of class objects, each with "day" and "time",
                         and optionally "class_name_prefix" to override the default.
                         Days: sunday, monday, tuesday, wednesday, thursday, friday, saturday.
                         Example: [{"day": "sunday", "time": "08:00"}, {"day": "tuesday", "time": "07:00", "class_name_prefix": "סאונה"}]
    TIMEZONE           – Timezone (default "Asia/Jerusalem")
    LOCATION_NAME      – Location name to book at (e.g. "CrossFit Binyamina")
"""

import json
import os
import sys
import time
import logging
from datetime import datetime, timedelta
from pathlib import Path

import requests

try:
    from dotenv import load_dotenv
    load_dotenv('.env.example')
except ImportError:
    pass

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger(__name__)

BASE_URL = "https://apiappv2.arboxapp.com/api/v2"

HEADERS_BASE = {
    "Accept": "application/json, text/plain, */*",
    "Content-Type": "application/json",
}


# ── Config ──────────────────────────────────────────────────────────────────

def load_config():
    email = os.environ.get("ARBOX_EMAIL", "")
    password = os.environ.get("ARBOX_PASSWORD", "")
    if not email or not password:
        log.error("ARBOX_EMAIL and ARBOX_PASSWORD must be set.")
        sys.exit(1)
    classes_raw = os.environ.get("CLASSES", "")
    if not classes_raw:
        log.error("CLASSES must be set (JSON list of {day, time} objects).")
        sys.exit(1)
    classes = json.loads(classes_raw)

    return {
        "email": email,
        "password": password,
        "location_name": os.environ.get("LOCATION_NAME", ""),
        "class_name_prefix": os.environ.get("CLASS_NAME_PREFIX", "WOD"),
        "classes": classes,
        "timezone": os.environ.get("TIMEZONE", "Asia/Jerusalem"),
    }


# ── API helpers ─────────────────────────────────────────────────────────────

class ArboxClient:
    def __init__(self):
        self.token = ""
        self.refresh_token = ""
        self.user_data = None
        self.membership_id = None
        self.locations_box_id = None
        self.session = requests.Session()
        self.session.headers.update(HEADERS_BASE)

    def _auth_headers(self):
        return {
            "accesstoken": self.token,
            "refreshtoken": self.refresh_token,
        }

    def login(self, email: str, password: str):
        log.info("Logging in...")
        resp = self.session.post(
            f"{BASE_URL}/user/login",
            json={"email": email, "password": password},
        )
        resp.raise_for_status()
        data = resp.json()["data"]
        self.token = data["token"]
        self.refresh_token = data["refreshToken"]
        self.user_data = data
        log.info("Login successful (user id: %s)", data.get("id"))

    def get_locations(self, location_name: str = ""):
        log.info("Fetching box locations...")
        resp = self.session.get(
            f"{BASE_URL}/boxes/locations",
            headers=self._auth_headers(),
        )
        resp.raise_for_status()
        locations = resp.json()["data"]

        if location_name:
            matched = [
                loc for loc in locations
                if loc.get("name", "").strip() == location_name
            ]
            if not matched:
                available = [loc.get("name", "?") for loc in locations]
                log.error(
                    "Location '%s' not found. Available: %s",
                    location_name, available,
                )
                sys.exit(1)
            location = matched[0]
        else:
            location = locations[0]

        self.locations_box_id = location["locations_box"][0]["id"]
        log.info(
            "Using location: %s (locations_box_id: %s)",
            location.get("name"), self.locations_box_id,
        )
        return location

    def get_membership(self, box_id: int):
        log.info("Fetching membership for box %s...", box_id)
        resp = self.session.get(
            f"{BASE_URL}/boxes/{box_id}/memberships/1",
            headers=self._auth_headers(),
        )
        resp.raise_for_status()
        memberships = resp.json()["data"]
        if not memberships:
            log.error("No active membership found.")
            sys.exit(1)
        self.membership_id = memberships[0]["id"]
        log.info("Membership id: %s", self.membership_id)
        return memberships[0]

    def get_schedule(self, date_str: str):
        """Get schedule for a date (YYYY-MM-DD)."""
        log.info("Fetching schedule for %s...", date_str)
        body = {
            "from": f"{date_str}T00:00:00.000Z",
            "to": f"{date_str}T00:00:00.000Z",
            "locations_box_id": self.locations_box_id,
        }
        resp = self.session.post(
            f"{BASE_URL}/schedule/betweenDates",
            headers=self._auth_headers(),
            json=body,
        )
        resp.raise_for_status()
        classes = resp.json()["data"]
        log.info("Found %d classes on %s", len(classes), date_str)
        return classes

    def register(self, schedule_id: int):
        """Register for a class by schedule_id."""
        log.info("Registering for schedule_id=%s ...", schedule_id)
        body = {
            "extras": None,
            "membership_user_id": self.membership_id,
            "schedule_id": schedule_id,
        }
        resp = self.session.post(
            f"{BASE_URL}/scheduleUser/insert",
            headers=self._auth_headers(),
            json=body,
        )
        data = resp.json()
        if resp.status_code == 200:
            log.info("Enrolled successfully!")
            return data
        else:
            msg = data.get("error", {}).get("messageToUser", resp.text)
            log.error("Registration failed: %s", msg)
            raise RuntimeError(msg)


# ── Booking logic ───────────────────────────────────────────────────────────

def find_target_class(classes, class_name_prefix: str, class_time: str):
    """Find the best matching class from the schedule."""
    matches = [
        c for c in classes
        if c.get("time") == class_time
        and c.get("box_categories", {}).get("name", "").strip().startswith(class_name_prefix)
    ]
    if not matches:
        return None

    return matches[0]


DAY_NAMES = ["sunday", "monday", "tuesday", "wednesday", "thursday", "friday", "saturday"]


def get_matching_entries(classes_config: list, tomorrow_day: str):
    """Return config entries whose day matches tomorrow's day of week."""
    return [
        entry for entry in classes_config
        if entry["day"].lower() == tomorrow_day
    ]


def book_tomorrow(config: dict, dry_run: bool = False):
    from zoneinfo import ZoneInfo

    tz = ZoneInfo(config["timezone"])
    tomorrow_dt = datetime.now(tz) + timedelta(days=1)
    tomorrow_str = tomorrow_dt.strftime("%Y-%m-%d")
    tomorrow_day = DAY_NAMES[tomorrow_dt.weekday()]

    matching_entries = get_matching_entries(config["classes"], tomorrow_day)
    if not matching_entries:
        log.info(
            "No configured classes for %s (%s). Nothing to book.",
            tomorrow_day, tomorrow_str,
        )
        return True

    log.info(
        "Tomorrow is %s (%s) — %d configured class(es) to book.",
        tomorrow_day, tomorrow_str, len(matching_entries),
    )

    client = ArboxClient()
    client.login(config["email"], config["password"])

    location = client.get_locations(config["location_name"])
    box_id = location["id"]
    client.get_membership(box_id)

    schedule = client.get_schedule(tomorrow_str)

    booked = 0
    for entry in matching_entries:
        class_time = entry["time"]
        prefix = entry.get("class_name_prefix", config["class_name_prefix"])

        target = find_target_class(schedule, prefix, class_time)
        if not target:
            log.warning(
                "No class found matching starts_with: '%s' at %s on %s",
                prefix, class_time, tomorrow_str,
            )
            continue

        log.info(
            "Target class: %s at %s (schedule_id: %s)",
            target["box_categories"]["name"].strip(),
            target["time"],
            target["id"],
        )

        if dry_run:
            log.info("[DRY RUN] Would register for schedule_id=%s", target["id"])
            booked += 1
            continue

        client.register(target["id"])
        booked += 1

    log.info("Booked %d / %d class(es).", booked, len(matching_entries))
    return booked > 0


def main():
    config = load_config()
    dry_run = "--dry-run" in sys.argv

    success = book_tomorrow(config, dry_run=dry_run)
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
