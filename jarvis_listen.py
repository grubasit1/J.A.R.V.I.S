import os
import speech_recognition as sr

def speak(text):
    os.system(f'bash ~/jarvis_speak.sh "{text}"')

def listen():
    r = sr.Recognizer()
    with sr.Microphone() as source:
        speak("Listening.")
        print("Listening...")
        audio = r.listen(source, timeout=5)
    try:
        text = r.recognize_google(audio)
        print(f"You said: {text}")
        return text
    except sr.UnknownValueError:
        speak("I did not catch that, sir.")
        return None
    except sr.RequestError:
        speak("Speech service unavailable.")
        return None

command = listen()
if command:
    speak(f"You said: {command}")
