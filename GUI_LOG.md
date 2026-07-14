# SIO2SD GUI Log

## 2026-07-12
- Started GUI implementation for the Altirra SIO2SD server.
- Scope chosen for V1: tkinter desktop control panel over the existing server logic.
- Explicitly excluded any special D1: warning or special D1: visual treatment.
- Added `SIO2SDServerRuntime` for programmatic start/stop of the TCP server.
- Added `altirra/sio2sd_gui.py` with settings, drive table, mount/empty/unmount actions, and log output.
- Added `sio2sd_gui.bat` as a simple launcher.
- Verified Python syntax with `py_compile`.
- Verified basic runtime start/stop with a temporary SD directory.
- Verified GUI module import without starting the window loop.
- Split the GUI into tabs: SD Card and Server, Drives, Log.
- Added polling-based automatic drive table refresh for remote mount/unmount changes.
- Marked host-side mount/empty/unmount operations as SIO2SD drive-map changes.
- Re-ran syntax, GUI import, and runtime smoke checks after the tab/refresh changes.
- Added a card file browser with type filtering and text search.
- Added mounting from the browser into a selected D1:-D15: drive.
- Re-ran syntax, GUI import, and runtime smoke checks after adding the browser.
- Added local JSON persistence for GUI settings and window geometry.
- Re-ran syntax, GUI import, and runtime smoke checks after settings persistence.
- Added a neutral Altirra checklist for card root, device file, TCP server, and emulator connection.
- Re-ran syntax, GUI import, and runtime smoke checks after adding the checklist.
- Removed internal drag-and-drop after deciding it was not useful enough for the workflow.
- Added a mini LCD-style SIO2SD control panel with drive navigation and function buttons.
- Re-ran syntax, GUI import, and runtime smoke checks after replacing drag-and-drop with mini LCD.
- Added server auto-start and persisted GUI mode (`full`/`mini`).
- Mini LCD now hides the full window when enabled and provides a way back to the full window.
- Removed the inner SIO2SD label from mini LCD and restyled the display as a compact 2x16 LCD.
- When the saved GUI mode is mini, the full window is hidden before startup rendering.
- Split the former combined SD/server tab into separate `Karta SD` and `Server` tabs.
- Moved SD directory selection and card file browsing into the `Karta SD` tab.
- Added red X / green check status icons to the Altirra checklist.
- Reordered tabs to `Karta SD`, `Napedy`, `Server`, `Log`.
- Replaced the mini LCD `FULL` button with a functional `TOP ON`/`TOP OFF` toggle.
- Added frozen-app path handling so EXE settings and SD files live beside the executable.
- Added `sio2sd_gui.spec` and `build_exe.bat` for repeatable GUI EXE builds.
- Built `dist\SIO2SD-GUI.exe` with PyInstaller.
- Replaced the mini LCD text labels with a custom 2x16 dot-matrix renderer.
- Rebuilt `dist\SIO2SD-GUI.exe` after the dot-matrix LCD change.
- Enlarged the mini LCD canvas so all 16 characters fit and tightened dot spacing for readability.
- Rebuilt `dist\SIO2SD-GUI.exe` after the LCD sizing/spacing fix.
- Added mini panel LEDs matching SIO2SD front labels: `SIOACT`, `SDACT`, `ERROR`.
- Changed mini LCD text layout to show selected drive/file on line 1 and current card path on line 2.
- Rebuilt `dist\SIO2SD-GUI.exe` after adding mini panel LEDs and the original-style LCD layout.
- Added a full-window status bar with shared `SIOACT`, `SDACT`, and `ERROR` LEDs.
- Moved the `Mini LCD` button from the Server tab to the full-window status bar.
- Rebuilt `dist\SIO2SD-GUI.exe` after the full-window status bar change.
- Added conservative read/update support for original `SIO2SD.CFG` D1:-D15: mappings in the SD card root.
- Rebuilt `dist\SIO2SD-GUI.exe` after adding `SIO2SD.CFG` support.
- Added CFG selector mode: on cold reset it mounts `SIO2SD.XEX`/selector ATR as D1 without rewriting `SIO2SD.CFG`.
- Included `Sio2SDBootLoaderCfgTools.atr` in the GUI EXE bundle as selector fallback.
- Rebuilt `dist\SIO2SD-GUI.exe` with CFG selector support.
- Fixed XEX selector boot in the EXE by finding a valid `xexboot.bin` in source, bundle, or EXE-side runtime files.
- Rebuilt `dist\SIO2SD-GUI.exe` after the `xexboot.bin` lookup fix.
- Routed verbose SIO/device-server output to the GUI Log tab and made the `Log SIO` switch update a running server.
- Rebuilt `dist\SIO2SD-GUI.exe` after the verbose Log tab routing fix.
- Moved `Log SIO` to the Log tab and compacted repeated log messages with an `[xN]` prefix.
- Rebuilt `dist\SIO2SD-GUI.exe` after moving `Log SIO` and adding log compaction.
- Improved log compaction for interleaved verbose pairs such as repeated `Script event` and `SIO2SD` lines.
- Rebuilt `dist\SIO2SD-GUI.exe` after improving interleaved verbose log compaction.
- Added a `Wyczysc log` button on the Log tab.
- Hid raw verbose `Script event(...)` device-server lines from the GUI log.
- Reviewed original SIO2SD SETUP/configurator docs and added config parity TODOs.
- Added a GUI panel for known `$12/$13` SIO2SD config fields: hIndex,
  turbo hIndex, device ID, ATR write-protect bit, and raw config preview.
- Moved original SIO2SD config options to a dedicated first `SIO2SD` tab.
- Made the ATR write-protect config bit honor the ATR header write-protect flag
  during mount and live config updates.
- Made SIO2SD config control changes auto-apply to a running server and
  preserved explicitly read-only ATR mounts such as the CFG selector.
- Fixed Altirra reconnect handling so the V2 protocol handshake no longer
  triggers a cold reset or replaces D1: with the CFG selector.
- Added a `Widoczny dla Atari` SIO2SD tab toggle that makes the emulated
  device silent on both API and D1:-D15: SIO commands.
- Added SIO2SD tab notes for hardware-only SETUP options: Shift-at-power-on
  loader behavior, LED mode, key repeat, and firmware update.
- Implemented real TopDrive-style turbo handling for D1:-D15: high-speed
  command frames, with a live `TopDrive turbo` switch on the SIO2SD tab.
- Fixed high-speed command-frame reception in `sio2sd.atdevice` v1.8 by
  arming the next command frame before COMMAND is asserted. This avoids
  losing the first byte of fast API/TopDrive frames in Altirra.
- Reverted the unsafe `SDCDEV /U` `$CFED` forcing approach. `SDCDEV /H` now
  probes high-speed support with SIO2SD API commands using bit `$80`
  (`$9E`, then `$80`) and never jumps to `$CFED`. Rebuilt `SDCDEV.SYS` as
  v2.6 and copied it to the sample SD card folders.
- Fixed SIO2SD API high-speed response timing: commands `$72-$75` with bit
  `$80` now use cpb derived from SIO2SD `Turbo hIndex` (`$1F`; value `6`
  -> `26 cpb`) instead of the XF551 fallback `46 cpb`. The selected HS cpb
  is passed to `sio2sd.atdevice` via `txbuffer[599]`; XF551 D: commands
  still use `46 cpb`.
- Adjusted the `/H` negotiation sequence: `$9F` returns the Turbo hIndex byte
  at normal speed, and only later `$80`-tagged API commands switch to the
  negotiated high-speed timing.
- Split SIO2SD API HS timing from XF551 timing in `sio2sd.atdevice`: for
  `$72-$75` API commands with bit `$80`, ACK and COMPLETE are sent at normal
  speed and only the data frame uses the negotiated HS cpb. XF551 D: commands
  still send COMPLETE and data in HS.
- Added an advanced editor for the full 16-byte SIO2SD `$12/$13` config block
  on the `SIO2SD` tab. Known fields and raw byte fields stay synchronized, so
  newly identified original SIO2SD options can be tested without adding a
  dedicated control first.
- Added backend support for original `SIO2SD.CFG` V1:-V99 virtual slots and
  `$14/$15` mapping. D1:-D15: sector access now follows the mapping table, so
  a drive mapped to a virtual slot reads and writes the virtual slot's image.
- Added a `Mapowanie` column to the D1:-D15: GUI table. The table and mini LCD
  now show the effective mapped slot, so `D1 -> V1` displays the virtual slot's
  mounted image instead of the physical D1 slot.
- Added a `Sloty wirtualne V1:-V99` table on the `Napedy` tab. It shows every
  virtual slot with status, mounted file, disk type, sector count, and read-only
  state, and refreshes together with the D1:-D15: table.
- Added mount/unmount controls for V1:-V99 slots and a `Zachowaj mapowanie`
  switch for D1:-D15: actions. Normal D mounts clear the mapping back to the
  physical drive, while preserved mounts keep mappings such as `D1 -> V1`.
- Added explicit mapping controls in the GUI: `D -> V` maps the selected D slot
  to the selected V slot, and `D -> D` resets the selected D slot back to its
  physical drive. The server now exposes public mapping methods used by both
  GUI actions and tests.
- Added a defensive fallback for mapped D drives: if `D1 -> Vn` points to an
  empty virtual slot but physical D1 has a mounted disk, sector access uses the
  physical D1 instead of going silent. This protects existing Atari-side mounts
  from stale or accidental empty mappings.
- Fixed mapped-drive sector sizing: D: command frame lengths now use the
  effective mapped drive entry instead of the physical D slot. This fixes DD
  ATR images mapped through V slots, where status reported 256-byte sectors but
  reads could still be framed as 128-byte transfers.
- Reverted the experimental D: `$3F` Happy/Speedy-style ACK. SDX expects more
  than an ACK+COMPLETE/no-data response and can stop with `Device does not
  respond`; unknown `$3F` is back to the previous NAK behavior.
- Added slot swapping for D/V assignments. The server can exchange any two
  stored D/V slot entries without changing the D1:-D15: mapping table, and the
  GUI exposes `Zamien D/V` for the selected drive and virtual slot.
- Added persistent empty ATR creation. The GUI can create `NEWxxxx.ATR` files
  in the card root and mount them directly into the selected D or V slot; the
  backend writes a real 720-sector SD ATR file, so later sector writes persist
  on disk.
- Added disk format selection for new persistent ATR files: SD 90 KB
  (720 x 128), ED 130 KB (1040 x 128), and DD 180 KB (720 x 256).
- Extended new ATR creation with custom geometry and filesystem selection.
  `Czysty ATR` supports arbitrary 128/256-byte sector counts, while `SDX`
  creates ready blank SD/ED images from SDX templates.
- Added filesystem generation for new persistent ATR files. The creator can
  now prepare DOS 2.x SD images, MyDOS images for supported geometries, and
  SDX images with an optional VOLUME label. SDX can also generate larger
  128-byte-sector images with an initial `MAIN` directory instead of relying on
  Atari-side formatting.
- Hid the new ATR creator from the normal GUI because filesystem generation is
  still experimental and should be rebuilt after the disk format descriptions
  are available. Existing ATR mounting and writing behavior is unchanged.
- Added a dedicated SIO2SD GUI icon. The app now loads the icon in Tk, sets a
  Windows AppUserModelID for taskbar grouping, includes PNG/ICO assets in the
  PyInstaller bundle, and rebuilds `dist\SIO2SD-GUI.exe` with the ICO embedded.
- Split `altirra/sio2sd_gui.py` into smaller functional modules under
  `altirra/sio2sd_gui_parts`: actions, browser, config, logging, mini panel,
  UI layout, constants, and assets. The main file now keeps startup wiring and
  the `SIO2SDGui` class composition.
- Gated experimental persistent ATR creator checks in `tools/test_devproto.py`
  behind `SIO2SD_EXPERIMENTAL_ATR_TESTS=1`, matching the hidden GUI state of
  that feature.
- Fixed the post-split GUI startup failure caused by missing `tk`/`ttk`
  imports in the config/checklist mixin, rebuilt `dist\SIO2SD-GUI.exe`, and
  verified that the EXE starts without immediately crashing.
- Fixed missing imports in the browser/log mixins after the GUI split. The
  drive refresh now fills all 15 D: rows and 99 V: rows again, including after
  auto-starting the server; rebuilt and smoke-tested `dist\SIO2SD-GUI.exe`.
- Reworked the GUI icon into a more explicit SIO2SD mark: large `SIO`, a
  highlighted `2`, and an SD card. Regenerated PNG/ICO assets and rebuilt
  `dist\SIO2SD-GUI.exe` with the updated taskbar icon.
- Fixed mini GUI LCD/LED rendering after the GUI split. Missing imports in the
  mini/config mixins could break `_update_mini_lcd()` during activity handling,
  which also stopped full-window status LED pulses. Verified mini LCD drawing,
  mini/status LED activity, protocol tests, and rebuilt `dist\SIO2SD-GUI.exe`.
- Added original-style transient SIO command display on the mini LCD. Accepted
  SIO frames now emit a `SIOCMD` activity with a short two-line description
  such as drive command/status and sector/length; the mini LCD shows it during
  transmission and returns to the normal drive/path display after 5 seconds of
  inactivity.
