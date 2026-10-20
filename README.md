# SnapShot Pro 1.1

Lightshot-style screenshot aur annotation desktop app. Native **PyQt6** UI; browser/Electron runtime nahi. Windows ko pehla target rakha gaya hai, Linux X11 aur macOS ke liye bhi source aur native build workflow diya gaya hai.

![SnapShot Pro control panel](**assets/screenshot_preview.png**)

## Windows par foran shuru karein

Python **3.11–3.13** install ho to source extract karke **`Run_Setup.bat`** double-click karein. Yeh project ki `.venv` mein runtime dependencies install karke app khol dega. Agli dafa **`start.bat`** use karein.

Portable build milne par `SnapShotPro` ka **poora folder** rakhein aur `SnapShotPro.exe` chalayein. Is folder build mein Python alag install karna zaroori nahi. Sirf EXE ko folder se alag na karein.

## Features

- **Region snip:** drag selection, live native-pixel dimensions, 8 resize handles, magnifier aur HEX color copy.
- **11 annotation tools:** move/resize, pen, line, arrow, rectangle, ellipse, highlighter, text, numbered steps, pixelation aur solid color redaction. Annotation undo/redo.
- **Floating toolbars:** chhoti screens par bhi controls screen bounds mein rehte hain. Export mein toolbars shamil nahi hotin.
- **Copy, quick save, Save As:** PNG, JPEG aur WebP. Atomic saves, unique names; save fail ho to selection khuli rehti hai.
- **OCR Text Grabber:** Tesseract ke zariye local text extraction; background worker, editable result aur clipboard copy. `eng+urd` jaise installed language codes Settings mein set karein.
- **Scrolling capture:** region select karte hi controller khulta hai. Manual frames ya auto-scroll; pixel overlap matching aur unchanged-frame skipping. Finish par stitched result copy/save hota hai.
- **Multi-snip:** frozen desktop se multiple independent regions collect karein, Enter se har snip add karein, Finish/Esc se vertically combine karein. Different widths supported; independent snips kabhi overlap-trim nahi hote.
- **Pin:** always-on-top image, drag, mouse-wheel zoom; right-click se copy, reset zoom, opacity ya close. Double-click/Esc bhi close karta hai.
- **Full desktop / each monitor:** aik combined screenshot ya har screen ki separate file.
- **Delayed region capture:** 3, 5 ya 10 seconds.
- **Open/Paste image:** saved ya clipboard image ko isi annotation editor mein edit/crop karein. Recent saves menu mein latest 12 files milti hain.
- **Tray + custom hotkeys:** Windows par native `RegisterHotKey`; macOS/X11 par pynput bridge. Conflicting/unavailable keys ka status panel mein dikhaya jata hai.
- **Single instance:** accidental duplicate launches block hoti hain. Tray available na ho to main window accessible rehti hai.

## Shortcuts

| Shortcut | Action |
| --- | --- |
| PrintScreen / Ctrl+Shift+S | Region capture |
| Ctrl+Shift+F | Copy + save full desktop |
| Ctrl+Shift+M | Multi-snip |
| Enter / Ctrl+C | Copy selected region; multi mode mein next snip |
| Ctrl+D | Quick save |
| Ctrl+S | Save As |
| Ctrl+T | OCR on selection |
| Ctrl+P | Pin selection |
| Ctrl+M | Multi-snip on/off |
| Ctrl+Z / Ctrl+Y | Undo / redo annotation |
| M / P / L / A / R / E / H / T / N / B / K | Move, pen, line, arrow, rect, ellipse, marker, text, steps, pixelate, solid redaction |
| C | Copy cursor-pixel HEX color |
| Right-click | Clear selection; next right-click closes overlay |
| Esc | Finish; multi mode mein collected snips combine hote hain |

## Source se run

```bash
python -m venv .venv
# Windows: .venv\Scripts\activate
# macOS / Linux:
source .venv/bin/activate
python -m pip install -r requirements.txt
python snapshot_pro.py
```

`python snapshot_pro.py --tray` background mode hai. Startup khud pip/network calls nahi karta. Setup/build scripts explicitly dependencies download karte hain. Screenshots, OCR input aur settings local rehte hain; app mein upload/telemetry service nahi.

### OCR engine (optional)

App ka baqi hissa Tesseract ke baghair kaam karta hai. OCR ke liye:

- Windows: `winget install UB-Mannheim.TesseractOCR`
- Ubuntu/Debian: `sudo apt install tesseract-ocr`
- macOS: `brew install tesseract`

Urdu ke liye Tesseract ka `urd` language data alag install karein. Language availability `tesseract --list-langs` se check hoti hai. Custom engine path `SNAPSHOT_TESSERACT` environment variable se diya ja sakta hai. Engine ko Python process mein load nahi kiya jata; sirf OCR action par subprocess chalta hai, 30 second timeout ke saath.

Linux source install mein agar `evdev` ka wheel available na ho to C compiler aur Python development headers zaroori ho sakte hain (`build-essential`, `python3-dev`). Portable Linux bundle in Python dependencies ko saath rakhta hai.

### Platform support aur practical limits

| Function | Windows | Linux | macOS |
| --- | --- | --- | --- |
| Region, annotations, images, copy/save, pin | Implemented | X11 | Implemented; Screen Recording permission |
| Global hotkeys | Native OS registration | X11/pynput | pynput; Accessibility permission |
| Smart window hover snap | Win32 window bounds | Monitor fallback | Monitor fallback |
| Automatic scrolling | Native mouse wheel | pynput | pynput; Accessibility permission |
| OCR | Optional Tesseract | Optional Tesseract | Optional Tesseract |

Wayland portal capture is **not implemented**; Linux release X11/Xorg session ke liye hai. Scrolling mein fixed headers/footers ko selection se bahar rakhein aur successive frames mein overlap rehne dein. Animating/video regions ki alignment reliable nahi ho sakti; uncertain frames append hote hain. Long captures aur combined snips ka guard 48 megapixels hai. Bohat lambi/wide images ke liye memory isi hisaab se barhti hai.

HiDPI canvas highest monitor scale par compose hota hai: high-density screen detail preserve hoti hai; lower-density screens combined capture mein upscale ho sakti hain. Each Monitor mode native per-screen image deta hai. Physical mixed-DPI Windows/macOS hardware validation abhi baqi hai.

## Build portable app / installer

Default **folder bundle** hai: startup par runtime unpack nahi hota. Build tools runtime requirements se alag hain.

### Windows

- **`Build_Windows_Setup.bat`**: clean build environment, `dist/SnapShotPro/SnapShotPro.exe` aur portable ZIP.
- **Inno Setup 6** installed ho to isi command se `dist/SnapShotPro-1.1.0-Windows-Setup.exe` bhi banegi. Yeh per-user install aur standard uninstaller deta hai.
- **`Build_Standalone_EXE_Windows.bat`**: optional single `dist/SnapShotPro.exe`. One-file mode cold start par extract hota hai, is liye folder build preferred hai.

### Linux / macOS

```bash
./Build_Linux_Setup.sh
# ya macOS par:
./Build_Mac_Setup.sh
```

Linux portable folder mein `./SnapShotPro` launch karein; optional `./install.sh` user applications menu mein install karta hai. `./uninstall.sh` app remove karta hai, images/settings preserve hoti hain. Ubuntu par zaroorat ho to `sudo apt install libxcb-cursor0` karein.

### Manual build / all-platform CI

```bash
python -m pip install -r requirements-build.txt
python build_all.py                 # current OS
python build_all.py --onefile       # optional Windows/Linux single file
```

PyInstaller cross-compile nahi karta. Windows EXE Windows par aur macOS .app macOS par build hoti hai. `.github/workflows/build.yml` ka **Run workflow** Windows, Linux aur macOS runners par tests aur packaging karta hai. Yeh workflow source mein diya gaya hai; is delivery mein remote workflow run/publish nahi kiya gaya.

Build `SHA256SUMS.txt`, dependency versions aur packaged runtime licenses bhi deta hai. macOS bundle unsigned hai; notarization/codesigning aur Windows signing is source build mein configured nahi.

## Verification

```bash
python -m pip install -r requirements-dev.txt
QT_QPA_PLATFORM=offscreen python -m pytest -q  # Windows par env variable alag set karein
python snapshot_pro.py --smoke-test
```

Is delivery ke actual checks aur platform limitations `BUILD_VERIFICATION.md` mein hain. Repository audit aur fixes `REPOSITORY_ANALYSIS.md` mein hain.
