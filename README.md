# Local Voice Dictation Using Whisper

**Speech-to-text using OpenAI's Whisper running locally on your GPU.**

A free, private alternative to cloud-based transcription services. All processing happens on your machine.

## Two Modes

### 1. Real-Time Dictation (`dragon_dictate.py`)
Talk to your computer and it types what you say - into any app (Word, Notepad, browser, etc.)

- **Dictation Mode** - Just talk, words appear where your cursor is
- **Command Mode** - Hold Ctrl while speaking to control your computer:
  - "Open Chrome" - launches Chrome
  - "New tab" - opens a new browser tab
  - "Save" - saves your document
- **Mute Toggle** - Press **Pause** key to turn mic on/off

### 2. Batch Transcription (`audio_file_batch_transcribe.ipynb`)
Transcribe existing audio files (recordings, interviews, etc.) to text.

- Supports multiple formats: .m4a, .mp3, .wav, .flac
- Outputs: .txt, .srt (subtitles), .json (with timestamps)
- Great for transcribing recordings, interviews, lectures

## How It Works

```
Your voice → Microphone → AI (Whisper) → Text → Types into active window
```

- Uses OpenAI's **Whisper** model running locally on the GPU (not cloud-based, so it's private)
- The RTX 3070 Ti makes it fast (~0.5 seconds to transcribe)
- Voice Activity Detection (VAD) figures out when you start/stop talking

## How to Run It

1. Open PowerShell in this folder
2. Activate the Python environment:
   ```
   .\whisperenv\Scripts\activate
   ```
3. Run the program:
   ```
   python dragon_dictate.py --log
   ```
4. Start talking - your words appear wherever your cursor is

## Controls

| Key | What it does |
|-----|--------------|
| **Pause** | Mute/unmute the microphone |
| **Ctrl + speak** | Command mode (say "open chrome", "save", etc.) |
| **Ctrl+C** | Quit the program (in PowerShell window) |

## Voice Commands (hold Ctrl while speaking)

### Open Apps
- "Open Chrome" / "Open Brave"
- "Open Word" / "Open PowerPoint"
- "Open Notepad" / "Open VS Code"
- "Open Claude" / "Open Terminal"
- "Open Explorer" / "Open Ableton"

### Keyboard Shortcuts
- "New tab" / "Close tab"
- "Copy" / "Paste" / "Cut"
- "Undo" / "Redo"
- "Save"
- "Select all"
- "Close window"

## Tips

- **Speak naturally** - Whisper handles punctuation automatically
- **Pause between sentences** - gives it time to process
- **The Pause key is your friend** - mute when you don't want it listening
- **Check the log** - run with `--log` to see what it heard vs. what you said

## If Something Goes Wrong

- **Wrong words?** Whisper sometimes mishears things. There's a word replacement dictionary in the code for common mistakes.
- **Typing in wrong window?** It types into whatever window is focused. Click where you want text first.
- **Not responding?** Check if mic is muted (press Pause). Check PowerShell for errors.

## The Tech Stack (if you're curious)

- **Python 3.10** - programming language
- **OpenAI Whisper** - speech-to-text AI model
- **PyTorch + CUDA** - runs the AI on the GPU
- **webrtcvad** - detects when you're speaking vs. silent
- **keyboard** - listens for hotkeys (Pause key toggle, Ctrl for commands)
- **pynput** - simulates keyboard typing into active window
- **sounddevice** - captures audio from the microphone

---

*December 2025*
