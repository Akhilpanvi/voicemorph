# voicemorph 🎙️

**Clone a voice from 10 seconds of audio and make it act: gasps, sighs, shock, whispers, two-person dialogue. Free, local, open source.**

An open-source voice cloning skill for Claude Code (and any Python user), built on [Chatterbox](https://github.com/resemble-ai/chatterbox) by Resemble AI (MIT). No API key, no subscription, no per-character billing.

🔊 Listen: [`demo/two-voices.mp3`](demo/two-voices.mp3), made from [`examples/two-voices.json`](examples/two-voices.json).

```text
N (dramatic): Your phone knows where you parked. Every single time.
R (shocked):  Wait... [gasp] WHAT?! Even if I never told it?
R (happy):    [laugh] Or never lose my car again. Honestly? I'll keep it.
```

## Why

Most free TTS reads every line in the same flat tone, so "Wait... what?!" sounds like a weather report. voicemorph gives each line an **emotion** and lets you drop **real sound tags** (`[gasp]`, `[sigh]`, `[laugh]`) exactly where they belong. It voices a whole multi-speaker script in one command and caches every take, so fixing one line takes seconds.

## Quick start

```bash
git clone https://github.com/Akhilpanvi/voicemorph && cd voicemorph
python3.11 -m venv .venv && . .venv/bin/activate
pip install -r requirements.txt
python scripts/voicemorph.py doctor

# 1. save a voice (yours, or someone who said yes)
python scripts/voicemorph.py clone me my_10s_clip.m4a --consent "my own voice"

# 2. one line
python scripts/voicemorph.py say me "Wait... [gasp] WHAT?!" -e shocked -o wow.wav

# 3. a whole script, two voices, per-line emotion
python scripts/voicemorph.py act examples/two-voices.json -o narration.wav --master deep
python scripts/voicemorph.py act examples/two-voices.json -o narration.wav --redo 1   # re-voice just line 1
```

## As a Claude Code skill

Copy this folder to `~/.claude/skills/voicemorph/`. Then ask Claude, for example: *"use voicemorph to voice this reel script with a shocked reactor voice"*. [`SKILL.md`](SKILL.md) tells Claude how to write scripts that act, which tags exist, and to verify the output.

## Features

- **Zero-shot cloning** from 8-15 s of clean speech, any audio format (with ffmpeg).
- **11 emotions**: neutral, narrator, dramatic, shocked, scared, sad, happy, excited, angry, sarcastic, whisper.
- **19 inline tags**, the exact tokens the Turbo model was trained on. Unknown tags are removed instead of being read aloud.
- **Two engines**: `turbo` (fast, tags) and `standard` (an emotion dial).
- **Multi-voice scripts** with pauses, plus a timings JSON for video captions.
- **Take cache** and `--redo` to re-voice single lines.
- **`--master deep`**: a slightly deeper, warmer, evenly loud finish for social video.
- Runs on **CUDA, Apple Silicon (mps) or plain CPU**.

## Responsible use

- `clone` requires a `--consent` note. Clone only your own voice or a voice whose owner agreed.
- Do not impersonate real people or make audio meant to deceive.
- Every file carries Resemble AI's imperceptible **Perth watermark**, which marks it as AI-generated. Please keep it.

## Credits & license

- Speech models: [Chatterbox / Chatterbox-Turbo](https://github.com/resemble-ai/chatterbox) by Resemble AI (MIT).
- voicemorph code: MIT, see [LICENSE](LICENSE).
- Demo voices are synthetic (Kokoro-82M, Apache-2.0); no real person was cloned.
