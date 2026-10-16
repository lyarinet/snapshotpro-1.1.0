# SnapShot Pro 1.1.0 — verification record

Date: 2026-10-16. Baseline repository: `3924280ac571a04af1b94a529f082559e90a644a`.

## Verified in this delivery

| Check | Result |
| --- | --- |
| Python compile checks | Passed for application, core, native bridge, installer and builder |
| Automated regression suite | **28 passed**; latest full run 1.04 seconds |
| Local OCR using real Tesseract | Passed, text and numeric output verified |
| Linux standalone executable | PyInstaller build succeeded; `--version`, offscreen `--smoke-test`, and real X11 `--smoke-test` passed |
| X11 desktop capture at 1280 × 800 | Passed, captured pixel colors match the real test window |
| Mouse drag to region selection | Passed, selection and crop dimensions verified |
| Mouse-drawn solid redaction export | Passed, exported pixels verified black in the requested area |
| Real global hotkey under X11 | Passed with pynput F8 trigger, not a local window shortcut |
| Duplicate launch/capture debounce | Passed |
| Quick-save, overlay cleanup and next capture | Passed |
| Image annotation editor | Open/Paste source pixels preserved in regression suite |
| PNG, JPEG, WebP | Files encoded and reopened successfully |
| HiDPI / negative-origin calculations | Synthetic 2×-DPR and negative-screen-coordinate regression tests passed |
| Scrolling | Large overlap, odd offsets, duplicate frames, blank margins and text content verified |
| Windows RegisterHotKey logic | API-mocked registration, MOD_NOREPEAT, conflict reporting and unregister test passed |

Tests cover every annotation renderer, empty-selection guards, small-screen toolbar bounds, independent/different-width multi-snips, step undo/redo, settings cancel/reset, duplicate hotkeys and asynchronous OCR responsiveness.

## Measured performance — environment-specific

Environment: Ubuntu 24.04, x86_64, Python 3.12.14, PyQt6 6.11.0 / Qt 6.11.2. This is a development container, not a physical Windows PC.

- Headless Qt main-panel idle RSS: **56.4 MiB**. Global hotkeys disabled for this measurement.
- Main panel creation and first paint after Python imports: **28.2 ms**. This is not a whole-process cold-start benchmark.
- Idle CPU time over a 2-second sample: **0.0065 seconds**.
- X11 desktop grab median: **4.15 ms**, 12 samples at 1280 × 800, no capture delay included.
- Native integration-test process RSS after captures: **84.0 MiB**, including the synthetic desktop/test window, screenshots and the active hotkey bridge.
- Neither Pillow nor MSS was imported during idle panel startup. Tesseract is launched only for OCR.

Measurements are observations of this run, not guaranteed hardware targets. Larger screens, many pins and long images increase memory.

## Build and dependency separation

Runtime uses PyQt6, MSS and Pillow; pynput is used outside Windows. OCR invokes an optional installed Tesseract executable. PyInstaller is a build dependency only. Folder bundles are the default for startup without extracting a second runtime. Linux binaries are stripped and ZIP entries preserve shared-library symlinks. The verified x86_64 portable archive is approximately 62.8 MiB; the installed folder is approximately 164 MiB. Windows/macOS sizes have not been measured.

The archive includes all required Python/Qt components. Linux still uses system graphics drivers, X11 and compatible glibc; the build target here is Ubuntu 24.04 x86_64. On older Linux releases, rebuild on the oldest release you intend to support.

## Not verified here

- Native Windows compilation, installer launch, real PrintScreen conflicts and Win32 hover snapping.
- macOS .app build, Accessibility/Screen Recording prompts, signing and notarization.
- Physical multi-monitor and mixed-DPI hardware. Coordinate and export paths have synthetic coverage only.
- Wayland portals, touch/stylus input and platform-specific clipboard persistence after process exit.
- Remote GitHub Actions execution or repository publication. The workflow is included but has not been run remotely.

Use the included Actions matrix or native build scripts for Windows/macOS binaries. A Linux PyInstaller build cannot be renamed into a Windows EXE.
