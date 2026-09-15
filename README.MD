# SchnuBbys sManagingTool

Graphical interface (Tkinter) for basicaly any management menu – Runs without any
extra dependencies, using only the Python standard library.

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
