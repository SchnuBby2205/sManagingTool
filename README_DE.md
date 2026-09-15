# SchnuBbys Repack

Grafische Oberfläche (Tkinter) für ein Server-Verwaltungsmenü – gedacht für den
Betrieb eines CMaNGOS-WoW-Servers (Classic / TBC / WotLK). Läuft ohne
zusätzliche Abhängigkeiten, nur mit der Python-Standardbibliothek.

## Funktionen

- **Run** – Server starten, stoppen, neu starten, Status abfragen, Logs
  auswerten (anzeigen, filtern, einlesen, archivieren)
- **Sources** – Server-Quellcode von GitHub laden (Classic, TBC, WotLK)
- **Misc** – Datei-Download per URL, Cache leeren, Netzwerk-/Speicher-Tools,
  Fortschritts-Demo, Programminfo
- Beliebig tief verschachtelbare Untermenüs mit Pfadleiste ("Breadcrumbs") und
  Zurück-Navigation
- Aktionen laufen in einem Hintergrund-Thread, damit die Oberfläche während
  langer Vorgänge (z. B. Downloads) reaktionsfähig bleibt
- Fortschrittsanzeige mit Geschwindigkeit, verbleibender Zeit und
  Protokollbereich; laufende Vorgänge lassen sich abbrechen
- Echte Downloads mit Fortschrittsbalken (inkl. `.part`-Dateien, damit
  unvollständige Downloads nicht als fertig gelten)

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

## Hinweis

Ein Teil der Aktionen (z. B. Server-Start/-Stopp, Plugin-Installation,
Netzwerk-Checks) ist aktuell simuliert (Demo-Zwecke) und führt keine echten
Systembefehle aus. Die Downloads unter **Sources** und **Misc → Download**
sind hingegen echte HTTP-Downloads.
