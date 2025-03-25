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
        """Simple rule-based intent extraction."""
        if any(
            word in query
            for word in ["schedule", "set up", "book", "create", "new meeting"]
        ):
            return "schedule_meeting"
        elif any(
            word in query for word in ["available", "free", "availability", "when can"]
        ):
            return "check_availability"
        elif any(
            word in query
            for word in ["list", "show", "view", "my meetings", "upcoming"]
        ):
            return "list_events"
        elif any(word in query for word in ["cancel", "delete", "remove"]):
            return "cancel_meeting"
        else:
            return "other"

    def _handle_scheduling(self, query: str) -> str:
        """Handle meeting scheduling requests."""
        # This is a simplified approach - in a real system, you'd use NLP to extract entities
        # For demonstration, we'll pass the query to the LLM and then parse essential information
        llm_response = self.generate_response(
            f"Extract the following information for scheduling a meeting from this request: '{query}'. Format as JSON with the fields: title, description, attendees (list of names or emails), start_time (ISO format), end_time (ISO format), meeting_room (optional). If any information is missing, say so."
        )

        # In a real implementation, you would parse the JSON from the LLM response
        # For simplicity, let's just return the suggestion from the LLM
        return f"I understood you want to schedule a meeting. Here's what I extracted:\n\n{llm_response}\n\nTo actually schedule this meeting, please provide all required information in a structured format."

    def _handle_availability_check(self, query: str) -> str:
        """Handle availability check requests."""
        # For simplicity, we'll just provide information about all meeting rooms
        rooms = self.model.get_all_meeting_rooms()

        response = "Here are the available meeting rooms:\n\n"
        for room in rooms:
            room_type = "Virtual" if room["is_virtual"] else "Physical"
            response += (
                f"- {room['name']} (Capacity: {room['capacity']}, Type: {room_type})\n"
            )

        response += "\nFor specific availability, please specify a date and time range."
        return response

    def _handle_list_events(self, query: str) -> str:
        """Handle requests to list events."""
        # For simplicity, assuming user ID 1
        user_id = 1
        today = datetime.datetime.now().date().isoformat()
        one_week_later = (
            (datetime.datetime.now() + datetime.timedelta(days=7)).date().isoformat()
        )

        events = self.model.get_user_events(user_id, today, one_week_later)

        if not events:
            return "You don't have any upcoming meetings in the next week."

        response = "Your upcoming meetings:\n\n"
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

            response += "\n"

        return response

    def _handle_cancel_meeting(self, query: str) -> str:
        """Handle meeting cancellation requests."""
        # For simplicity, we'll just suggest which meetings could be cancelled
        user_id = 1  # Assuming user ID 1
        today = datetime.datetime.now().date().isoformat()
        one_week_later = (
            (datetime.datetime.now() + datetime.timedelta(days=7)).date().isoformat()
        )

        events = self.model.get_user_events(user_id, today, one_week_later)

        if not events:
            return "You don't have any upcoming meetings to cancel."

        response = "Which of these meetings would you like to cancel?\n\n"
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
        """Set up sample data for demonstration purposes."""
        print("Setting up sample data...")

        # Add users
        user1_id = self.controller.create_user("John Doe", "john@example.com")
        user2_id = self.controller.create_user("Jane Smith", "jane@example.com")
        user3_id = self.controller.create_user("Bob Johnson", "bob@example.com")

        # Add meeting rooms
        room1_id = self.controller.create_meeting_room("Conference Room A", 10)
        room2_id = self.controller.create_meeting_room("Conference Room B", 6)
        room3_id = self.controller.create_meeting_room("Small Meeting Room", 4)

        # Add a sample meeting
        now = datetime.datetime.now()
        tomorrow = now + datetime.timedelta(days=1)

        start_time = tomorrow.replace(hour=10, minute=0, second=0).isoformat()
        end_time = tomorrow.replace(hour=11, minute=0, second=0).isoformat()

        self.controller.schedule_meeting(
            "Project Kickoff",
            "Initial meeting to discuss project goals",
            start_time,
            end_time,
            user1_id,
            [user1_id, user2_id, user3_id],
            room1_id,
        )

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
