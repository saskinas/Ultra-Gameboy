"""Build the Windows app for players: dist/Ultra Game Boy/ and a zip of it.

    .venv\\Scripts\\python tools\\build_windows.py

Needs PyInstaller in the environment (pip install pyinstaller). The result
runs on Windows 10/11 without Python. No games are included: players choose
their own ROM files in the app.
"""
import os
import shutil
import subprocess
import sys
import zipfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
NAME = 'Ultra Game Boy'


def main():
    os.chdir(ROOT)
    cmd = [sys.executable, '-m', 'PyInstaller', '--noconfirm', '--clean',
           '--name', NAME, '--windowed', '--onedir',
           '--collect-submodules', 'ugb',          # (presets are looked up by name)
           '--collect-all', 'pyboy',
           '--collect-all', 'sdl2dll',
           '--collect-submodules', 'scipy.ndimage',
           '--exclude-module', 'matplotlib',
           'UltraGameBoy.py']
    print(' '.join(cmd))
    subprocess.check_call(cmd)
    dist = os.path.join(ROOT, 'dist', NAME)
    shutil.copy(os.path.join(ROOT, 'docs', 'PLAYERS.md'), os.path.join(dist, 'How to play.txt'))
    zpath = os.path.join(ROOT, 'dist', 'UltraGameBoy-windows.zip')
    with zipfile.ZipFile(zpath, 'w', zipfile.ZIP_DEFLATED) as z:
        for base, _, files in os.walk(dist):
            for fn in files:
                full = os.path.join(base, fn)
                z.write(full, os.path.join(NAME, os.path.relpath(full, dist)))
    print('built', dist)
    print('zip', zpath, '%.0f MB' % (os.path.getsize(zpath) / 1e6))


if __name__ == '__main__':
    main()
