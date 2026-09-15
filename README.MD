# SchnuBbys Repack

Graphical interface (Tkinter) for a server management menu – built for
running a CMaNGOS WoW server (Classic / TBC / WotLK). Runs without any
extra dependencies, using only the Python standard library.

## Features

- **Run** – start, stop, restart the server, check status, review logs
  (view, filter, load, archive)
- **Sources** – download server source code from GitHub (Classic, TBC,
  WotLK)
- **Misc** – download a file via URL, clear cache, network/disk tools,
  progress demo, program info
- Arbitrarily deep, nestable submenus with a breadcrumb bar and back
  navigation
- Actions run in a background thread so the interface stays responsive
  during long-running operations (e.g. downloads)
- Progress display with speed, remaining time, and a log area; running
  tasks can be cancelled
- Real downloads with a progress bar (including `.part` files, so an
  incomplete download is never mistaken for a finished one)

## Requirements

- Python 3.10 or newer
- Tkinter (included in most Python installations on Windows)

No external packages required – only standard library modules are used
(`tkinter`, `urllib`, `threading`, `queue`, ...).

## Usage

```bash
python menu_ui.py
```

In the window, pick a main entry on the left (Run / Sources / Misc); the
matching subitems open on the right. Clicking a card with `›` opens a
submenu, a card with `▸` runs an action. Use the breadcrumb bar or the
"Back" card to go up one level. A running task can be stopped with the
"Cancel" button below the progress display.

## Structure

```
menu_ui.py
├── Ui / Cancelled        Bridge between the background thread and the UI
├── run_steps / simulate_download / download_with_progress
│                         Shared building blocks for the actions
├── run_* / source_* / install_* / misc_* / logs_* / net_* / disk_*
│                         The actual menu actions
├── MENU                  Menu structure as nested tuples
└── SubItem / App         Tkinter interface (sidebar, detail panel, footer)
```

The menu structure (`MENU`) is a nested tuple data structure: each entry
consists of `(name, description, target)`. If `target` is a function, it
runs when clicked; if `target` is itself a list of entries, a submenu
opens instead. New menu items or actions can be added easily without
touching the rest of the interface.

## Note

Some actions (e.g. server start/stop, plugin installation, network
checks) are currently simulated (for demo purposes) and don't run any
real system commands. The downloads under **Sources** and **Misc →
Download**, however, are real HTTP downloads.
