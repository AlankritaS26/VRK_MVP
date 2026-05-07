"""
Integration Test Script for Slice 2 (Engine)
=============================================
This script simulates what Slice 1 and Slice 3 will do,
so you can test your backend WITHOUT waiting for their code.

HOW TO USE:
1. Make sure your FastAPI server is running: uvicorn main:app --reload
2. Open a NEW terminal
3. Run: python test_integration.py
"""

import requests
import json
import os

BASE_URL = "http://127.0.0.1:8000"

# -------------------------------------------------------
# TEST 1: Health Check
# Simulates: anyone checking if your engine is online
# -------------------------------------------------------
def test_health():
    print("\n--- TEST 1: Health Check ---")
    response = requests.get(f"{BASE_URL}/")
    print(f"Status Code: {response.status_code}")
    print(f"Response: {response.json()}")
    assert response.status_code == 200, "❌ Server is not running!"
    print("✅ Engine is online")


# -------------------------------------------------------
# TEST 2: Simulate Slice 1 sending a NEW_USER event
# Slice 1 (Host) will call this when a person walks up
# -------------------------------------------------------
def test_new_user():
    print("\n--- TEST 2: Simulating Slice 1 → New User Arrives ---")
    payload = {"session_id": "999"}
    response = requests.post(f"{BASE_URL}/new-user", params=payload)
    print(f"Status Code: {response.status_code}")
    print(f"Response: {response.json()}")
    if response.status_code == 200:
        print("✅ Slice 2 received the new user signal correctly")
    else:
        print("❌ Failed - check your /new-user endpoint")


# -------------------------------------------------------
# TEST 3: Simulate the full /chat pipeline
# Frontend sends audio → you transcribe → return voice
# -------------------------------------------------------
def test_chat():
    print("\n--- TEST 3: Simulating Frontend → /chat pipeline ---")

    # We need a real audio file for this test
    # Uses test.wav if it exists, otherwise skips
    audio_file = "test.wav"
    if not os.path.exists(audio_file):
        print(f"⚠️  Skipping: '{audio_file}' not found in this folder.")
        print("   Copy your test.wav here and re-run.")
        return

    with open(audio_file, "rb") as f:
        files = {"file": ("test.wav", f, "audio/wav")}
        params = {"session_id": "999"}
        response = requests.post(f"{BASE_URL}/chat", files=files, params=params)

    print(f"Status Code: {response.status_code}")

    if response.status_code == 200:
        # Save the audio response so you can listen to it
        with open("test_chat_response.wav", "wb") as out:
            out.write(response.content)
        user_said = response.headers.get("x-user-said", "unknown")
        print(f"✅ Got audio back! User was heard saying: '{user_said}'")
        print("   Saved response as: test_chat_response.wav")
    else:
        print(f"❌ Failed: {response.text}")


# -------------------------------------------------------
# TEST 4: Simulate Slice 3 sending an answer back to you
# Slice 3 (Brain) will call this after looking up the database
# -------------------------------------------------------
def test_speak_answer():
    print("\n--- TEST 4: Simulating Slice 3 → Sending Answer to Engine ---")
    payload = {
        "session_id": "999",
        "answer": "The library is behind the main hall."
    }
    response = requests.post(f"{BASE_URL}/speak-answer", params=payload)
    print(f"Status Code: {response.status_code}")

    if response.status_code == 200:
        with open("test_answer_response.wav", "wb") as out:
            out.write(response.content)
        print("✅ Slice 2 turned the answer into voice!")
        print("   Saved response as: test_answer_response.wav")
    else:
        print(f"❌ Failed: {response.text}")


# -------------------------------------------------------
# TEST 5: Simulate the /transcribe endpoint alone
# Useful for checking just the Whisper part
# -------------------------------------------------------
def test_transcribe():
    print("\n--- TEST 5: Simulating /transcribe alone ---")

    audio_file = "test.wav"
    if not os.path.exists(audio_file):
        print(f"⚠️  Skipping: '{audio_file}' not found in this folder.")
        return

    with open(audio_file, "rb") as f:
        files = {"file": ("test.wav", f, "audio/wav")}
        response = requests.post(f"{BASE_URL}/transcribe", files=files)

    print(f"Status Code: {response.status_code}")
    if response.status_code == 200:
        data = response.json()
        print(f"✅ Transcription: '{data['transcription']}'")
        print(f"   Language detected: {data['language']} ({data['language_probability']*100:.0f}% confident)")
    else:
        print(f"❌ Failed: {response.text}")


# -------------------------------------------------------
# RUN ALL TESTS
# -------------------------------------------------------
if __name__ == "__main__":
    print("=" * 50)
    print("  Digital Receptionist — Integration Tests")
    print("  Simulating Slice 1, Frontend, and Slice 3")
    print("=" * 50)

    test_health()
    test_new_user()
    test_transcribe()
    test_chat()
    test_speak_answer()

    print("\n" + "=" * 50)
    print("  All tests complete!")
    print("  Check any .wav files saved above — play them")
    print("  to confirm the voice output sounds correct.")
    print("=" * 50)