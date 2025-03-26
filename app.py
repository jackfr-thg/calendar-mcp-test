import os
import sqlite3
import traceback
from datetime import datetime

from flask import Flask, jsonify, request

app = Flask(__name__)

# Database configuration
DB_PATH = "calendar_database.db"


# Helper function to get database connection
def get_db_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


# User endpoints
@app.route("/api/users", methods=["GET"])
def get_users():
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT id, name FROM USERS")
    users = [{"id": row["id"], "username": row["name"]} for row in cursor.fetchall()]
    conn.close()

    return jsonify(users)


@app.route("/api/users/<user_id>", methods=["GET"])
def get_user(user_id):
    conn = get_db_connection()
    cursor = conn.cursor()

    # Get user details
    cursor.execute("SELECT id, name, email FROM USERS WHERE id = ?", (user_id,))
    user = cursor.fetchone()

    if not user:
        conn.close()
        return jsonify({"error": "User not found"}), 404

    # Get user's events
    cursor.execute(
        """
        SELECT e.id, e.title 
        FROM EVENTS e
        JOIN USER_EVENTS ue ON e.id = ue.event_id
        WHERE ue.user_id = ?
    """,
        (user_id,),
    )

    events = [{"id": row["id"], "title": row["title"]} for row in cursor.fetchall()]
    conn.close()

    return jsonify({"id": user["id"], "username": user["name"], "events": events})


@app.route("/api/users", methods=["POST"])
def create_user():
    data = request.json
    if not data or not data.get("username"):
        return jsonify({"error": "Username is required"}), 400

    conn = get_db_connection()
    cursor = conn.cursor()

    try:
        # Get email from request or generate one
        email = data.get("email", f"{data['username']}@example.com")

        cursor.execute(
            "INSERT INTO USERS (name, email) VALUES (?, ?)", (data["username"], email)
        )

        user_id = cursor.lastrowid
        conn.commit()
        conn.close()

        return jsonify({"id": user_id, "username": data["username"]}), 201
    except sqlite3.IntegrityError:
        conn.close()
        return jsonify({"error": "Username already exists or email is taken"}), 400
    except Exception as e:
        conn.close()
        return jsonify({"error": str(e)}), 500


@app.route("/api/users/username/<username>", methods=["GET"])
def get_user_by_username(username):
    conn = get_db_connection()
    cursor = conn.cursor()

    # Get user details
    cursor.execute("SELECT id, name, email FROM USERS WHERE name = ?", (username,))
    user = cursor.fetchone()

    if not user:
        conn.close()
        return jsonify({"error": f"User '{username}' not found"}), 404

    # Get user's events
    cursor.execute(
        """
        SELECT e.id, e.title, e.description, e.start_time, e.end_time
        FROM EVENTS e
        JOIN USER_EVENTS ue ON e.id = ue.event_id
        WHERE ue.user_id = ?
    """,
        (user["id"],),
    )

    events = [
        {
            "id": row["id"],
            "title": row["title"],
            "description": row["description"],
            "start_time": row["start_time"],
            "end_time": row["end_time"],
        }
        for row in cursor.fetchall()
    ]

    conn.close()

    return jsonify({"id": user["id"], "username": user["name"], "events": events})


@app.route("/api/users/username/<username>/events", methods=["GET"])
def get_user_events_by_username(username):
    conn = get_db_connection()
    cursor = conn.cursor()

    # Get user ID
    cursor.execute("SELECT id FROM USERS WHERE name = ?", (username,))
    user = cursor.fetchone()

    if not user:
        conn.close()
        return jsonify({"error": f"User '{username}' not found"}), 404

    # Get user's events
    cursor.execute(
        """
        SELECT e.id, e.title, e.description, e.start_time, e.end_time
        FROM EVENTS e
        JOIN USER_EVENTS ue ON e.id = ue.event_id
        WHERE ue.user_id = ?
    """,
        (user["id"],),
    )

    events_data = cursor.fetchall()
    events = []

    for event in events_data:
        # Get event organizer
        cursor.execute(
            """
            SELECT user_id 
            FROM USER_EVENTS 
            WHERE event_id = ? AND is_organizer = 1
        """,
            (event["id"],),
        )
        organizer = cursor.fetchone()
        organizer_id = organizer["user_id"] if organizer else None

        # Get participants
        cursor.execute(
            """
            SELECT u.id, u.name
            FROM USERS u
            JOIN USER_EVENTS ue ON u.id = ue.user_id
            WHERE ue.event_id = ?
        """,
            (event["id"],),
        )

        participants = [
            {"id": row["id"], "username": row["name"]} for row in cursor.fetchall()
        ]

        events.append(
            {
                "id": event["id"],
                "title": event["title"],
                "description": event["description"],
                "start_time": event["start_time"],
                "end_time": event["end_time"],
                "user_id": organizer_id,
                "participants": participants,
            }
        )

    conn.close()
    return jsonify(events)


@app.route("/api/users/search", methods=["GET"])
def search_users():
    query = request.args.get("q", "")
    if not query or len(query) < 2:
        return jsonify([]), 200

    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute(
        "SELECT id, name FROM USERS WHERE name LIKE ? LIMIT 10", (f"%{query}%",)
    )
    users = [{"id": row["id"], "username": row["name"]} for row in cursor.fetchall()]
    conn.close()

    return jsonify(users)


# Event endpoints
@app.route("/api/events", methods=["GET"])
def get_events():
    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute("SELECT id, title, description, start_time, end_time FROM EVENTS")
    events_data = cursor.fetchall()
    result = []

    for event in events_data:
        # Get organizer
        cursor.execute(
            """
            SELECT user_id 
            FROM USER_EVENTS 
            WHERE event_id = ? AND is_organizer = 1
        """,
            (event["id"],),
        )
        organizer = cursor.fetchone()
        organizer_id = organizer["user_id"] if organizer else None

        # Get participants
        cursor.execute(
            """
            SELECT u.id, u.name
            FROM USERS u
            JOIN USER_EVENTS ue ON u.id = ue.user_id
            WHERE ue.event_id = ?
        """,
            (event["id"],),
        )

        participants = [
            {"id": row["id"], "username": row["name"]} for row in cursor.fetchall()
        ]

        result.append(
            {
                "id": event["id"],
                "title": event["title"],
                "description": event["description"],
                "start_time": event["start_time"],
                "end_time": event["end_time"],
                "user_id": organizer_id,
                "participants": participants,
            }
        )

    conn.close()
    return jsonify(result)


@app.route("/api/events", methods=["POST"])
def create_event():
    data = request.json
    if not data:
        return jsonify({"error": "No data provided"}), 400

    # Validate required fields
    required_fields = ["title", "start_time", "end_time"]
    for field in required_fields:
        if field not in data:
            return jsonify({"error": f"Missing required field: {field}"}), 400

    conn = get_db_connection()
    cursor = conn.cursor()

    try:
        # Create event
        cursor.execute(
            """
            INSERT INTO EVENTS (title, description, start_time, end_time, meeting_room_id) 
            VALUES (?, ?, ?, ?, ?)
        """,
            (
                data["title"],
                data.get("description", ""),
                data["start_time"],
                data["end_time"],
                data.get("meeting_room_id"),  # Store but don't return
            ),
        )

        event_id = cursor.lastrowid

        # Add organizer
        if data.get("user_id"):
            cursor.execute(
                """
                INSERT INTO USER_EVENTS (user_id, event_id, is_organizer) 
                VALUES (?, ?, 1)
            """,
                (data["user_id"], event_id),
            )

        # Add participants
        if data.get("invited_users") and isinstance(data["invited_users"], list):
            for user_id in data["invited_users"]:
                if user_id != data.get("user_id"):  # Skip organizer
                    cursor.execute(
                        """
                        INSERT INTO USER_EVENTS (user_id, event_id, is_organizer) 
                        VALUES (?, ?, 0)
                    """,
                        (user_id, event_id),
                    )

        conn.commit()

        # Get the created event
        cursor.execute(
            """
            SELECT id, title, description, start_time, end_time
            FROM EVENTS WHERE id = ?
        """,
            (event_id,),
        )
        event = cursor.fetchone()

        # Get participants
        cursor.execute(
            """
            SELECT u.id, u.name
            FROM USERS u
            JOIN USER_EVENTS ue ON u.id = ue.user_id
            WHERE ue.event_id = ?
        """,
            (event_id,),
        )

        participants = [
            {"id": row["id"], "username": row["name"]} for row in cursor.fetchall()
        ]

        conn.close()

        return (
            jsonify(
                {
                    "id": event["id"],
                    "title": event["title"],
                    "description": event["description"],
                    "start_time": event["start_time"],
                    "end_time": event["end_time"],
                    "user_id": data.get("user_id"),
                    "participants": participants,
                }
            ),
            201,
        )
    except Exception as e:
        conn.rollback()
        conn.close()
        return jsonify({"error": str(e)}), 500


@app.route("/api/events/<event_id>/users", methods=["POST"])
def add_user_to_event(event_id):
    data = request.json
    if not data or not data.get("user_id"):
        return jsonify({"error": "User ID is required"}), 400

    conn = get_db_connection()
    cursor = conn.cursor()

    # Check if event exists
    cursor.execute("SELECT id FROM EVENTS WHERE id = ?", (event_id,))
    event = cursor.fetchone()
    if not event:
        conn.close()
        return jsonify({"error": "Event not found"}), 404

    # Check if user exists
    cursor.execute("SELECT id FROM USERS WHERE id = ?", (data["user_id"],))
    user = cursor.fetchone()
    if not user:
        conn.close()
        return jsonify({"error": "User not found"}), 404

    # Check if user is already in event
    cursor.execute(
        """
        SELECT 1 FROM USER_EVENTS
        WHERE event_id = ? AND user_id = ?
    """,
        (event_id, data["user_id"]),
    )

    if cursor.fetchone():
        conn.close()
        return jsonify({"success": True}), 200

    # Add user to event
    cursor.execute(
        """
        INSERT INTO USER_EVENTS (user_id, event_id, is_organizer)
        VALUES (?, ?, 0)
    """,
        (data["user_id"], event_id),
    )

    conn.commit()
    conn.close()

    return jsonify({"success": True}), 200


@app.route("/api/events/<event_id>", methods=["DELETE"])
def delete_event(event_id):
    conn = get_db_connection()
    cursor = conn.cursor()

    # Check if event exists
    cursor.execute("SELECT id FROM EVENTS WHERE id = ?", (event_id,))
    event = cursor.fetchone()
    if not event:
        conn.close()
        return jsonify({"error": f"Event with ID {event_id} not found"}), 404

    try:
        # Delete event participants
        cursor.execute("DELETE FROM USER_EVENTS WHERE event_id = ?", (event_id,))

        # Delete event
        cursor.execute("DELETE FROM EVENTS WHERE id = ?", (event_id,))

        conn.commit()
        conn.close()

        return jsonify({"success": True}), 200
    except Exception as e:
        conn.rollback()
        conn.close()
        return jsonify({"error": str(e)}), 500


@app.route("/api/events/<event_id>", methods=["PATCH"])
def update_event(event_id):
    data = request.json
    if not data:
        return jsonify({"error": "No data provided"}), 400

    conn = get_db_connection()
    cursor = conn.cursor()

    # Check if event exists
    cursor.execute(
        "SELECT id, title, description, start_time, end_time FROM EVENTS WHERE id = ?",
        (event_id,),
    )
    event = cursor.fetchone()
    if not event:
        conn.close()
        return jsonify({"error": f"Event {event_id} not found"}), 404

    try:
        # Update event fields
        update_fields = []
        update_values = []

        for field in ["title", "description", "start_time", "end_time"]:
            if field in data:
                update_fields.append(f"{field} = ?")
                update_values.append(data[field])

        if update_fields:
            query = f"UPDATE EVENTS SET {', '.join(update_fields)} WHERE id = ?"
            update_values.append(event_id)
            cursor.execute(query, update_values)

        # Handle participants if present
        if "invited_users" in data:
            operation = data.get("user_operation", "set")

            if operation == "set":
                # Get organizer
                cursor.execute(
                    """
                    SELECT user_id FROM USER_EVENTS 
                    WHERE event_id = ? AND is_organizer = 1
                """,
                    (event_id,),
                )

                organizer = cursor.fetchone()
                organizer_id = organizer["user_id"] if organizer else None

                # Remove all participants except organizer
                cursor.execute(
                    """
                    DELETE FROM USER_EVENTS 
                    WHERE event_id = ? AND (is_organizer = 0 OR user_id != ?)
                """,
                    (event_id, organizer_id),
                )

                # Re-add organizer if they were removed
                if organizer_id:
                    cursor.execute(
                        """
                        INSERT OR IGNORE INTO USER_EVENTS (user_id, event_id, is_organizer)
                        VALUES (?, ?, 1)
                    """,
                        (organizer_id, event_id),
                    )

                # Add all invited users
                for user_id in data["invited_users"]:
                    if user_id != organizer_id:
                        cursor.execute(
                            """
                            INSERT OR IGNORE INTO USER_EVENTS (user_id, event_id, is_organizer)
                            VALUES (?, ?, 0)
                        """,
                            (user_id, event_id),
                        )
            else:
                # Just add new users
                for user_id in data["invited_users"]:
                    cursor.execute(
                        """
                        INSERT OR IGNORE INTO USER_EVENTS (user_id, event_id, is_organizer)
                        VALUES (?, ?, 0)
                    """,
                        (user_id, event_id),
                    )

        conn.commit()

        # Get updated event details
        cursor.execute(
            """
            SELECT id, title, description, start_time, end_time 
            FROM EVENTS 
            WHERE id = ?
        """,
            (event_id,),
        )

        updated_event = cursor.fetchone()

        # Get organizer
        cursor.execute(
            """
            SELECT user_id FROM USER_EVENTS 
            WHERE event_id = ? AND is_organizer = 1
        """,
            (event_id,),
        )

        organizer = cursor.fetchone()
        organizer_id = organizer["user_id"] if organizer else None

        # Get participants
        cursor.execute(
            """
            SELECT u.id, u.name
            FROM USERS u
            JOIN USER_EVENTS ue ON u.id = ue.user_id
            WHERE ue.event_id = ?
        """,
            (event_id,),
        )

        participants = [
            {"id": row["id"], "username": row["name"]} for row in cursor.fetchall()
        ]

        conn.close()

        return jsonify(
            {
                "id": updated_event["id"],
                "title": updated_event["title"],
                "description": updated_event["description"],
                "start_time": updated_event["start_time"],
                "end_time": updated_event["end_time"],
                "user_id": organizer_id,
                "participants": participants,
            }
        )
    except Exception as e:
        conn.rollback()
        conn.close()
        return jsonify({"error": str(e)}), 500


@app.route("/api/events/<event_id>", methods=["GET"])
def get_event(event_id):
    conn = get_db_connection()
    cursor = conn.cursor()

    # Get event details
    cursor.execute(
        """
        SELECT id, title, description, start_time, end_time
        FROM EVENTS 
        WHERE id = ?
    """,
        (event_id,),
    )

    event = cursor.fetchone()
    if not event:
        conn.close()
        return jsonify({"error": f"Event with ID {event_id} not found"}), 404

    # Get organizer
    cursor.execute(
        """
        SELECT user_id FROM USER_EVENTS 
        WHERE event_id = ? AND is_organizer = 1
    """,
        (event_id,),
    )

    organizer = cursor.fetchone()
    organizer_id = organizer["user_id"] if organizer else None

    # Get participants
    cursor.execute(
        """
        SELECT u.id, u.name
        FROM USERS u
        JOIN USER_EVENTS ue ON u.id = ue.user_id
        WHERE ue.event_id = ?
    """,
        (event_id,),
    )

    participants = [
        {"id": row["id"], "username": row["name"]} for row in cursor.fetchall()
    ]

    conn.close()

    return jsonify(
        {
            "id": event["id"],
            "title": event["title"],
            "description": event["description"],
            "start_time": event["start_time"],
            "end_time": event["end_time"],
            "user_id": organizer_id,
            "participants": participants,
        }
    )


@app.route("/api/health", methods=["GET"])
def health_check():
    db_exists = os.path.exists(DB_PATH)
    return jsonify({"status": "healthy", "db_exists": db_exists, "db_path": DB_PATH})


@app.route("/api/admin/reset-database", methods=["POST"])
def admin_reset_database():
    return (
        jsonify(
            {
                "error": "This endpoint is disabled in this implementation as the database is pre-populated"
            }
        ),
        403,
    )


if __name__ == "__main__":
    app.run(debug=True)
