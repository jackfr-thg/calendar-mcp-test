import datetime
import json
import os
import sqlite3
from typing import Any, Dict, List, Optional, Set, Tuple

import requests


# Model component
class CalendarDatabaseModel:
    def __init__(self, db_path: str):
        """Initialize the database connection and create tables if they don't exist."""
        self.conn = sqlite3.connect(db_path)
        self.conn.row_factory = sqlite3.Row  # Makes rows accessible by column name
        self.cursor = self.conn.cursor()
        self.setup_database()

    def setup_database(self):
        """Create necessary tables if they don't exist."""
        # Users table
        self.cursor.execute(
            """
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            email TEXT UNIQUE NOT NULL
        )
        """
        )

        # Meeting rooms table
        self.cursor.execute(
            """
        CREATE TABLE IF NOT EXISTS meeting_rooms (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            capacity INTEGER NOT NULL,
            is_virtual BOOLEAN NOT NULL DEFAULT 0
        )
        """
        )

        # Events table (with optional meeting_room_id)
        self.cursor.execute(
            """
        CREATE TABLE IF NOT EXISTS events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            description TEXT,
            start_time DATETIME NOT NULL,
            end_time DATETIME NOT NULL,
            meeting_room_id INTEGER,
            FOREIGN KEY (meeting_room_id) REFERENCES meeting_rooms (id)
        )
        """
        )

        # User-Event junction table (for many-to-many relationship)
        self.cursor.execute(
            """
        CREATE TABLE IF NOT EXISTS user_events (
            user_id INTEGER NOT NULL,
            event_id INTEGER NOT NULL,
            is_organizer BOOLEAN NOT NULL DEFAULT 0,
            PRIMARY KEY (user_id, event_id),
            FOREIGN KEY (user_id) REFERENCES users (id),
            FOREIGN KEY (event_id) REFERENCES events (id) ON DELETE CASCADE
        )
        """
        )

        # Insert a virtual meeting room if it doesn't exist
        self.cursor.execute(
            """
        INSERT OR IGNORE INTO meeting_rooms (id, name, capacity, is_virtual)
        VALUES (1, 'Online Meeting', 999, 1)
        """
        )

        self.conn.commit()

    # User operations
    def add_user(self, name: str, email: str) -> int:
        """Add a new user to the database."""
        try:
            self.cursor.execute(
                "INSERT INTO users (name, email) VALUES (?, ?)", (name, email)
            )
            self.conn.commit()
            return self.cursor.lastrowid
        except sqlite3.IntegrityError:
            # If user with email already exists, return their ID
            self.cursor.execute("SELECT id FROM users WHERE email = ?", (email,))
            return self.cursor.fetchone()[0]

    def get_user_by_email(self, email: str) -> Optional[Dict]:
        """Get user details by email."""
        self.cursor.execute(
            "SELECT id, name, email FROM users WHERE email = ?", (email,)
        )
        row = self.cursor.fetchone()
        if row:
            return dict(row)
        return None

    def get_user_by_name(self, name: str) -> List[Dict]:
        """Get user details by name (might return multiple users)."""
        self.cursor.execute(
            "SELECT id, name, email FROM users WHERE name LIKE ?", (f"%{name}%",)
        )
        rows = self.cursor.fetchall()
        return [dict(row) for row in rows]

    def get_all_users(self) -> List[Dict]:
        """Get all users."""
        self.cursor.execute("SELECT id, name, email FROM users")
        rows = self.cursor.fetchall()
        return [dict(row) for row in rows]

    # Meeting room operations
    def add_meeting_room(
        self, name: str, capacity: int, is_virtual: bool = False
    ) -> int:
        """Add a new meeting room."""
        self.cursor.execute(
            "INSERT INTO meeting_rooms (name, capacity, is_virtual) VALUES (?, ?, ?)",
            (name, capacity, is_virtual),
        )
        self.conn.commit()
        return self.cursor.lastrowid

    def get_all_meeting_rooms(self) -> List[Dict]:
        """Get all meeting rooms."""
        self.cursor.execute("SELECT id, name, capacity, is_virtual FROM meeting_rooms")
        rows = self.cursor.fetchall()
        return [dict(row) for row in rows]

    def get_available_meeting_rooms(
        self, start_time: str, end_time: str, min_capacity: int = 1
    ) -> List[Dict]:
        """Get meeting rooms available during the specified time period."""
        self.cursor.execute(
            """
        SELECT m.id, m.name, m.capacity, m.is_virtual
        FROM meeting_rooms m
        WHERE m.capacity >= ?
        AND (m.is_virtual = 1 OR m.id NOT IN (
            SELECT DISTINCT meeting_room_id
            FROM events
            WHERE meeting_room_id IS NOT NULL
            AND ((start_time <= ? AND end_time > ?) OR
                 (start_time < ? AND end_time >= ?) OR
                 (start_time >= ? AND end_time <= ?))
        ))
        """,
            (
                min_capacity,
                end_time,
                start_time,
                end_time,
                start_time,
                start_time,
                end_time,
            ),
        )

        rows = self.cursor.fetchall()
        return [dict(row) for row in rows]

    # Event operations
    def create_event(
        self,
        title: str,
        description: str,
        start_time: str,
        end_time: str,
        organizer_id: int,
        attendee_ids: List[int],
        meeting_room_id: Optional[int] = None,
    ) -> int:
        """Create a new event with organizer and attendees."""
        try:
            # Insert the event
            self.cursor.execute(
                "INSERT INTO events (title, description, start_time, end_time, meeting_room_id) VALUES (?, ?, ?, ?, ?)",
                (title, description, start_time, end_time, meeting_room_id),
            )
            event_id = self.cursor.lastrowid

            # Add organizer
            self.cursor.execute(
                "INSERT INTO user_events (user_id, event_id, is_organizer) VALUES (?, ?, 1)",
                (organizer_id, event_id),
            )

            # Add attendees
            for user_id in attendee_ids:
                if (
                    user_id != organizer_id
                ):  # Avoid duplicate if organizer is also in attendees
                    self.cursor.execute(
                        "INSERT INTO user_events (user_id, event_id, is_organizer) VALUES (?, ?, 0)",
                        (user_id, event_id),
                    )

            self.conn.commit()
            return event_id
        except sqlite3.Error as e:
            self.conn.rollback()
            raise e

    def get_event_by_id(self, event_id: int) -> Optional[Dict]:
        """Get event details by ID, including attendees."""
        self.cursor.execute(
            """
        SELECT e.id, e.title, e.description, e.start_time, e.end_time, 
               e.meeting_room_id, m.name as meeting_room_name
        FROM events e
        LEFT JOIN meeting_rooms m ON e.meeting_room_id = m.id
        WHERE e.id = ?
        """,
            (event_id,),
        )

        event_row = self.cursor.fetchone()
        if not event_row:
            return None

        event = dict(event_row)

        # Get attendees
        self.cursor.execute(
            """
        SELECT u.id, u.name, u.email, ue.is_organizer
        FROM users u
        JOIN user_events ue ON u.id = ue.user_id
        WHERE ue.event_id = ?
        """,
            (event_id,),
        )

        attendee_rows = self.cursor.fetchall()
        event["attendees"] = [dict(row) for row in attendee_rows]

        return event

    def get_user_events(
        self,
        user_id: int,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
    ) -> List[Dict]:
        """Get events for a specific user in a date range."""
        query = """
        SELECT e.id, e.title, e.description, e.start_time, e.end_time, 
               e.meeting_room_id, m.name as meeting_room_name
        FROM events e
        LEFT JOIN meeting_rooms m ON e.meeting_room_id = m.id
        JOIN user_events ue ON e.id = ue.event_id
        WHERE ue.user_id = ?
        """

        params = [user_id]

        if start_date:
            query += " AND e.start_time >= ?"
            params.append(start_date)

        if end_date:
            query += " AND e.start_time <= ?"
            params.append(end_date)

        query += " ORDER BY e.start_time"

        self.cursor.execute(query, params)
        rows = self.cursor.fetchall()

        events = []
        for row in rows:
            event = dict(row)
            event_id = event["id"]

            # Get attendees for each event
            self.cursor.execute(
                """
            SELECT u.id, u.name, u.email, ue.is_organizer
            FROM users u
            JOIN user_events ue ON u.id = ue.user_id
            WHERE ue.event_id = ?
            """,
                (event_id,),
            )

            attendee_rows = self.cursor.fetchall()
            event["attendees"] = [dict(row) for row in attendee_rows]

            events.append(event)

        return events

    def check_user_availability(
        self, user_id: int, start_time: str, end_time: str
    ) -> bool:
        """Check if a user is available during the specified time period."""
        self.cursor.execute(
            """
        SELECT COUNT(*) as count
        FROM events e
        JOIN user_events ue ON e.id = ue.event_id
        WHERE ue.user_id = ?
        AND ((e.start_time <= ? AND e.end_time > ?) OR
             (e.start_time < ? AND e.end_time >= ?) OR
             (e.start_time >= ? AND e.end_time <= ?))
        """,
            (user_id, end_time, start_time, end_time, start_time, start_time, end_time),
        )

        result = self.cursor.fetchone()
        return result["count"] == 0

    def find_common_available_time(
        self,
        user_ids: List[int],
        duration_minutes: int,
        start_date: str,
        end_date: str,
        start_hour: int = 9,
        end_hour: int = 17,
    ) -> List[Dict]:
        """Find common available time slots for multiple users."""
        # Get all events for these users in the date range
        events_by_user = {}
        for user_id in user_ids:
            self.cursor.execute(
                """
            SELECT e.start_time, e.end_time
            FROM events e
            JOIN user_events ue ON e.id = ue.event_id
            WHERE ue.user_id = ?
            AND e.start_time >= ?
            AND e.end_time <= ?
            ORDER BY e.start_time
            """,
                (user_id, start_date, end_date),
            )

            events_by_user[user_id] = self.cursor.fetchall()

        # Convert start_date and end_date strings to datetime objects
        start_datetime = datetime.datetime.fromisoformat(
            start_date.replace("Z", "+00:00")
        )
        end_datetime = datetime.datetime.fromisoformat(end_date.replace("Z", "+00:00"))

        # Generate potential time slots
        available_slots = []
        current_date = start_datetime.date()

        while current_date <= end_datetime.date():
            for hour in range(start_hour, end_hour):
                slot_start = datetime.datetime.combine(
                    current_date, datetime.time(hour, 0)
                )

                slot_end = slot_start + datetime.timedelta(minutes=duration_minutes)

                # Skip if the slot extends beyond our search range
                if slot_end > end_datetime:
                    continue

                # Check if all users are available for this slot
                all_available = True

                for user_id, user_events in events_by_user.items():
                    for event in user_events:
                        event_start = datetime.datetime.fromisoformat(
                            event[0].replace("Z", "+00:00")
                        )
                        event_end = datetime.datetime.fromisoformat(
                            event[1].replace("Z", "+00:00")
                        )

                        # Check if there's an overlap
                        if event_start <= slot_end and event_end > slot_start:
                            all_available = False
                            break

                    if not all_available:
                        break

                if all_available:
                    available_slots.append(
                        {
                            "start_time": slot_start.isoformat(),
                            "end_time": slot_end.isoformat(),
                        }
                    )

            current_date += datetime.timedelta(days=1)

        return available_slots

    def cancel_event(self, event_id: int) -> bool:
        """Cancel (delete) an event."""
        try:
            self.cursor.execute("DELETE FROM events WHERE id = ?", (event_id,))
            rows_affected = self.cursor.rowcount
            self.conn.commit()
            return rows_affected > 0
        except sqlite3.Error:
            self.conn.rollback()
            return False

    def close(self):
        """Close the database connection."""
        if self.conn:
            self.conn.close()


# Controller component
class CalendarController:
    def __init__(
        self,
        model: CalendarDatabaseModel,
        ollama_url: str = "http://localhost:11434",
        model_name: str = "llama3",
    ):
        """Initialize the controller with a database model and LLM settings."""
        self.model = model
        self.ollama_url = ollama_url
        self.llm_model = model_name

    def generate_response(self, prompt: str) -> str:
        """Send prompt to Ollama API and get response."""
        api_url = f"{self.ollama_url}/api/generate"

        # Add system context to help the LLM understand its role
        system_context = """
        You are a helpful meeting scheduling assistant. You can:
        1. Schedule meetings between users
        2. Check availability of users and meeting rooms
        3. Cancel meetings
        4. List upcoming events for users
        
        Please respond to the user's request about meetings and scheduling.
        """

        full_prompt = f"{system_context}\n\nUser request: {prompt}\n\nYour response:"

        data = {"model": self.llm_model, "prompt": full_prompt, "stream": False}

        try:
            response = requests.post(api_url, json=data)
            response.raise_for_status()
            result = response.json()
            return result.get("response", "I couldn't generate a response.")
        except requests.exceptions.RequestException as e:
            return f"Error connecting to Ollama: {str(e)}"

    def process_query(self, user_query: str) -> str:
        """Process the user query and either perform actions on the calendar or get LLM response."""
        # Extract potential intent from the query
        intent = self._extract_intent(user_query.lower())

        if intent == "schedule_meeting":
            return self._handle_scheduling(user_query)
        elif intent == "check_availability":
            return self._handle_availability_check(user_query)
        elif intent == "list_events":
            return self._handle_list_events(user_query)
        elif intent == "cancel_meeting":
            return self._handle_cancel_meeting(user_query)
        else:
            # For other intents, generate a response from the LLM
            response = self.generate_response(user_query)
            return response

    def _extract_intent(self, query: str) -> str:
        """Extract intent using the LLM."""
        # Create a prompt for the LLM to classify the intent
        intent_prompt = f"""
        Analyze the following user query and determine the intent. 
        Respond with exactly one of these categories: 
        - schedule_meeting: For queries about creating or booking new meetings
        - check_availability: For queries about when users or rooms are available
        - list_events: For queries about showing or listing existing meetings
        - cancel_meeting: For queries about canceling or removing meetings
        - other: For queries that don't fit the above categories
        
        User query: "{query}"
        
        Intent:
        """

        # Get the response from the LLM
        response = self.generate_response(intent_prompt).strip().lower()

        # Extract the intent from the response
        if "schedule_meeting" in response:
            return "schedule_meeting"
        elif "check_availability" in response:
            return "check_availability"
        elif "list_events" in response:
            return "list_events"
        elif "cancel_meeting" in response:
            return "cancel_meeting"
        else:
            return "other"

        # Fallback to rule-based intent extraction if LLM classification fails
        try:
            # Get the response from the LLM
            response = self.generate_response(intent_prompt).strip().lower()

            # Extract the intent from the response
            if "schedule_meeting" in response:
                return "schedule_meeting"
            elif "check_availability" in response:
                return "check_availability"
            elif "list_events" in response:
                return "list_events"
            elif "cancel_meeting" in response:
                return "cancel_meeting"
            else:
                return "other"
        except Exception as e:
            # If there's an error with the LLM, fall back to rule-based approach
            if any(
                word in query.lower()
                for word in ["schedule", "set up", "book", "create", "new meeting"]
            ):
                return "schedule_meeting"
            elif any(
                word in query.lower()
                for word in ["available", "free", "availability", "when can"]
            ):
                return "check_availability"
            elif any(
                word in query.lower()
                for word in ["list", "show", "view", "my meetings", "upcoming"]
            ):
                return "list_events"
            elif any(word in query.lower() for word in ["cancel", "delete", "remove"]):
                return "cancel_meeting"
            else:
                return "other"

    def _handle_scheduling(self, query: str) -> str:
        """Handle meeting scheduling requests by extracting info and creating the meeting."""
        # Get current date information for proper context
        current_date = datetime.datetime.now()
        current_year = current_date.year
        current_month = current_date.month
        current_day = current_date.day

        # Create a structured prompt for the LLM to extract meeting details
        extraction_prompt = f"""
        Today's date is {current_date.strftime('%A, %B %d, %Y')}.
        
        Extract the following information for scheduling a meeting from this request: '{query}'.
        Format as JSON with these fields:
        - title: A concise meeting title
        - description: Brief description of the meeting purpose
        - attendees: Array of names of people attending
        - start_time: ISO format date/time for the meeting start (infer a reasonable time if not specified)
        - end_time: ISO format date/time for the meeting end (assume 1 hour duration if not specified)
        - meeting_room: Meeting room name or number (if specified)
        
        For dates, if "tomorrow" is mentioned, use tomorrow's date. If a day of week is mentioned like "Monday", 
        use the date for the next occurrence of that day. If no specific date is mentioned, assume tomorrow.
        For times, if not specified, assume business hours (9 AM start time).
        
        IMPORTANT: All dates must be in {current_year}. Do not use any dates from past years.
        
        Return ONLY the JSON with no additional text.
        """

        # Get the structured data from the LLM
        llm_response = self.generate_response(extraction_prompt)

        try:
            # Try to parse the JSON response
            # First, find JSON content if it's wrapped in any markdown or other text
            json_start = llm_response.find("{")
            json_end = llm_response.rfind("}") + 1

            if json_start >= 0 and json_end > json_start:
                json_str = llm_response[json_start:json_end]
                meeting_data = json.loads(json_str)
            else:
                # Fallback if no JSON found
                return "I couldn't understand the meeting details. Please try again with more specific information."

            # Validate required fields
            required_fields = ["title", "attendees", "start_time", "end_time"]
            for field in required_fields:
                if field not in meeting_data:
                    return f"I couldn't extract the {field} from your request. Please specify it clearly."

            # Validate and correct dates if needed
            start_time_str = meeting_data["start_time"]
            end_time_str = meeting_data["end_time"]

            try:
                # Parse the dates
                start_time = datetime.datetime.fromisoformat(
                    start_time_str.replace("Z", "+00:00")
                )
                end_time = datetime.datetime.fromisoformat(
                    end_time_str.replace("Z", "+00:00")
                )

                # Check if the year is correct (current year)
                if start_time.year != current_year:
                    # Fix the year while keeping other date components
                    start_time = start_time.replace(year=current_year)
                    meeting_data["start_time"] = start_time.isoformat()

                if end_time.year != current_year:
                    # Fix the year while keeping other date components
                    end_time = end_time.replace(year=current_year)
                    meeting_data["end_time"] = end_time.isoformat()
            except (ValueError, TypeError):
                return "The date format provided is invalid. Please use a standard date format."

            # Look up attendee IDs
            attendee_ids = []
            organizer_id = None
            missing_attendees = []

            # Process attendees
            for attendee_name in meeting_data["attendees"]:
                # Look for partial name matches
                users = self.model.get_user_by_name(attendee_name)

                if users:
                    # Use the first matching user
                    attendee_ids.append(users[0]["id"])
                    # Set the first attendee as the organizer if not set yet
                    if organizer_id is None:
                        organizer_id = users[0]["id"]
                else:
                    missing_attendees.append(attendee_name)

            if missing_attendees:
                attendee_list = ", ".join(missing_attendees)
                return f"I couldn't find these users in the system: {attendee_list}. Please check the names and try again."

            # Look up meeting room ID if specified
            meeting_room_id = None
            if "meeting_room" in meeting_data and meeting_data["meeting_room"]:
                room_name = meeting_data["meeting_room"]

                # Handle room specified by number
                if (
                    room_name.lower()
                    .replace("meeting room ", "")
                    .replace("room ", "")
                    .isdigit()
                ):
                    room_number = (
                        room_name.lower()
                        .replace("meeting room ", "")
                        .replace("room ", "")
                    )
                    rooms = self.model.get_all_meeting_rooms()
                    for room in rooms:
                        if str(room["id"]) == room_number or room[
                            "name"
                        ].lower().endswith(f" {room_number}"):
                            meeting_room_id = room["id"]
                            break
                else:
                    # Look for room by name
                    rooms = self.model.get_all_meeting_rooms()
                    for room in rooms:
                        if (
                            room["name"].lower() == room_name.lower()
                            or room_name.lower() in room["name"].lower()
                        ):
                            meeting_room_id = room["id"]
                            break

            # Ensure description exists
            description = meeting_data.get("description", "No description provided")

            # Create the meeting
            try:
                event_id = self.model.create_event(
                    meeting_data["title"],
                    description,
                    meeting_data["start_time"],
                    meeting_data["end_time"],
                    organizer_id,
                    attendee_ids,
                    meeting_room_id,
                )

                # Format the response
                start_time = datetime.datetime.fromisoformat(
                    meeting_data["start_time"].replace("Z", "+00:00")
                )
                end_time = datetime.datetime.fromisoformat(
                    meeting_data["end_time"].replace("Z", "+00:00")
                )

                attendee_names = [
                    user["name"]
                    for user in self.model.get_all_users()
                    if user["id"] in attendee_ids
                ]
                room_info = ""
                if meeting_room_id:
                    rooms = self.model.get_all_meeting_rooms()
                    for room in rooms:
                        if room["id"] == meeting_room_id:
                            room_info = f" in {room['name']}"
                            break

                response = f"✓ Meeting scheduled: \"{meeting_data['title']}\"\n"
                response += f"Date: {start_time.strftime('%A, %B %d, %Y')}\n"
                response += f"Time: {start_time.strftime('%I:%M %p')} - {end_time.strftime('%I:%M %p')}\n"
                response += f"Attendees: {', '.join(attendee_names)}\n"
                if room_info:
                    response += f"Location: {room_info}\n"
                else:
                    response += "Location: Online meeting\n"

                return response

            except sqlite3.Error as e:
                return f"Error creating the meeting: {str(e)}"

        except json.JSONDecodeError:
            return "I couldn't understand the meeting details. Please provide a clearer description of when, where, and who should attend the meeting."
        except Exception as e:
            return f"An error occurred: {str(e)}"

    def _handle_availability_check(self, query: str) -> str:
        """Handle availability check requests."""
        query_lower = query.lower()

        # Check if it's a user availability query
        user_id = None
        for user in self.model.get_all_users():
            if user["name"].lower() in query_lower:
                user_id = user["id"]
                user_name = user["name"]
                break

        # If asking about a user's availability
        if user_id:
            # Try to extract date from query
            today = datetime.datetime.now().date()
            check_date = today

            if "tomorrow" in query_lower:
                check_date = today + datetime.timedelta(days=1)
            elif "next" in query_lower and "week" in query_lower:
                check_date = today + datetime.timedelta(days=7)

            # Format date for database query
            date_str = check_date.isoformat()
            start_of_day = f"{date_str}T00:00:00"
            end_of_day = f"{date_str}T23:59:59"

            # Get events for that user on that day
            events = self.model.get_user_events(user_id, start_of_day, end_of_day)

            if not events:
                date_desc = (
                    "today" if check_date == today else check_date.strftime("%A, %B %d")
                )
                return f"{user_name} is available all day {date_desc}."

            # Build time blocks of availability
            busy_periods = []
            for event in events:
                start_time = datetime.datetime.fromisoformat(
                    event["start_time"].replace("Z", "+00:00")
                )
                end_time = datetime.datetime.fromisoformat(
                    event["end_time"].replace("Z", "+00:00")
                )
                busy_periods.append((start_time, end_time, event["title"]))

            # Sort by start time
            busy_periods.sort(key=lambda x: x[0])

            date_desc = (
                "today" if check_date == today else check_date.strftime("%A, %B %d")
            )
            response = f"{user_name}'s availability for {date_desc}:\n\n"

            # Add busy periods
            response += "Busy during:\n"
            for start, end, title in busy_periods:
                response += (
                    f"- {start.strftime('%H:%M')} - {end.strftime('%H:%M')}: {title}\n"
                )

            # Calculate free periods (assuming 9 AM - 5 PM workday)
            work_start = datetime.datetime.combine(check_date, datetime.time(9, 0))
            work_end = datetime.datetime.combine(check_date, datetime.time(17, 0))

            free_periods = []
            current_time = work_start

            for start, end, _ in busy_periods:
                if current_time < start:
                    free_periods.append((current_time, start))
                current_time = max(current_time, end)

            if current_time < work_end:
                free_periods.append((current_time, work_end))

            # Add free periods
            response += "\nAvailable during:\n"
            if not free_periods:
                response += "- No availability during work hours (9 AM - 5 PM)\n"
            else:
                for start, end in free_periods:
                    response += (
                        f"- {start.strftime('%H:%M')} - {end.strftime('%H:%M')}\n"
                    )

            return response

        # Check if it's a meeting room availability query
        room_id = None
        for room in self.model.get_all_meeting_rooms():
            room_name = room["name"].lower()
            if room_name in query_lower or f"room {room['id']}" in query_lower:
                room_id = room["id"]
                room_name = room["name"]
                break

        # If asking about a specific room
        if room_id:
            # Try to extract date from query
            today = datetime.datetime.now().date()
            check_date = today

            if "tomorrow" in query_lower:
                check_date = today + datetime.timedelta(days=1)

            # Format date for database query
            date_str = check_date.isoformat()
            start_of_day = f"{date_str}T00:00:00"
            end_of_day = f"{date_str}T23:59:59"

            # Get events in that room on that day
            self.cursor.execute(
                """
            SELECT title, start_time, end_time 
            FROM events 
            WHERE meeting_room_id = ? 
            AND start_time >= ? 
            AND start_time <= ?
            ORDER BY start_time
            """,
                (room_id, start_of_day, end_of_day),
            )

            events = self.cursor.fetchall()

            date_desc = (
                "today" if check_date == today else check_date.strftime("%A, %B %d")
            )

            if not events:
                return f"{room_name} is available all day {date_desc}."

            response = f"{room_name} availability for {date_desc}:\n\n"
            response += "Booked for:\n"

            for event in events:
                start_time = datetime.datetime.fromisoformat(
                    event["start_time"].replace("Z", "+00:00")
                )
                end_time = datetime.datetime.fromisoformat(
                    event["end_time"].replace("Z", "+00:00")
                )
                response += f"- {start_time.strftime('%H:%M')} - {end_time.strftime('%H:%M')}: {event['title']}\n"

            return response

        # If no specific user or room was found, return info about all meeting rooms
        rooms = self.model.get_all_meeting_rooms()

        response = "Here are the available meeting rooms:\n\n"
        for room in rooms:
            room_type = "Virtual" if room["is_virtual"] else "Physical"
            response += (
                f"- {room['name']} (Capacity: {room['capacity']}, Type: {room_type})\n"
            )

        response += "\nFor specific availability, please specify a user or room name and a date."
        return response

    def _handle_list_events(self, query: str) -> str:
        """Handle requests to list events."""
        # Extract user name from query
        query_lower = query.lower()
        user_id = None

        # Get all users and look for mention in the query
        users = self.model.get_all_users()
        for user in users:
            # Check for user's name in the query (case insensitive)
            if user["name"].lower() in query_lower:
                user_id = user["id"]
                user_name = user["name"]
                break

        # If no user found or ambiguous, handle accordingly
        if not user_id:
            return "I'm not sure whose meetings you're asking about. Please specify a user by name."

        # Determine time range from query
        today = datetime.datetime.now().date()
        start_date = today.isoformat()

        # Default to one week
        end_date = (today + datetime.timedelta(days=7)).isoformat()

        # Check for specific time ranges
        if "today" in query_lower:
            end_date = today.isoformat()
        elif "tomorrow" in query_lower:
            start_date = (today + datetime.timedelta(days=1)).isoformat()
            end_date = start_date
        elif "this week" in query_lower:
            # Keep the default week range
            pass
        elif "next week" in query_lower:
            start_date = (today + datetime.timedelta(days=7)).isoformat()
            end_date = (today + datetime.timedelta(days=14)).isoformat()

        # Get events for the specified user and time range
        events = self.model.get_user_events(user_id, start_date, end_date)

        if not events:
            time_description = (
                "today"
                if start_date == end_date and start_date == today.isoformat()
                else "in the specified time period"
            )
            return f"{user_name} doesn't have any meetings {time_description}."

        response = f"{user_name}'s meetings:\n\n"
        for event in events:
            start_time = datetime.datetime.fromisoformat(
                event["start_time"].replace("Z", "+00:00")
            )
            end_time = datetime.datetime.fromisoformat(
                event["end_time"].replace("Z", "+00:00")
            )

            response += f"- {event['title']}\n"
            response += f"  Date: {start_time.strftime('%Y-%m-%d')}\n"
            response += f"  Time: {start_time.strftime('%H:%M')} - {end_time.strftime('%H:%M')}\n"

            if event["meeting_room_name"]:
                response += f"  Location: {event['meeting_room_name']}\n"
            else:
                response += f"  Location: Online\n"

            # Add attendees information
            response += "  Attendees: "
            attendee_names = [att["name"] for att in event["attendees"]]
            response += ", ".join(attendee_names)
            response += "\n\n"

        return response

    def _handle_cancel_meeting(self, query: str) -> str:
        """Handle meeting cancellation requests."""
        # Extract user name from query
        query_lower = query.lower()
        user_id = None

        # Get all users and look for mention in the query
        users = self.model.get_all_users()
        for user in users:
            # Check for user's name in the query (case insensitive)
            if user["name"].lower() in query_lower:
                user_id = user["id"]
                user_name = user["name"]
                break

        # If no user found, use generic approach
        if not user_id:
            return "I'm not sure whose meetings you're asking about. Please specify a user by name."

        today = datetime.datetime.now().date().isoformat()
        one_week_later = (
            (datetime.datetime.now() + datetime.timedelta(days=7)).date().isoformat()
        )

        events = self.model.get_user_events(user_id, today, one_week_later)

        if not events:
            return f"{user_name} doesn't have any upcoming meetings to cancel."

        response = (
            f"Here are {user_name}'s upcoming meetings that could be cancelled:\n\n"
        )
        for event in events:
            start_time = datetime.datetime.fromisoformat(
                event["start_time"].replace("Z", "+00:00")
            )

            response += f"- ID: {event['id']}, {event['title']} on {start_time.strftime('%Y-%m-%d at %H:%M')}\n"

        response += "\nTo cancel a meeting, please specify the meeting ID."
        return response

    # Additional calendar-specific functions
    def create_user(self, name: str, email: str) -> int:
        """Create a new user."""
        return self.model.add_user(name, email)

    def create_meeting_room(
        self, name: str, capacity: int, is_virtual: bool = False
    ) -> int:
        """Create a new meeting room."""
        return self.model.add_meeting_room(name, capacity, is_virtual)

    def schedule_meeting(
        self,
        title: str,
        description: str,
        start_time: str,
        end_time: str,
        organizer_id: int,
        attendee_ids: List[int],
        meeting_room_id: Optional[int] = None,
    ) -> int:
        """Schedule a new meeting."""
        return self.model.create_event(
            title,
            description,
            start_time,
            end_time,
            organizer_id,
            attendee_ids,
            meeting_room_id,
        )

    def cancel_meeting_by_id(self, event_id: int) -> bool:
        """Cancel a meeting by ID."""
        return self.model.cancel_event(event_id)


# Presenter component (CLI interface)
class CalendarChatbotPresenter:
    def __init__(self, controller: CalendarController):
        """Initialize the presenter with a controller."""
        self.controller = controller

    def display_welcome(self):
        """Display welcome message and instructions."""
        print("=" * 60)
        print("Welcome to Meeting Calendar Assistant")
        print("You can ask me to:")
        print("- Schedule meetings")
        print("- Check user or meeting room availability")
        print("- List your upcoming meetings")
        print("- Cancel meetings")
        print("\nType 'exit' to quit, 'help' for more information.")
        print("=" * 60)

    def display_response(self, response: str):
        """Display chatbot response with formatting."""
        print("\nAssistant: ", end="")
        print(response)
        print()

    def setup_sample_data(self):
        # """Set up sample data for demonstration purposes."""
        # print("Setting up sample data...")
        #
        # # Add users
        # user1_id = self.controller.create_user("John Doe", "john@example.com")
        # user2_id = self.controller.create_user("Jane Smith", "jane@example.com")
        # user3_id = self.controller.create_user("Bob Johnson", "bob@example.com")
        #
        # # Add meeting rooms
        # room1_id = self.controller.create_meeting_room("Conference Room A", 10)
        # room2_id = self.controller.create_meeting_room("Conference Room B", 6)
        # room3_id = self.controller.create_meeting_room("Small Meeting Room", 4)
        #
        # # Add a sample meeting
        # now = datetime.datetime.now()
        # tomorrow = now + datetime.timedelta(days=1)
        #
        # start_time = tomorrow.replace(hour=10, minute=0, second=0).isoformat()
        # end_time = tomorrow.replace(hour=11, minute=0, second=0).isoformat()
        #
        # self.controller.schedule_meeting(
        #     "Project Kickoff",
        #     "Initial meeting to discuss project goals",
        #     start_time,
        #     end_time,
        #     user1_id,
        #     [user1_id, user2_id, user3_id],
        #     room1_id
        # )

        print("Sample data created successfully!")

    def run(self):
        """Run the chatbot interface."""
        self.display_welcome()
        self.setup_sample_data()

        while True:
            user_input = input("You: ").strip()

            if user_input.lower() == "exit":
                print("Goodbye!")
                break

            elif user_input.lower() == "help":
                self.display_welcome()

            else:
                response = self.controller.process_query(user_input)
                self.display_response(response)


# Main application
def main():
    db_path = "calendar_database.db"
    ollama_url = os.environ.get("OLLAMA_URL", "http://localhost:11434")
    model_name = os.environ.get("OLLAMA_MODEL", "llama3")

    # Initialize components
    db_model = CalendarDatabaseModel(db_path)
    controller = CalendarController(db_model, ollama_url, model_name)
    presenter = CalendarChatbotPresenter(controller)

    try:
        # Run the chatbot
        presenter.run()
    finally:
        # Ensure database connection is closed
        db_model.close()


if __name__ == "__main__":
    main()
