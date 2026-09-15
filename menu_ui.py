#!/usr/bin/env python3
"""Grafische Variante des Menüs aus menu.py (Tkinter, Standardbibliothek).

Start:  python menu_ui.py

Aufbau:
    links   Hauptpunkte (Run / Install / Misc)
    rechts  Detailblock mit den Unterpunkten des gewählten Hauptpunktes;
            Unterpunkte können selbst wieder Untermenüs sein (beliebig
            tief), Pfadleiste und Zurück-Karte führen wieder heraus
    unten   Fortschrittsbox und Protokoll

Aktionen laufen in einem Hintergrund-Thread, damit das Fenster während
langer Vorgänge (z. B. Downloads) bedienbar bleibt. Alle Zugriffe auf die
Oberfläche gehen dabei über die Klasse ``Ui``, die sie in den Hauptthread
zurückreicht.
"""

from __future__ import annotations

import os
import queue
import sys
import threading
import time
import tkinter as tk
import urllib.error
import urllib.parse
import urllib.request
from tkinter import filedialog, messagebox, simpledialog, ttk

APP_TITLE = "SchnuBbys Repack"


# --------------------------------------------------------------------------
# Farben / Abmessungen
# --------------------------------------------------------------------------

class T:
    """Farbpalette (dunkles Thema, angelehnt an die Konsolenversion)."""

    BG = "#1b1e24"          # Fensterhintergrund
    SIDEBAR = "#161920"     # linke Spalte
    PANEL = "#22262f"       # Detailblock
    CARD = "#2a2f3a"        # Unterpunkt-Karte
    CARD_HOVER = "#353c4a"
    LINE = "#333947"        # Trennlinien
    FG = "#e8eaed"          # Haupttext
    DIM = "#98a0ae"         # Nebentext
    ACCENT = "#4fc3f7"      # Cyan wie im Terminal
    GREEN = "#8bc34a"
    YELLOW = "#ffb74d"
    RED = "#ef5350"


FONT = ("Segoe UI", 10)
FONT_BOLD = ("Segoe UI", 10, "bold")
FONT_TITLE = ("Segoe UI", 15, "bold")
FONT_SMALL = ("Segoe UI", 9)
FONT_MONO = ("Consolas", 9)


# --------------------------------------------------------------------------
# Hilfsfunktionen (identisch zur Konsolenversion, hier bewusst dupliziert,
# damit menu_ui.py ohne menu.py lauffähig bleibt)
# --------------------------------------------------------------------------

def fmt_bytes(n: float) -> str:
    """1536 -> '1.5 KB'."""
    n = float(n)
    for unit in ("B", "KB", "MB", "GB"):
        if abs(n) < 1024 or unit == "GB":
            return f"{n:.0f} {unit}" if unit == "B" else f"{n:.1f} {unit}"
        n /= 1024.0
    return f"{n:.1f} TB"


def fmt_time(seconds: float) -> str:
    """90 -> '1m 30s'."""
    seconds = int(max(0, seconds))
    if seconds < 60:
        return f"{seconds}s"
    if seconds < 3600:
        return f"{seconds // 60}m {seconds % 60:02d}s"
    return f"{seconds // 3600}h {(seconds % 3600) // 60:02d}m"


def resolve_dest(dest: str, url: str, response=None) -> str:
    """Bestimmt den endgültigen Dateipfad.

    ``dest`` darf ein Verzeichnis sein - dann wird der Dateiname aus dem
    Header ``Content-Disposition`` bzw. aus der URL abgeleitet. Fehlende
    Ordner werden angelegt. (``open()`` auf ein Verzeichnis führt sonst zu
    ``[Errno 13] Permission denied``.)
    """
    looks_like_dir = dest.endswith(("/", "\\")) or os.path.isdir(dest)
    dest = os.path.abspath(os.path.expanduser(dest))
    if looks_like_dir:
        name = response.headers.get_filename() if response is not None else None
        if not name:
            name = os.path.basename(urllib.parse.urlsplit(url).path)
        dest = os.path.join(dest, os.path.basename(name) or "download.bin")
    os.makedirs(os.path.dirname(dest) or ".", exist_ok=True)
    return dest


# --------------------------------------------------------------------------
# Brücke zwischen Arbeits-Thread und Oberfläche
# --------------------------------------------------------------------------

class Cancelled(Exception):
    """Wird ausgelöst, wenn der Benutzer den laufenden Vorgang abbricht."""


class Ui:
    """Alles, was eine Aktion mit der Oberfläche machen darf.

    Die Methoden sind aus dem Arbeits-Thread heraus aufrufbar: Ausgaben
    werden per ``after()`` in den Hauptthread geschoben, Rückfragen warten
    dort auf die Antwort des Benutzers.
    """

    def __init__(self, app: "App"):
        self.app = app
        self.cancel = threading.Event()
        self._last_progress = 0.0

    # -- Zustand -------------------------------------------------------

    @property
    def cancelled(self) -> bool:
        return self.cancel.is_set()

    def check_cancel(self) -> None:
        """Bricht die Aktion ab, wenn der Benutzer auf 'Abbrechen' geklickt hat."""
        if self.cancel.is_set():
            raise Cancelled()

    def sleep(self, seconds: float) -> None:
        """Wie time.sleep, reagiert aber sofort auf einen Abbruch."""
        if self.cancel.wait(seconds):
            raise Cancelled()

    # -- Ausgaben (asynchron) ------------------------------------------

    def log(self, text: str, kind: str = "info") -> None:
        self._post(self.app.append_log, text, kind)

    def info(self, text: str) -> None:
        self.log(text, "ok")

    def error(self, text: str) -> None:
        self.log(text, "err")

    def progress(self, current=None, total=None, status=None,
                 unit="B", title=None, force=False) -> None:
        """Aktualisiert die Fortschrittsbox (gedrosselt auf ca. 12 Bilder/s)."""
        now = time.monotonic()
        if not force and status is None and now - self._last_progress < 0.08:
            return
        self._last_progress = now
        self._post(self.app.set_progress, current, total, status, unit, title)

    def progress_start(self, title: str, total=None, unit="B", status="") -> None:
        self._post(self.app.start_progress, title, total, unit, status)

    def progress_done(self, status: str = "", ok: bool = True) -> None:
        self._post(self.app.finish_progress, status, ok)

    # -- Rückfragen (synchron) ----------------------------------------

    def confirm(self, message: str, title: str = "Achtung") -> bool:
        return bool(self._call(messagebox.askyesno, title, message,
                               icon="warning", parent=self.app.root))

    def warn(self, message: str, title: str = "Warnung") -> None:
        self.log(message.replace("\n", " "), "warn")
        self._call(messagebox.showwarning, title, message, parent=self.app.root)

    def ask_string(self, prompt: str, title: str = "Eingabe", initial: str = ""):
        return self._call(simpledialog.askstring, title, prompt,
                          initialvalue=initial, parent=self.app.root)

    def ask_directory(self, title: str = "Zielordner wählen"):
        return self._call(filedialog.askdirectory, title=title,
                          parent=self.app.root)

    # -- intern --------------------------------------------------------

    def _post(self, fn, *args) -> None:
        """Reicht ``fn`` an den Hauptthread weiter, ohne auf das Ergebnis zu warten.

        Tkinter darf nur aus dem Hauptthread bedient werden - auch ``after()``
        ist aus einem Fremd-Thread nicht zuverlaessig (``RuntimeError: main
        thread is not in main loop``). Deshalb wandern alle Aufrufe ueber eine
        Queue, die ``App.pump()`` im Hauptthread abarbeitet.
        """
        if not self.app.closing:
            self.app.jobs.put((fn, args))

    def _call(self, fn, *args, **kwargs):
        """Ruft ``fn`` im Hauptthread auf und wartet auf das Ergebnis."""
        result: dict = {}
        done = threading.Event()

        def runner():
            try:
                result["value"] = fn(*args, **kwargs)
            except BaseException as exc:      # noqa: BLE001 - wird weitergereicht
                result["error"] = exc
            finally:
                done.set()

        self._post(runner)
        while not done.wait(0.1):
            if self.app.closing:              # Fenster zu -> Aktion beenden
                raise Cancelled()
        if "error" in result:
            raise result["error"]
        return result.get("value")


# --------------------------------------------------------------------------
# Gemeinsame Bausteine für die Aktionen
# --------------------------------------------------------------------------

def run_steps(ui: Ui, title: str, steps, unit: str = "Schritt") -> None:
    """Führt ``(beschreibung, dauer)``-Schritte mit Fortschrittsanzeige aus."""
    ui.progress_start(title, total=len(steps), unit=unit)
    for index, (text, duration) in enumerate(steps, start=1):
        ui.log(text)
        ui.progress(index - 1, len(steps), text, unit, force=True)
        end = time.monotonic() + duration
        while time.monotonic() < end:
            ui.sleep(0.05)
        ui.progress(index, len(steps), text, unit, force=True)
    ui.progress_done("Abgeschlossen.")


def simulate_download(ui: Ui, title: str, name: str, size: int, rate: int) -> None:
    """Tut so, als würde eine Datei geladen - für die Demo-Aktionen."""
    ui.progress_start(title, total=size, unit="B", status=name)
    loaded = 0
    while loaded < size:
        ui.sleep(0.04)
        loaded = min(size, loaded + rate)
        ui.progress(loaded, size, name)
    ui.progress_done("Download abgeschlossen.")


def parse_size(raw) -> "int | None":
    """Liest eine Groessenangabe aus einem Header.

    Robuster als ``int(raw)``: manche Proxys und CDNs senden den Header
    doppelt ("123, 123") oder mit Leerzeichen. Genau dann schlug die
    Erkennung frueher fehl und der Balken lief ohne Prozentanzeige.
    """
    text = (raw or "").split(",")[0].strip()
    try:
        size = int(text)
    except ValueError:
        return None
    return size if size > 0 else None


def probe_size(url: str) -> "int | None":
    """Holt die Dateigroesse nach, wenn die Antwort kein Content-Length hat.

    Fragt nur das erste Byte an: Server mit Range-Unterstuetzung antworten
    mit ``Content-Range: bytes 0-0/<groesse>``. Liefert None, wenn auch das
    nichts ergibt (dann bleibt der Balken zwangslaeufig unbestimmt).
    """
    request = urllib.request.Request(
        url, headers={"User-Agent": "menu_ui.py", "Range": "bytes=0-0"})
    try:
        with urllib.request.urlopen(request, timeout=15) as response:
            rng = response.headers.get("Content-Range") or ""
            if "/" in rng:
                return parse_size(rng.rsplit("/", 1)[1])
            return parse_size(response.headers.get("Content-Length"))
    except (urllib.error.URLError, OSError, ValueError):
        return None


def download_with_progress(ui: Ui, url: str, dest: str) -> bool:
    """Lädt ``url`` nach ``dest`` (Datei oder Zielordner) mit Fortschritt.

    Geschrieben wird zuerst in ``<datei>.part``; erst ein vollständiger
    Download wird an den endgültigen Namen umbenannt.
    """
    request = urllib.request.Request(url, headers={"User-Agent": "menu_ui.py"})
    part = None
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            dest = resolve_dest(dest, url, response)
            part = dest + ".part"
            total = parse_size(response.headers.get("Content-Length"))
            if total is None:                 # Server schweigt -> nachfragen
                total = probe_size(url)
            if total:
                ui.log(f"Gesamtgröße laut Server: {fmt_bytes(total)}")
            else:
                ui.log("Server meldet keine Gesamtgröße - der Balken läuft "
                       "ohne Prozentanzeige.", "warn")
            name = os.path.basename(dest)
            ui.progress_start(f"Download - {name}", total=total, unit="B",
                              status=url)
            loaded = 0
            with open(part, "wb") as handle:
                while True:
                    ui.check_cancel()
                    chunk = response.read(64 * 1024)
                    if not chunk:
                        break
                    handle.write(chunk)
                    loaded += len(chunk)
                    ui.progress(loaded, total, unit="B")
            # erst nach dem Schließen umbenennen - Windows sperrt offene
            # Dateien und wirft sonst PermissionError
            os.replace(part, dest)
            part = None
            ui.progress(loaded, total or loaded, unit="B", force=True)
            ui.progress_done(f"Gespeichert unter {dest}")
    except Cancelled:
        _cleanup(part)
        ui.progress_done("Abgebrochen.", ok=False)
        raise
    except PermissionError as exc:
        _cleanup(part)
        ui.progress_done("Fehlgeschlagen.", ok=False)
        ui.warn(f"Kein Schreibzugriff auf:\n{exc.filename or dest}\n\n"
                "Mögliche Ursachen: die Datei ist geöffnet oder "
                "schreibgeschützt, oder der Ordner gehört dem System.\n"
                "Bitte ein anderes Ziel wählen.", title="Fehler")
        return False
    except (urllib.error.URLError, OSError, ValueError) as exc:
        _cleanup(part)
        ui.progress_done("Fehlgeschlagen.", ok=False)
        ui.warn(f"Download fehlgeschlagen:\n{exc}", title="Fehler")
        return False
    return True


def _cleanup(path) -> None:
    """Entfernt eine unvollständige .part-Datei (Fehler dabei ignorieren)."""
    if path:
        try:
            os.remove(path)
        except OSError:
            pass


# --------------------------------------------------------------------------
# Aktionen - Run
# --------------------------------------------------------------------------

def run_start(ui: Ui) -> None:
    run_steps(ui, "Server startet", [
        ("Konfiguration lesen", 0.6),
        ("Ports prüfen", 0.5),
        ("Welt laden", 1.2),
        ("Dienste hochfahren", 0.8),
    ])
    ui.info("Server läuft auf 127.0.0.1:25565.")


def run_stop(ui: Ui) -> None:
    if not ui.confirm("Der laufende Server wird beendet.\n"
                      "Nicht gespeicherte Daten gehen verloren.\n\nFortfahren?"):
        ui.log("Abgebrochen.", "warn")
        return
    run_steps(ui, "Server stoppt", [
        ("Spieler benachrichtigen", 0.5),
        ("Welt speichern", 1.0),
        ("Prozess beenden", 0.5),
    ])
    ui.info("Server gestoppt.")


def run_restart(ui: Ui) -> None:
    run_steps(ui, "Neustart", [
        ("Herunterfahren", 0.8),
        ("Aufräumen", 0.4),
        ("Wieder starten", 1.0),
    ])
    ui.info("Neustart abgeschlossen.")


def run_status(ui: Ui) -> None:
    for line in ("Status      : läuft",
                 "Adresse     : 127.0.0.1:25565",
                 "Spieler     : 3 / 20",
                 "Laufzeit    : 4h 12m",
                 "Speicher    : 2.1 GB / 4.0 GB"):
        ui.log(line)
    ui.info("Status abgefragt.")


def run_logs(ui: Ui) -> None:
    ui.progress_start("Log wird gelesen", total=None, unit="B",
                      status="latest.log")
    read = 0
    for _ in range(60):
        ui.sleep(0.03)
        read += 4096
        ui.progress(read, None, unit="B")
    ui.progress_done("245 KB gelesen.")
    ui.info("Hier würden die letzten Logzeilen erscheinen.")


# --------------------------------------------------------------------------
# Aktionen - Install
# --------------------------------------------------------------------------

def source_classic(ui: Ui) -> None:
    download_with_progress(ui, "https://github.com/SchnuBby2205/cmangos-classic-server/archive/refs/heads/master.zip", "./downloads/")
    #simulate_download(ui, "Serverpaket wird geladen", "server-1.21.zip",
    #                  48 * 1024 * 1024, 900 * 1024)
    run_steps(ui, "Installation", [
        ("Archiv entpacken", 1.0),
        ("Abhängigkeiten prüfen", 0.7),
        ("Startskript schreiben", 0.4),
    ])
    ui.info("Server installiert.")
    
def source_tbc(ui: Ui) -> None:
    download_with_progress(ui, "https://github.com/SchnuBby2205/cmangos-tbc-server/archive/refs/heads/master.zip", "./downloads/")
    #simulate_download(ui, "Serverpaket wird geladen", "server-1.21.zip",
    #                  48 * 1024 * 1024, 900 * 1024)
    run_steps(ui, "Installation", [
        ("Archiv entpacken", 1.0),
        ("Abhängigkeiten prüfen", 0.7),
        ("Startskript schreiben", 0.4),
    ])
    ui.info("Server installiert.")
    
def source_wotlk(ui: Ui) -> None:
    download_with_progress(ui, "https://github.com/SchnuBby2205/cmangos-classic-server/archive/refs/heads/master.zip", "./downloads/")
    #simulate_download(ui, "Serverpaket wird geladen", "server-1.21.zip",
    #                  48 * 1024 * 1024, 900 * 1024)
    run_steps(ui, "Installation", [
        ("Archiv entpacken", 1.0),
        ("Abhängigkeiten prüfen", 0.7),
        ("Startskript schreiben", 0.4),
    ])
    ui.info("Server installiert.")


def install_plugins(ui: Ui) -> None:
    plugins = ["EssentialsX", "LuckPerms", "WorldEdit", "Vault", "PlaceholderAPI"]
    ui.progress_start("Plugins werden installiert", total=len(plugins),
                      unit="Plugin")
    for index, plugin in enumerate(plugins, start=1):
        ui.progress(index - 1, len(plugins), f"lade {plugin} ...",
                    "Plugin", force=True)
        ui.sleep(0.6)
        ui.log(f"{plugin} installiert.")
        ui.progress(index, len(plugins), unit="Plugin", force=True)
    ui.progress_done(f"{len(plugins)} Plugins installiert.")


def install_update(ui: Ui) -> None:
    if not ui.confirm("Das Update ersetzt die vorhandene Serverversion.\n"
                      "Ein Backup wird vorher angelegt.\n\nFortfahren?"):
        ui.log("Abgebrochen.", "warn")
        return
    run_steps(ui, "Backup", [("Daten sichern", 1.2)])
    simulate_download(ui, "Update wird geladen", "patch-1.21.1.bin",
                      22 * 1024 * 1024, 700 * 1024)
    ui.info("Update eingespielt.")


def install_config(ui: Ui) -> None:
    if not ui.confirm("Dieser Schritt überschreibt die bestehende "
                      "Konfiguration.\n\nVorgang wirklich ausführen?"):
        ui.log("Abgebrochen.", "warn")
        return
    run_steps(ui, "Konfiguration", [
        ("Vorlage lesen", 0.4),
        ("Werte schreiben", 0.6),
    ])
    ui.info("Konfiguration erneuert.")


def install_uninstall(ui: Ui) -> None:
    if not ui.confirm("Alle Serverdateien werden gelöscht.\n"
                      "Dieser Schritt lässt sich nicht rückgängig machen!\n\n"
                      "Wirklich fortfahren?"):
        ui.log("Abgebrochen.", "warn")
        return
    run_steps(ui, "Deinstallation", [
        ("Dienste stoppen", 0.6),
        ("Dateien entfernen", 1.0),
    ])
    ui.info("Deinstallation abgeschlossen.")


# --------------------------------------------------------------------------
# Aktionen - Misc
# --------------------------------------------------------------------------

def misc_download(ui: Ui) -> None:
    url = ui.ask_string("Adresse der Datei:", title="Download",
                        initial="https://")
    if not url or url.strip() in ("", "https://"):
        ui.log("Kein Download gestartet.", "warn")
        return
    target = ui.ask_directory("Zielordner wählen")
    if not target:
        ui.log("Kein Zielordner gewählt.", "warn")
        return
    ui.log(f"Lade {url.strip()}")
    download_with_progress(ui, url.strip(), target)


def misc_cache(ui: Ui) -> None:
    total = 320
    ui.progress_start("Cache wird geleert", total=total, unit="Datei")
    for i in range(total):
        ui.sleep(0.005)
        status = f"cache/{i:04d}.tmp" if i % 20 == 0 else None
        ui.progress(i + 1, total, status, "Datei")
    ui.progress_done("Cache geleert.")


def misc_experimental(ui: Ui) -> None:
    ui.warn("Diese Funktion ist noch experimentell und kann "
            "unerwartete Ergebnisse liefern.")


def misc_progress_demo(ui: Ui) -> None:
    ui.log("1) Balken mit bekannter Gesamtgröße:")
    simulate_download(ui, "Demo-Download", "beispiel.iso",
                      10 * 1024 * 1024, 256 * 1024)
    ui.log("2) Balken ohne bekannte Gesamtgröße:")
    ui.progress_start("Unbekannte Größe", total=None, unit="B",
                      status="Daten werden empfangen ...")
    got = 0
    for _ in range(70):
        ui.sleep(0.04)
        got += 128 * 1024
        ui.progress(got, None, unit="B")
    ui.progress_done("Übertragung beendet.")


def misc_about(ui: Ui) -> None:
    ui.log(APP_TITLE)
    ui.log("Grafische Oberfläche zum Menügerüst (Tkinter).")
    ui.log(f"Python {sys.version.split()[0]} auf {sys.platform}")
    ui.info("Bereit.")


# --------------------------------------------------------------------------
# Aktionen - tiefere Ebenen (Beispiele)
# --------------------------------------------------------------------------

def logs_tail(ui: Ui) -> None:
    run_steps(ui, "Log wird gelesen", [("letzte 50 Zeilen holen", 0.6)])
    ui.info("Hier würden die letzten 50 Zeilen stehen.")


def logs_errors(ui: Ui) -> None:
    run_steps(ui, "Log wird gefiltert", [("nach WARN/ERROR suchen", 0.8)])
    ui.info("3 Fehler und 7 Warnungen gefunden.")


def logs_archive(ui: Ui) -> None:
    if not ui.confirm("Die aktuelle Logdatei wird gepackt und geleert.\n\n"
                      "Fortfahren?"):
        ui.log("Abgebrochen.", "warn")
        return
    run_steps(ui, "Archivierung", [("packen", 0.7), ("Log leeren", 0.3)])
    ui.info("Log archiviert.")


def plugins_all(ui: Ui) -> None:
    install_plugins(ui)


def plugins_pick(ui: Ui) -> None:
    name = ui.ask_string("Name des Plugins:", title="Plugin installieren")
    if not name or not name.strip():
        ui.log("Kein Plugin gewählt.", "warn")
        return
    name = name.strip()
    run_steps(ui, f"{name} wird installiert",
              [("herunterladen", 0.8), ("einrichten", 0.5)])
    ui.info(f"{name} installiert.")


def plugins_refresh(ui: Ui) -> None:
    run_steps(ui, "Pluginliste", [("Quelle abfragen", 0.9)])
    ui.info("Liste aktualisiert.")


def net_ping(ui: Ui) -> None:
    run_steps(ui, "Ping", [("3 Pakete senden", 1.0)])
    ui.info("Antwortzeit: 24 ms (0 % Verlust).")


def net_ports(ui: Ui) -> None:
    run_steps(ui, "Portprüfung", [("25565 testen", 0.6), ("3306 testen", 0.6)])
    ui.info("25565 offen, 3306 geschlossen.")


def disk_usage(ui: Ui) -> None:
    run_steps(ui, "Speicher wird geprüft", [("Verzeichnisse messen", 1.0)])
    ui.info("Serverordner belegt 12.4 GB.")


def disk_clean(ui: Ui) -> None:
    if not ui.confirm("Alle Backups älter als 30 Tage werden gelöscht.\n\n"
                      "Fortfahren?"):
        ui.log("Abgebrochen.", "warn")
        return
    run_steps(ui, "Aufräumen", [("Backups prüfen", 0.6), ("löschen", 0.8)])
    ui.info("4.1 GB freigegeben.")


# --------------------------------------------------------------------------
# Menüstruktur - identisch aufgebaut wie in menu.py
# --------------------------------------------------------------------------

# Ein Eintrag ist (Name, Beschreibung, Ziel).
#   Ziel = Funktion      -> Aktion, wird beim Anklicken ausgeführt
#   Ziel = Tupel/Liste   -> Untermenü mit weiteren Einträgen
# Die Schachtelung ist beliebig tief - einfach weitere Tupel einhängen.
MENU = (
    ("Run", "Run a Server", (
        ("Start", "Server starten", run_start),
        ("Stop", "Server beenden", run_stop),
        ("Restart", "Server neu starten", run_restart),
        ("Status", "Laufzeit und Auslastung", run_status),
        ("Logs", "Logdatei auswerten", (
            ("Anzeigen", "letzte 50 Zeilen", logs_tail),
            ("Fehler", "nur WARN und ERROR", logs_errors),
            ("Einlesen", "komplette Datei laden", run_logs),
            ("Archiv", "packen und leeren", logs_archive),
        )),
    )),
    ("Sources", "Download Serversources (Github)", (
        ("Classic", "Download Classic Server Sources", source_classic),
        ("TBC", "Download TBC Server Sources", source_tbc),
        ("Wotlk", "Download Wotlk Server Sources", source_wotlk),
        #("Plugins", "Plugins verwalten", (
        #    ("Alle", "Standardpaket installieren", plugins_all),
        #    ("Einzeln", "ein bestimmtes Plugin", plugins_pick),
        #    ("Liste", "Pluginliste aktualisieren", plugins_refresh),
        #)),
        #("Update", "Vorhandene Version aktualisieren", install_update),
        #("Config", "Konfiguration neu schreiben", install_config),
        #("Remove", "Installation entfernen", install_uninstall),
    )),
    ("Misc", "miscellaneous", (
        ("Download", "Datei von einer URL laden", misc_download),
        ("Cache", "Temporäre Dateien löschen", misc_cache),
        ("Tools", "Werkzeugkasten", (
            ("Netzwerk", "Verbindung prüfen", (
                ("Ping", "Erreichbarkeit testen", net_ping),
                ("Ports", "offene Ports prüfen", net_ports),
            )),
            ("Speicher", "Belegung und Aufräumen", (
                ("Belegung", "Größe der Ordner", disk_usage),
                ("Aufräumen", "alte Backups löschen", disk_clean),
            )),
            ("Beta", "Experimentelle Funktion", misc_experimental),
        )),
        ("Demo", "Fortschrittsbox ansehen", misc_progress_demo),
        ("Info", "Über dieses Programm", misc_about),
    )),
)


def is_submenu(target) -> bool:
    """Untermenü (Tupel/Liste von Einträgen) oder ausführbare Aktion?"""
    return not callable(target)


# --------------------------------------------------------------------------
# Oberfläche
# --------------------------------------------------------------------------

class SubItem(tk.Frame):
    """Anklickbare Karte im Detailblock.

    ``kind`` bestimmt das Aussehen und das Verhalten:
        "action"  fuehrt eine Funktion aus (waehrend eines Vorgangs gesperrt)
        "folder"  oeffnet ein Untermenue
        "back"    geht eine Ebene zurueck
    """

    def __init__(self, master, index, name: str, desc: str, command,
                 kind: str = "action"):
        super().__init__(master, bg=T.CARD, cursor="hand2",
                         highlightthickness=1, highlightbackground=T.LINE)
        self.command = command
        self.kind = kind
        self.enabled = True

        lead = {"back": "‹", "folder": f"{index}", "action": f"{index}"}[kind]
        tail = {"back": "", "folder": "›", "action": "▸"}[kind]
        self.base_fg = T.ACCENT if kind in ("folder", "back") else T.FG

        self.num = tk.Label(self, text=lead, bg=T.CARD, fg=T.ACCENT,
                            font=FONT_BOLD, width=3)
        self.title = tk.Label(self, text=name, bg=T.CARD, fg=self.base_fg,
                              font=FONT_BOLD, anchor="w", width=10)
        self.desc = tk.Label(self, text=desc, bg=T.CARD, fg=T.DIM,
                             font=FONT, anchor="w")
        self.arrow = tk.Label(self, text=tail, bg=T.CARD, fg=T.DIM,
                              font=("Segoe UI", 14))

        self.num.pack(side="left", padx=(10, 0), pady=11)
        self.title.pack(side="left", padx=(4, 10), pady=11)
        self.desc.pack(side="left", fill="x", expand=True, pady=11)
        self.arrow.pack(side="right", padx=12)

        for widget in self._parts():
            widget.bind("<Button-1>", self._click)
            widget.bind("<Enter>", lambda _e: self._paint(T.CARD_HOVER))
            widget.bind("<Leave>", lambda _e: self._paint(T.CARD))

    def _parts(self):
        return (self, self.num, self.title, self.desc, self.arrow)

    def _paint(self, color: str) -> None:
        if not self.enabled:
            return
        for widget in self._parts():
            widget.configure(bg=color)

    def _click(self, _event=None) -> None:
        if self.enabled:
            self.command()

    def set_enabled(self, enabled: bool) -> None:
        """Navigation bleibt immer nutzbar - nur Aktionen werden gesperrt."""
        if self.kind != "action":
            return
        self.enabled = enabled
        self.configure(cursor="hand2" if enabled else "watch")
        self.title.configure(fg=self.base_fg if enabled else T.DIM)
        self._paint(T.CARD)


class App:
    """Hauptfenster: Sidebar links, Detailblock rechts, Fortschritt unten."""

    def __init__(self, root: tk.Tk):
        self.root = root
        self.closing = False
        self.jobs: queue.Queue = queue.Queue()   # Auftraege aus dem Worker
        self.ui = Ui(self)
        self.worker: threading.Thread | None = None
        self.sub_items: list[SubItem] = []
        self.side_buttons: list[tuple[tk.Frame, tk.Frame, tk.Label]] = []
        self.active = 0
        # Pfad durch die Menuebaeume: [(Name, Beschreibung, Eintraege), ...]
        self.stack: list[tuple] = [MENU[0]]
        self.progress_state = {"total": None, "unit": "B", "start": 0.0}

        root.title(APP_TITLE)
        root.geometry("940x620")
        root.minsize(760, 520)
        root.configure(bg=T.BG)
        root.protocol("WM_DELETE_WINDOW", self.on_close)

        self._build_header()
        self._build_body()
        self._build_footer()
        self.select(0)
        root.bind("<Escape>", lambda _e: self.on_close())
        self.pump()          # Auftragsschleife starten

    # -- Aufbau --------------------------------------------------------

    def _build_header(self) -> None:
        head = tk.Frame(self.root, bg=T.SIDEBAR, height=56)
        head.pack(side="top", fill="x")
        head.pack_propagate(False)
        tk.Label(head, text=APP_TITLE, bg=T.SIDEBAR, fg=T.FG,
                 font=FONT_TITLE).pack(side="left", padx=18)
        self.busy_label = tk.Label(head, text="", bg=T.SIDEBAR, fg=T.ACCENT,
                                   font=FONT_SMALL)
        self.busy_label.pack(side="right", padx=18)
        tk.Frame(self.root, bg=T.LINE, height=1).pack(side="top", fill="x")

    def _build_body(self) -> None:
        body = tk.Frame(self.root, bg=T.BG)
        body.pack(side="top", fill="both", expand=True)

        # linke Spalte: Hauptpunkte
        sidebar = tk.Frame(body, bg=T.SIDEBAR, width=190)
        sidebar.pack(side="left", fill="y")
        sidebar.pack_propagate(False)
        tk.Label(sidebar, text="HAUPTMENÜ", bg=T.SIDEBAR, fg=T.DIM,
                 font=("Segoe UI", 8, "bold")).pack(anchor="w", padx=16,
                                                    pady=(16, 8))
        for index, (name, label, _entries) in enumerate(MENU):
            self._add_side_button(sidebar, index, name, label)

        tk.Frame(sidebar, bg=T.LINE, height=1).pack(fill="x", padx=12, pady=10)
        quit_btn = tk.Label(sidebar, text="Beenden", bg=T.SIDEBAR, fg=T.DIM,
                            font=FONT, cursor="hand2", anchor="w")
        quit_btn.pack(fill="x", padx=20, pady=4)
        quit_btn.bind("<Button-1>", lambda _e: self.on_close())

        tk.Frame(body, bg=T.LINE, width=1).pack(side="left", fill="y")

        # rechte Spalte: Detailblock
        detail = tk.Frame(body, bg=T.PANEL)
        detail.pack(side="left", fill="both", expand=True)

        self.crumb_bar = tk.Frame(detail, bg=T.PANEL)
        self.crumb_bar.pack(fill="x", padx=22, pady=(14, 0))

        self.detail_title = tk.Label(detail, text="", bg=T.PANEL, fg=T.FG,
                                     font=FONT_TITLE, anchor="w")
        self.detail_title.pack(fill="x", padx=22, pady=(2, 0))
        self.detail_desc = tk.Label(detail, text="", bg=T.PANEL, fg=T.DIM,
                                    font=FONT, anchor="w")
        self.detail_desc.pack(fill="x", padx=22, pady=(2, 12))
        tk.Frame(detail, bg=T.LINE, height=1).pack(fill="x", padx=22)

        self.item_area = tk.Frame(detail, bg=T.PANEL)
        self.item_area.pack(fill="both", expand=True, padx=16, pady=14)

    def _add_side_button(self, parent, index: int, name: str, label: str) -> None:
        row = tk.Frame(parent, bg=T.SIDEBAR, cursor="hand2")
        row.pack(fill="x")
        marker = tk.Frame(row, bg=T.SIDEBAR, width=3)
        marker.pack(side="left", fill="y")
        text = tk.Label(row, text=name, bg=T.SIDEBAR, fg=T.DIM, font=FONT_BOLD,
                        anchor="w", padx=14, pady=10)
        text.pack(side="left", fill="x", expand=True)
        for widget in (row, text):
            widget.bind("<Button-1>", lambda _e, i=index: self.select(i))
        self.side_buttons.append((row, marker, text))

    def _build_footer(self) -> None:
        tk.Frame(self.root, bg=T.LINE, height=1).pack(side="top", fill="x")
        foot = tk.Frame(self.root, bg=T.BG)
        foot.pack(side="top", fill="x")

        # Fortschrittsbox
        box = tk.Frame(foot, bg=T.PANEL, highlightthickness=1,
                       highlightbackground=T.LINE)
        box.pack(fill="x", padx=14, pady=(12, 8))

        top = tk.Frame(box, bg=T.PANEL)
        top.pack(fill="x", padx=14, pady=(10, 2))
        self.prog_title = tk.Label(top, text="Bereit", bg=T.PANEL, fg=T.FG,
                                   font=FONT_BOLD, anchor="w")
        self.prog_title.pack(side="left")
        self.prog_pct = tk.Label(top, text="", bg=T.PANEL, fg=T.ACCENT,
                                 font=FONT_BOLD)
        self.prog_pct.pack(side="right")

        style = ttk.Style(self.root)
        style.theme_use("clam")
        style.configure("Bar.Horizontal.TProgressbar", troughcolor=T.CARD,
                        bordercolor=T.CARD, background=T.ACCENT,
                        lightcolor=T.ACCENT, darkcolor=T.ACCENT, thickness=14)
        self.prog_var = tk.DoubleVar(value=0.0)
        self.prog_bar = ttk.Progressbar(box, style="Bar.Horizontal.TProgressbar",
                                        variable=self.prog_var, maximum=100.0)
        self.prog_bar.pack(fill="x", padx=14, pady=4)

        bottom = tk.Frame(box, bg=T.PANEL)
        bottom.pack(fill="x", padx=14, pady=(2, 10))
        self.prog_status = tk.Label(bottom, text="", bg=T.PANEL, fg=T.DIM,
                                    font=FONT_SMALL, anchor="w")
        self.prog_status.pack(side="left", fill="x", expand=True)
        self.prog_detail = tk.Label(bottom, text="", bg=T.PANEL, fg=T.DIM,
                                    font=FONT_SMALL, anchor="e")
        self.prog_detail.pack(side="right")
        self.cancel_btn = tk.Button(bottom, text="Abbrechen", font=FONT_SMALL,
                                    bg=T.CARD, fg=T.FG, activebackground=T.RED,
                                    activeforeground="#ffffff", relief="flat",
                                    bd=0, padx=10, state="disabled",
                                    command=self.cancel_task)
        self.cancel_btn.pack(side="right", padx=(12, 0))

        # Protokoll
        logbox = tk.Frame(foot, bg=T.BG)
        logbox.pack(fill="both", padx=14, pady=(0, 12))
        self.log = tk.Text(logbox, height=8, bg="#14171d", fg=T.DIM,
                           font=FONT_MONO, relief="flat", wrap="word",
                           insertbackground=T.FG, state="disabled",
                           highlightthickness=1, highlightbackground=T.LINE)
        scroll = ttk.Scrollbar(logbox, command=self.log.yview)
        self.log.configure(yscrollcommand=scroll.set)
        scroll.pack(side="right", fill="y")
        self.log.pack(side="left", fill="both", expand=True)
        self.log.tag_configure("info", foreground=T.DIM)
        self.log.tag_configure("ok", foreground=T.GREEN)
        self.log.tag_configure("warn", foreground=T.YELLOW)
        self.log.tag_configure("err", foreground=T.RED)

    # -- Navigation ----------------------------------------------------

    def select(self, index: int) -> None:
        """Waehlt einen Hauptpunkt und springt auf dessen oberste Ebene."""
        self.active = index
        self.stack = [MENU[index]]
        for i, (row, marker, text) in enumerate(self.side_buttons):
            chosen = i == index
            bg = T.PANEL if chosen else T.SIDEBAR
            row.configure(bg=bg)
            text.configure(bg=bg, fg=T.FG if chosen else T.DIM)
            marker.configure(bg=T.ACCENT if chosen else bg)
        self.render_detail()

    def enter(self, entry) -> None:
        """Steigt in ein Untermenue ab."""
        self.stack.append(entry)
        self.render_detail()

    def go_up(self, depth: int) -> None:
        """Springt auf die Ebene ``depth`` des aktuellen Pfades zurueck."""
        self.stack = self.stack[:max(1, depth + 1)]
        self.render_detail()

    def render_detail(self) -> None:
        """Baut Pfadleiste und Karten fuer die aktuelle Ebene neu auf."""
        name, label, entries = self.stack[-1]
        self.detail_title.configure(text=name)
        self.detail_desc.configure(text=label)

        # Pfadleiste: jedes Segment ausser dem letzten ist anklickbar
        for widget in self.crumb_bar.winfo_children():
            widget.destroy()
        for depth, (part, _desc, _target) in enumerate(self.stack):
            last = depth == len(self.stack) - 1
            crumb = tk.Label(self.crumb_bar, text=part, bg=T.PANEL,
                             fg=T.DIM if last else T.ACCENT, font=FONT_SMALL,
                             cursor="" if last else "hand2")
            crumb.pack(side="left")
            if not last:
                crumb.bind("<Button-1>", lambda _e, d=depth: self.go_up(d))
                tk.Label(self.crumb_bar, text="  ›  ", bg=T.PANEL,
                         fg=T.DIM, font=FONT_SMALL).pack(side="left")

        # Karten
        for widget in self.item_area.winfo_children():
            widget.destroy()
        self.sub_items = []
        if len(self.stack) > 1:
            parent = self.stack[-2][0]
            back = SubItem(self.item_area, "", "Zurück", f"zu {parent}",
                           lambda: self.go_up(len(self.stack) - 2), kind="back")
            back.pack(fill="x", pady=(0, 8), padx=6)
            self.sub_items.append(back)

        for number, (sub, desc, target) in enumerate(entries, start=1):
            if is_submenu(target):
                item = SubItem(self.item_area, number, sub, desc,
                               lambda e=(sub, desc, target): self.enter(e),
                               kind="folder")
            else:
                item = SubItem(self.item_area, number, sub, desc,
                               lambda a=target, s=sub: self.start_task(s, a),
                               kind="action")
            item.pack(fill="x", pady=4, padx=6)
            self.sub_items.append(item)
        self.set_busy(self.worker is not None and self.worker.is_alive())

    # -- Aktionen ausführen -------------------------------------------

    def start_task(self, name: str, action) -> None:
        if self.worker is not None and self.worker.is_alive():
            messagebox.showinfo("Bitte warten",
                                "Es läuft bereits ein Vorgang.",
                                parent=self.root)
            return
        self.ui.cancel.clear()
        self.append_log(f"--- {name} ---", "ok")
        self.set_busy(True)
        self.worker = threading.Thread(target=self._run_task,
                                       args=(name, action), daemon=True)
        self.worker.start()

    def _run_task(self, name: str, action) -> None:
        """Läuft im Hintergrund-Thread."""
        try:
            action(self.ui)
        except Cancelled:
            self.ui.log(f"{name}: abgebrochen.", "warn")
            self.ui.progress_done("Abgebrochen.", ok=False)
        except Exception as exc:                      # noqa: BLE001
            self.ui.error(f"{name}: {type(exc).__name__}: {exc}")
            self.ui.progress_done("Fehlgeschlagen.", ok=False)
        finally:
            self.ui._post(self.set_busy, False)

    def cancel_task(self) -> None:
        if self.worker is not None and self.worker.is_alive():
            self.ui.cancel.set()
            self.append_log("Abbruch angefordert ...", "warn")

    def set_busy(self, busy: bool) -> None:
        self.busy_label.configure(text="Vorgang läuft ..." if busy else "")
        self.cancel_btn.configure(state="normal" if busy else "disabled")
        for item in self.sub_items:
            item.set_enabled(not busy)

    # -- Fortschrittsbox -----------------------------------------------

    def start_progress(self, title: str, total, unit: str, status: str) -> None:
        self.progress_state = {"total": total, "unit": unit,
                               "start": time.monotonic()}
        self.prog_title.configure(text=title, fg=T.FG)
        self.prog_status.configure(text=status)
        self.prog_detail.configure(text="")
        self._set_bar_color(T.ACCENT)
        if total is None:
            self.prog_bar.configure(mode="indeterminate")
            self.prog_bar.start(14)
            self.prog_pct.configure(text="--%")
        else:
            self.prog_bar.stop()
            self.prog_bar.configure(mode="determinate")
            self.prog_var.set(0.0)
            self.prog_pct.configure(text="0.0%")

    def set_progress(self, current, total, status, unit, title) -> None:
        state = self.progress_state
        if total is not None:
            state["total"] = total
        if unit:
            state["unit"] = unit
        if title:
            self.prog_title.configure(text=title)
        if status is not None:
            self.prog_status.configure(text=status)
        if current is None:
            return

        total = state["total"]
        unit = state["unit"]
        elapsed = max(1e-6, time.monotonic() - state["start"])
        speed = current / elapsed

        def fmt(value: float) -> str:
            return fmt_bytes(value) if unit == "B" else f"{value:.0f} {unit}"

        parts = [f"{fmt(current)} / {fmt(total)}" if total else fmt(current)]
        if unit == "B":
            parts.append(f"{fmt_bytes(speed)}/s")
        if total and speed > 0 and current < total:
            parts.append(f"noch {fmt_time((total - current) / speed)}")
        else:
            parts.append(fmt_time(elapsed))
        self.prog_detail.configure(text="   ·   ".join(parts))

        if total:
            if str(self.prog_bar.cget("mode")) == "indeterminate":
                self.prog_bar.stop()
                self.prog_bar.configure(mode="determinate")
            fraction = min(1.0, max(0.0, current / total))
            self.prog_var.set(fraction * 100)
            self.prog_pct.configure(text=f"{fraction * 100:.1f}%")

    def finish_progress(self, status: str, ok: bool) -> None:
        self.prog_bar.stop()
        self.prog_bar.configure(mode="determinate")
        state = self.progress_state
        if ok:
            self.prog_var.set(100.0)
            self.prog_pct.configure(text="100%")
            self._set_bar_color(T.GREEN)
            self.prog_title.configure(fg=T.GREEN)
        else:
            self._set_bar_color(T.RED)
            self.prog_title.configure(fg=T.RED)
        if status:
            self.prog_status.configure(text=status)
            self.append_log(status, "ok" if ok else "warn")
        state["total"] = None

    def _set_bar_color(self, color: str) -> None:
        ttk.Style(self.root).configure("Bar.Horizontal.TProgressbar",
                                       background=color, lightcolor=color,
                                       darkcolor=color)

    # -- Protokoll -----------------------------------------------------

    def append_log(self, text: str, kind: str = "info") -> None:
        stamp = time.strftime("%H:%M:%S")
        self.log.configure(state="normal")
        self.log.insert("end", f"{stamp}  {text}\n", kind)
        self.log.see("end")
        self.log.configure(state="disabled")

    # -- Auftragsschleife ----------------------------------------------

    def pump(self) -> None:
        """Arbeitet die vom Worker eingereihten Aufrufe im Hauptthread ab."""
        while True:
            try:
                fn, args = self.jobs.get_nowait()
            except queue.Empty:
                break
            try:
                fn(*args)
            except tk.TclError:          # Fenster bereits geschlossen
                return
            except Exception as exc:     # noqa: BLE001 - Schleife am Leben halten
                print(f"Fehler in der Oberflaeche: {exc!r}")
        if not self.closing:
            self.root.after(40, self.pump)

    # -- Ende ----------------------------------------------------------

    def on_close(self) -> None:
        if self.worker is not None and self.worker.is_alive():
            if not messagebox.askyesno(
                    "Beenden", "Es läuft noch ein Vorgang.\nTrotzdem beenden?",
                    parent=self.root):
                return
        self.closing = True
        self.ui.cancel.set()
        self.root.destroy()


def main() -> None:
    root = tk.Tk()
    app = App(root)
    app.append_log(f"{APP_TITLE} gestartet. Links einen Hauptpunkt wählen.")
    root.mainloop()


if __name__ == "__main__":
    main()
