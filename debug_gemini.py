"""
Quick debug script — run locally to verify Gemini extraction works.
Usage: python debug_gemini.py
"""
import os
from dotenv import load_dotenv
load_dotenv()

from app.ai.gemini_client import analyze_message

tests = [
    ("hashir", {}, ["first_name","last_name","date_of_birth","sex","phone_number","address_line_1","city","state","zip_code"], None, "What is your full name?"),
    ("hashir ahmed", {}, ["first_name","last_name","date_of_birth","sex","phone_number","address_line_1","city","state","zip_code"], None, "What is your full name?"),
    ("2 august 1998", {"first_name":"Hashir","last_name":"Ahmed"}, ["date_of_birth","sex","phone_number","address_line_1","city","state","zip_code"], None, "What is your date of birth?"),
    ("male", {"first_name":"Hashir","last_name":"Ahmed","date_of_birth":"1998-08-02"}, ["sex","phone_number","address_line_1","city","state","zip_code"], None, "What is your gender?"),
    ("1234567890", {"first_name":"Hashir","last_name":"Ahmed","date_of_birth":"1998-08-02","sex":"male"}, ["phone_number","address_line_1","city","state","zip_code"], None, "What is your phone number?"),
]

for msg, collected, missing, status, last_q in tests:
    print(f"\n{'='*60}")
    print(f"User: {msg!r}")
    print(f"Last question: {last_q!r}")
    try:
        result = analyze_message(
            message=msg,
            collected_data=collected,
            missing_fields=missing,
            registration_status=status or "in_progress",
            conversation_history=[],
            last_question=last_q,
        )
        print(f"extracted_fields : {result.extracted_fields}")
        print(f"uncertain_fields : {result.uncertain_fields}")
        print(f"corrected_fields : {result.corrected_fields}")
        print(f"confirmation     : {result.confirmation_response}")
    except Exception as e:
        print(f"ERROR: {e}")
