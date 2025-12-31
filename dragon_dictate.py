"""
Dragon-Style Dictation with Command Mode
- Normal mode: Types into active window
- Command mode: Hold Ctrl while speaking to execute commands
- Press Ctrl+C in terminal to quit

Usage:
  python dragon_dictate.py           # Normal mode
  python dragon_dictate.py --log     # Enable logging to dragon_log.txt
"""
import sounddevice as sd
import numpy as np
import wave
import torch
import whisper
import threading
import queue
import time
import sys
import os
import subprocess
import argparse
import datetime
import webrtcvad
from pynput.keyboard import Controller, Key, Listener
from pynput import keyboard

# ============================================================
# COMMAND LINE ARGUMENTS
# ============================================================
parser = argparse.ArgumentParser(description='Dragon-style voice dictation')
parser.add_argument('--log', action='store_true', help='Enable logging to dragon_log.txt')
parser.add_argument('--logfile', type=str, default='dragon_log.txt', help='Log file path')
args = parser.parse_args()

# Set up logging
log_file = None
if args.log:
    log_file = open(args.logfile, 'a', encoding='utf-8')
    log_file.write(f"\n{'='*60}\n")
    log_file.write(f"Session started: {datetime.datetime.now()}\n")
    log_file.write(f"{'='*60}\n")
    log_file.flush()

def log(message, end='\n'):
    """Print to console and optionally to log file."""
    print(message, end=end, flush=True)
    if log_file:
        log_file.write(message + end)
        log_file.flush()

# ============================================================
# SETTINGS
# ============================================================
SAMPLE_RATE = 16000
FRAME_DURATION_MS = 30
FRAME_SIZE = int(SAMPLE_RATE * FRAME_DURATION_MS / 1000)
VAD_AGGRESSIVENESS = 2  # Back to original
SILENCE_FRAMES = 50  # ~1.5 seconds of silence before processing (was 30 = ~0.9s)
MIN_SPEECH_FRAMES = 10  # Back to original
MAX_RECORDING_SECONDS = 30

# ============================================================
# APPLICATION PATHS (verified on this system)
# ============================================================
APP_PATHS = {
    "brave": r"C:\Program Files\BraveSoftware\Brave-Browser\Application\brave.exe",
    "chrome": r"C:\Program Files\Google\Chrome\Application\chrome.exe",
    "word": r"C:\Program Files\Microsoft Office\root\Office16\WINWORD.EXE",
    "powerpoint": r"C:\Program Files\Microsoft Office\root\Office16\POWERPNT.EXE",
    "claude": r"C:\Users\raj_s\AppData\Roaming\Microsoft\Windows\Start Menu\Programs\Anthropic\Claude.lnk",
    "terminal": r"C:\Windows\System32\WindowsPowerShell\v1.0\powershell.exe",
    "explorer": r"C:\Windows\explorer.exe",
    "notepad++": r"C:\Program Files\Notepad++\notepad++.exe",
    "vscode": r"C:\Users\raj_s\AppData\Local\Programs\Microsoft VS Code\Code.exe",
    "ableton": r"C:\ProgramData\Ableton\Live 11 Suite\Program\Ableton Live 11 Suite.exe",
    "youtube_music": r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge_proxy.exe",
}

# Voice command aliases -> app key
APP_ALIASES = {
    # Browsers
    "brave": "brave",
    "chrome": "chrome",
    "google": "chrome",
    "google chrome": "chrome",
    # Office
    "word": "word",
    "microsoft word": "word",
    "powerpoint": "powerpoint",
    "power point": "powerpoint",
    "ppt": "powerpoint",
    # Dev tools
    "notepad": "notepad++",
    "notepad++": "notepad++",
    "note pad": "notepad++",
    "vs code": "vscode",
    "vscode": "vscode",
    "visual studio code": "vscode",
    "code": "vscode",
    # Other
    "claude": "claude",
    "cloud": "claude",  # Common mishearing
    "claud": "claude",
    "clawed": "claude",
    "terminal": "terminal",
    "powershell": "terminal",
    "explorer": "explorer",
    "file explorer": "explorer",
    "windows explorer": "explorer",
    "files": "explorer",
    "folder": "explorer",
    "folders": "explorer",
    "ableton": "ableton",
    "live": "ableton",
    # Music
    "youtube music": "youtube_music",
    "youtube": "youtube_music",
    "music": "youtube_music",
}

def launch_app(app_key):
    """Launch an application by its key."""
    if app_key not in APP_PATHS:
        log(f"[CMD] Unknown app: {app_key}")
        return False

    path = APP_PATHS[app_key]
    if not os.path.exists(path):
        log(f"[CMD] App not found: {path}")
        return False

    log(f"[CMD] Launching {app_key}...")
    try:
        if path.endswith('.lnk'):
            # Launch shortcut
            os.startfile(path)
        elif app_key == "terminal":
            # Launch terminal in NEW window
            subprocess.Popen(
                ["powershell", "-NoExit"],
                creationflags=subprocess.CREATE_NEW_CONSOLE
            )
        elif app_key == "youtube_music":
            # Launch YouTube Music PWA (Edge app)
            subprocess.Popen([
                path,
                "--profile-directory=Default",
                "--app-id=cinhimbnkkaeohfgghhklpknlkffjgod",
                "--app-url=https://music.youtube.com/?source=pwa",
                "--app-launch-source=4"
            ])
        else:
            subprocess.Popen([path])
        return True
    except Exception as e:
        log(f"[CMD] Launch failed: {e}")
        return False

def execute_command(text):
    """
    Parse and execute voice commands.
    Returns True if command was recognized, False otherwise.
    """
    text_lower = text.lower().strip()

    # Remove trailing punctuation (Whisper often adds periods)
    text_lower = text_lower.rstrip('.,!?;:')

    # Normalize common transcription variations
    text_lower = text_lower.replace("plus plus", "++")
    text_lower = text_lower.replace("plus-plus", "++")
    text_lower = text_lower.replace("plusplus", "++")

    log(f"[CMD] Processing: '{text_lower}'")

    # --- OPEN APP COMMANDS ---
    if text_lower.startswith("open "):
        app_name = text_lower[5:].strip()  # Remove "open "

        # Check aliases
        if app_name in APP_ALIASES:
            return launch_app(APP_ALIASES[app_name])

        # Try direct match
        if app_name in APP_PATHS:
            return launch_app(app_name)

        log(f"[CMD] Unknown app: '{app_name}'")
        log(f"[CMD] Available: {', '.join(sorted(set(APP_ALIASES.keys())))}")
        return True

    # --- KEYSTROKE COMMANDS ---
    # Import Key for special keys (already imported at top)
    from pynput.keyboard import Key

    keystroke_commands = {
        # ==========================================
        # BROWSER COMMANDS
        # ==========================================
        "new tab": (Key.ctrl, 't'),
        "open tab": (Key.ctrl, 't'),  # Alias
        "close tab": (Key.ctrl, 'w'),
        "closed tab": (Key.ctrl, 'w'),  # Alias (mishearing)
        "go back": (Key.alt, Key.left),
        "go forward": (Key.alt, Key.right),
        "refresh": (Key.f5,),

        # ==========================================
        # TEXT EDITING / BUFFER COMMANDS
        # ==========================================
        # Clipboard
        "copy": (Key.ctrl, 'c'),
        "copy that": (Key.ctrl, 'c'),
        "paste": (Key.ctrl, 'v'),
        "cut": (Key.ctrl, 'x'),
        # Selection
        "select all": (Key.ctrl, 'a'),
        # Undo/Redo
        "undo": (Key.ctrl, 'z'),
        "redo": (Key.ctrl, 'y'),
        # Line/Paragraph (use dictation mode phrases instead for these)
        "new paragraph": (Key.enter, Key.enter),  # Special: two enters
        # File operations
        "save": (Key.ctrl, 's'),
        "safe": (Key.ctrl, 's'),  # Alias (mishearing)
        "save file": (Key.ctrl, 's'),
        "find": (Key.ctrl, 'f'),

        # ==========================================
        # WINDOW / NAVIGATION
        # ==========================================
        "close window": (Key.alt, Key.f4),
        "page up": (Key.page_up,),
        "page down": (Key.page_down,),
    }

    if text_lower in keystroke_commands:
        keys = keystroke_commands[text_lower]
        log(f"[CMD] Sending keystroke: {keys}")

        # Special case: new paragraph (two enters)
        if text_lower == "new paragraph":
            kb.press(Key.enter)
            kb.release(Key.enter)
            kb.press(Key.enter)
            kb.release(Key.enter)
        # Single key
        elif len(keys) == 1:
            kb.press(keys[0])
            kb.release(keys[0])
        # Modifier + key combo
        else:
            modifier, key = keys
            kb.press(modifier)
            kb.press(key)
            kb.release(key)
            kb.release(modifier)
        return True

    log(f"[CMD] Command not recognized: '{text}'")
    return False

# ============================================================
# INITIALIZATION
# ============================================================
log("="*60)
log("  DRAGON-STYLE DICTATION + COMMANDS")
log("="*60)

if torch.cuda.is_available():
    log(f"\nCUDA: True ({torch.cuda.get_device_name(0)})")
else:
    log("\nCUDA: False")

log("Loading Whisper model...", end=" ")
model = whisper.load_model("small")
log("ready!")

vad = webrtcvad.Vad(VAD_AGGRESSIVENESS)
kb = Controller()

# State
listening = True
running = True
audio_queue = queue.Queue()
last_transcription = ""  # For context-aware transcription

# Word replacements (post-transcription corrections)
# Add your domain-specific terms here
WORD_REPLACEMENTS = {
    # Keysight
    "K-Site": "Keysight",
    "K-site": "Keysight",
    "key site": "Keysight",
    "key sites": "Keysight's",
    "KeySight": "Keysight",
    # Ansys
    "Nantz": "Ansys",
    "nans": "Ansys",
    "ANSYS": "Ansys",
    # Synopsys
    "synopsis": "Synopsys",
    "Synopsis": "Synopsys",
    # PowerArtist
    "power artists": "PowerArtist",
    "power artist": "PowerArtist",
    "Power Artists": "PowerArtist",
}

# Words that indicate a sentence continuation (shouldn't have period before them)
CONTINUATION_WORDS = {"and", "or", "but", "which", "that", "where", "when", "while",
                      "because", "since", "although", "though", "if", "unless",
                      "enabling", "allowing", "providing", "including", "such"}

# ============================================================
# TYPE INTO ACTIVE WINDOW
# ============================================================
def apply_word_replacements(text):
    """Apply word replacements for known terms."""
    for wrong, right in WORD_REPLACEMENTS.items():
        text = text.replace(wrong, right)
    return text

def delete_last_period():
    """Delete the period we just typed if this is a continuation."""
    # Delete ". " (2 chars) and add back just a space
    kb.press(Key.backspace)
    kb.release(Key.backspace)
    time.sleep(0.005)
    kb.press(Key.backspace)
    kb.release(Key.backspace)
    time.sleep(0.005)
    kb.type(" ")
    time.sleep(0.005)

def type_text(text, is_continuation=False):
    """Type text into whatever window is currently focused."""
    if not text.strip():
        return

    # Clean up Whisper artifacts
    text = text.strip()
    text = text.replace("...", "")  # Remove ellipses
    text = text.replace("…", "")    # Remove unicode ellipsis
    text = text.replace(" .", ".")  # Fix space before period
    text = text.strip()

    if not text:  # If nothing left after cleanup
        return

    # Apply word replacements
    text = apply_word_replacements(text)

    # If this is a continuation, delete the previous period
    if is_continuation:
        delete_last_period()

    text = text + " "
    for char in text:
        kb.type(char)
        time.sleep(0.005)

# ============================================================
# VOICE ACTIVITY DETECTION RECORDING
# ============================================================
def record_with_vad():
    """Record audio, using VAD to detect speech boundaries."""
    global listening, running, ctrl_held

    while running:
        if not listening:
            time.sleep(0.1)
            continue

        frames = []
        speech_frames = 0
        silence_frames = 0
        is_speech = False
        was_command_mode = False

        try:
            with sd.InputStream(samplerate=SAMPLE_RATE,
                               channels=1,
                               dtype='int16',
                               blocksize=FRAME_SIZE) as stream:

                while running and listening:
                    frame, _ = stream.read(FRAME_SIZE)
                    frame_bytes = frame.tobytes()

                    try:
                        frame_is_speech = vad.is_speech(frame_bytes, SAMPLE_RATE)
                    except:
                        frame_is_speech = False

                    if frame_is_speech:
                        if not is_speech:
                            was_command_mode = ctrl_held
                            if was_command_mode:
                                sys.stdout.write("[CMD] ")

                        is_speech = True
                        speech_frames += 1
                        silence_frames = 0
                        frames.append(frame)

                        if was_command_mode:
                            sys.stdout.write("◆")
                        else:
                            sys.stdout.write("▓")
                        sys.stdout.flush()
                    else:
                        if is_speech:
                            silence_frames += 1
                            frames.append(frame)

                            sys.stdout.write("░")
                            sys.stdout.flush()

                            if silence_frames >= SILENCE_FRAMES:
                                if speech_frames >= MIN_SPEECH_FRAMES:
                                    audio_data = np.concatenate(frames)
                                    audio_queue.put((audio_data, was_command_mode))
                                    print()

                                frames = []
                                speech_frames = 0
                                silence_frames = 0
                                is_speech = False
                                was_command_mode = False

                    if len(frames) > MAX_RECORDING_SECONDS * SAMPLE_RATE / FRAME_SIZE:
                        if speech_frames >= MIN_SPEECH_FRAMES:
                            audio_data = np.concatenate(frames)
                            audio_queue.put((audio_data, was_command_mode))
                            print()
                        frames = []
                        speech_frames = 0
                        silence_frames = 0
                        is_speech = False
                        was_command_mode = False

        except Exception as e:
            if running:
                log(f"\nRecording error: {e}")
            time.sleep(0.5)

# ============================================================
# TRANSCRIPTION WORKER
# ============================================================
def transcribe_worker():
    """Transcribe audio and either type or execute command."""
    global running, last_transcription
    temp_file = "temp_vad_chunk.wav"

    while running:
        try:
            item = audio_queue.get(timeout=1)
            audio, is_command = item

            with wave.open(temp_file, 'w') as wf:
                wf.setnchannels(1)
                wf.setsampwidth(2)
                wf.setframerate(SAMPLE_RATE)
                wf.writeframes(audio.tobytes())

            # Use last transcription as context (helps with sentence continuity)
            prompt = last_transcription[-100:] if last_transcription else None

            result = model.transcribe(
                temp_file,
                fp16=torch.cuda.is_available(),
                language="en",
                initial_prompt=prompt
            )

            text = result['text'].strip()
            if text:
                if is_command:
                    if not execute_command(text):
                        log(f"[CMD] Unknown command. Try: 'open notepad'")
                else:
                    # Check if this starts with a continuation word
                    first_word = text.split()[0].lower().rstrip('.,!?') if text.split() else ""
                    is_continuation = first_word in CONTINUATION_WORDS

                    # Also check if it starts with lowercase (except "I")
                    if text and text[0].islower() and text[0] != 'i':
                        is_continuation = True

                    if is_continuation:
                        log(f">> (cont) {text}")
                    else:
                        log(f">> {text}")

                    type_text(text, is_continuation=is_continuation)
                    last_transcription = text

        except queue.Empty:
            continue
        except Exception as e:
            if running:
                log(f"\nTranscription error: {e}")

    if os.path.exists(temp_file):
        os.remove(temp_file)

# ============================================================
# HOTKEY HANDLER
# ============================================================
ctrl_held = False
shift_held = False

def on_press(key):
    global ctrl_held, shift_held, listening
    if key in (keyboard.Key.ctrl_l, keyboard.Key.ctrl_r):
        ctrl_held = True
    elif key in (keyboard.Key.shift_l, keyboard.Key.shift_r, keyboard.Key.shift):
        shift_held = True

    # Pause key = toggle microphone
    if key == keyboard.Key.pause:
        listening = not listening
        if listening:
            log("\n*** MIC ON - LISTENING ***\n")
        else:
            log("\n*** MIC OFF ***\n")

def on_release(key):
    global ctrl_held, shift_held
    if key in (keyboard.Key.ctrl_l, keyboard.Key.ctrl_r):
        ctrl_held = False
    elif key in (keyboard.Key.shift_l, keyboard.Key.shift_r, keyboard.Key.shift):
        shift_held = False

# ============================================================
# MAIN
# ============================================================
log("\n" + "-"*60)
log("MODES:")
log("  Normal speech    = Text typed into active window")
log("  Hold Ctrl+speak  = Command mode (e.g., 'open notepad')")
log("")
log("CONTROLS:")
log("  Pause key = Toggle microphone on/off")
log("  Ctrl+C    = Quit (in terminal)")
log("-"*60)
log("\nAPP COMMANDS (hold Ctrl + speak):")
log("  'open brave'      'open chrome'       'open word'")
log("  'open powerpoint' 'open claude'       'open terminal'")
log("  'open explorer'   'open notepad'      'open vs code'")
log("  'open ableton'    'open youtube music'")
log("\nKEYSTROKE COMMANDS (Ctrl + speak):")
log("  'new tab'    'close tab'    'close window'   'save'")
log("  'undo'       'redo'         'copy'           'paste'")
log("  'select all' 'find'         'new paragraph'")
log("  'go back'    'go forward'   'refresh'")
log("-"*60)
log("\n*** LISTENING ***")
log("(▓ = dictation, ◆ = command mode, ░ = silence)\n")

hotkey_listener = Listener(on_press=on_press, on_release=on_release)
hotkey_listener.start()

record_thread = threading.Thread(target=record_with_vad, daemon=True)
transcribe_thread = threading.Thread(target=transcribe_worker, daemon=True)

record_thread.start()
transcribe_thread.start()

try:
    while True:
        time.sleep(0.1)
except KeyboardInterrupt:
    log("\n\nShutting down...")
    running = False
    listening = False
    hotkey_listener.stop()
    record_thread.join(timeout=2)
    transcribe_thread.join(timeout=2)
    if log_file:
        log_file.close()
    print("Done!")
