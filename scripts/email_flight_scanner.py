"""
GateTime Flight Email Scanner v2
Reads Gmail for flight confirmation emails, parses flight details with Claude,
creates Google Calendar events, and sends scheduled email reminders:
  - 1 day before departure: full timeline with leave-home + arrive-at-airport times
  - 5 hours before leave time: urgent reminder with fresh traffic data

Integrates Google Routes API for drive time from home to BOS.
"""

import os
import sys
import base64
import json
import re
import requests
from datetime import datetime, timezone, timedelta
from email import message_from_bytes
from email.mime.text import MIMEText
from typing import Optional
from dotenv import load_dotenv

import anthropic
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from googleapiclient.discovery import build

# Fix Unicode output on Windows (cp932)
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_DIR = os.path.dirname(SCRIPT_DIR)

# Load both .env files
load_dotenv(os.path.join(SCRIPT_DIR, '.env'))
load_dotenv(os.path.join(PROJECT_DIR, '.env'))

# Gmail + Calendar + Send scopes
SCOPES = [
    "https://www.googleapis.com/auth/gmail.readonly",
    "https://www.googleapis.com/auth/gmail.send",
    "https://www.googleapis.com/auth/calendar.events",
]

TOKEN_FILE = os.path.join(SCRIPT_DIR, "token.json")
CREDENTIALS_FILE = os.getenv("GOOGLE_CREDENTIALS_PATH", os.path.join(SCRIPT_DIR, "credentials.json"))
USERS_FILE = os.path.join(SCRIPT_DIR, "users.json")
FLIGHTS_FILE = os.path.join(SCRIPT_DIR, "flights.json")

GOOGLE_ROUTES_API_KEY = os.getenv("GOOGLE_ROUTES_API_KEY", "")


# ─── Data files ──────────────────────────────────────────────────────────────

def load_json(path, default=None):
    try:
        if os.path.exists(path):
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
    except Exception:
        pass
    return default if default is not None else []


def save_json(path, data):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False, default=str)


def load_users():
    return load_json(USERS_FILE, [])


def load_flights():
    return load_json(FLIGHTS_FILE, [])


def save_flights(flights):
    save_json(FLIGHTS_FILE, flights)


# ─── Auth ────────────────────────────────────────────────────────────────────

def get_google_credentials() -> Credentials:
    creds = None
    if os.path.exists(TOKEN_FILE):
        creds = Credentials.from_authorized_user_file(TOKEN_FILE, SCOPES)
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(CREDENTIALS_FILE, SCOPES)
            creds = flow.run_local_server(port=0)
        with open(TOKEN_FILE, "w") as f:
            f.write(creds.to_json())
    return creds


# ─── Gmail ───────────────────────────────────────────────────────────────────

def search_flight_emails(gmail_service, max_results: int = 10) -> list:
    query = (
        "subject:(flight OR booking OR confirmation OR itinerary OR e-ticket OR reservation OR receipt OR trip OR purchased "
        "OR delta OR latam OR jetblue OR united OR american) "
        "newer_than:60d"
    )
    result = gmail_service.users().messages().list(
        userId="me", q=query, maxResults=max_results
    ).execute()

    messages = result.get("messages", [])
    if not messages:
        print("No flight emails found.")
        return []

    emails = []
    for msg_ref in messages:
        raw = gmail_service.users().messages().get(
            userId="me", id=msg_ref["id"], format="raw"
        ).execute()

        raw_bytes = base64.urlsafe_b64decode(raw["raw"])
        email_msg = message_from_bytes(raw_bytes)

        plain_body = ""
        html_body = ""
        if email_msg.is_multipart():
            for part in email_msg.walk():
                content_type = part.get_content_type()
                payload = part.get_payload(decode=True)
                if not payload:
                    continue
                decoded = payload.decode("utf-8", errors="ignore")
                if content_type == "text/plain" and not plain_body:
                    plain_body = decoded
                elif content_type == "text/html" and not html_body:
                    html_body = decoded
        else:
            payload = email_msg.get_payload(decode=True)
            if payload:
                plain_body = payload.decode("utf-8", errors="ignore")

        if html_body:
            body = re.sub(r"<[^>]+>", " ", html_body)
            body = re.sub(r"[ \t]{2,}", " ", body)
            body = re.sub(r"\n{3,}", "\n\n", body)
        else:
            body = plain_body

        emails.append({
            "subject": email_msg.get("Subject", ""),
            "from": email_msg.get("From", ""),
            "date": email_msg.get("Date", ""),
            "body": body[:8000],
            "message_id": msg_ref["id"],
        })

    return emails


# ─── Claude parsing ──────────────────────────────────────────────────────────

def parse_flight_details(email: dict) -> Optional[dict]:
    client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))

    prompt = f"""You are a flight itinerary parser. Extract all flight details from the email below.

Email subject: {email['subject']}
From: {email['from']}
Date received: {email['date']}

Email body:
{email['body']}

Return ONLY a JSON object with this exact structure (no markdown, no explanation):
{{
  "is_flight_confirmation": true/false,
  "passenger_name": "...",
  "confirmation_code": "...",
  "airline": "...",
  "flights": [
    {{
      "flight_number": "...",
      "origin": "city name and airport code, e.g. Los Angeles (LAX)",
      "destination": "city name and airport code, e.g. New York (JFK)",
      "departure_datetime": "ISO 8601 format WITHOUT timezone suffix, e.g. 2024-06-15T16:13:00",
      "departure_timezone": "IANA timezone of departure city",
      "arrival_datetime": "ISO 8601 format WITHOUT timezone suffix",
      "arrival_timezone": "IANA timezone of arrival city",
      "duration_minutes": 123
    }}
  ]
}}

If this is not a flight confirmation email, return {{"is_flight_confirmation": false}}.
If a field is unknown, use null."""

    response = client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=2048,
        messages=[{"role": "user", "content": prompt}],
    )

    # Find the text block (skip thinking blocks)
    raw = ""
    for block in response.content:
        if hasattr(block, "text"):
            raw = block.text.strip()
            break
    if not raw:
        print("  [WARN] No text in Claude response")
        return None
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        # Try stripping markdown code fences
        if "```" in raw:
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]
            raw = raw.strip()
        # Try to find JSON object in the text
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            # Last resort: find first { and last }
            start = raw.find("{")
            end = raw.rfind("}") + 1
            if start >= 0 and end > start:
                try:
                    data = json.loads(raw[start:end])
                except json.JSONDecodeError:
                    print(f"  [WARN] Could not parse Claude response")
                    return None
            else:
                print(f"  [WARN] No JSON found in Claude response")
                return None

    if not data.get("is_flight_confirmation"):
        return None

    return data


# ─── Google Calendar ──────────────────────────────────────────────────────────

def create_calendar_event(calendar_service, flight: dict, trip: dict) -> str:
    departure = flight["departure_datetime"]
    arrival = flight["arrival_datetime"]
    departure_tz = flight.get("departure_timezone") or "UTC"
    arrival_tz = flight.get("arrival_timezone") or "UTC"

    summary = (
        f"{trip.get('airline', 'Flight')} {flight['flight_number']} -- "
        f"{flight['origin']} -> {flight['destination']}"
    )

    description_lines = [
        f"Airline: {trip.get('airline', 'N/A')}",
        f"Flight: {flight['flight_number']}",
        f"From: {flight['origin']}",
        f"To: {flight['destination']}",
        f"Confirmation: {trip.get('confirmation_code', 'N/A')}",
        f"Passenger: {trip.get('passenger_name', 'N/A')}",
    ]

    event = {
        "summary": summary,
        "description": "\n".join(description_lines),
        "start": {"dateTime": departure, "timeZone": departure_tz},
        "end": {"dateTime": arrival, "timeZone": arrival_tz},
        "reminders": {
            "useDefault": False,
            "overrides": [
                {"method": "email", "minutes": 24 * 60},
                {"method": "popup", "minutes": 180},
            ],
        },
    }

    created = calendar_service.events().insert(calendarId="primary", body=event).execute()
    return created.get("htmlLink", "")


# ─── GateTime Airport Arrival Calculator ─────────────────────────────────────

SEED_ESTIMATES = {
    "A": {"early_morning": (8, 8), "morning": (15, 20), "midday": (10, 12), "afternoon": (15, 18), "evening": (12, 15)},
    "B": {"early_morning": (10, 10), "morning": (18, 25), "midday": (12, 15), "afternoon": (18, 22), "evening": (14, 18)},
    "C": {"early_morning": (8, 10), "morning": (15, 22), "midday": (10, 14), "afternoon": (15, 20), "evening": (12, 16)},
    "E": {"early_morning": (12, 12), "morning": (20, 25), "midday": (15, 15), "afternoon": (22, 25), "evening": (18, 20)},
}

WALK_TIMES = {"A": 6, "B": 6, "C": 5, "E": 6}

AIRLINE_TERMINAL = {
    "delta": "A",
    "american": "B", "american airlines": "B",
    "united": "B", "united airlines": "B",
    "jetblue": "C",
    "southwest": "B", "southwest airlines": "B",
    "spirit": "B", "spirit airlines": "B",
    "frontier": "B", "frontier airlines": "B",
    "air canada": "B",
    "cape air": "C",
    "british airways": "E",
    "emirates": "E",
    "aer lingus": "E",
    "tap air portugal": "E", "tap portugal": "E",
    "iberia": "E",
    "latam": "E", "latam airlines": "E",
    "lufthansa": "E",
    "turkish airlines": "E", "turkish": "E",
    "copa airlines": "E", "copa": "E",
}

INTERNATIONAL_TERMINALS = {"E"}

BOS_ADDRESS = "1 Harborside Dr, Boston, MA 02128"  # Logan Airport address


def get_time_bucket(hour: int) -> str:
    if 4 <= hour < 7: return "early_morning"
    if 7 <= hour < 10: return "morning"
    if 10 <= hour < 14: return "midday"
    if 14 <= hour < 17: return "afternoon"
    return "evening"


def calculate_arrive_by(departure_dt: datetime, airline: str) -> dict:
    airline_lower = airline.lower().strip()
    terminal = None
    for key, term in AIRLINE_TERMINAL.items():
        if key in airline_lower or airline_lower in key:
            terminal = term
            break
    if not terminal:
        terminal = "B"

    is_international = terminal in INTERNATIONAL_TERMINALS
    boarding_buffer = 45 if is_international else 30
    walk_time = WALK_TIMES.get(terminal, 6)

    estimated_arrival_hour = (departure_dt - timedelta(minutes=boarding_buffer + walk_time + 20)).hour
    time_bucket = get_time_bucket(estimated_arrival_hour)

    check_in, security = SEED_ESTIMATES.get(terminal, SEED_ESTIMATES["B"]).get(time_bucket, (15, 20))

    total_buffer = boarding_buffer + walk_time + security + check_in
    arrive_by = departure_dt - timedelta(minutes=total_buffer)

    return {
        "arrive_by": arrive_by,
        "terminal": terminal,
        "is_international": is_international,
        "boarding_buffer": boarding_buffer,
        "walk_time": walk_time,
        "security": security,
        "check_in": check_in,
        "total_buffer": total_buffer,
    }


# ─── Google Routes API (Drive Time) ─────────────────────────────────────────

def get_drive_time(home_address: str, departure_time_iso: str = None) -> Optional[dict]:
    """Call Google Routes API to get drive time from home to BOS."""
    if not GOOGLE_ROUTES_API_KEY:
        print("  [WARN] No GOOGLE_ROUTES_API_KEY, skipping drive time")
        return None

    url = "https://routes.googleapis.com/directions/v2:computeRoutes"
    headers = {
        "Content-Type": "application/json",
        "X-Goog-Api-Key": GOOGLE_ROUTES_API_KEY,
        "X-Goog-FieldMask": "routes.duration,routes.staticDuration,routes.distanceMeters",
    }

    body = {
        "origin": {"address": home_address},
        "destination": {"address": BOS_ADDRESS},
        "travelMode": "DRIVE",
        "routingPreference": "TRAFFIC_AWARE",
    }

    if departure_time_iso:
        # Ensure proper ISO 8601 with timezone
        if not departure_time_iso.endswith("Z") and "+" not in departure_time_iso:
            departure_time_iso = departure_time_iso + "-05:00"  # ET default
        body["departureTime"] = departure_time_iso

    try:
        resp = requests.post(url, json=body, headers=headers, timeout=10)
        resp.raise_for_status()
        data = resp.json()

        routes = data.get("routes", [])
        if not routes:
            return None

        route = routes[0]
        duration_str = route.get("duration", "0s")
        static_str = route.get("staticDuration", duration_str)
        distance_m = route.get("distanceMeters", 0)

        def parse_duration(s):
            s = s.rstrip("s")
            return int(s) // 60

        return {
            "durationMinutes": parse_duration(duration_str),
            "durationInTrafficMinutes": parse_duration(static_str),
            "distanceMiles": round(distance_m / 1609.34, 1),
        }
    except Exception as e:
        print(f"  [WARN] Drive time API error: {e}")
        return None


# ─── Email Templates ─────────────────────────────────────────────────────────

def build_day_before_email(flight, trip, calc, drive_info, leave_home_dt, dep_dt):
    """Build HTML for the day-before reminder with full timeline."""
    arrive_by = calc["arrive_by"]
    drive_mins = drive_info["durationMinutes"] if drive_info else 30
    drive_dist = drive_info["distanceMiles"] if drive_info else "?"

    return f"""<html><body style="font-family: 'Inter', Arial, sans-serif; background: #F5F6F8; padding: 20px;">
<div style="max-width: 560px; margin: 0 auto; background: white; border-radius: 16px; overflow: hidden; box-shadow: 0 2px 12px rgba(0,0,0,0.06);">

  <!-- Header -->
  <div style="background: #0A0F1E; padding: 32px 28px; text-align: center;">
    <div style="color: #C5A255; font-size: 12px; letter-spacing: 3px; text-transform: uppercase; margin-bottom: 4px;">GateTime Reminder</div>
    <div style="color: white; font-size: 14px; opacity: 0.6; margin-bottom: 20px;">Tomorrow you fly from Boston Logan (BOS)</div>

    <div style="color: #34D399; font-size: 11px; letter-spacing: 2px; text-transform: uppercase; margin-bottom: 4px;">LEAVE HOME BY</div>
    <div style="color: white; font-size: 52px; font-weight: 700; font-family: 'Poppins', Arial, sans-serif; line-height: 1.1;">{leave_home_dt.strftime('%I:%M %p')}</div>

    <div style="height: 1px; background: rgba(255,255,255,0.1); margin: 16px 0;"></div>

    <div style="color: rgba(255,255,255,0.5); font-size: 11px; letter-spacing: 2px; text-transform: uppercase; margin-bottom: 4px;">ARRIVE AT AIRPORT BY</div>
    <div style="color: white; font-size: 32px; font-weight: 700; font-family: 'Poppins', Arial, sans-serif;">{arrive_by.strftime('%I:%M %p')}</div>
    <div style="color: rgba(255,255,255,0.4); font-size: 13px; margin-top: 6px;">Terminal {calc['terminal']} &middot; {trip.get('airline', '')}</div>
  </div>

  <!-- Flight info -->
  <div style="padding: 24px 28px; border-bottom: 1px solid #F0F0F0;">
    <div style="font-size: 11px; color: #6B7280; text-transform: uppercase; letter-spacing: 1px; margin-bottom: 8px;">Your Flight</div>
    <div style="font-size: 18px; font-weight: 700; color: #1A1A2E; margin-bottom: 4px;">{flight['flight_number']}: {flight['origin']} &rarr; {flight['destination']}</div>
    <div style="font-size: 14px; color: #6B7280;">Departs {dep_dt.strftime('%B %d, %Y')} at {dep_dt.strftime('%I:%M %p')}</div>
    <div style="font-size: 13px; color: #6B7280; margin-top: 2px;">Confirmation: <strong>{trip.get('confirmation_code', 'N/A')}</strong></div>
  </div>

  <!-- Timeline -->
  <div style="padding: 24px 28px;">
    <div style="font-size: 11px; color: #6B7280; text-transform: uppercase; letter-spacing: 1px; margin-bottom: 16px;">Your Timeline</div>

    <!-- Leave home -->
    <div style="display: flex; align-items: flex-start;">
      <div style="width: 24px; display: flex; flex-direction: column; align-items: center; flex-shrink: 0;">
        <div style="width: 14px; height: 14px; border-radius: 50%; background: #34D399; border: 3px solid #D1FAE5;"></div>
        <div style="width: 1px; height: 28px; background: #E5E7EB;"></div>
      </div>
      <div style="margin-left: 12px; padding-bottom: 12px;">
        <div style="font-size: 15px; font-weight: 700; color: #1A1A2E;">{leave_home_dt.strftime('%I:%M %p')} - Leave home</div>
      </div>
    </div>

    <!-- Drive -->
    <div style="display: flex; align-items: flex-start;">
      <div style="width: 24px; display: flex; flex-direction: column; align-items: center; flex-shrink: 0;">
        <div style="width: 10px; height: 10px; border-radius: 50%; background: #8B5CF6; margin-top: 2px;"></div>
        <div style="width: 1px; height: 28px; background: #E5E7EB;"></div>
      </div>
      <div style="margin-left: 12px; padding-bottom: 12px;">
        <div style="font-size: 14px; color: #1A1A2E;"><strong>{drive_mins} min</strong> - Drive to BOS ({drive_dist} mi)</div>
      </div>
    </div>

    <!-- Arrive at airport -->
    <div style="display: flex; align-items: flex-start;">
      <div style="width: 24px; display: flex; flex-direction: column; align-items: center; flex-shrink: 0;">
        <div style="width: 12px; height: 12px; border-radius: 50%; background: #34D399; margin-top: 1px;"></div>
        <div style="width: 1px; height: 28px; background: #E5E7EB;"></div>
      </div>
      <div style="margin-left: 12px; padding-bottom: 12px;">
        <div style="font-size: 15px; font-weight: 700; color: #1A1A2E;">{arrive_by.strftime('%I:%M %p')} - Arrive at airport</div>
        <div style="font-size: 12px; color: #6B7280;">Terminal {calc['terminal']} entrance</div>
      </div>
    </div>

    <!-- Check-in -->
    <div style="display: flex; align-items: flex-start;">
      <div style="width: 24px; display: flex; flex-direction: column; align-items: center; flex-shrink: 0;">
        <div style="width: 10px; height: 10px; border-radius: 50%; background: #3B82F6; margin-top: 2px;"></div>
        <div style="width: 1px; height: 28px; background: #E5E7EB;"></div>
      </div>
      <div style="margin-left: 12px; padding-bottom: 12px;">
        <div style="font-size: 14px; color: #1A1A2E;"><strong>{calc['check_in']} min</strong> - Check-in</div>
      </div>
    </div>

    <!-- Security -->
    <div style="display: flex; align-items: flex-start;">
      <div style="width: 24px; display: flex; flex-direction: column; align-items: center; flex-shrink: 0;">
        <div style="width: 10px; height: 10px; border-radius: 50%; background: #F59E0B; margin-top: 2px;"></div>
        <div style="width: 1px; height: 28px; background: #E5E7EB;"></div>
      </div>
      <div style="margin-left: 12px; padding-bottom: 12px;">
        <div style="font-size: 14px; color: #1A1A2E;"><strong>{calc['security']} min</strong> - Security</div>
      </div>
    </div>

    <!-- Walk -->
    <div style="display: flex; align-items: flex-start;">
      <div style="width: 24px; display: flex; flex-direction: column; align-items: center; flex-shrink: 0;">
        <div style="width: 10px; height: 10px; border-radius: 50%; background: #6B7280; margin-top: 2px;"></div>
        <div style="width: 1px; height: 28px; background: #E5E7EB;"></div>
      </div>
      <div style="margin-left: 12px; padding-bottom: 12px;">
        <div style="font-size: 14px; color: #1A1A2E;"><strong>{calc['walk_time']} min</strong> - Walk to gate</div>
      </div>
    </div>

    <!-- Boarding -->
    <div style="display: flex; align-items: flex-start;">
      <div style="width: 24px; display: flex; flex-direction: column; align-items: center; flex-shrink: 0;">
        <div style="width: 10px; height: 10px; border-radius: 50%; background: #34D399; margin-top: 2px;"></div>
        <div style="width: 1px; height: 28px; background: #E5E7EB;"></div>
      </div>
      <div style="margin-left: 12px; padding-bottom: 12px;">
        <div style="font-size: 14px; color: #1A1A2E;"><strong>{calc['boarding_buffer']} min</strong> - Boarding</div>
      </div>
    </div>

    <!-- Departure -->
    <div style="display: flex; align-items: flex-start;">
      <div style="width: 24px; display: flex; flex-direction: column; align-items: center; flex-shrink: 0;">
        <div style="width: 14px; height: 14px; border-radius: 50%; background: #0A0F1E; border: 3px solid #D1D5DB;"></div>
      </div>
      <div style="margin-left: 12px;">
        <div style="font-size: 15px; font-weight: 700; color: #1A1A2E;">{dep_dt.strftime('%I:%M %p')} - Flight departs</div>
        <div style="font-size: 12px; color: #6B7280;">{flight['flight_number']} to {flight['destination']}</div>
      </div>
    </div>
  </div>

  <!-- Footer -->
  <div style="padding: 16px 28px; background: #F9FAFB; border-top: 1px solid #F0F0F0; text-align: center;">
    <div style="font-size: 11px; color: #9CA3AF;">Visit <a href="https://gatetime-v2.vercel.app" style="color: #34D399; text-decoration: none;">GateTime</a> for live wait times</div>
  </div>

</div>
</body></html>"""


def build_urgent_email(flight, trip, calc, drive_info, leave_home_dt, dep_dt):
    """Build HTML for the 5-hours-before urgent reminder."""
    arrive_by = calc["arrive_by"]
    drive_mins = drive_info["durationMinutes"] if drive_info else 30

    return f"""<html><body style="font-family: 'Inter', Arial, sans-serif; background: #F5F6F8; padding: 20px;">
<div style="max-width: 560px; margin: 0 auto; background: white; border-radius: 16px; overflow: hidden; box-shadow: 0 2px 12px rgba(0,0,0,0.06);">

  <!-- Header - urgent orange accent -->
  <div style="background: #0A0F1E; padding: 32px 28px; text-align: center;">
    <div style="color: #F59E0B; font-size: 12px; letter-spacing: 3px; text-transform: uppercase; margin-bottom: 4px;">TIME TO GET READY</div>
    <div style="color: white; font-size: 14px; opacity: 0.6; margin-bottom: 20px;">{trip.get('airline', '')} {flight['flight_number']} to {flight['destination']}</div>

    <div style="color: #F59E0B; font-size: 11px; letter-spacing: 2px; text-transform: uppercase; margin-bottom: 4px;">LEAVE HOME BY</div>
    <div style="color: white; font-size: 56px; font-weight: 700; font-family: 'Poppins', Arial, sans-serif; line-height: 1.1;">{leave_home_dt.strftime('%I:%M %p')}</div>

    <div style="height: 1px; background: rgba(255,255,255,0.1); margin: 16px 0;"></div>

    <div style="display: inline-block; background: rgba(255,255,255,0.1); border-radius: 12px; padding: 12px 24px;">
      <div style="color: rgba(255,255,255,0.5); font-size: 10px; letter-spacing: 2px; text-transform: uppercase;">ARRIVE AT BOS BY</div>
      <div style="color: white; font-size: 24px; font-weight: 700; font-family: 'Poppins', Arial, sans-serif;">{arrive_by.strftime('%I:%M %p')}</div>
      <div style="color: rgba(255,255,255,0.4); font-size: 12px;">Terminal {calc['terminal']} &middot; {drive_mins} min drive</div>
    </div>
  </div>

  <!-- Flight info -->
  <div style="padding: 24px 28px; border-bottom: 1px solid #F0F0F0;">
    <div style="font-size: 14px; color: #1A1A2E; margin-bottom: 4px;">Flight departs at <strong>{dep_dt.strftime('%I:%M %p')}</strong></div>
    <div style="font-size: 13px; color: #6B7280;">Confirmation: <strong>{trip.get('confirmation_code', 'N/A')}</strong></div>
  </div>

  <!-- Timeline breakdown -->
  <div style="padding: 24px 28px;">
    <div style="font-size: 11px; color: #6B7280; text-transform: uppercase; letter-spacing: 1px; margin-bottom: 16px;">Your Timeline</div>

    <!-- Leave home -->
    <div style="display: flex; align-items: flex-start;">
      <div style="width: 24px; display: flex; flex-direction: column; align-items: center; flex-shrink: 0;">
        <div style="width: 14px; height: 14px; border-radius: 50%; background: #F59E0B; border: 3px solid #FEF3C7;"></div>
        <div style="width: 1px; height: 28px; background: #E5E7EB;"></div>
      </div>
      <div style="margin-left: 12px; padding-bottom: 12px;">
        <div style="font-size: 15px; font-weight: 700; color: #1A1A2E;">{leave_home_dt.strftime('%I:%M %p')} - Leave home</div>
      </div>
    </div>

    <!-- Drive -->
    <div style="display: flex; align-items: flex-start;">
      <div style="width: 24px; display: flex; flex-direction: column; align-items: center; flex-shrink: 0;">
        <div style="width: 10px; height: 10px; border-radius: 50%; background: #8B5CF6; margin-top: 2px;"></div>
        <div style="width: 1px; height: 28px; background: #E5E7EB;"></div>
      </div>
      <div style="margin-left: 12px; padding-bottom: 12px;">
        <div style="font-size: 14px; color: #1A1A2E;"><strong>{drive_mins} min</strong> - Drive to BOS</div>
      </div>
    </div>

    <!-- Arrive at airport -->
    <div style="display: flex; align-items: flex-start;">
      <div style="width: 24px; display: flex; flex-direction: column; align-items: center; flex-shrink: 0;">
        <div style="width: 12px; height: 12px; border-radius: 50%; background: #34D399; margin-top: 1px;"></div>
        <div style="width: 1px; height: 28px; background: #E5E7EB;"></div>
      </div>
      <div style="margin-left: 12px; padding-bottom: 12px;">
        <div style="font-size: 15px; font-weight: 700; color: #1A1A2E;">{arrive_by.strftime('%I:%M %p')} - Arrive at airport</div>
        <div style="font-size: 12px; color: #6B7280;">Terminal {calc['terminal']} entrance</div>
      </div>
    </div>

    <!-- Check-in -->
    <div style="display: flex; align-items: flex-start;">
      <div style="width: 24px; display: flex; flex-direction: column; align-items: center; flex-shrink: 0;">
        <div style="width: 10px; height: 10px; border-radius: 50%; background: #3B82F6; margin-top: 2px;"></div>
        <div style="width: 1px; height: 28px; background: #E5E7EB;"></div>
      </div>
      <div style="margin-left: 12px; padding-bottom: 12px;">
        <div style="font-size: 14px; color: #1A1A2E;"><strong>{calc['check_in']} min</strong> - Check-in</div>
      </div>
    </div>

    <!-- Security -->
    <div style="display: flex; align-items: flex-start;">
      <div style="width: 24px; display: flex; flex-direction: column; align-items: center; flex-shrink: 0;">
        <div style="width: 10px; height: 10px; border-radius: 50%; background: #F59E0B; margin-top: 2px;"></div>
        <div style="width: 1px; height: 28px; background: #E5E7EB;"></div>
      </div>
      <div style="margin-left: 12px; padding-bottom: 12px;">
        <div style="font-size: 14px; color: #1A1A2E;"><strong>{calc['security']} min</strong> - Security</div>
      </div>
    </div>

    <!-- Walk -->
    <div style="display: flex; align-items: flex-start;">
      <div style="width: 24px; display: flex; flex-direction: column; align-items: center; flex-shrink: 0;">
        <div style="width: 10px; height: 10px; border-radius: 50%; background: #6B7280; margin-top: 2px;"></div>
        <div style="width: 1px; height: 28px; background: #E5E7EB;"></div>
      </div>
      <div style="margin-left: 12px; padding-bottom: 12px;">
        <div style="font-size: 14px; color: #1A1A2E;"><strong>{calc['walk_time']} min</strong> - Walk to gate</div>
      </div>
    </div>

    <!-- Boarding -->
    <div style="display: flex; align-items: flex-start;">
      <div style="width: 24px; display: flex; flex-direction: column; align-items: center; flex-shrink: 0;">
        <div style="width: 10px; height: 10px; border-radius: 50%; background: #34D399; margin-top: 2px;"></div>
        <div style="width: 1px; height: 28px; background: #E5E7EB;"></div>
      </div>
      <div style="margin-left: 12px; padding-bottom: 12px;">
        <div style="font-size: 14px; color: #1A1A2E;"><strong>{calc['boarding_buffer']} min</strong> - Boarding</div>
      </div>
    </div>

    <!-- Departure -->
    <div style="display: flex; align-items: flex-start;">
      <div style="width: 24px; display: flex; flex-direction: column; align-items: center; flex-shrink: 0;">
        <div style="width: 14px; height: 14px; border-radius: 50%; background: #0A0F1E; border: 3px solid #D1D5DB;"></div>
      </div>
      <div style="margin-left: 12px;">
        <div style="font-size: 15px; font-weight: 700; color: #1A1A2E;">{dep_dt.strftime('%I:%M %p')} - Flight departs</div>
        <div style="font-size: 12px; color: #6B7280;">{flight['flight_number']} to {flight['destination']}</div>
      </div>
    </div>
  </div>

  <!-- Schedule Uber -->
  <div style="padding: 0 28px 24px; text-align: center;">
    <a href="https://m.uber.com/ul/?client_id=gatetime&action=setPickup&pickup=my_location&dropoff%5Bformatted_address%5D=Boston+Logan+International+Airport%2C+1+Harborside+Dr%2C+Boston%2C+MA+02128&dropoff%5Blatitude%5D=42.3656&dropoff%5Blongitude%5D=-71.0096"
       style="display: inline-block; background: #000000; color: white; font-weight: 700; font-size: 15px; padding: 14px 32px; border-radius: 12px; text-decoration: none; font-family: 'Poppins', Arial, sans-serif;">
       Schedule an Uber to BOS
    </a>
    <div style="font-size: 11px; color: #9CA3AF; margin-top: 8px;">Opens the Uber app with Logan Airport as destination</div>
  </div>

  <!-- Footer -->
  <div style="padding: 16px 28px; background: #F9FAFB; border-top: 1px solid #F0F0F0; text-align: center;">
    <div style="font-size: 11px; color: #9CA3AF;">Drive time based on current traffic conditions</div>
    <div style="font-size: 11px; color: #9CA3AF; margin-top: 4px;">Visit <a href="https://gatetime-v2.vercel.app" style="color: #34D399; text-decoration: none;">GateTime</a> for live wait times</div>
  </div>

</div>
</body></html>"""


def send_html_email(gmail_service, to_email: str, subject: str, html: str):
    """Send an HTML email via Gmail API."""
    message = MIMEText(html, "html")
    message["to"] = to_email
    message["subject"] = subject
    raw = base64.urlsafe_b64encode(message.as_bytes()).decode()
    gmail_service.users().messages().send(userId="me", body={"raw": raw}).execute()
    print(f"     Email sent to {to_email}")


# ─── Main Logic ──────────────────────────────────────────────────────────────

def flight_key(flight_number, departure_datetime, user_email):
    """Unique key to identify a flight for dedup."""
    return f"{flight_number}|{departure_datetime}|{user_email}"


def main():
    print("Authenticating with Google...")
    creds = get_google_credentials()
    gmail = build("gmail", "v1", credentials=creds)
    calendar = build("calendar", "v3", credentials=creds)

    # Get signed-in user email
    profile = gmail.users().getProfile(userId="me").execute()
    user_email = profile["emailAddress"]
    print(f"Signed in as: {user_email}")

    # Load registered users
    users = load_users()
    user = next((u for u in users if u["email"].lower() == user_email.lower()), None)
    home_address = user["homeAddress"] if user else None

    if home_address:
        print(f"Home address: {home_address}")
    else:
        print("No home address registered (drive time will be estimated)")

    # Load tracked flights
    tracked_flights = load_flights()
    tracked_keys = {f.get("key", "") for f in tracked_flights}

    # ── Phase A: Scan for new flight emails ──────────────────────────────────

    print("\nSearching for flight confirmation emails...")
    emails = search_flight_emails(gmail, max_results=10)

    new_flights_found = 0
    if emails:
        print(f"Found {len(emails)} candidate email(s). Parsing with Claude...")

        for email_data in emails:
            print(f"\n  Checking: {email_data['subject'][:70]}")
            trip = parse_flight_details(email_data)

            if not trip:
                print("  -> Not a flight confirmation, skipping.")
                continue

            print(f"  -> Flight found! {trip.get('airline')} | {trip.get('confirmation_code')}")

            for flight in trip.get("flights", []):
                fkey = flight_key(flight["flight_number"], flight["departure_datetime"], user_email)

                if fkey in tracked_keys:
                    print(f"     {flight['flight_number']}: Already tracked, skipping.")
                    continue

                print(f"     {flight['flight_number']}: {flight['origin']} -> {flight['destination']}")

                # Create calendar event
                try:
                    url = create_calendar_event(calendar, flight, trip)
                    print(f"     Calendar event created: {url}")
                except Exception as e:
                    print(f"     Calendar event error: {e}")

                # Calculate arrive-by
                if not flight.get("departure_datetime"):
                    print(f"     Skipping - no departure time found")
                    continue
                dep_dt = datetime.fromisoformat(flight["departure_datetime"])
                calc = calculate_arrive_by(dep_dt, trip.get("airline", ""))

                # Get drive time
                drive_info = None
                leave_home_dt = calc["arrive_by"] - timedelta(minutes=30)  # default 30 min
                if home_address:
                    drive_info = get_drive_time(home_address, calc["arrive_by"].isoformat() + "Z")
                    if drive_info:
                        leave_home_dt = calc["arrive_by"] - timedelta(minutes=drive_info["durationMinutes"])
                        print(f"     Drive time: {drive_info['durationMinutes']} min ({drive_info['distanceMiles']} mi)")

                print(f"     Leave home by: {leave_home_dt.strftime('%I:%M %p')}")
                print(f"     Arrive at airport by: {calc['arrive_by'].strftime('%I:%M %p')}")

                # Save to tracked flights
                flight_record = {
                    "key": fkey,
                    "flightNumber": flight["flight_number"],
                    "airline": trip.get("airline", ""),
                    "origin": flight["origin"],
                    "destination": flight["destination"],
                    "departureDateTime": flight["departure_datetime"],
                    "departureTz": flight.get("departure_timezone", "America/New_York"),
                    "confirmationCode": trip.get("confirmation_code", ""),
                    "passengerName": trip.get("passenger_name", ""),
                    "userEmail": user_email,
                    "homeAddress": home_address or "",
                    "terminal": calc["terminal"],
                    "arriveByTime": calc["arrive_by"].isoformat(),
                    "leaveHomeTime": leave_home_dt.isoformat(),
                    "driveMinutes": drive_info["durationMinutes"] if drive_info else 30,
                    "driveMiles": drive_info["distanceMiles"] if drive_info else None,
                    "reminderDayBeforeSent": False,
                    "reminder5HoursSent": False,
                    "detectedAt": datetime.now().isoformat(),
                }
                tracked_flights.append(flight_record)
                tracked_keys.add(fkey)
                new_flights_found += 1

                # Send immediate confirmation email (day-before style)
                try:
                    html = build_day_before_email(flight, trip, calc, drive_info, leave_home_dt, dep_dt)
                    subject = f"GateTime: Leave home by {leave_home_dt.strftime('%I:%M %p')} for {flight['flight_number']}"
                    send_html_email(gmail, user_email, subject, html)
                except Exception as e:
                    print(f"     Email error: {e}")

    save_flights(tracked_flights)

    # ── Phase B: Check for due reminders ─────────────────────────────────────

    print("\nChecking scheduled reminders...")
    now = datetime.now()
    reminders_sent = 0

    for rec in tracked_flights:
        dep_dt = datetime.fromisoformat(rec["departureDateTime"])

        # Skip past flights
        if dep_dt < now:
            continue

        leave_home_dt = datetime.fromisoformat(rec["leaveHomeTime"])
        hours_until_departure = (dep_dt - now).total_seconds() / 3600
        hours_until_leave = (leave_home_dt - now).total_seconds() / 3600

        # Build minimal flight/trip dicts for email templates
        flight_info = {
            "flight_number": rec["flightNumber"],
            "origin": rec["origin"],
            "destination": rec["destination"],
            "departure_datetime": rec["departureDateTime"],
        }
        trip_info = {
            "airline": rec["airline"],
            "confirmation_code": rec["confirmationCode"],
        }
        calc_info = calculate_arrive_by(dep_dt, rec["airline"])

        # Day-before reminder: 23-25 hours before departure
        if not rec.get("reminderDayBeforeSent") and 23 <= hours_until_departure <= 25:
            print(f"  Sending day-before reminder for {rec['flightNumber']}...")
            drive_info = None
            if rec.get("homeAddress"):
                drive_info = get_drive_time(rec["homeAddress"], calc_info["arrive_by"].isoformat() + "Z")
                if drive_info:
                    leave_home_dt = calc_info["arrive_by"] - timedelta(minutes=drive_info["durationMinutes"])

            html = build_day_before_email(flight_info, trip_info, calc_info, drive_info, leave_home_dt, dep_dt)
            subject = f"Tomorrow you fly! Leave home by {leave_home_dt.strftime('%I:%M %p')}"
            try:
                send_html_email(gmail, rec["userEmail"], subject, html)
                rec["reminderDayBeforeSent"] = True
                reminders_sent += 1
            except Exception as e:
                print(f"     Error: {e}")

        # 5-hours-before reminder: 4.5-5.5 hours before leave time
        if not rec.get("reminder5HoursSent") and 4.5 <= hours_until_leave <= 5.5:
            print(f"  Sending 5-hours-before reminder for {rec['flightNumber']}...")
            # Fresh drive time with current traffic
            drive_info = None
            if rec.get("homeAddress"):
                drive_info = get_drive_time(rec["homeAddress"], calc_info["arrive_by"].isoformat() + "Z")
                if drive_info:
                    leave_home_dt = calc_info["arrive_by"] - timedelta(minutes=drive_info["durationMinutes"])

            html = build_urgent_email(flight_info, trip_info, calc_info, drive_info, leave_home_dt, dep_dt)
            subject = f"Time to get ready! Leave by {leave_home_dt.strftime('%I:%M %p')} for {rec['flightNumber']}"
            try:
                send_html_email(gmail, rec["userEmail"], subject, html)
                rec["reminder5HoursSent"] = True
                reminders_sent += 1
            except Exception as e:
                print(f"     Error: {e}")

    save_flights(tracked_flights)

    print(f"\nDone. {new_flights_found} new flight(s) detected, {reminders_sent} reminder(s) sent.")


if __name__ == "__main__":
    main()
