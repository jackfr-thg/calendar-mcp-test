import datetime
import json
import os
import sqlite3
from typing import Any, Dict, List, Optional, Set, Tuple

import requests

from calendar_controller import CalendarController
from calendar_database_model import CalendarDatabaseModel


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
