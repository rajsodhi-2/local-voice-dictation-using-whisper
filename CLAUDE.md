# Audio Transcription Project

## Overview
Audio transcription workspace using OpenAI Whisper with CUDA GPU acceleration on an NVIDIA GeForce RTX 3070 Ti.

## Environment Setup
- **Python Version**: 3.10.7 (managed via pyenv)
- **Virtual Environment**: `whisperenv/`
- **GPU**: NVIDIA GeForce RTX 3070 Ti with CUDA 12.1

### Activate Environment
```bash
# Windows
.\whisperenv\Scripts\activate

# Or run directly
.\whisperenv\Scripts\python.exe <script.py>
```

## Key Dependencies
- `openai-whisper` - Speech-to-text transcription (installed from GitHub)
- `torch==2.5.1+cu121` - PyTorch with CUDA 12.1 support
- `numba`, `numpy` - Numerical processing acceleration

## Output Formats
Whisper generates multiple output formats:
- `.txt` - Plain text transcript
- `.json` - Full output with segments, timestamps, tokens, confidence scores
- `.srt` - SubRip subtitle format
- `.vtt` - WebVTT subtitle format
- `.tsv` - Tab-separated values with timestamps

## Usage

### Basic Transcription
```python
import whisper
model = whisper.load_model("base")  # or "small", "medium", "large"
result = model.transcribe("audio_file.m4a")
print(result["text"])
```

### CLI Usage
```bash
whisper audio_file.m4a --model medium --output_format all
```

## Whisper Model Sizes
| Model  | Parameters | VRAM Required | Relative Speed |
|--------|------------|---------------|----------------|
| tiny   | 39M        | ~1 GB         | ~32x           |
| base   | 74M        | ~1 GB         | ~16x           |
| small  | 244M       | ~2 GB         | ~6x            |
| medium | 769M       | ~5 GB         | ~2x            |
| large  | 1550M      | ~10 GB        | 1x             |

RTX 3070 Ti (8GB VRAM) can handle up to `large` model with some constraints.

## Project Structure
```
Audio/
├── CLAUDE.md               # This file
├── requirements.txt        # Python dependencies
├── .python-version         # pyenv version (3.10.7)
├── whisperenv/                      # Virtual environment
├── audio_file_batch_transcribe.ipynb # Batch transcription notebook
├── dragon_dictate.py       # Main Dragon clone application
├── test_audio_input.py     # Audio input verification
├── test_transcribe.py      # Single transcription test
├── continuous_transcribe.py # Continuous transcription test
├── test_components.py      # Component isolation tests
├── test_keyboard.py        # Keyboard listener test
├── test_app_launchers.py   # App path finder and launcher test
├── dragon_log.txt          # Debug log output (when --log used)
└── *.m4a, *.txt, etc.      # Audio files and transcriptions
```

## Dragon Clone - dragon_dictate.py

A working Dragon NaturallySpeaking-style voice dictation system with command mode.

### Features Implemented
- **Real-time dictation** - Types transcribed speech into the active window
- **Voice Activity Detection (VAD)** - Uses webrtcvad to detect speech boundaries
- **Command mode** - Hold Ctrl while speaking to execute voice commands
- **App launchers** - "open brave", "open chrome", "open word", "open notepad", etc.
- **Keystroke commands** - "new tab", "close tab", "save", "undo", "copy", "paste", etc.
- **Context-aware transcription** - Uses previous text as context for better continuity
- **Sentence continuation detection** - Detects "and", "which", etc. to avoid mid-sentence periods
- **Word replacements** - Post-processing corrections for domain-specific terms
- **Debug logging** - `--log` flag to output to dragon_log.txt

### Usage
```bash
# Activate environment first
.\whisperenv\Scripts\activate

# Normal mode (types into active window)
python dragon_dictate.py

# With debug logging
python dragon_dictate.py --log
python dragon_dictate.py --log --logfile my_debug.txt
```

### Modes
- **Normal speech** - Text is typed into whatever window is currently focused
- **Hold Ctrl + speak** - Command mode (e.g., "open notepad", "close tab", "save")

### Controls
| Key | Action |
|-----|--------|
| **Pause** | Toggle microphone on/off |
| **Ctrl+C** | Quit (in terminal) |

### Voice Commands

**App Launchers (Ctrl + speak):**
| Command | Action |
|---------|--------|
| "open brave" | Launch Brave browser |
| "open chrome" | Launch Chrome |
| "open word" | Launch Microsoft Word |
| "open powerpoint" | Launch PowerPoint |
| "open notepad" | Launch Notepad++ |
| "open vs code" | Launch VS Code |
| "open terminal" | Open new PowerShell window |
| "open explorer" | Open File Explorer |
| "open claude" | Launch Claude desktop app |
| "open ableton" | Launch Ableton Live |
| "open youtube music" | Launch YouTube Music PWA |

**Keystroke Commands (Ctrl + speak):**

*Browser:*
- "new tab" - Ctrl+T
- "close tab" - Ctrl+W
- "go back" - Alt+Left
- "go forward" - Alt+Right
- "refresh" - F5

*Text Editing:*
- "copy" - Ctrl+C
- "paste" - Ctrl+V
- "cut" - Ctrl+X
- "select all" - Ctrl+A
- "undo" - Ctrl+Z
- "redo" - Ctrl+Y
- "save" - Ctrl+S
- "find" - Ctrl+F
- "new paragraph" - Enter, Enter

*Window:*
- "close window" - Alt+F4
- "page up" / "page down"

**Note:** Punctuation is handled automatically by Whisper - just speak naturally.

### Visual Indicators
- `▓` = Dictation mode (normal speech)
- `◆` = Command mode (Ctrl held)
- `░` = Silence detected

### Key Dependencies
- `openai-whisper` - Speech-to-text (small model)
- `sounddevice` - Audio capture
- `webrtcvad-wheels` - Voice activity detection
- `pynput` - Keyboard control and hotkey detection
- `torch` + CUDA - GPU acceleration

### Audio Hardware
Configured for PreSonus Studio 1824c audio interface (16kHz sample rate).

### Settings (tunable in code)
- `VAD_AGGRESSIVENESS = 2` - How aggressive VAD is (0-3)
- `SILENCE_FRAMES = 50` - Frames of silence before processing (~1.5 seconds)
- `MIN_SPEECH_FRAMES = 10` - Minimum speech to transcribe
- `MAX_RECORDING_SECONDS = 30` - Max chunk length

### Word Replacements
Edit `WORD_REPLACEMENTS` dict in the code to add domain-specific terms:
```python
WORD_REPLACEMENTS = {
    "K-Site": "Keysight",
    "key site": "Keysight",
    "Nantz": "Ansys",
    "power artists": "PowerArtist",
    "synopsis": "Synopsys",
    # Add your own...
}
```

### Known Command Aliases
The system handles common mishearings:
- "safe" → "save"
- "cloud" / "claud" / "clawed" → "claude"
- "folder" / "files" → "explorer"
- "closed tab" → "close tab"
- "open tab" → "new tab"

### Sentence Continuation
These words trigger continuation detection (removes previous period):
`and`, `or`, `but`, `which`, `that`, `enabling`, `allowing`, `including`, etc.
