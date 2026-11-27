"""Ultra Game Boy: play a Game Boy (Color) game with live 16-bit-style enhancement.

    python -m ugb.app [rom] [--state file.state]

Controls
  Arrows      D-pad            Z / X     A / B
  Enter       Start            Backspace Select
  Tab         toggle enhanced / original
  G           generic shading: subtle / strong
  E           eye candy on / off (the preset's EYE_CANDY effects)
  Space       hold to fast-forward
  F2 / F4     quick save / load state (states/quick.state)
  F12         screenshot (original | enhanced) and the game state to out/shots
  Esc         quit (the in-game save is written to the ROM's .ram file)
"""
import argparse
import os
import shutil
import threading
import time

import numpy as np
import pygame
from pyboy import PyBoy

from ugb.gb import Frame, note_tick
from ugb.paths import data_path
from ugb.render import Enhancer
from ugb import presets
from ugb.roms import rom_path

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

KEYS = {
    pygame.K_UP: 'up', pygame.K_DOWN: 'down', pygame.K_LEFT: 'left', pygame.K_RIGHT: 'right',
    pygame.K_z: 'a', pygame.K_x: 'b', pygame.K_RETURN: 'start', pygame.K_BACKSPACE: 'select',
}
SCALE = 4


class Audio:
    """Stream PyBoy's samples through an SDL audio callback.

    Emulated frames push samples into a ring buffer; the sound card pulls from it
    on its own thread. The main loop runs the emulator whenever the buffer drops
    below TARGET, so the sound card is the clock: a slow render just means the
    next loop emulates two frames, and the music keeps playing.
    """
    TARGET = 0.09    # seconds of audio to keep queued
    LIMIT = 0.25     # drop the oldest audio past this (e.g. after fast-forward)

    def __init__(self, pb):
        self.ok = False
        self.rate = pb.sound.sample_rate
        self.ring = np.zeros((self.rate, 2), np.int16)   # one second
        self.rd = 0
        self.n = 0
        self.lock = threading.Lock()
        self.underruns = 0   # callbacks that found the buffer short (audible gaps)
        self.started = False
        try:
            from pygame._sdl2.audio import AudioDevice, AUDIO_S16
            self.dev = AudioDevice(devicename=None, iscapture=False, frequency=self.rate,
                                   audioformat=AUDIO_S16, numchannels=2, chunksize=512,
                                   allowed_changes=0, callback=self._pull)
            self.dev.pause(0)
            self.ok = True
        except Exception as e:   # no audio device: play silently, pace by the clock
            print('audio off:', e)

    def _pull(self, dev, mem):
        want = len(mem) // 4
        out = np.zeros((want, 2), np.int16)
        with self.lock:
            k = min(want, self.n)
            if self.started and k < want:
                self.underruns += 1
            if k:
                self.started = True
            if k:
                idx = (self.rd + np.arange(k)) % len(self.ring)
                out[:k] = self.ring[idx]
                self.rd = (self.rd + k) % len(self.ring)
                self.n -= k
        mem[:] = out.tobytes()

    def push(self, pb):
        s = pb.sound.ndarray
        if not self.ok or not s.size:
            return
        s = (s.astype(np.int16) * 128).reshape(-1, 2)
        with self.lock:
            cap = len(self.ring)
            wr = (self.rd + self.n) % cap
            idx = (wr + np.arange(len(s))) % cap
            self.ring[idx] = s
            self.n += len(s)
            limit = int(self.LIMIT * self.rate)
            if self.n > limit:   # too far ahead: skip the oldest
                drop = self.n - limit
                self.rd = (self.rd + drop) % cap
                self.n = limit

    def hungry(self):
        with self.lock:
            return self.n < self.TARGET * self.rate

    def clear(self):
        with self.lock:
            self.n = 0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('rom', nargs='?', default='yellow',
                    help='ROM path or short name: yellow, zelda, balloon')
    ap.add_argument('--state')
    ap.add_argument('--no-save', action='store_true',
                    help="don't write the in-game save (.ram) on exit, e.g. for tests")
    args = ap.parse_args()

    args.rom = rom_path(args.rom)
    pb = PyBoy(args.rom, window='null', cgb=True, sound_emulated=True)
    pb.set_emulation_speed(0)
    preset = presets.for_title(pb.cartridge_title)
    if preset.TITLE is None:
        print('No preset for', repr(pb.cartridge_title), '- using the generic enhancer.')
    en = Enhancer(preset)
    if args.state:
        with open(args.state, 'rb') as f:
            pb.load_state(f)

    pygame.init()
    screen = pygame.display.set_mode((160 * SCALE, 144 * SCALE))
    surf = pygame.Surface((160, 144))
    audio = Audio(pb)
    clock = pygame.time.Clock()
    enhanced = en is not None
    qs = data_path('states', 'quick.state')
    shots = os.path.dirname(data_path('out', 'shots', 'x'))
    times = []
    pace = {}      # emulated frames per displayed frame (debug)
    running = True
    while running:
        ff = pygame.key.get_pressed()[pygame.K_SPACE]
        for ev in pygame.event.get():
            if ev.type == pygame.QUIT:
                running = False
            elif ev.type == pygame.KEYDOWN:
                if ev.key in KEYS:
                    pb.button_press(KEYS[ev.key])
                elif ev.key == pygame.K_ESCAPE:
                    running = False
                elif ev.key == pygame.K_TAB and en:
                    enhanced = not enhanced
                elif ev.key == pygame.K_e and en:
                    en.eye_candy = not en.eye_candy
                    print('eye candy:', 'on' if en.eye_candy else 'off')
                elif ev.key == pygame.K_g and en:
                    en.generic_level = 3 - en.generic_level
                    print('generic shading:', 'strong' if en.generic_level == 2 else 'subtle')
                elif ev.key == pygame.K_F2:
                    with open(qs, 'wb') as f:
                        pb.save_state(f)
                    print('saved', qs)
                elif ev.key == pygame.K_F4 and os.path.exists(qs):
                    with open(qs, 'rb') as f:
                        pb.load_state(f)
                    audio.clear()
                    print('loaded', qs)
                elif ev.key == pygame.K_F12 and en:
                    os.makedirs(shots, exist_ok=True)
                    from PIL import Image
                    o = pb.screen.ndarray[:, :, :3]
                    e = en.render(Frame(pb))
                    name = os.path.join(shots, time.strftime('%Y%m%d-%H%M%S') + '.png')
                    with open(name[:-4] + '.state', 'wb') as sf:     # (the game too, to revisit the spot)
                        pb.save_state(sf)
                    Image.fromarray(np.concatenate([o, e], 1)).resize((320 * 3, 144 * 3), Image.NEAREST).save(name)
                    print('screenshot', name)
            elif ev.type == pygame.KEYUP and ev.key in KEYS:
                pb.button_release(KEYS[ev.key])

        if ff:
            pb.tick(4, True)
            audio.clear()
            stepped = True
        elif audio.ok:
            # the sound card is the clock: emulate until enough audio is queued
            stepped = 0
            for _ in range(4):
                if not audio.hungry():
                    break
                pb.tick(1, True)
                note_tick(pb)
                audio.push(pb)
                stepped += 1
            if stepped:
                pace[stepped] = pace.get(stepped, 0) + 1
            if not stepped:
                time.sleep(0.002)
                continue
        else:
            pb.tick(1, True)
            note_tick(pb)
            stepped = True

        t = time.perf_counter()
        if enhanced:
            img = en.render(Frame(pb))
        else:
            img = pb.screen.ndarray[:, :, :3]
        times.append(time.perf_counter() - t)
        pygame.surfarray.blit_array(surf, np.ascontiguousarray(img.transpose(1, 0, 2)))
        pygame.transform.scale(surf, screen.get_size(), screen)
        pygame.display.flip()

        if len(times) >= 60:
            ms = 1000 * sum(times) / len(times)
            pygame.display.set_caption('Ultra Game Boy - %s - %s - render %.1f ms - %d fps' % (
                pb.cartridge_title.strip(), 'enhanced' if enhanced else 'original', ms, clock.get_fps()))
            times = []
        if not audio.ok or ff:
            clock.tick(0 if ff else 60)
        else:
            clock.tick()

    if audio.ok:
        print('audio gaps:', audio.underruns)
        print('frames emulated per frame shown:', dict(sorted(pace.items())))
    ram = args.rom + '.ram'
    if not args.no_save and os.path.exists(ram):
        shutil.copyfile(ram, ram + '.bak')   # keep the previous in-game save
    pb.stop(save=not args.no_save)
    pygame.quit()


if __name__ == '__main__':
    main()
