#!/usr/bin/env python3
"""CLI-Menü-Gerüst mit eigenen Untermenüs je Hauptpunkt.

Start:  python menu.py

Enthält:
  * Hauptmenü (Run / Install / Misc)
  * je Hauptpunkt ein eigenes Untermenü mit eigenen Aktionen
  * beliebig tief verschachtelbare Untermenüs (siehe MENU)
  * Warn- und Bestätigungsbox
  * ProgressBox: Fortschrittsbalken mit Prozent, Tempo und Restzeit
    (z. B. für Downloads)

Benötigt nur die Standardbibliothek, läuft unter Windows und Linux.
"""

from __future__ import annotations

import os
import sys
import textwrap
import time
import urllib.error
import urllib.parse
import urllib.request

# --------------------------------------------------------------------------
# Terminal-Vorbereitung
# --------------------------------------------------------------------------

def _init_terminal() -> None:
    """Aktiviert ANSI-Sequenzen und UTF-8-Ausgabe (vor allem unter Windows)."""
    if os.name == "nt":
        os.system("")  # schaltet die VT-Verarbeitung in cmd.exe/PowerShell ein
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except (AttributeError, OSError):
        pass


def _unicode_ok() -> bool:
    """Prüft, ob die Konsole die Rahmenzeichen darstellen kann."""
    enc = getattr(sys.stdout, "encoding", None) or "ascii"
    try:
        "─│┌╔⚠█░".encode(enc)
    except (UnicodeEncodeError, LookupError):
        return False
    return True


_init_terminal()
UNICODE = _unicode_ok()
TTY = sys.stdout.isatty()
COLOR = os.environ.get("NO_COLOR") is None and TTY
ANSI = TTY  # Cursor-Steuerung für die Live-Fortschrittsbox


class C:
    """ANSI-Farbcodes (leere Strings, wenn Farben deaktiviert sind)."""

    RESET = "\033[0m" if COLOR else ""
    BOLD = "\033[1m" if COLOR else ""
    DIM = "\033[2m" if COLOR else ""
    CYAN = "\033[36m" if COLOR else ""
    GREEN = "\033[32m" if COLOR else ""
    YELLOW = "\033[33m" if COLOR else ""
    RED = "\033[31m" if COLOR else ""


# Rahmenzeichen: einfach (Menü) und doppelt (Warnung)
if UNICODE:
    LIGHT = ("┌", "┐", "└", "┘", "─", "│")
    HEAVY = ("╔", "╗", "╚", "╝", "═", "║")
    WARN_SIGN = "⚠"
    BAR_FULL, BAR_EMPTY = "█", "░"
    DOT = "·"
    SUB_SIGN = "›"
else:
    LIGHT = ("+", "+", "+", "+", "-", "|")
    HEAVY = ("+", "+", "+", "+", "=", "|")
    WARN_SIGN = "!"
    BAR_FULL, BAR_EMPTY = "#", "-"
    DOT = "*"
    SUB_SIGN = ">"

BOX_WIDTH = 46
WIDE_WIDTH = BOX_WIDTH + 14


def clear_screen() -> None:
    os.system("cls" if os.name == "nt" else "clear")


# --------------------------------------------------------------------------
# Ausgabe-Bausteine
# --------------------------------------------------------------------------

def box_lines(lines, title=None, style=LIGHT, color=C.CYAN, width=BOX_WIDTH):
    """Baut die Zeilen einer Box, ohne sie auszugeben.

    ``lines`` darf reine Strings oder Tupel ``(klartext, eingefärbt)``
    enthalten - so lassen sich Farben innerhalb einer Zeile nutzen, ohne
    die Breitenberechnung zu stören.
    """
    tl, tr, bl, br, hz, vt = style
    content = [t if isinstance(t, tuple) else (t, t) for t in lines] or [("", "")]
    inner = max([len(plain) for plain, _ in content] + [width - 4])
    if title:
        inner = max(inner, len(title) + 4)
        head = f"{tl}{hz} {title} {hz * (inner - len(title) - 1)}{tr}"
    else:
        head = f"{tl}{hz * (inner + 2)}{tr}"

    out = [f"{color}{head}{C.RESET}"]
    for plain, shown in content:
        pad = " " * max(0, inner - len(plain))
        out.append(f"{color}{vt}{C.RESET} {shown}{pad} {color}{vt}{C.RESET}")
    out.append(f"{color}{bl}{hz * (inner + 2)}{br}{C.RESET}")
    return out


def draw_box(lines, title=None, style=LIGHT, color=C.CYAN, width=BOX_WIDTH):
    """Zeichnet einen Rahmen um die Textzeilen."""
    for line in box_lines(lines, title=title, style=style, color=color, width=width):
        print(line)


def _wrap(message: str, width: int) -> list[str]:
    """Bricht den Text auf die Boxbreite um und behält Leerzeilen."""
    out: list[str] = []
    for para in message.splitlines() or [""]:
        out.extend(textwrap.wrap(para, width - 8) or [""])
    return out or [""]


def warning_box(message: str, title: str = "WARNUNG", width: int = WIDE_WIDTH):
    """Zeigt eine Warnungsbox an und wartet auf eine Bestätigung."""
    body = _wrap(message, width)
    lines = [f"{WARN_SIGN}  {body[0]}"] + [f"   {t}" for t in body[1:]]
    print()
    draw_box(lines, title=title, style=HEAVY, color=C.YELLOW, width=width)
    ask(f"{C.DIM}   [Enter] zum Fortfahren ...{C.RESET}")


def confirm_box(message: str, title: str = "ACHTUNG", width: int = WIDE_WIDTH):
    """Wie warning_box, fragt aber nach einer Ja/Nein-Entscheidung."""
    body = _wrap(message, width)
    lines = [f"{WARN_SIGN}  {body[0]}"] + [f"   {t}" for t in body[1:]]
    print()
    draw_box(lines, title=title, style=HEAVY, color=C.RED, width=width)
    return ask("   Fortfahren? [j/N]: ").strip().lower() in ("j", "ja", "y", "yes")


def info(text: str) -> None:
    print(f"{C.GREEN}>>{C.RESET} {text}")


def ask(prompt: str) -> str:
    """input() mit sauberem Abbruch bei Strg+C / Strg+D."""
    try:
        return input(prompt)
    except (KeyboardInterrupt, EOFError):
        print()
        return "q"


def pause() -> None:
    ask(f"{C.DIM}   [Enter] zurück zum Menü ...{C.RESET}")


# --------------------------------------------------------------------------
# Fortschrittsbox
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


class ProgressBox:
    """Fortschrittsbox, die sich an Ort und Stelle aktualisiert.

    Beispiel::

        with ProgressBox("Download", total=groesse, unit="B") as bar:
            for chunk in chunks:
                bar.advance(len(chunk), status="lade ...")
            bar.finish("fertig")

    ``total=None`` schaltet auf einen unbestimmten Laufbalken um (wenn die
    Gesamtgröße nicht bekannt ist). Ohne Terminal (Ausgabe in Datei oder
    Pipe) fällt die Box automatisch auf einfache Textzeilen zurück.
    """

    def __init__(self, title="Fortschritt", total=None, unit="B",
                 width=WIDE_WIDTH, status=""):
        self.title = title
        self.total = total if total and total > 0 else None
        self.unit = unit
        self.width = width
        self.status = status
        self.current = 0
        self.color = C.CYAN
        self._start = time.monotonic()
        self._last_draw = 0.0
        self._drawn_height = 0
        self._done = False
        self._last_bucket = -1

    # -- öffentliche API -----------------------------------------------

    def __enter__(self) -> "ProgressBox":
        self.render(force=True)
        return self

    def __exit__(self, exc_type, exc, tb) -> bool:
        if exc_type is KeyboardInterrupt:
            self.finish("Abgebrochen.", ok=False)
        elif exc_type is not None:
            self.finish("Fehlgeschlagen.", ok=False)
        else:
            self.finish()
        return False

    def update(self, current=None, status=None, total=None, force=False) -> None:
        """Setzt den absoluten Stand (und optional Statustext / Gesamtwert)."""
        if total is not None:
            self.total = total if total > 0 else None
        if current is not None:
            self.current = current
        if status is not None:
            self.status = status
            force = True
        self.render(force=force)

    def advance(self, step=1, status=None) -> None:
        """Erhöht den Stand um ``step``."""
        self.update(self.current + step, status=status)

    def finish(self, status=None, ok=True) -> None:
        """Zeichnet den Endzustand und schließt die Box ab."""
        if self._done:
            return
        if self.total is not None and ok:
            self.current = self.total
        self.color = C.GREEN if ok else C.RED
        if status is not None:
            self.status = status
        self.render(force=True)
        self._done = True

    # -- Darstellung ---------------------------------------------------

    @property
    def fraction(self):
        if self.total is None:
            return None
        return min(1.0, max(0.0, self.current / self.total))

    @property
    def _elapsed(self) -> float:
        return max(1e-6, time.monotonic() - self._start)

    def _fmt(self, value: float) -> str:
        if self.unit == "B":
            return fmt_bytes(value)
        return f"{value:.0f} {self.unit}".strip()

    def _bar(self, inner: int):
        """Balkenzeile als (klartext, eingefärbt)."""
        bar_width = max(10, inner - 10)
        frac = self.fraction
        if frac is None:
            # unbestimmt: ein Block wandert hin und her
            block = max(3, bar_width // 6)
            span = max(1, bar_width - block)
            pos = int(self._elapsed * 12) % (2 * span)
            pos = pos if pos <= span else 2 * span - pos
            cells = [BAR_EMPTY] * bar_width
            for i in range(pos, min(pos + block, bar_width)):
                cells[i] = BAR_FULL
            filled = "".join(cells)
            plain = f"[{filled}]   --%"
            shown = f"[{C.CYAN}{filled}{C.RESET}]{C.DIM}   --%{C.RESET}"
            return plain, shown

        done = int(round(frac * bar_width))
        filled, rest = BAR_FULL * done, BAR_EMPTY * (bar_width - done)
        pct = f"{frac * 100:5.1f}%"
        plain = f"[{filled}{rest}] {pct}"
        shown = (f"[{C.GREEN}{filled}{C.RESET}{C.DIM}{rest}{C.RESET}] "
                 f"{C.BOLD}{pct}{C.RESET}")
        return plain, shown

    def _detail(self, inner: int):
        speed = self.current / self._elapsed
        parts = []
        if self.total is not None:
            parts.append(f"{self._fmt(self.current)} / {self._fmt(self.total)}")
        else:
            parts.append(self._fmt(self.current))
        if self.unit == "B":  # Tempo nur bei Datenmengen sinnvoll
            parts.append(f"{self._fmt(speed)}/s")
        if self.total is not None and speed > 0 and self.current < self.total:
            parts.append(f"noch {fmt_time((self.total - self.current) / speed)}")
        else:
            parts.append(fmt_time(self._elapsed))

        # Teile von hinten weglassen, damit die Box nie breiter wird
        sep = "  " + DOT + "  "
        while len(parts) > 1 and len("  " + sep.join(parts)) > inner:
            parts.pop()
        plain = ("  " + sep.join(parts))[:inner]
        return plain, f"{C.DIM}{plain}{C.RESET}"

    def _lines(self):
        inner = self.width - 4
        text = self.status or ""
        if len(text) > inner - 2:
            text = text[: inner - 5] + "..."
        return [
            self._bar(inner),
            self._detail(inner),
            (f"  {text}", f"  {C.DIM}{text}{C.RESET}"),
        ]

    def render(self, force=False) -> None:
        if self._done:
            return
        now = time.monotonic()
        if not force and now - self._last_draw < 0.08:
            return
        self._last_draw = now

        if not ANSI:
            self._render_plain(force)
            return

        rendered = box_lines(self._lines(), title=self.title,
                             color=self.color, width=self.width)
        if self._drawn_height:
            # Cursor um die Höhe der Box nach oben, dann neu zeichnen
            sys.stdout.write(f"\033[{self._drawn_height}F")
        sys.stdout.write("".join(f"\033[2K{line}\n" for line in rendered))
        sys.stdout.flush()
        self._drawn_height = len(rendered)

    def _render_plain(self, force: bool) -> None:
        """Rückfallmodus ohne Cursor-Steuerung: Ausgabe in 10-Prozent-Schritten."""
        frac = self.fraction
        bucket = int((frac or 0) * 10)
        if not force and bucket == self._last_bucket:
            return
        self._last_bucket = bucket
        pct = "--%" if frac is None else f"{frac * 100:.0f}%"
        status = f" - {self.status}" if self.status else ""
        print(f"   [{self.title}] {pct}{status}")


def run_steps(title: str, steps, unit: str = "Schritt") -> None:
    """Hilfsfunktion: Liste von ``(beschreibung, dauer)`` mit Fortschrittsbox."""
    with ProgressBox(title, total=len(steps), unit=unit) as bar:
        for text, duration in steps:
            bar.update(status=text)
            end = time.monotonic() + duration
            while time.monotonic() < end:  # Balken währenddessen animieren
                time.sleep(0.05)
                bar.render()
            bar.advance(1)
        bar.finish("Abgeschlossen.")


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


def parse_size(raw):
    """Liest eine Größenangabe aus einem Header.

    Robuster als ``int(raw)``: manche Proxys und CDNs senden den Header
    doppelt ("123, 123") oder mit Leerzeichen. Genau dann schlug die
    Erkennung früher fehl und der Balken lief ohne Prozentanzeige.
    """
    text = (raw or "").split(",")[0].strip()
    try:
        size = int(text)
    except ValueError:
        return None
    return size if size > 0 else None


def probe_size(url: str):
    """Holt die Dateigröße nach, wenn die Antwort kein Content-Length hat."""
    request = urllib.request.Request(
        url, headers={"User-Agent": "menu.py", "Range": "bytes=0-0"})
    try:
        with urllib.request.urlopen(request, timeout=15) as response:
            rng = response.headers.get("Content-Range") or ""
            if "/" in rng:
                return parse_size(rng.rsplit("/", 1)[1])
            return parse_size(response.headers.get("Content-Length"))
    except (urllib.error.URLError, OSError, ValueError):
        return None


def download_with_progress(url: str, dest: str) -> bool:
    """Lädt ``url`` nach ``dest`` und zeigt dabei die Fortschrittsbox.

    ``dest`` darf eine Datei oder ein Zielverzeichnis sein. Geschrieben wird
    zuerst in ``<datei>.part``; erst ein vollständiger Download wird an den
    endgültigen Namen umbenannt.
    """
    request = urllib.request.Request(url, headers={"User-Agent": "menu.py"})
    part = None
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            dest = resolve_dest(dest, url, response)
            part = dest + ".part"
            total = parse_size(response.headers.get("Content-Length"))
            if total is None:                 # Server schweigt -> nachfragen
                total = probe_size(url)
            if not total:
                info("Server meldet keine Gesamtgröße - "
                     "der Balken läuft ohne Prozentanzeige.")
            name = os.path.basename(dest)
            with ProgressBox(f"Download {DOT} {name}", total=total, unit="B",
                             status=url) as bar:
                with open(part, "wb") as handle:
                    while True:
                        chunk = response.read(64 * 1024)
                        if not chunk:
                            break
                        handle.write(chunk)
                        bar.advance(len(chunk))
                # erst nach dem Schliessen umbenennen - Windows sperrt
                # offene Dateien und wirft sonst PermissionError
                os.replace(part, dest)
                part = None
                bar.finish(f"Gespeichert unter {dest}")
    except KeyboardInterrupt:
        _cleanup(part)
        warning_box("Download durch den Benutzer abgebrochen.", title="HINWEIS")
        return False
    except PermissionError as exc:
        _cleanup(part)
        warning_box(f"Kein Schreibzugriff auf:\n{exc.filename or dest}\n\n"
                    "Mögliche Ursachen: die Datei ist geöffnet oder\n"
                    "schreibgeschützt, oder der Ordner gehört dem System.\n"
                    "Ein anderes Ziel wählen, z. B. im Benutzerordner.",
                    title="FEHLER")
        return False
    except (urllib.error.URLError, OSError, ValueError) as exc:
        _cleanup(part)
        warning_box(f"Download fehlgeschlagen:\n{exc}", title="FEHLER")
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

def run_start() -> None:
    run_steps("Server startet", [
        ("Konfiguration lesen", 0.6),
        ("Ports prüfen", 0.5),
        ("Welt laden", 1.2),
        ("Dienste hochfahren", 0.8),
    ])
    info("Server läuft auf 127.0.0.1:25565.")
    pause()


def run_stop() -> None:
    if not confirm_box("Der laufende Server wird beendet.\n"
                       "Nicht gespeicherte Daten gehen verloren."):
        info("Abgebrochen.")
        pause()
        return
    run_steps("Server stoppt", [
        ("Spieler benachrichtigen", 0.5),
        ("Welt speichern", 1.0),
        ("Prozess beenden", 0.5),
    ])
    info("Server gestoppt.")
    pause()


def run_restart() -> None:
    run_steps("Neustart", [
        ("Herunterfahren", 0.8),
        ("Aufräumen", 0.4),
        ("Wieder starten", 1.0),
    ])
    info("Neustart abgeschlossen.")
    pause()


def run_status() -> None:
    print()
    draw_box([
        "Status      : läuft",
        "Adresse     : 127.0.0.1:25565",
        "Spieler     : 3 / 20",
        "Laufzeit    : 4h 12m",
        "Speicher    : 2.1 GB / 4.0 GB",
    ], title="SERVERSTATUS", width=WIDE_WIDTH)
    print()
    pause()


def run_logs() -> None:
    with ProgressBox("Log wird gelesen", total=None, unit="B",
                     status="latest.log") as bar:
        for _ in range(60):
            time.sleep(0.03)
            bar.advance(4096)
        bar.finish("245 KB gelesen.")
    info("Hier würden die letzten Logzeilen erscheinen.")
    pause()


# --------------------------------------------------------------------------
# Aktionen - Install
# --------------------------------------------------------------------------

def install_server() -> None:
    #with ProgressBox("Serverpaket wird geladen", total=48 * 1024 * 1024,
    #                 unit="B", status="server-1.21.zip") as bar:
    #    while bar.current < bar.total:
    #        time.sleep(0.04)
    #        bar.advance(900 * 1024)
    #    bar.finish("Download abgeschlossen.")
    #run_steps("Installation", [
    #    ("Archiv entpacken", 1.0),
    #    ("Abhängigkeiten prüfen", 0.7),
    #    ("Startskript schreiben", 0.4),
    #])
    #info("Server installiert.")
    download_with_progress("https://github.com/SchnuBby2205/cmangos-classic-server/archive/refs/heads/master.zip", "./downloads")
    pause()


def install_plugins() -> None:
    plugins = ["EssentialsX", "LuckPerms", "WorldEdit", "Vault", "PlaceholderAPI"]
    with ProgressBox("Plugins werden installiert", total=len(plugins),
                     unit="Plugin") as bar:
        for plugin in plugins:
            bar.update(status=f"lade {plugin} ...")
            time.sleep(0.6)
            bar.advance(1)
        bar.finish(f"{len(plugins)} Plugins installiert.")
    pause()


def install_update() -> None:
    if not confirm_box("Das Update ersetzt die vorhandene Serverversion.\n"
                       "Ein Backup wird vorher angelegt."):
        info("Abgebrochen.")
        pause()
        return
    run_steps("Backup", [("Daten sichern", 1.2)])
    with ProgressBox("Update wird geladen", total=22 * 1024 * 1024,
                     unit="B", status="patch-1.21.1.bin") as bar:
        while bar.current < bar.total:
            time.sleep(0.04)
            bar.advance(700 * 1024)
        bar.finish("Update eingespielt.")
    pause()


def install_config() -> None:
    if not confirm_box("Dieser Schritt überschreibt die bestehende\n"
                       "Konfiguration. Vorgang wirklich ausführen?"):
        info("Abgebrochen.")
        pause()
        return
    run_steps("Konfiguration", [
        ("Vorlage lesen", 0.4),
        ("Werte schreiben", 0.6),
    ])
    info("Konfiguration erneuert.")
    pause()


def install_uninstall() -> None:
    if not confirm_box("Alle Serverdateien werden gelöscht.\n"
                       "Dieser Schritt lässt sich nicht rückgängig machen!"):
        info("Abgebrochen.")
        pause()
        return
    run_steps("Deinstallation", [
        ("Dienste stoppen", 0.6),
        ("Dateien entfernen", 1.0),
    ])
    info("Deinstallation abgeschlossen.")
    pause()


# --------------------------------------------------------------------------
# Aktionen - Misc
# --------------------------------------------------------------------------

def misc_download() -> None:
    print()
    url = ask("  URL (leer = abbrechen): ").strip()
    if not url or url == "q":
        return
    target = ask("  Zieldatei [download.bin]: ").strip() or "download.bin"
    if download_with_progress(url, target):
        info(f"Fertig: {target}")
    pause()


def misc_cache() -> None:
    with ProgressBox("Cache wird geleert", total=320, unit="Datei") as bar:
        for i in range(320):
            time.sleep(0.005)
            bar.advance(1, status=f"cache/{i:04d}.tmp" if i % 20 == 0 else None)
        bar.finish("Cache geleert.")
    pause()


def misc_experimental() -> None:
    warning_box("Diese Funktion ist noch experimentell und kann\n"
                "unerwartete Ergebnisse liefern.")


def misc_progress_demo() -> None:
    print()
    info("1) Balken mit bekannter Gesamtgröße:")
    with ProgressBox("Demo-Download", total=10 * 1024 * 1024, unit="B",
                     status="beispiel.iso") as bar:
        while bar.current < bar.total:
            time.sleep(0.03)
            bar.advance(256 * 1024)
        bar.finish("Fertig.")
    print()
    info("2) Balken ohne bekannte Gesamtgröße:")
    with ProgressBox("Unbekannte Größe", total=None, unit="B",
                     status="Daten werden empfangen ...") as bar:
        for _ in range(70):
            time.sleep(0.04)
            bar.advance(128 * 1024)
        bar.finish("Übertragung beendet.")
    print()
    pause()


def misc_about() -> None:
    print()
    draw_box([
        TITLE,
        "",
        "Menügerüst mit Untermenüs und Fortschrittsbox.",
        f"Python {sys.version.split()[0]} auf {sys.platform}",
        f"Unicode: {'ja' if UNICODE else 'nein'}   Farben: {'ja' if COLOR else 'nein'}",
    ], title="INFO", width=WIDE_WIDTH)
    print()
    pause()


# --------------------------------------------------------------------------
# Aktionen - tiefere Ebenen (Beispiele)
# --------------------------------------------------------------------------

def logs_tail() -> None:
    run_steps("Log wird gelesen", [("letzte 50 Zeilen holen", 0.6)])
    info("Hier würden die letzten 50 Zeilen stehen.")
    pause()


def logs_errors() -> None:
    run_steps("Log wird gefiltert", [("nach WARN/ERROR suchen", 0.8)])
    info("3 Fehler und 7 Warnungen gefunden.")
    pause()


def logs_archive() -> None:
    if not confirm_box("Die aktuelle Logdatei wird gepackt und geleert."):
        info("Abgebrochen.")
        pause()
        return
    run_steps("Archivierung", [("packen", 0.7), ("Log leeren", 0.3)])
    info("Log archiviert.")
    pause()


def plugins_all() -> None:
    install_plugins()


def plugins_pick() -> None:
    print()
    name = ask("  Name des Plugins: ").strip()
    if not name or name == "q":
        return
    run_steps(f"{name} wird installiert", [("herunterladen", 0.8),
                                           ("einrichten", 0.5)])
    info(f"{name} installiert.")
    pause()


def plugins_refresh() -> None:
    run_steps("Pluginliste", [("Quelle abfragen", 0.9)])
    info("Liste aktualisiert.")
    pause()


def net_ping() -> None:
    run_steps("Ping", [("3 Pakete senden", 1.0)])
    info("Antwortzeit: 24 ms (0 % Verlust).")
    pause()


def net_ports() -> None:
    run_steps("Portprüfung", [("25565 testen", 0.6), ("3306 testen", 0.6)])
    info("25565 offen, 3306 geschlossen.")
    pause()


def disk_usage() -> None:
    run_steps("Speicher wird geprüft", [("Verzeichnisse messen", 1.0)])
    info("Serverordner belegt 12.4 GB.")
    pause()


def disk_clean() -> None:
    if not confirm_box("Alte Backups älter als 30 Tage werden gelöscht."):
        info("Abgebrochen.")
        pause()
        return
    run_steps("Aufräumen", [("Backups prüfen", 0.6), ("löschen", 0.8)])
    info("4.1 GB freigegeben.")
    pause()


# --------------------------------------------------------------------------
# Menüstruktur
# --------------------------------------------------------------------------

TITLE = "SchnuBbys Repack"

# (Name, Beschreibung, ((Untereintrag, Beschreibung, Aktion), ...))
# Ein Eintrag ist (Name, Beschreibung, Ziel).
#   Ziel = Funktion          -> Aktion, wird beim Auswählen ausgeführt
#   Ziel = Tupel/Liste       -> Untermenü mit weiteren Einträgen
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
    ("Install", "Install a Server", (
        ("Server", "Serverpaket herunterladen", install_server),
        ("Plugins", "Plugins verwalten", (
            ("Alle", "Standardpaket installieren", plugins_all),
            ("Einzeln", "ein bestimmtes Plugin", plugins_pick),
            ("Liste", "Pluginliste aktualisieren", plugins_refresh),
        )),
        ("Update", "Vorhandene Version aktualisieren", install_update),
        ("Config", "Konfiguration neu schreiben", install_config),
        ("Remove", "Installation entfernen", install_uninstall),
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


def submenu(path, entries) -> str:
    """Zeigt eine Menüebene. ``path`` ist die Liste der Namen bis hierher.

    Ruft sich für verschachtelte Einträge selbst auf.
    Rückgabe: 'back' (eine Ebene hoch) oder 'quit'.
    """
    while True:
        clear_screen()
        draw_box([TITLE + "   /  " + "  /  ".join(path)])
        print()
        pad = max(len(sub) for sub, _, _ in entries)
        for i, (sub, desc, target) in enumerate(entries, start=1):
            mark = SUB_SIGN if is_submenu(target) else " "
            print(f"   {C.CYAN}{i}{C.RESET}) {mark} {sub:<{pad}}  "
                  f"{C.DIM}{desc}{C.RESET}")
        print()
        print(f"   {C.CYAN}b{C.RESET})  zurück")
        print(f"   {C.CYAN}q{C.RESET})  beenden")
        print()

        choice = ask("  Auswahl: ").strip().lower()
        if choice in ("b", "0", ""):
            return "back"
        if choice == "q":
            return "quit"
        if choice.isdigit() and 1 <= int(choice) <= len(entries):
            sub, _desc, target = entries[int(choice) - 1]
            if is_submenu(target):
                if submenu(path + [sub], target) == "quit":
                    return "quit"
            else:
                target()
            continue
        warning_box(f"Ungültige Eingabe: {choice!r}", title="HINWEIS")


def main_menu() -> None:
    while True:
        clear_screen()
        draw_box([TITLE])
        print()
        for i, (name, label, _) in enumerate(MENU, start=1):
            print(f"   {C.CYAN}{i}{C.RESET})  {name:<7} {C.DIM}{label}{C.RESET}")
        print()
        print(f"   {C.CYAN}w{C.RESET})  Warnungsbox (Demo)")
        print(f"   {C.CYAN}p{C.RESET})  Fortschrittsbox (Demo)")
        print(f"   {C.CYAN}q{C.RESET})  beenden")
        print()

        choice = ask("  Auswahl: ").strip().lower()
        if choice in ("q", "0"):
            print("  Tschüss.")
            return
        if choice == "":
            continue
        if choice == "w":
            warning_box("Dies ist eine Beispiel-Warnung.\n"
                        "So sieht die Warnungsbox aus.")
            continue
        if choice == "p":
            misc_progress_demo()
            continue
        if choice.isdigit() and 1 <= int(choice) <= len(MENU):
            name, _label, entries = MENU[int(choice) - 1]
            if submenu([name], entries) == "quit":
                print("  Tschüss.")
                return
            continue
        warning_box(f"Ungültige Eingabe: {choice!r}", title="HINWEIS")


if __name__ == "__main__":
    main_menu()
