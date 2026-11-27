"""Record a demo video of Kirby's Dream Land through Ultra Game Boy.

    .venv\\Scripts\\python tools\\kirby_demo.py out\\kirby_demo.mp4

The title screen, Kirby playing through each stage (scripted presses from
saved states), then the title again switching to the Extra Game. Video at
60 fps, the game alone at 5x (800x720) with its own sound, short fades
between the clips. Needs imageio-ffmpeg (pip install imageio-ffmpeg) and the
saves listed in SCENES.
"""
import os
import subprocess
import sys
import time
import wave

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import imageio_ffmpeg   # noqa: E402
import numpy as np   # noqa: E402
from PIL import Image   # noqa: E402
from pyboy import PyBoy   # noqa: E402

from ugb import presets   # noqa: E402
from ugb.gb import Frame   # noqa: E402
from ugb.render import Enhancer   # noqa: E402
from ugb.roms import rom_path   # noqa: E402

S = 5                           # game scale: the video is the game alone, 800x720
W, H = 160 * S, 144 * S
GX, GY = (W - 160 * S) // 2, (H - 144 * S) // 2
FADE = 12

# (save, stage name, place, script); a script is steps of (frames, held
# buttons, 'a' taps: None, 'jump' every so often, or 'fly' quickly[, the
# place's new caption from that step on])
SCENES = [
    ('states/kirby_title.state', "Kirby's Dream Land", 'Title screen', [(300, '', None)]),
    ('states/kirby_hoops.state', 'Green Greens', 'Stage 1', [(80, 'right', None), (200, 'right', 'jump')]),
    ('states/kirby_s2_0-1-3-0.state', 'Castle Lololo', 'Stage 2', [(260, 'right', 'jump')]),
    ('states/kirby_s3_start.state', 'Float Islands', 'Stage 3', [(260, 'right', 'jump')]),
    ('states/kirby_s4_play.state', 'Bubbly Clouds', 'Stage 4', [(260, 'right', 'fly')]),
    ('out/shots/20261126-141534.state', 'Bubbly Clouds', 'Among the stars', [(200, 'right', 'fly')]),
    ('states/kirby_s5_play2.state', 'Mt. DeDeDe', 'Stage 5', [(260, 'right', 'jump')]),
    ('states/kirby_title.state', "Kirby's Dream Land", 'Title screen',
     [(150, '', None), (330, 'up+select+a', None, 'Extra Game')]),   # (the Extra Game's code)
]


def frame_image(game):
    return np.array(Image.fromarray(game).resize((W, H), Image.NEAREST))


def main():
    out = sys.argv[1] if len(sys.argv) > 1 else 'out/kirby_demo.mp4'
    p = presets.for_title('KIRBY DREAM LAN')
    pb = PyBoy(rom_path('kirby'), window='null', cgb=True, sound_emulated=True)
    rate = pb.sound.sample_rate
    video = out + '.video.mp4'
    writer = imageio_ffmpeg.write_frames(video, (W, H), fps=60, codec='libx264', quality=8,
                                         pix_fmt_out='yuv420p', macro_block_size=8)
    writer.send(None)
    audio = []
    en = Enhancer(p)
    # boot the game first (not recorded), as the app does: a plain Game Boy
    # game's sprite colours are learned from the picture, and a sprite first
    # drawn before that keeps its grey look
    for _ in range(900):
        pb.tick(1, True)
        en.render(Frame(pb))
    n_out = 0
    for state, title, place, script in SCENES:
        if state:
            with open(state, 'rb') as f:
                pb.load_state(f)
            pb.tick(1, True)
            pb.sound.ndarray          # (drop the sound queued before)
            for _ in range(40):       # let the area's capture load
                en.render(Frame(pb))
                if en._kind is not None or p.area_key(pb.memory) is None:
                    break
                time.sleep(0.1)
        m = pb.memory
        frames = []
        places = []
        for n, held, tap, *cap in script:
            if cap:
                place = cap[0]
            keys = [b for b in held.split('+') if b]
            for b in keys:
                pb.button_press(b)
            for i in range(n):
                if p.area_key(m) is not None:
                    m[0xD086] = 6      # (full health, so nothing interrupts)
                if tap == 'fly':
                    if i % 8 == 0:
                        pb.button_press('a')
                    elif i % 8 == 4:
                        pb.button_release('a')
                elif tap == 'jump':
                    if i % 50 == 10:
                        pb.button_press('a')
                    elif i % 50 == 30:
                        pb.button_release('a')
                pb.tick(1, True)
                frames.append(en.render(Frame(pb)))
                places.append(place)
                s = pb.sound.ndarray
                if s is not None and len(s):
                    audio.append(np.array(s, np.int16).reshape(-1, 2))
                else:            # (silence, so the sound stays in step with the picture)
                    audio.append(np.zeros((rate // 60, 2), np.int16))
            for b in keys + ['a']:
                pb.button_release(b)
        first = {}
        for k, pl in enumerate(places):
            first.setdefault(pl, k)
        for k, g in enumerate(frames):
            fade = min(1.0, k / FADE, (len(frames) - 1 - k) / FADE)
            img = frame_image(g)
            if fade < 1:     # (a short fade through black between clips)
                img = (img.astype(np.float32) * fade).astype(np.uint8)
            writer.send(np.ascontiguousarray(img))
            n_out += 1
        print('%-20s %-16s %d frames' % (title, place, len(frames)), flush=True)
    writer.close()
    pb.stop(save=False)
    # the sound: scaled up (the emulator's samples are quiet), then muxed in
    wav = out + '.wav'
    a = np.concatenate(audio) if audio else np.zeros((1, 2), np.int16)
    a = np.clip(a.astype(np.int32) * 180, -32767, 32767).astype(np.int16)
    with wave.open(wav, 'wb') as w:
        w.setnchannels(2)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(a.tobytes())
    ff = imageio_ffmpeg.get_ffmpeg_exe()
    subprocess.check_call([ff, '-y', '-loglevel', 'error', '-i', video, '-i', wav, '-c:v', 'copy',
                           '-c:a', 'aac', '-b:a', '160k', '-shortest', out])
    os.remove(video)
    os.remove(wav)
    print('wrote', out, '%.1f s' % (n_out / 60), '%.1f MB' % (os.path.getsize(out) / 1e6))


if __name__ == '__main__':
    main()
