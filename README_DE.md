# SchnuBbys Repack

Grafische Oberfläche (Tkinter) für praktisch jedes Verwaltungsmenü – Läuft ohne
zusätzliche Abhängigkeiten, nur mit der Python-Standardbibliothek.

## Voraussetzungen

- Python 3.10 oder neuer
- Tkinter (bei den meisten Python-Installationen unter Windows bereits
  enthalten)

Keine externen Pakete nötig – es werden ausschließlich Module aus der
Standardbibliothek verwendet (`tkinter`, `urllib`, `threading`, `queue`, ...).

## Verwendung

```bash
python menu_ui.py
```

Im Fenster links einen Hauptpunkt wählen (Run / Sources / Misc), rechts
öffnen sich die zugehörigen Unterpunkte. Klick auf eine Karte mit `›` führt
in ein Untermenü, eine Karte mit `▸` führt eine Aktion aus. Über die
Pfadleiste oder die "Zurück"-Karte geht es wieder eine Ebene nach oben.
Laufende Vorgänge lassen sich über den Button "Abbrechen" unterhalb der
Fortschrittsanzeige stoppen.

## Aufbau

```
menu_ui.py
├── Ui / Cancelled        Brücke zwischen Hintergrund-Thread und Oberfläche
├── run_steps / simulate_download / download_with_progress
│                         Gemeinsame Bausteine für die Aktionen
├── run_* / source_* / install_* / misc_* / logs_* / net_* / disk_*
│                         Die eigentlichen Menüaktionen
├── MENU                  Menüstruktur als verschachtelte Tupel
└── SubItem / App         Tkinter-Oberfläche (Sidebar, Detailblock, Footer)
```

Die Menüstruktur (`MENU`) ist eine verschachtelte Tupel-Datenstruktur:
Jeder Eintrag besteht aus `(Name, Beschreibung, Ziel)`. Ist `Ziel` eine
Funktion, wird sie beim Anklicken ausgeführt; ist `Ziel` selbst wieder eine
Liste von Einträgen, öffnet sich ein Untermenü. Neue Menüpunkte oder
Aktionen lassen sich dadurch einfach ergänzen, ohne den Rest der Oberfläche
anzufassen.
