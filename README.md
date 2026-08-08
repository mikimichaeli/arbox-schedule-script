# Arbox Auto-Booking

Automatically books tomorrow's class on [Arbox](https://www.arboxapp.com/) by calling the Arbox member API directly.

## How it works

1. Checks tomorrow's day of week against your configured `CLASSES` list
2. If no entries match tomorrow — exits successfully with nothing to do
3. Logs in with your Arbox credentials
4. Fetches your locations and selects the one matching `LOCATION_NAME`
5. Pulls tomorrow's schedule for that location
6. For each matching class entry, finds the class at the configured time whose name starts with the prefix
7. Registers you for each matched class

## Setup

### Requirements

- Python 3.9+
- `requests` and `python-dotenv` (optional)

```bash
pip install -r requirements.txt
```

### Configuration

All configuration is via environment variables. Copy the example and fill in your values:

```bash
cp .env.example .env
# edit .env with your credentials
```

| Variable | Required | Default | Description |
|---|---|---|---|
| `ARBOX_EMAIL` | Yes | — | Your Arbox account email |
| `ARBOX_PASSWORD` | Yes | — | Your Arbox account password |
| `CLASSES` | Yes | — | JSON list of class objects (see below) |
| `LOCATION_NAME` | No | *(first location)* | Exact location name (e.g. `CrossFit Binyamina`). Exits with an error listing available names if no match is found. |
| `CLASS_NAME_PREFIX` | No | `WOD` | Default prefix to match against class names. Can be overridden per class entry. |
| `TIMEZONE` | No | `Asia/Jerusalem` | Timezone for date calculations |

### `CLASSES` format

A JSON array where each object has:
- `day` (required) — day of week: `sunday`, `monday`, `tuesday`, `wednesday`, `thursday`, `friday`, `saturday`
- `time` (required) — class start time in `HH:MM` format
- `class_name_prefix` (optional) — overrides the default `CLASS_NAME_PREFIX` for this entry

Example:
```
CLASSES='[{"day": "sunday", "time": "08:00"}, {"day": "tuesday", "time": "08:00"}, {"day": "thursday", "time": "07:00", "class_name_prefix": "Open Gym"}]'
```

This would book the default class (WOD) at 08:00 on Sundays and Tuesdays, and "Open Gym" at 07:00 on Thursdays.

## Usage

```bash
# Book tomorrow's matching classes now
python arbox_book.py

# Preview what would be booked without actually booking
python arbox_book.py --dry-run
```

### Exit codes

- `0` — booking succeeded, or no classes configured for tomorrow (nothing to do)
- `1` — a configured class wasn't found in the schedule, login failed, or other error

## Scheduling

The script itself has no built-in scheduler — it books and exits. Use an external scheduler to run it at registration-open time:

**crontab** (e.g. daily at 21:00 Israel time):
```
0 21 * * * cd /path/to/arbox-schedule-script && /usr/bin/python3 arbox_book.py
```

**AWS EventBridge + Lambda**, **Cloud Run + Cloud Scheduler**, or similar for more reliable timing.

> Tip: If class spots fill instantly at registration open, consider firing the script a few seconds early with a short sleep to the exact second, or using a warm-connection approach.
