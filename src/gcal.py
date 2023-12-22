from datetime import datetime, timedelta
from googleapiclient.discovery import build
from hypercorn.asyncio import serve
from hypercorn.config import Config
from zoneinfo import ZoneInfo
import asyncio
import config
import os
import threading

API_KEY = config.ensure("MAIA_GCAL_API_KEY")
CALENDAR_ID = config.ensure("MAIA_GCAL_CALENDAR_ID")

def get_google_calendar_events_for_today():
    service = build('calendar', 'v3', developerKey=API_KEY)
    user_timezone = ZoneInfo("America/Los_Angeles")
    utc_now = datetime.utcnow().replace(tzinfo=ZoneInfo("UTC"))
    local_now = utc_now.astimezone(user_timezone)
    today_start = local_now.replace(hour=0, minute=0, second=0, microsecond=0).isoformat()
    today_end = local_now.replace(hour=23, minute=59, second=59, microsecond=999999).isoformat()
    print(today_start)
    print(today_end)
    events_result = service.events().list(
            calendarId=CALENDAR_ID,
            timeMin=today_start,
            timeMax=today_end,
            singleEvents=True,
            orderBy='startTime'
            ).execute()
    events = events_result.get('items', [])
    if not events:
        return 'No Events for Today.'
    else:
        text = 'Events for Today:\n'
        for event in events:
            start_time = event['start'].get('dateTime', event['start'].get('date'))
            end_time = event['end'].get('dateTime', event['end'].get('date'))
            description = f", Description: {event['description']}" if 'description' in event else ''
            text += f"- Title: {event['summary']}, Start: {start_time}, End: {end_time}{description}\n"
        return text

chatbot_functions = [
        {"type": "function",
         "function": {"name": "get_google_calendar_events_for_today",
                      "description": "Gets the calendar events for today"
                      }
         }
]

function_callbacks = {
        "get_google_calendar_events_for_today": lambda *args: get_google_calendar_events_for_today()
        }
