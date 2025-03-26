import datetime
import json
import os
import sqlite3
from typing import Any, Dict, List, Optional, Set, Tuple

import requests

from calendar_chatbot_presenter import CalendarChatbotPresenter
from calendar_controller import CalendarController
from calendar_database_model import CalendarDatabaseModel


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
