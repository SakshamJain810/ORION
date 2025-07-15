import os
import time
import random
import json
import requests
import speech_recognition as sr
from gtts import gTTS
import threading
from datetime import datetime
import webbrowser
import re
import subprocess
import pygame
import psutil
import logging
import queue

# === CONFIG ===
SERP_API_KEY = "e72745ef9cd7230496a575fe5facd19a4cc7b77e476cd7a97395abf915d5cb22"
MODEL = "serpapi"
HEADERS = {
    "Content-Type": "application/json"
}

# === FLAGS & QUEUES ===
muted = False
speaking = False
stop_speaking = False
interrupt_command = None
wake_word_active = True
wake_word_queue = queue.Queue()
memory_file = "orion_memory.json"

# === INIT ===
pygame.mixer.init()
logging.basicConfig(filename="orion.log", level=logging.INFO)

# === MICROPHONES ===
main_mic = sr.Microphone(device_index=None, sample_rate=16000)
wake_mic = sr.Microphone(device_index=None, sample_rate=8000)

# === MEMORY ===
def load_memory():
    if os.path.exists(memory_file):
        with open(memory_file, "r") as f:
            return json.load(f)
    return []

def save_memory(mem):
    with open(memory_file, "w") as f:
        json.dump(mem, f, indent=2)

conversation_memory = load_memory()

# === CONTINUOUS WAKE WORD LISTENER ===
def continuous_wake_word_listener():
    global wake_word_active, stop_speaking
    wake_recognizer = sr.Recognizer()
    wake_recognizer.energy_threshold = 4000

    while wake_word_active:
        try:
            with wake_mic as source:
                audio = wake_recognizer.listen(source, timeout=1, phrase_time_limit=2)
                text = wake_recognizer.recognize_google(audio).lower()
                if "hey orion" in text or "ok orion" in text:
                    wake_word_queue.put("WAKE_WORD_DETECTED")
                    print("🔥 Wake word detected!")
                    if speaking:
                        stop_speaking = True
        except (sr.WaitTimeoutError, sr.UnknownValueError):
            continue
        except Exception:
            time.sleep(0.1)

# === TEXT CLEANER ===
def clean_text(text):
    return re.sub(r'[:;=8][-^]?[)D]', '', re.sub(r'[\U0001F600-\U0001F64F]+', '', text))

# === SPEAK FUNCTION ===
def speak(text):
    global muted, speaking, stop_speaking
    speaking = True
    stop_speaking = False
    print(f"{('(Muted) ' if muted else '')}ORION: {text}")
    if not muted:
        try:
            text = clean_text(text)
            tts = gTTS(text=text)
            filename = f"voice_{random.randint(1000,9999)}.mp3"
            tts.save(filename)

            pygame.mixer.music.load(filename)
            pygame.mixer.music.play()

            while pygame.mixer.music.get_busy():
                try:
                    wake_word_queue.get_nowait()
                    print("🔇 Interrupted by Wake Word!")
                    pygame.mixer.music.stop()
                    stop_speaking = True
                    break
                except queue.Empty:
                    pass

                if stop_speaking:
                    break
                time.sleep(0.1)

            pygame.mixer.music.unload()
            os.remove(filename)

        except Exception as e:
            print(f"Audio Error: {e}")
    speaking = False

# === LISTEN FUNCTION ===
def listen():
    global speaking
    while speaking:
        time.sleep(0.5)

    recognizer = sr.Recognizer()
    with main_mic as source:
        print("🎤 Listening...")
        recognizer.adjust_for_ambient_noise(source, duration=0.5)
        try:
            audio = recognizer.listen(source, timeout=5, phrase_time_limit=10)
        except sr.WaitTimeoutError:
            print("⏱️ Listening timed out")
            return None

    try:
        print("🤠 Recognizing...")
        command = recognizer.recognize_google(audio).lower()
        print(f"🗣️ You said: {command}")
        return command
    except sr.UnknownValueError:
        print("❌ Could not understand audio")
        speak("Sorry, I didn't catch that.")
        return None
    except sr.RequestError as e:
        print(f"❌ Speech recognition error: {e}")
        speak("Speech recognition service is unavailable.")
        return None

# === SYSTEM FEATURES ===
def get_battery_status():
    try:
        battery = psutil.sensors_battery()
        if battery:
            return f"The battery is at {battery.percent}%."
        else:
            return "Battery information is not available."
    except Exception as e:
        print(f"Battery Error: {e}")
        return "Could not fetch battery info."

# === APP LAUNCHING ===
def open_app_or_website(prompt):
    app_mappings = {
        "notepad": "notepad.exe",
        "calculator": "calc.exe",
        "chrome": "chrome.exe",
        "spotify": "spotify.exe"
    }
    for app in app_mappings:
        if app in prompt:
            try:
                subprocess.Popen(app_mappings[app])
                return f"Opening {app}."
            except:
                return f"Couldn't open {app}."
    if "youtube" in prompt:
        webbrowser.open("https://youtube.com")
        return "Opening YouTube."
    if "google" in prompt:
        webbrowser.open("https://google.com")
        return "Opening Google."
    if "search for" in prompt:
        query = prompt.split("search for")[-1].strip()
        webbrowser.open(f"https://www.google.com/search?q={query}")
        return f"Searching for {query}."
    return None

# === ORION CHAT ===
def chat_with_orion(prompt):
    global conversation_memory
    try:
        if "time" in prompt:
            return datetime.now().strftime("The time is %I:%M %p.")
        if "date" in prompt:
            return datetime.now().strftime("Today is %A, %d %B %Y.")
        if "battery" in prompt:
            return get_battery_status()

        app_response = open_app_or_website(prompt)
        if app_response:
            return app_response

        speak(random.choice(["Let me think...", "Just a second...", "Working on it..."]))

        # Use SerpAPI for search-based response
        query = prompt.replace(" ", "+")
        serp_url = f"https://serpapi.com/search.json?q={query}&api_key={SERP_API_KEY}"
        response = requests.get(serp_url)
        response.raise_for_status()
        results = response.json()

        if "answer_box" in results and "answer" in results["answer_box"]:
            return results["answer_box"]["answer"]
        elif "organic_results" in results and len(results["organic_results"]) > 0:
            return results["organic_results"][0].get("snippet", "Here's what I found online.")
        else:
            return "Sorry, I couldn't find anything relevant."

    except Exception as e:
        print(f"❌ API Error: {e}")
        return "Sorry, I couldn't reach the server."

# === COMMAND HANDLER ===
def handle_command(command):
    global muted
    if not command:
        return

    if any(x in command for x in ["stop", "exit", "goodbye", "cancel"]):
        speak("Goodbye! See you soon.")
        exit()

    if "mute" in command:
        muted = True
        print("🔇 ORION is now muted.")
        return

    if "unmute" in command or "start talking" in command:
        muted = False
        print("🔊 ORION is unmuted.")
        speak("Voice is back on.")
        return

    if any(greet in command for greet in ["hello", "hi", "hey"]):
        speak(random.choice([
            "Hello Saksham! It's a pleasure to assist you.",
            "Hi there! What can I do for you?",
            "Hey! How can I help you today?"
        ]))
        return

    speak(chat_with_orion(command))

# === MAIN LOOP ===
def run_orion():
    global wake_word_active, stop_speaking

    wake_word_active = True
    threading.Thread(target=continuous_wake_word_listener, daemon=True).start()

    speak("Hello Saksham! I am ORION. How can I help you?")

    while True:
        if not wake_word_queue.empty():
            wake_word_queue.get()
            if speaking:
                stop_speaking = True
                time.sleep(0.5)

        command = listen()
        handle_command(command)

if __name__ == "__main__":
    run_orion()