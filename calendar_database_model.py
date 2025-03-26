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
