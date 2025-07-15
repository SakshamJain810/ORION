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

# === CONFIG ===
API_KEY = "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"
MODEL = "mistralai/mistral-7b-instruct:free"
HEADERS = {
    "Authorization": f"Bearer {API_KEY}",
    "Content-Type": "application/json"
}

# === FLAGS ===
muted = False
speaking = False
stop_speaking = False
interrupt_command = None
memory_file = "orion_memory.json"

# === INIT PYGAME ===
pygame.mixer.init()

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
interrupt_recognizer = sr.Recognizer()

# === INTERRUPT LISTENER ===
def interrupt_listener():
    global stop_speaking, interrupt_command
    try:
        with sr.Microphone() as source:
            interrupt_recognizer.adjust_for_ambient_noise(source, duration=0.5)
            audio = interrupt_recognizer.listen(source, timeout=3, phrase_time_limit=3)
            command = interrupt_recognizer.recognize_google(audio).lower()
            if command:
                print(f"🚩 Interrupt: {command}")
                stop_speaking = True
                interrupt_command = command
                pygame.mixer.music.stop()
    except:
        pass

# === TEXT CLEANER ===
def clean_text(text):
    return re.sub(r'[:;=8][-^]?[)D]', '', re.sub(r'[🙂😀😊😂😉😎😍😭😢😅😆🤔🤯💬✨❤️💯🚀👏👀👍🙏]', '', text))

# === SPEAK FUNCTION ===
def speak(text):
    global muted, speaking, stop_speaking
    speaking = True
    stop_speaking = False
    print(f"{'(Muted) ' if muted else ''}ORION: {text}")
    if not muted:
        try:
            text = clean_text(text)
            tts = gTTS(text=text)
            filename = f"voice_{random.randint(1000,9999)}.mp3"
            tts.save(filename)

            interrupt_thread = threading.Thread(target=interrupt_listener)
            interrupt_thread.start()

            pygame.mixer.music.load(filename)
            pygame.mixer.music.play()

            while pygame.mixer.music.get_busy():
                if stop_speaking:
                    print("🔇 Speech interrupted by user.")
                    pygame.mixer.music.stop()
                    break
                time.sleep(0.1)

            while pygame.mixer.music.get_busy():
                time.sleep(0.1)

            pygame.mixer.music.unload()
            time.sleep(0.2)
            os.remove(filename)

        except Exception as e:
            print(f"Audio Error: {e}")
    speaking = False

# === LISTEN ===
def listen():
    global speaking
    while speaking:
        time.sleep(0.5)

    recognizer = sr.Recognizer()
    with sr.Microphone() as source:
        print("🎤 Listening...")
        recognizer.adjust_for_ambient_noise(source, duration=0.5)
        try:
            audio = recognizer.listen(source, timeout=5, phrase_time_limit=10)
        except sr.WaitTimeoutError:
            print("⏱️ Listening timed out")
            return None

    try:
        print("🤠 Recognizing...")
        command = recognizer.recognize_google(audio)
        print(f"🗣️ You said: {command}")
        return command.lower()
    except sr.UnknownValueError:
        print("❌ Could not understand audio")
        speak("Sorry, I didn't catch that.")
        return None
    except sr.RequestError as e:
        print(f"❌ Speech recognition error: {e}")
        speak("Speech recognition service is unavailable.")
        return None

# === WEATHER / TIME / APP ===
def get_live_news():
    try:
        url = "https://newsapi.org/v2/top-headlines?country=in&apiKey=your_news_api_key"
        response = requests.get(url)
        articles = response.json().get("articles", [])[:3]
        headlines = [article["title"] for article in articles]
        return "Here are the latest headlines: " + ". ".join(headlines) if headlines else "No news available."
    except:
        return "Sorry, couldn't fetch news."

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

# === CHAT ===
def chat_with_orion(prompt):
    global conversation_memory
    try:
        if "time" in prompt:
            return datetime.now().strftime("The time is %I:%M %p.")
        if "date" in prompt:
            return datetime.now().strftime("Today is %A, %d %B %Y.")

        app_response = open_app_or_website(prompt)
        if app_response:
            return app_response

        if "news" in prompt:
            return get_live_news()

        speak(random.choice(["Let me think...", "Just a second...", "Working on it..."]))

        conversation_memory.append({"role": "user", "content": prompt})
        payload = {
            "model": MODEL,
            "messages": [{"role": "system", "content": "You are ORION, a friendly voice assistant."}] + conversation_memory[-10:]
        }

        res = requests.post("https://openrouter.ai/api/v1/chat/completions", headers=HEADERS, json=payload)
        res.raise_for_status()
        reply = res.json()['choices'][0]['message']['content']
        conversation_memory.append({"role": "assistant", "content": reply})
        save_memory(conversation_memory)
        return reply
    except Exception as e:
        print(f"❌ API Error: {e}")
        return "Sorry, I couldn't reach the server."

# === HANDLE COMMAND ===
def handle_command(command):
    global muted

    if command is None:
        return

    if "stop" in command or "exit" in command or "goodbye" in command:
        speak("Goodbye! See you soon.")
        exit()

    if "mute" in command or "stop talking" in command:
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

# === RUN ORION ===
def run_orion():
    global interrupt_command
    speak("Hello Saksham! I am ORION. How can I help you?")
    while True:
        if interrupt_command:
            command = interrupt_command
            interrupt_command = None
        else:
            command = listen()
        handle_command(command)

if __name__ == "__main__":
    run_orion()
