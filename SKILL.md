---
name: voicemorph
description: Clone a voice from ~10 s of audio and make it act (gasps, sighs, shock, whispers, two-person dialogue) with free, local, open-source TTS. Use for voiceovers, reels/Shorts narration, podcasts or any "make this voice sound emotional" request.
---

# voicemorph

Free, local voice cloning with real emotion, built on Chatterbox by Resemble AI (MIT). No API key, no account, no per-character cost. One script: `scripts/voicemorph.py`.

## Ground rules (always)

1. **Consent first.** Only clone a voice when the user says it is their own, or that the speaker agreed. `clone` refuses to run without `--consent "..."`; write down whose voice it is. Never clone a public figure, a celebrity or anyone who has not agreed, and never make audio meant to pass as a real person saying something they did not say.
2. **Keep the watermark.** Chatterbox adds Resemble's imperceptible Perth watermark to every file, which marks it as AI-generated. Do not strip, filter out or work around it.
3. **Check what was said.** Generated speech is sampled and can occasionally skip or garble a word. After `act`, transcribe the result (Whisper or similar) and re-voice only the bad lines with `--redo`.

## Setup (once)

```bash
python3.11 -m venv ~/.voicemorph/venv && . ~/.voicemorph/venv/bin/activate
pip install -r requirements.txt          # chatterbox-tts, soundfile, setuptools<81
python scripts/voicemorph.py doctor       # checks everything, shows cuda / mps / cpu
```

ffmpeg is optional but recommended (`--master`, speed changes, any input format for `clone`). First use downloads the model weights from Hugging Face.

## Commands

| Command | What it does |
| --- | --- |
| `clone NAME ref.wav --consent "..."` | Save a voice from 8-15 s of clean speech (any format with ffmpeg). Stored in `~/.voicemorph/voices/`. |
| `voices` | List saved voices and their consent notes. |
| `tags` | Show the emotions and inline tags. |
| `say NAME "text" -e shocked -o out.wav` | One line, one voice. |
| `act script.json -o narration.wav` | A whole script: several voices, emotion per line, pauses. Also writes `narration.json` with start/end per line. |
| `act ... --redo 2,9` | Re-voice only lines 2 and 9. Every other line is reused from the `narration.takes/` cache. |

Options: `--engine turbo` (default: fast, understands inline tags) or `--engine standard` (slower; uses an emotion dial instead of tags). `--master deep|clean|none` (default `clean`): `deep` lowers the voice slightly and adds warmth and punch.

## Writing a script that acts

```json
{
  "engine": "turbo",
  "voices": { "N": "deep", "R": "bella" },
  "lead": 0.3, "outro": 0.8,
  "lines": [
    { "who": "N", "emotion": "dramatic", "text": "Its founder... resigned. In four days.", "pause": 0.35 },
    { "who": "R", "emotion": "shocked",  "text": "Wait... [gasp] WHAT?! Four days?!", "pause": 0.4 },
    { "who": "R", "emotion": "sad",      "text": "Thirty three years... [sigh] gone.", "pause": 0.45 }
  ]
}
```

- **emotion** per line: `neutral narrator dramatic shocked scared sad happy excited angry sarcastic whisper`.
- **inline tags** (turbo only) go exactly where the sound should happen: `[gasp] [sigh] [laugh] [chuckle] [groan] [sniff] [cough] [clear throat] [shush] [crying] [whispering] [surprised] [fear] [angry] [happy] [sarcastic] [dramatic] [narration] [advertisement]`. These are the tokens the model was trained on. Any other `[tag]` is removed with a warning, because it would be read out loud.
- Optional per line: `speed` (0.8-1.2), `gain`, `engine`, `pause` (seconds after the line).

What makes a line land:
- Write the emotion into the words, not only the tag. "Wait... WHAT?!" acts better than "What."
- Capitals and `?!` raise the energy. `...` adds a hesitation.
- Two voices beat one: a narrator, plus a reactor who says what the viewer feels ("No way!", "Oh no...").
- Short reaction lines between longer narrator lines keep the rhythm moving.

## Speed

Turbo runs at about real time on a GPU or Apple Silicon (mps). On a 2-core CPU it is roughly 3-4× slower than real time, so a 60 s script takes about 4 minutes. The standard engine is about 3× slower than turbo. Cached takes make re-runs nearly instant.

## Hand-off

`act` writes `narration.wav` plus `narration.json` (`{duration, lines: [{i, who, text, start, end}]}`), the same shape as faceless-shorts `data/lines.json`. Drop them into a video pipeline and run word alignment as usual.
