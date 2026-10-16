# SnapShot Pro — repository analysis aur implementation

Baseline: `lyarinet/snapshot_pro`, branch `main`, commit `3924280ac571a04af1b94a529f082559e90a644a`.

## Repository ka asal haal

Yeh screenshot desktop application thi: 2,578-line PyQt6 file, MSS capture, Pillow stitching, pynput hotkeys aur optional pytesseract. Lightshot-style overlay aur zyada tar advertised features ke initial implementations maujood thay. Kaam ko naya browser demo banane ke bajaye isi native desktop project mein complete/repair kiya gaya.

## Aham findings aur resulting behavior

| Baseline issue | Delivered behavior |
| --- | --- |
| Import/startup par automatic pip installs | Runtime import aur app launch network/package changes nahi karte; explicit venv setup alag hai |
| OCR aur stitching GUI thread par | QImage-based worker jobs; interface responsive rehta hai |
| Full desktop ki duplicate allocation aur export par full desktop repaint | Implicitly shared source; sirf selected native-pixel crop par paint |
| Image conversion ke liye PNG encode/decode round trips | Direct raw pixel conversion for image processing |
| Scroll match absolute-error bias, every-other-row search, 500-pixel cap | Textured anchor, every-row search, full overlap RMS verification, duplicate skipping |
| Independent multi-snips ko bhi overlap-trim karna; mismatched widths | Snips explicit concatenate hote hain, pixels preserve aur widths pad hoti hain |
| README mein automatic scrolling, code mein manual frames only | User-started automatic scroll plus manual capture, stop on unchanged frames, cancellation aur pixel budget |
| Scrolling crop local coordinates se global screenshot par lagta tha | Overlay origin + logical-to-physical crop mapping; negative screen origins supported |
| HiDPI capture/output coordinate mismatch | Per-monitor Qt composition, shared canvas DPR aur native-resolution crop/annotation export |
| Fixed long horizontal bars screen se bahar | Compact grids, small-screen bounds checks aur monitor-aware placement |
| Enter without selection full desktop copy kar sakta tha | Empty selection returns no image; Copy/Save/Pin/OCR guarded |
| Destroyed overlay ka Python reference stale rehta tha | Lifecycle cleanup; repeated capture, debounced launch aur compositor delay |
| Save result unchecked, timestamp collisions | Atomic checked writes, microseconds + unique suffix; failure par editor remains usable |
| Ctrl+M button state nahi badalta tha | Keyboard aur button multi-snip state synchronized |
| Undo/redo numbered steps aur selection reset state | Step counter recomputed; fresh selection clears redo/steps |
| Settings Reset persisted even after Cancel | Reset form-only; validated Save commits changes |
| Windows key listener plus local shortcut duplicate trigger | Native RegisterHotKey/MOD_NOREPEAT; conflicting registration reported |
| Tray na ho to app hidden/unreachable | Main panel accessible, unavailable tray action disabled |
| `start.bat` missing `launcher.py`; `Run_Setup.bat` unrelated GitHub script launch karta tha | Correct source launcher aur isolated runtime setup |
| Windows `"py -3"` invocation aur absolute .spec paths | Executable paths separated from arguments, relative source specs, checked build exit codes |
| `--all` real cross-build nahi karta tha | Host-only validation plus Windows/macOS/Linux Actions matrix |
| One-file default startup extraction | Default folder bundle; one-file explicitly optional |

## Added usable features

Solid color redaction; Open/Paste image annotation editor; latest 12 saved files; OCR language selector; 3/5/10-second capture delay; pinned-image opacity/copy/reset zoom; single-instance guard; standard per-user Inno Setup packaging; runtime/build/dev dependency separation; runtime license collection and artifact checksums.

## Lightweight design

Core application mein Chromium, WebEngine, database server, cloud backend, model weights ya tracking SDK shamil nahi. MSS/Pillow capture/processing actions par load hote hain. Tesseract sirf OCR action par separate process mein chalta hai. Windows global keys OS messages se aate hain; background screen polling loop nahi. Pins aur open dialogs user close kare to references release hote hain. Scroll/multi-snip combined images ka 48MP guard hai.

Native Qt aur Python runtime ki apni size hai: yeh single-digit-MB Win32 executable hone ka claim nahi karta. Actual measured Linux size/memory `BUILD_VERIFICATION.md` mein di gayi hai. Build archive symlinks preserve karta hai, jis se repeated shared libraries ZIP mein duplicate nahi hotin.

## Jo OS-dependent hai

Smart individual-window snapping Win32 implementation hai; Linux/macOS par monitor fallback hai. Linux Wayland portal support, cloud upload/link sharing, recording/video editor aur automatic updater implement nahi kiye gaye. Yeh original screenshot scope ka hissa nahi thay. Physical mixed-DPI monitors, native Windows installer/hotkeys aur macOS permissions/signing ko un platforms par validate karna baqi hai.
