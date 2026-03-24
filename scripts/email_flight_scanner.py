"""
GateTime Flight Email Scanner
Reads Gmail for flight confirmation emails, parses flight details with Claude,
and creates a Google Calendar event automatically.
"""

import os
import base64
import json
import re
from datetime import datetime, timezone
from email import message_from_bytes
from typing import Optional
from dotenv import load_dotenv

import anthropic
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from googleapiclient.discovery import build

load_dotenv()

# Gmail + Calendar both need these scopes
SCOPES = [
    "https://www.googleapis.com/auth/gmail.readonly",
    "https://www.googleapis.com/auth/calendar.events",
]

TOKEN_FILE = "token.json"
CREDENTIALS_FILE = os.getenv("GOOGLE_CREDENTIALS_PATH", "credentials.json")


# ─── Auth ────────────────────────────────────────────────────────────────────

def get_google_credentials() -> Credentials:
    """
    Loads cached OAuth token or runs the browser-based login flow.
    On first run a browser window will open — log in and grant access.
    The token is saved to token.json so you only do this once.
    """
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

def search_flight_emails(gmail_service, max_results: int = 5) -> list:
    """
    Searches Gmail for flight confirmation emails.
    Returns a list of dicts with 'subject', 'from', 'date', and 'body'.
    """
    # Common flight confirmation keywords — adjust as needed
    query = (
        "subject:(flight OR booking OR confirmation OR itinerary OR e-ticket OR reservation) "
        "newer_than:5d"
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

        # Prefer HTML stripped of tags — airline emails often have garbled plain text
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
            "body": body[:8000],  # cap at 8k chars to stay within token budget
        })

    return emails


# ─── Claude parsing ──────────────────────────────────────────────────────────

def parse_flight_details(email: dict) -> Optional[dict]:
    """
    Sends the email content to Claude and asks it to extract structured
    flight information. Returns a dict or None if no flight info found.
    """
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
      "departure_datetime": "ISO 8601 format WITHOUT timezone suffix, exactly as shown in the email, e.g. 2024-06-15T16:13:00 — do NOT convert to UTC",
      "departure_timezone": "IANA timezone of departure city based on airport code, e.g. America/New_York for BOS",
      "arrival_datetime": "ISO 8601 format WITHOUT timezone suffix, exactly as shown in the email, e.g. 2024-06-15T18:48:00 — do NOT convert to UTC",
      "arrival_timezone": "IANA timezone of arrival city based on airport code, e.g. America/New_York for CHS",
      "duration_minutes": 123
    }}
  ]
}}

If this is not a flight confirmation email, return {{"is_flight_confirmation": false}}.
If a field is unknown, use null."""

    response = client.messages.create(
        model="claude-opus-4-6",
        max_tokens=1024,
        thinking={"type": "adaptive"},
        messages=[{"role": "user", "content": prompt}],
    )

    raw = response.content[-1].text.strip()

    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        # Claude occasionally wraps JSON in markdown — strip it
        if "```" in raw:
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]
        data = json.loads(raw.strip())

    if not data.get("is_flight_confirmation"):
        return None

    # Debug — print what Claude extracted so we can verify times
    print("\n  [DEBUG] Claude extracted:")
    for f in data.get("flights", []):
        print(f"    departure_datetime : {f.get('departure_datetime')}")
        print(f"    departure_timezone : {f.get('departure_timezone')}")
        print(f"    arrival_datetime   : {f.get('arrival_datetime')}")
        print(f"    arrival_timezone   : {f.get('arrival_timezone')}")

    return data


# ─── Google Calendar ──────────────────────────────────────────────────────────

def create_calendar_event(calendar_service, flight: dict, trip: dict) -> str:
    """
    Creates a Google Calendar event for a single flight leg.
    Returns the event URL.
    """
    departure = flight["departure_datetime"]
    arrival = flight["arrival_datetime"]
    departure_tz = flight.get("departure_timezone") or "UTC"
    arrival_tz = flight.get("arrival_timezone") or "UTC"

    summary = (
        f"{trip.get('airline', 'Flight')} {flight['flight_number']} — "
        f"{flight['origin']} → {flight['destination']}"
    )

    description_lines = [
        f"Airline: {trip.get('airline', 'N/A')}",
        f"Flight: {flight['flight_number']}",
        f"From: {flight['origin']}",
        f"To: {flight['destination']}",
        f"Confirmation: {trip.get('confirmation_code', 'N/A')}",
        f"Passenger: {trip.get('passenger_name', 'N/A')}",
    ]
    if flight.get("duration_minutes"):
        h, m = divmod(flight["duration_minutes"], 60)
        description_lines.append(f"Duration: {h}h {m}m")

    event = {
        "summary": summary,
        "description": "\n".join(description_lines),
        "start": {"dateTime": departure, "timeZone": departure_tz},
        "end": {"dateTime": arrival, "timeZone": arrival_tz},
        "reminders": {
            "useDefault": False,
            "overrides": [
                {"method": "email", "minutes": 24 * 60},  # 1 day before
                {"method": "popup", "minutes": 180},       # 3 hours before
            ],
        },
    }

    created = calendar_service.events().insert(calendarId="primary", body=event).execute()
    return created.get("htmlLink", "")


# ─── Main ─────────────────────────────────────────────────────────────────────

def main():
    print("Authenticating with Google...")
    creds = get_google_credentials()
    gmail = build("gmail", "v1", credentials=creds)
    calendar = build("calendar", "v3", credentials=creds)

    print("Searching for flight confirmation emails...")
    emails = search_flight_emails(gmail, max_results=10)

    if not emails:
        print("Done — no flight emails found.")
        return

    print(f"Found {len(emails)} candidate email(s). Parsing with Claude...")

    created_count = 0
    for email in emails:
        print(f"\n  Checking: {email['subject'][:70]}")
        trip = parse_flight_details(email)

        if not trip:
            print("  → Not a flight confirmation, skipping.")
            continue

        print(f"  → Flight found! {trip.get('airline')} | {trip.get('confirmation_code')}")

        for flight in trip.get("flights", []):
            print(f"     {flight['flight_number']}: {flight['origin']} → {flight['destination']}")
            url = create_calendar_event(calendar, flight, trip)
            print(f"     Calendar event created: {url}")
            created_count += 1

    print(f"\nDone. Created {created_count} calendar event(s).")


if __name__ == "__main__":
    main()
