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
import keyboard as kb_hook  # For hotkey detection (more reliable than pynput on Windows)
from pynput.keyboard import Controller, Key  # For typing output

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
SILENCE_FRAMES = 30  # ~0.9 seconds of silence before processing
MIN_SPEECH_FRAMES = 10  # Back to original
MAX_RECORDING_SECONDS = 30

# ============================================================
# APPLICATION PATHS (verified on this system)
# ============================================================
APP_PATHS = {
    # Browsers
    "brave": r"C:\Program Files\BraveSoftware\Brave-Browser\Application\brave.exe",
    "chrome": r"C:\Program Files\Google\Chrome\Application\chrome.exe",
    "edge": r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
    "firefox": r"C:\Program Files\Mozilla Firefox\firefox.exe",
    # Microsoft Office
    "word": r"C:\Program Files\Microsoft Office\root\Office16\WINWORD.EXE",
    "powerpoint": r"C:\Program Files\Microsoft Office\root\Office16\POWERPNT.EXE",
    "excel": r"C:\Program Files\Microsoft Office\root\Office16\EXCEL.EXE",
    "onenote": r"C:\Program Files\Microsoft Office\root\Office16\ONENOTE.EXE",
    "teams": r"C:\Users\raj_s\AppData\Local\Microsoft\Teams\Update.exe",
    # Dev tools
    "claude": r"C:\Users\raj_s\AppData\Roaming\Microsoft\Windows\Start Menu\Programs\Anthropic\Claude.lnk",
    "terminal": r"C:\Windows\System32\WindowsPowerShell\v1.0\powershell.exe",
    "notepad++": r"C:\Program Files\Notepad++\notepad++.exe",
    "vscode": r"C:\Users\raj_s\AppData\Local\Programs\Microsoft VS Code\Code.exe",
    # System utilities
    "explorer": r"C:\Windows\explorer.exe",
    "calculator": r"C:\Windows\System32\calc.exe",
    "taskmgr": r"C:\Windows\System32\Taskmgr.exe",
    "snippingtool": r"C:\Windows\System32\SnippingTool.exe",
    "settings": "ms-settings:",  # Special URI handler
    # Communication
    "discord": r"C:\Users\raj_s\AppData\Local\Discord\Update.exe",
    "zoom": r"C:\Users\raj_s\AppData\Roaming\Zoom\bin\Zoom.exe",
    # Media
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
    "edge": "edge",
    "microsoft edge": "edge",
    "firefox": "firefox",
    "mozilla": "firefox",
    "mozilla firefox": "firefox",
    # Microsoft Office
    "word": "word",
    "microsoft word": "word",
    "powerpoint": "powerpoint",
    "power point": "powerpoint",
    "ppt": "powerpoint",
    "excel": "excel",
    "microsoft excel": "excel",
    "spreadsheet": "excel",
    "spreadsheets": "excel",
    "onenote": "onenote",
    "one note": "onenote",
    "microsoft onenote": "onenote",
    "teams": "teams",
    "microsoft teams": "teams",
    # Dev tools
    "notepad": "notepad++",
    "notepad++": "notepad++",
    "note pad": "notepad++",
    "vs code": "vscode",
    "vscode": "vscode",
    "visual studio code": "vscode",
    "code": "vscode",
    "claude": "claude",
    "cloud": "claude",  # Common mishearing
    "claud": "claude",
    "clawed": "claude",
    "terminal": "terminal",
    "powershell": "terminal",
    # System utilities
    "explorer": "explorer",
    "file explorer": "explorer",
    "windows explorer": "explorer",
    "files": "explorer",
    "folder": "explorer",
    "folders": "explorer",
    "calculator": "calculator",
    "calc": "calculator",
    "task manager": "taskmgr",
    "taskmgr": "taskmgr",
    "snipping tool": "snippingtool",
    "snip": "snippingtool",
    "screenshot": "snippingtool",
    "screen shot": "snippingtool",
    "settings": "settings",
    "windows settings": "settings",
    # Communication
    "discord": "discord",
    "zoom": "zoom",
    "zoom meeting": "zoom",
    # Media
    "ableton": "ableton",
    "live": "ableton",
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

    # Special cases that don't need path existence check
    if app_key == "settings":
        log(f"[CMD] Launching {app_key}...")
        os.startfile(path)  # ms-settings: URI
        return True

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
        elif app_key == "teams":
            # Teams uses Update.exe with --processStart
            subprocess.Popen([path, "--processStart", "Teams.exe"])
        elif app_key == "discord":
            # Discord uses Update.exe with --processStart
            subprocess.Popen([path, "--processStart", "Discord.exe"])
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

# Health monitoring
last_record_heartbeat = time.time()
last_transcribe_heartbeat = time.time()
HEARTBEAT_TIMEOUT = 10  # seconds before considering thread stuck
AUDIO_DEVICE_CHECK_INTERVAL = 30  # Check audio device health periodically

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
    global listening, running, last_record_heartbeat

    consecutive_errors = 0
    MAX_CONSECUTIVE_ERRORS = 5

    while running:
        # Update heartbeat even when not listening
        last_record_heartbeat = time.time()

        if not listening:
            time.sleep(0.1)
            continue

        frames = []
        speech_frames = 0
        silence_frames = 0
        is_speech = False
        was_command_mode = False
        stream = None

        try:
            # Use callback-based streaming for more reliable audio capture
            audio_buffer = queue.Queue()

            def audio_callback(indata, frames_count, time_info, status):
                if status:
                    log(f"\n[AUDIO STATUS] {status}")
                audio_buffer.put(indata.copy())

            stream = sd.InputStream(
                samplerate=SAMPLE_RATE,
                channels=1,
                dtype='int16',
                blocksize=FRAME_SIZE,
                callback=audio_callback
            )
            stream.start()
            consecutive_errors = 0  # Reset on successful open

            while running and listening:
                last_record_heartbeat = time.time()

                try:
                    # Non-blocking get with timeout - prevents hanging
                    frame = audio_buffer.get(timeout=0.5)
                except queue.Empty:
                    # No audio data received - check if stream is still alive
                    if stream.active:
                        continue
                    else:
                        log("\n[WARN] Audio stream became inactive, restarting...")
                        break

                frame_bytes = frame.tobytes()

                try:
                    frame_is_speech = vad.is_speech(frame_bytes, SAMPLE_RATE)
                except:
                    frame_is_speech = False

                if frame_is_speech:
                    if not is_speech:
                        was_command_mode = is_ctrl_held()
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

        except sd.PortAudioError as e:
            consecutive_errors += 1
            if running:
                log(f"\n[AUDIO ERROR] PortAudio: {e} (attempt {consecutive_errors}/{MAX_CONSECUTIVE_ERRORS})")
            if consecutive_errors >= MAX_CONSECUTIVE_ERRORS:
                log("\n[FATAL] Too many audio errors, waiting longer before retry...")
                time.sleep(5)
                consecutive_errors = 0
            else:
                time.sleep(1)
        except Exception as e:
            consecutive_errors += 1
            if running:
                log(f"\n[AUDIO ERROR] {type(e).__name__}: {e} (attempt {consecutive_errors}/{MAX_CONSECUTIVE_ERRORS})")
            if consecutive_errors >= MAX_CONSECUTIVE_ERRORS:
                log("\n[FATAL] Too many audio errors, waiting longer before retry...")
                time.sleep(5)
                consecutive_errors = 0
            else:
                time.sleep(0.5)
        finally:
            # Always clean up the stream
            if stream is not None:
                try:
                    stream.stop()
                    stream.close()
                except:
                    pass

# ============================================================
# TRANSCRIPTION WORKER
# ============================================================
def transcribe_worker():
    """Transcribe audio and either type or execute command."""
    global running, last_transcription, last_transcribe_heartbeat
    temp_file = "temp_vad_chunk.wav"

    while running:
        last_transcribe_heartbeat = time.time()
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
                log(f"\n[TRANSCRIBE ERROR] {type(e).__name__}: {e}")

    if os.path.exists(temp_file):
        os.remove(temp_file)

# ============================================================
# HOTKEY HANDLER (using 'keyboard' library - more reliable on Windows)
# ============================================================
last_key_event = time.time()

def is_ctrl_held():
    """Check if Ctrl key is currently held down."""
    try:
        return kb_hook.is_pressed('ctrl')
    except:
        return False

def toggle_microphone():
    """Toggle microphone on/off when Pause key is pressed."""
    global listening, last_key_event
    last_key_event = time.time()
    listening = not listening
    if listening:
        log("\n*** MIC ON - LISTENING ***\n")
    else:
        log("\n*** MIC OFF ***\n")

def setup_keyboard_hooks():
    """Set up keyboard hooks using the keyboard library."""
    # Hook the Pause key for mic toggle
    kb_hook.on_press_key('pause', lambda e: toggle_microphone(), suppress=False)
    log("[KEYBOARD] Hooks registered (using 'keyboard' library)")

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
log("  Browsers:    brave, chrome, edge, firefox")
log("  Office:      word, excel, powerpoint, onenote, teams")
log("  Dev:         vs code, notepad, claude, terminal")
log("  Utils:       explorer, calculator, settings, task manager, snipping tool")
log("  Comms:       discord, zoom")
log("  Media:       ableton, youtube music")
log("\nKEYSTROKE COMMANDS (Ctrl + speak):")
log("  'new tab'    'close tab'    'close window'   'save'")
log("  'undo'       'redo'         'copy'           'paste'")
log("  'select all' 'find'         'new paragraph'")
log("  'go back'    'go forward'   'refresh'")
log("-"*60)
log("\n*** LISTENING ***")
log("(▓ = dictation, ◆ = command mode, ░ = silence)\n")

# Set up keyboard hooks (using 'keyboard' library - more reliable than pynput on Windows)
setup_keyboard_hooks()

record_thread = threading.Thread(target=record_with_vad, daemon=True)
transcribe_thread = threading.Thread(target=transcribe_worker, daemon=True)

record_thread.start()
transcribe_thread.start()

# Watchdog settings
last_status_print = time.time()
STATUS_PRINT_INTERVAL = 60  # Print status every 60 seconds (only when logging enabled)

try:
    while True:
        time.sleep(1)

        now = time.time()

        # Watchdog: Check if threads are responsive
        if now - last_record_heartbeat > HEARTBEAT_TIMEOUT:
            log(f"\n[WATCHDOG] Recording thread unresponsive for {HEARTBEAT_TIMEOUT}s")
            # Thread will auto-recover due to timeout-based design

        if now - last_transcribe_heartbeat > HEARTBEAT_TIMEOUT + 30:  # Extra time for transcription
            log(f"\n[WATCHDOG] Transcription thread may be processing...")

        # Periodic status (only with --log flag, to avoid console spam)
        if args.log and now - last_status_print > STATUS_PRINT_INTERVAL:
            status = "ON" if listening else "OFF"
            log(f"\n[STATUS] Mic: {status} | Record: {int(now - last_record_heartbeat)}s ago | Transcribe: {int(now - last_transcribe_heartbeat)}s ago")
            last_status_print = now

except KeyboardInterrupt:
    log("\n\nShutting down...")
    running = False
    listening = False
    kb_hook.unhook_all()  # Clean up keyboard hooks
    record_thread.join(timeout=2)
    transcribe_thread.join(timeout=2)
    if log_file:
        log_file.close()
    print("Done!")
