#!/usr/bin/env python3
"""voicemorph: clone a voice from ~10 s of audio and make it ACT (gasps, sighs, shock, whispers).

Free and local. Built on Chatterbox by Resemble AI (MIT). No API key, no account.

  voicemorph.py doctor                                   check the install
  voicemorph.py clone NAME ref.wav --consent "..."       save a voice (only with the speaker's permission)
  voicemorph.py voices                                   list saved voices
  voicemorph.py say NAME "Wait... WHAT?!" -e shocked -o out.wav
  voicemorph.py act script.json -o narration.wav         multi-voice, per-line emotion, timings JSON
  voicemorph.py act script.json -o narration.wav --redo 2,9   re-voice only lines 2 and 9 (others are cached)
  voicemorph.py tags                                     emotions and sound tags you can use

Engines: turbo (default, fast, inline tags like [gasp]) and standard (slower, an emotion dial).
"""
import argparse, hashlib, json, re, shutil, subprocess, sys, time
from datetime import date
from pathlib import Path

HOME = Path.home() / '.voicemorph'
VOICES = HOME / 'voices'

# Tags the Turbo tokenizer knows (read from ResembleAI/chatterbox-turbo added_tokens.json).
# Anything else in [brackets] would be read out loud, so it is removed with a warning.
TAGS = ['advertisement', 'angry', 'chuckle', 'clear throat', 'cough', 'crying', 'dramatic', 'fear', 'gasp',
        'groan', 'happy', 'laugh', 'narration', 'sarcastic', 'shush', 'sigh', 'sniff', 'surprised', 'whispering']

# emotion -> (turbo style tag, standard exaggeration, standard cfg_weight)
EMOTIONS = {
    'neutral':   (None,            0.5,  0.5),
    'narrator':  ('narration',     0.5,  0.5),
    'dramatic':  ('dramatic',      0.75, 0.35),
    'shocked':   ('surprised',     0.95, 0.3),
    'scared':    ('fear',          0.85, 0.3),
    'sad':       ('crying',        0.6,  0.4),
    'happy':     ('happy',         0.75, 0.4),
    'excited':   ('advertisement', 0.9,  0.3),
    'angry':     ('angry',         0.9,  0.3),
    'sarcastic': ('sarcastic',     0.6,  0.45),
    'whisper':   ('whispering',    0.4,  0.5),
}

# optional finish: a little deeper, fuller, evenly loud (needs ffmpeg with rubberband)
MASTERS = {
    'none': None,
    'clean': 'acompressor=threshold=-18dB:ratio=3:attack=5:release=80:makeup=2,loudnorm=I=-16:TP=-1.5',
    'deep': 'rubberband=pitch=0.94:formant=preserved,highpass=f=60,equalizer=f=120:t=q:w=1:g=4,'
            'equalizer=f=350:t=q:w=1.2:g=-2,equalizer=f=3200:t=q:w=1.5:g=2.5,'
            'acompressor=threshold=-18dB:ratio=3:attack=5:release=80:makeup=2,loudnorm=I=-16:TP=-1.5',
}


def die(msg):
    sys.exit(f'voicemorph: {msg}')


def clean_tags(text, engine):
    def keep(m):
        t = m.group(1).strip().lower()
        if engine == 'turbo' and t in TAGS: return f'[{t}]'
        print(f'  note: [{m.group(1)}] removed ({"unknown tag" if engine == "turbo" else "tags need --engine turbo"})', file=sys.stderr)
        return ''
    return re.sub(r'\s{2,}', ' ', re.sub(r'\[([^\]]+)\]', keep, text)).strip()


def device():
    import torch
    if torch.cuda.is_available(): return 'cuda'
    if getattr(torch.backends, 'mps', None) and torch.backends.mps.is_available(): return 'mps'
    return 'cpu'


_models = {}
def model(engine):
    if engine not in _models:
        dev = device(); t = time.time()
        if engine == 'turbo':
            from chatterbox.tts_turbo import ChatterboxTurboTTS as M
        else:
            from chatterbox.tts import ChatterboxTTS as M
        _models[engine] = M.from_pretrained(device=dev)
        print(f'  {engine} model on {dev} ({time.time() - t:.0f} s)', file=sys.stderr)
    return _models[engine]


def voice_path(name):
    p = VOICES / f'{name}.wav'
    if p.exists(): return p
    q = Path(name)
    if q.exists():
        print(f'  using {q} directly as the reference voice', file=sys.stderr); return q
    die(f'no voice "{name}". Save one with: voicemorph.py clone {name} ref.wav --consent "..."')


def synth(text, voice, emotion='neutral', engine='turbo', speed=1.0):
    """Returns (numpy float32 mono, sample_rate)."""
    import numpy as np
    if emotion not in EMOTIONS: die(f'unknown emotion "{emotion}". Try: {", ".join(EMOTIONS)}')
    tag, ex, cfg = EMOTIONS[emotion]
    text = clean_tags(text, engine)
    m = model(engine)
    if engine == 'turbo':
        if tag and not text.startswith(f'[{tag}]'): text = f'[{tag}] {text}'
        w = m.generate(text, audio_prompt_path=str(voice_path(voice)))
    else:
        w = m.generate(text, audio_prompt_path=str(voice_path(voice)), exaggeration=ex, cfg_weight=cfg)
    a = w.squeeze().cpu().numpy().astype(np.float32)
    if abs(speed - 1.0) > 0.01: a = stretch(a, m.sr, speed)
    return trim(a), m.sr


def trim(a, th=0.01):
    import numpy as np
    i = np.where(np.abs(a) > th)[0]
    return a[max(0, i[0] - 240):i[-1] + 960] if len(i) else a


def stretch(a, sr, speed):
    """Tempo change without pitch change (ffmpeg atempo). Skipped if ffmpeg is missing."""
    if not shutil.which('ffmpeg'): return a
    import numpy as np, tempfile, soundfile as sf
    with tempfile.TemporaryDirectory() as d:
        sf.write(f'{d}/i.wav', a, sr)
        subprocess.run(['ffmpeg', '-v', 'error', '-y', '-i', f'{d}/i.wav', '-af', f'atempo={speed}', f'{d}/o.wav'], check=True)
        return sf.read(f'{d}/o.wav', dtype='float32')[0]


def master(path, kind):
    chain = MASTERS.get(kind)
    if not chain: return
    if not shutil.which('ffmpeg'):
        print('  note: ffmpeg not found, skipping --master', file=sys.stderr); return
    tmp = path.with_suffix('.tmp.wav')
    import soundfile as sf
    rate = str(sf.info(path).samplerate)            # loudnorm would otherwise resample to 192 kHz
    r = subprocess.run(['ffmpeg', '-v', 'error', '-y', '-i', str(path), '-af', chain, '-ac', '1', '-ar', rate, str(tmp)])
    if r.returncode and 'rubberband' in chain:       # ffmpeg built without rubberband: drop the pitch step
        chain = chain.split(',', 1)[1]
        r = subprocess.run(['ffmpeg', '-v', 'error', '-y', '-i', str(path), '-af', chain, '-ac', '1', '-ar', rate, str(tmp)])
    if r.returncode == 0: tmp.replace(path)


# ─────────────────────────────── commands ───────────────────────────────
def cmd_doctor(a):
    ok = True
    print(f'python {sys.version.split()[0]}' + ('' if sys.version_info[:2] == (3, 11) else '  (Chatterbox is tested on 3.11)'))
    for mod in ['torch', 'torchaudio', 'chatterbox', 'soundfile', 'perth']:
        try: __import__(mod); print(f'ok   {mod}')
        except Exception as e:
            ok = False; print(f'MISS {mod}: {e}')
            if 'pkg_resources' in str(e): print('     fix: pip install "setuptools<81"')
    print(('ok   ' if shutil.which('ffmpeg') else 'opt  ') + 'ffmpeg (needed for --master and speed)')
    if ok: print(f'device: {device()}')
    print('ready' if ok else 'install: pip install -r requirements.txt')


def cmd_clone(a):
    import soundfile as sf, numpy as np
    if not a.consent: die('--consent is required: say whose voice this is and that they agreed (your own voice counts).')
    src = Path(a.ref)
    if not src.exists(): die(f'{src} not found')
    VOICES.mkdir(parents=True, exist_ok=True)
    out = VOICES / f'{a.name}.wav'
    if shutil.which('ffmpeg'):                       # any format in, 24 kHz mono, first 20 s
        subprocess.run(['ffmpeg', '-v', 'error', '-y', '-i', str(src), '-t', '20', '-ac', '1', '-ar', '24000', str(out)], check=True)
    else:
        x, sr = sf.read(src, dtype='float32'); x = x.mean(1) if x.ndim > 1 else x; sf.write(out, x[:sr * 20], sr)
    x, sr = sf.read(out); dur = len(x) / sr
    if dur < 5: print(f'  warning: only {dur:.1f} s. 8-15 s of clean speech clones best.', file=sys.stderr)
    (VOICES / f'{a.name}.json').write_text(json.dumps({'name': a.name, 'source': src.name, 'seconds': round(dur, 1),
                                                       'consent': a.consent, 'saved': str(date.today())}, indent=1))
    print(f'saved voice "{a.name}" ({dur:.1f} s) -> {out}')


def cmd_voices(a):
    for j in sorted(VOICES.glob('*.json')) if VOICES.exists() else []:
        d = json.loads(j.read_text()); print(f'{d["name"]:14s} {d["seconds"]:5.1f} s  consent: {d["consent"]}')


def cmd_tags(a):
    print('emotions (-e / "emotion"):'); [print(f'  {k:10s} turbo [{v[0] or "-"}]  standard x{v[1]}') for k, v in EMOTIONS.items()]
    print('inline tags (turbo): ' + ' '.join(f'[{t}]' for t in TAGS))


def cmd_say(a):
    import soundfile as sf
    x, sr = synth(a.text, a.voice, a.emotion, a.engine, a.speed)
    out = Path(a.o); sf.write(out, x, sr); master(out, a.master); print(f'{out} ({len(x) / sr:.2f} s)')


def cmd_act(a):
    """script.json: {"voices": {"N": "deepguy", "R": "bella"}, "engine": "turbo", "lead": 0.3, "outro": 0.8,
                     "lines": [{"who": "R", "emotion": "shocked", "text": "Wait... [gasp] WHAT?!", "pause": 0.4}, ...]}
    Writes the WAV plus <out>.json with start/end per line (faceless-shorts lines.json format)."""
    import numpy as np, soundfile as sf
    S = json.loads(Path(a.script).read_text())
    engine = a.engine or S.get('engine', 'turbo'); voices = S.get('voices', {})
    sr = None; parts = []; t = float(S.get('lead', 0.3)); lines = []
    cache = Path(a.o).with_suffix('.takes'); cache.mkdir(exist_ok=True)
    redo = {int(n) for n in a.redo.split(',')} if a.redo else set()
    for i, ln in enumerate(S['lines']):
        who = ln.get('who', 'N'); v = voices.get(who, who)
        emo, eng, spd = ln.get('emotion', S.get('emotion', 'neutral')), ln.get('engine', engine), ln.get('speed', 1.0)
        # takes are cached per line: re-running only re-voices lines you changed (or pass --redo 3,7)
        key = hashlib.sha1(json.dumps([ln['text'], v, emo, eng, spd]).encode()).hexdigest()[:12]
        take = cache / f'{i:02d}-{key}.wav'
        if take.exists() and i not in redo: x, sr = sf.read(take, dtype='float32')
        else: x, sr = synth(ln['text'], v, emo, eng, spd); sf.write(take, x, sr)
        x = x * float(ln.get('gain', 1.0))
        lines.append({'i': i, 'who': who, 'text': re.sub(r'\[[^\]]+\]\s*', '', ln['text']).strip(), 'start': round(t, 3), 'end': round(t + len(x) / sr, 3)})
        print(f'{i:2d} {who:2s} {lines[-1]["start"]:6.2f}-{lines[-1]["end"]:6.2f} [{ln.get("emotion", "neutral")}] {ln["text"]}', flush=True)
        parts.append((x, float(ln.get('pause', S.get('pause', 0.3))))); t += len(x) / sr + parts[-1][1]
    y = [np.zeros(int(float(S.get('lead', 0.3)) * sr), np.float32)]
    for x, p in parts: y += [x, np.zeros(int(p * sr), np.float32)]
    y.append(np.zeros(int(float(S.get('outro', 0.8)) * sr), np.float32))
    y = np.concatenate(y); y = y / (np.abs(y).max() + 1e-9) * 0.9
    out = Path(a.o); sf.write(out, y, sr); master(out, a.master)
    dur = sf.info(out).duration
    out.with_suffix('.json').write_text(json.dumps({'duration': round(dur, 3), 'engine': engine, 'voices': voices, 'lines': lines}, indent=1))
    print(f'{out} ({dur:.2f} s) + {out.with_suffix(".json")}')


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    s = p.add_subparsers(dest='cmd', required=True)
    s.add_parser('doctor'); s.add_parser('voices'); s.add_parser('tags')
    c = s.add_parser('clone'); c.add_argument('name'); c.add_argument('ref'); c.add_argument('--consent', required=True)
    for name in ['say', 'act']:
        c = s.add_parser(name)
        if name == 'say': c.add_argument('voice'); c.add_argument('text'); c.add_argument('-e', '--emotion', default='neutral'); c.add_argument('--speed', type=float, default=1.0)
        else: c.add_argument('script'); c.add_argument('--redo', help='line numbers to re-voice even if cached, e.g. 2,9')
        c.add_argument('-o', default='out.wav'); c.add_argument('--engine', choices=['turbo', 'standard'], default=None if name == 'act' else 'turbo')
        c.add_argument('--master', choices=list(MASTERS), default='clean')
    a = p.parse_args()
    {'doctor': cmd_doctor, 'clone': cmd_clone, 'voices': cmd_voices, 'tags': cmd_tags, 'say': cmd_say, 'act': cmd_act}[a.cmd](a)


if __name__ == '__main__':
    main()
