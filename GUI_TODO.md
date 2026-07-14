# SIO2SD GUI TODO

## V1
- [x] Start/stop server from a desktop window.
- [x] Select SD base directory and show the effective `Atari` card root.
- [x] Configure SIO2SD ID, TCP port, read-only mode, and verbose logging.
- [x] Add repeatable EXE packaging for the GUI.
- [x] Add a project icon used by the GUI window, taskbar, and packaged EXE.
- [x] Read and update original `SIO2SD.CFG` drive mappings in the SD card root.
- [x] Show D1:-D15: drive mappings in a table.
- [x] Mount a file into the selected drive.
- [x] Mount an empty in-memory disk into the selected drive.
- [x] Unmount the selected drive.
- [x] Show user-facing log messages.
- [x] Keep D1: visually identical to other drive slots.
- [x] Automatically refresh after remote image mount/unmount.
- [x] Split the window into tabs: SD Card, Drives, Server, Log.
- [x] Move the SD directory selector and card file browser to the SD Card tab.
- [x] Add red X / green check icons to the Altirra checklist.
- [x] Add a full-window status bar with SIOACT/SDACT/ERROR LEDs.
- [x] Move the Mini LCD button to the full-window status bar.
- [x] Add CFG selector mode that boots `SIO2SD.XEX` on cold reset.
- [x] Add server auto-start setting.
- [x] Remember last GUI mode: full or mini.
- [ ] Test manually with Altirra connected to the GUI-started server.

## Later
- [x] Add a card file browser with filtering.
- [x] Replace drag-and-drop with a mini LCD-style SIO2SD control panel.
- [x] Hide the full window when mini LCD mode is enabled.
- [x] Make the mini LCD display look closer to a 2x16 hardware LCD.
- [x] Render the mini LCD as a dot-matrix character display.
- [x] Add SIOACT/SDACT/ERROR LEDs to the mini LCD panel.
- [x] Match the mini LCD text layout to the original drive/path style.
- [x] Replace the mini LCD `FULL` button with a persisted `TOP ON`/`TOP OFF` toggle.
- [x] Persist last used directory and GUI settings.
- [x] Split the monolithic GUI source into smaller functional modules.
- [x] Add a small Altirra setup checklist without drive-specific warnings.

## Original SIO2SD config parity

Sources reviewed:
- `Configurator_35/Opis SETUP i K1-K4 v3.1.pdf`
- `Configurator_35/OPIS Configurator v35.pdf`
- `Configurator_35/Sio2SD_CFG_PJ.HLP`
- Current server support in `altirra/sio2sd_server.py` for `$12/$13` config,
  `$14/$15` virtual mapping, `SIO2SD.CFG`, and D1:-D15: mappings.

Firmware SETUP options:
- [x] Provide SIO2SD device number selection in GUI.
- [x] Provide global read-only mode as a safe equivalent of write protection.
- [x] Boot the configurator/selector from `SIO2SD.XEX` or bundled fallback.
- [x] Decode known fields from the 16-byte firmware config block (`$12`)
      while preserving unknown bytes.
- [x] Move original SIO2SD config options to a dedicated first `SIO2SD` tab.
- [x] Persist edited known config fields in GUI settings and apply them to
      the runtime config path used by `$13`.
- [x] Add UI for Ultra Speed hIndex / drive transmission speed.
- [x] Implement TopDrive-style high-speed D: command-frame enable/disable.
- [x] Document Shift-at-power-on loader behavior as hardware-only.
- [x] Add UI or compatibility notes for LED indication mode.
- [x] Add UI for ATR write-protection config bit, separate from global GUI
      read-only mode.
- [x] Add exact ATR write-protection behavior based on original config bit.
- [x] Add UI or compatibility notes for keyboard repeat delay/rate; likely
      hardware-only unless mini-panel key repeat is expanded.
- [x] Add an explicit "SIO2SD disabled / invisible to Atari" runtime toggle
      matching Shift+K4 disable mode.
- [x] Document firmware update from `SIO2SD.BIN` as out of scope for emulator,
      unless a real-firmware workflow is later added.

Virtual drives and mapping:
- [x] Read/write original D1:-D15: slots from `SIO2SD.CFG`.
- [x] Preserve and save the 15-byte virtual mapping table (`$14/$15`).
- [x] Read/write V1:-V99 virtual slots from `SIO2SD.CFG` and honor mapped
      D1:-D15: sector access through `$14/$15`.
- [x] Expose a Mapping view that shows whether each D1:-D15: slot maps to
      itself, another drive, a virtual drive, or the configurator (`d/v/x`).
- [x] Expose V1:-V99 virtual drive slots in the GUI and in `SIO2SD.CFG`
      compatibility storage where possible.
- [x] Support mount-to-drive while either clearing mapping or preserving
      mapping, matching normal vs Ctrl mount in the configurator.
- [x] Support unmapping/off actions for D1:-D15: and virtual slots.
- [x] Add swap mode for exchanging two drive/virtual slot assignments.
- [ ] Add undo for the last mapping/mount change.
- [ ] Add "test all mounted paths" cleanup for missing files.

Configurator-style file browser:
- [x] Browse the card directory and mount selected files to a chosen drive.
- [ ] Add 10 editable filename masks, with mask 0 fixed to `*.*`.
- [ ] Add pause/resume/background read behavior only if large-card browsing
      still needs it in the desktop GUI.
- [ ] Add whole-card search by current mask and "jump to containing folder".
- [ ] Add favorites / recently used list, including protected favorites and
      clearing unprotected recent entries.
- [ ] Add create directory, rename, and delete actions from the GUI browser.
- [ ] Rebuild ATR creation after filesystem format descriptions are available.
      The current creator is kept in code as experimental and hidden in the
      GUI.
- [ ] Add extended MyDOS VTOC for very large 256-byte-sector images if ATR
      creation returns.
- [ ] Add SDX filesystem generation for 256-byte-sector images if ATR creation
      returns and this is needed by real Atari-side workflows.
- [ ] Add "mount to D1 and cold start Atari" as a documented workflow if
      Altirra control becomes available.
- [ ] Add save/load for masks and favorites compatible with the original
      configurator where the file format can be identified.
