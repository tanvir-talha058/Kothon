# Building & Releasing Kothon

## Prerequisites

- Python 3.11 with project dependencies: `pip install -r requirements.txt`
- PyInstaller: `pip install pyinstaller`
- [Inno Setup 6](https://jrsoftware.org/isinfo.php) (for the installer)
- Speech models present in `models/` (see README — they are not in git)

## 1. Run the tests

```powershell
python -m unittest discover tests
python -m unittest tests.test_integration -v   # needs the Bangla model
```

## 2. Build the executable

```powershell
python -m PyInstaller kothon.spec --noconfirm
```

Output: `dist\Kothon\Kothon.exe` (onedir, ~160 MB). The exe expects a `models\`
folder beside it. For a quick local test:

```powershell
New-Item -ItemType Junction -Path dist\Kothon\models -Target "$PWD\models"
dist\Kothon\Kothon.exe
```

Notes:
- `kothon.spec` excludes torch/scipy/etc. — heavyweight libraries on dev
  machines that optional imports would otherwise drag in (kept the build from
  ballooning 892 MB → 163 MB). If the built exe fails on a clean machine with
  a missing-module error, that module may need removing from `excludes`.
- Version lives in three places — keep them in sync:
  `main.py` (`__version__`), `version_info.txt`, `kothon.iss` (`AppVersion`).

## 3. Build the installer

```powershell
iscc kothon.iss
```

Output: `installer\KothonSetup-<version>.exe`. It installs per-user (no admin
prompt), bundles the models from `models\`, and offers desktop-shortcut and
start-with-Windows options. Uninstall keeps the user's `~/.kothon` settings.

## 4. Code signing (strongly recommended before public release)

Kothon registers a global keyboard hook and synthesizes keystrokes — unsigned,
that combination will trigger SmartScreen warnings and some antivirus
heuristics. With an OV/EV code-signing certificate:

```powershell
signtool sign /fd SHA256 /td SHA256 /tr http://timestamp.digicert.com dist\Kothon\Kothon.exe
iscc kothon.iss
signtool sign /fd SHA256 /td SHA256 /tr http://timestamp.digicert.com installer\KothonSetup-*.exe
```

## 5. Release checklist

- [ ] Tests green (unit + integration)
- [ ] Version bumped in `main.py`, `version_info.txt`, `kothon.iss`
- [ ] Exe smoke-tested on a machine without Python
- [ ] Dictation verified in all three language modes, both themes
- [ ] Binaries signed
- [ ] Git tag `v<version>` + GitHub Release with the installer attached
