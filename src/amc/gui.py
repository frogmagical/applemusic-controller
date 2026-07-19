"""tkinter GUI: now-playing display with seek bar, transport,
key/pitch sliders, device selection and Apple Music output routing."""

from __future__ import annotations

import time
import tkinter as tk
import tkinter.font as tkfont
from tkinter import messagebox, ttk

from . import devices as dev
from . import routing
from .dsp import StretchEngine
from .lyrics import LyricsClient
from .pipeline import AudioPipeline
from .seek import AppleMusicSeeker
from .smtc import SmtcClient, format_timedelta

BG = "#1e1e1e"
FG = "#e8e8e8"
FG_DIM = "#9a9a9a"
ACCENT = "#e8b93c"

POLL_MS = 500
SEEK_SUPPRESS_S = 1.5  # ignore SMTC position for a moment after a seek


def _set_window_icon(root: tk.Tk) -> None:
    """PyInstaller's --icon only brands the exe file; the running window
    needs the .ico set explicitly (bundled via --add-data when frozen)."""
    import os
    import sys

    candidates = []
    bundle_dir = getattr(sys, "_MEIPASS", None)
    if bundle_dir:
        candidates.append(os.path.join(bundle_dir, "icon.ico"))
    candidates.append(os.path.normpath(os.path.join(
        os.path.dirname(__file__), "..", "..", "assets", "icon.ico")))
    for path in candidates:
        if os.path.exists(path):
            try:
                root.iconbitmap(path)
            except tk.TclError:
                continue
            return

CONTENT_WIDTH = 320          # fixed inner width for the text area (px)
SCROLL_WAIT_MS = 3000        # delay before the one-shot overflow scroll
SCROLL_STEP_MS = 33
SCROLL_CHARS_PER_S = 2.0     # full-width chars per second (= 4 half-width)


class ScrollingLabel(tk.Canvas):
    """Fixed-width one-line label. When the text overflows, it scrolls
    left exactly once (wait 3 s, scroll until every glyph has left the
    canvas, snap back) and then stays static until the text changes."""

    def __init__(self, parent: tk.Misc, width: int, font, fill: str) -> None:
        self._font = tkfont.Font(font=font)
        height = self._font.metrics("linespace") + 2
        super().__init__(parent, width=width, height=height, bg=BG,
                         highlightthickness=0, bd=0)
        self._width = width
        self._y = height // 2
        self._text = None
        self._text_width = 0
        self._px_per_step = (SCROLL_CHARS_PER_S * self._font.measure("あ")
                             * SCROLL_STEP_MS / 1000.0)
        self._after_id: str | None = None
        self._item = self.create_text(0, self._y, anchor="w", font=font,
                                      fill=fill, text="")

    def set_text(self, text: str) -> None:
        if text == self._text:
            return
        self._text = text
        self._cancel()
        self.itemconfig(self._item, text=text)
        self.coords(self._item, 0, self._y)
        self._text_width = self._font.measure(text)
        if self._text_width > self._width:
            self._after_id = self.after(SCROLL_WAIT_MS, self._step)

    def _step(self) -> None:
        x = self.coords(self._item)[0] - self._px_per_step
        if x <= -self._text_width:  # every glyph has scrolled out
            self.coords(self._item, 0, self._y)
            self._after_id = None
            return
        self.coords(self._item, x, self._y)
        self._after_id = self.after(SCROLL_STEP_MS, self._step)

    def _cancel(self) -> None:
        if self._after_id is not None:
            self.after_cancel(self._after_id)
            self._after_id = None


LYRICS_FONT_SIZE = 12
LYRICS_FONT_MIN = 8
LYRICS_FONT_MAX = 48


class LyricsWindow(tk.Toplevel):
    """Resizable scrollable lyrics viewer, opened at the main window's size,
    with fixed zoom buttons in the bottom-right corner."""

    def __init__(self, master: tk.Misc, width: int, height: int) -> None:
        super().__init__(master, bg=BG)
        self.geometry(f"{width}x{height}")
        self.minsize(240, 180)
        _set_window_icon(self)

        self._font = tkfont.Font(family="Yu Gothic UI", size=LYRICS_FONT_SIZE)

        scrollbar = ttk.Scrollbar(self)
        scrollbar.pack(side="right", fill="y")
        self.text = tk.Text(self, bg=BG, fg=FG, font=self._font,
                            wrap="word", bd=0, highlightthickness=0,
                            padx=14, pady=12, state="disabled",
                            yscrollcommand=scrollbar.set)
        self.text.pack(side="left", fill="both", expand=True)
        scrollbar.config(command=self.text.yview)

        # Fixed zoom overlay (bottom-right, does not scroll with the text).
        zoom = ttk.Frame(self)
        ttk.Button(zoom, text="🔍−", width=4,
                   command=lambda: self._zoom(-2)).pack(side="left")
        ttk.Button(zoom, text="🔍+", width=4,
                   command=lambda: self._zoom(+2)).pack(side="left", padx=(4, 0))
        zoom.place(relx=1.0, rely=1.0, anchor="se", x=-24, y=-12)

        # Keyboard scrolling (the mouse wheel works out of the box).
        for key, (amount, unit) in {"<Up>": (-1, "units"),
                                    "<Down>": (1, "units"),
                                    "<Prior>": (-1, "pages"),
                                    "<Next>": (1, "pages"),
                                    "<Home>": (None, "top"),
                                    "<End>": (None, "bottom")}.items():
            self.bind(key, self._scroller(amount, unit))

    def _zoom(self, delta: int) -> None:
        size = max(LYRICS_FONT_MIN,
                   min(LYRICS_FONT_MAX, self._font.cget("size") + delta))
        self._font.configure(size=size)

    def _scroller(self, amount, unit):
        def handler(_evt):
            if unit == "top":
                self.text.yview_moveto(0.0)
            elif unit == "bottom":
                self.text.yview_moveto(1.0)
            else:
                self.text.yview_scroll(amount, unit)
            return "break"
        return handler

    def show(self, track_title: str, lyrics: str) -> None:
        self.title(f"Lyrics — {track_title}")
        self.text.config(state="normal")
        self.text.delete("1.0", "end")
        self.text.insert("1.0", lyrics)
        self.text.config(state="disabled")
        self.text.yview_moveto(0.0)
        self.deiconify()
        self.focus_set()


class App:
    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        root.title("Apple Music Controller")
        root.configure(bg=BG)
        root.resizable(False, False)
        _set_window_icon(root)

        self.engine = StretchEngine()
        self.pipeline: AudioPipeline | None = None
        self.smtc = SmtcClient()
        self.smtc.start()
        self.seeker = AppleMusicSeeker()
        try:
            self.router: routing.AppleMusicRouter | None = routing.AppleMusicRouter()
        except Exception:
            self.router = None

        self._seek_dragging = False
        self._seek_suppress_until = 0.0

        self.lyrics_client = LyricsClient()
        self._lyrics_window: LyricsWindow | None = None
        self._current_lyrics: str | None = None
        self._shown_lyrics_track: tuple[str, str] | None = None

        self._build_style()
        self._build_now_playing()
        self._build_sliders()
        self._build_devices()
        self._build_footer()
        self._init_route_state()

        # Freeze the window at its natural size: text is drawn on
        # fixed-width canvases, so nothing can push the layout around.
        root.update_idletasks()
        width, height = root.winfo_reqwidth(), root.winfo_reqheight()
        root.geometry(f"{width}x{height}")
        root.minsize(width, height)
        root.maxsize(width, height)

        self._poll()

        root.protocol("WM_DELETE_WINDOW", self._on_close)

    # -- UI construction ---------------------------------------------------

    def _build_style(self) -> None:
        style = ttk.Style(self.root)
        style.theme_use("clam")
        style.configure(".", background=BG, foreground=FG, fieldbackground="#2a2a2a")
        style.configure("TLabel", background=BG, foreground=FG)
        style.configure("Dim.TLabel", foreground=FG_DIM)
        style.configure("Title.TLabel", font=("Yu Gothic UI", 12, "bold"))
        style.configure("Value.TLabel", foreground=ACCENT, font=("Consolas", 11, "bold"))
        style.configure("TButton", background="#2f2f2f", foreground=FG, borderwidth=0)
        style.map("TButton", background=[("active", "#3d3d3d")])
        style.configure("Horizontal.TScale", background=BG, troughcolor="#2a2a2a")
        style.configure("TCombobox", fieldbackground="#2a2a2a", background="#2f2f2f",
                        foreground=FG, arrowcolor=FG)
        style.configure("TCheckbutton", background=BG, foreground=FG)
        style.map("TCheckbutton", background=[("active", BG)])

    def _section(self) -> ttk.Frame:
        frame = ttk.Frame(self.root, padding=(14, 8))
        frame.pack(fill="x")
        return frame

    def _build_now_playing(self) -> None:
        f = self._section()
        self.var_time = tk.StringVar(value="0:00 / 0:00")
        self.label_title = ScrollingLabel(
            f, CONTENT_WIDTH, ("Yu Gothic UI", 12, "bold"), FG)
        self.label_title.pack(anchor="w")
        self.label_title.set_text("—")
        self.label_artist = ScrollingLabel(
            f, CONTENT_WIDTH, ("Yu Gothic UI", 9), FG_DIM)
        self.label_artist.pack(anchor="w")
        self.label_artist.set_text("")

        self.var_seek = tk.DoubleVar(value=0.0)
        self.seek_scale = ttk.Scale(f, from_=0.0, to=1.0, variable=self.var_seek)
        self.seek_scale.pack(fill="x", pady=(6, 0))
        self.seek_scale.bind("<ButtonPress-1>", self._on_seek_press)
        self.seek_scale.bind("<ButtonRelease-1>", self._on_seek_release)

        row = ttk.Frame(f)
        row.pack(fill="x", pady=(6, 0))
        ttk.Button(row, text="⏮", width=4,
                   command=self.smtc.skip_previous).pack(side="left")
        ttk.Button(row, text="⏯", width=4,
                   command=self.smtc.toggle_play_pause).pack(side="left", padx=4)
        ttk.Button(row, text="⏭", width=4,
                   command=self.smtc.skip_next).pack(side="left")
        self.btn_lyrics = ttk.Button(row, text="Lyrics", width=7,
                                     command=self._open_lyrics,
                                     state="disabled")
        self.btn_lyrics.pack(side="left", padx=(10, 0))
        ttk.Label(row, textvariable=self.var_time,
                  style="Dim.TLabel").pack(side="right")

    def _slider_row(self, parent: ttk.Frame, label: str, var: tk.DoubleVar,
                    lo: float, hi: float, fmt, on_change, on_reset) -> None:
        head = ttk.Frame(parent)
        head.pack(fill="x")
        ttk.Label(head, text=label).pack(side="left")
        value_label = ttk.Label(head, style="Value.TLabel")
        value_label.pack(side="left", padx=8)
        ttk.Button(head, text="⟳", width=3, command=on_reset).pack(side="right")

        def update(_evt=None):
            value_label.config(text=fmt(var.get()))
            on_change(var.get())

        scale = ttk.Scale(parent, from_=lo, to=hi, variable=var, command=update)
        scale.pack(fill="x", pady=(0, 6))
        value_label.config(text=fmt(var.get()))

    def _build_sliders(self) -> None:
        f = self._section()
        self.var_semitones = tk.DoubleVar(value=0)
        self.var_cents = tk.DoubleVar(value=0)

        def set_semitones(v: float) -> None:
            v = round(v)
            self.var_semitones.set(v)
            self.engine.set_semitones(v)

        def reset_semitones() -> None:
            self.var_semitones.set(0)
            set_semitones(0)

        def set_cents(v: float) -> None:
            v = round(v)
            self.var_cents.set(v)
            self.engine.set_cents(v)

        def reset_cents() -> None:
            self.var_cents.set(0)
            set_cents(0)

        self._slider_row(f, "Transpose", self.var_semitones, -12, 12,
                         lambda v: f"{round(v):+d} st", set_semitones, reset_semitones)
        self._slider_row(f, "Pitch", self.var_cents, -100, 100,
                         lambda v: f"{round(v):+d} ct", set_cents, reset_cents)

    def _build_devices(self) -> None:
        f = self._section()
        self.capture_devices = dev.list_capture_devices()
        self.output_devices = dev.list_output_devices()

        ttk.Label(f, text="Capture (virtual cable)", style="Dim.TLabel").pack(anchor="w")
        self.combo_capture = ttk.Combobox(
            f, state="readonly", values=[d.name for d in self.capture_devices])
        self.combo_capture.pack(fill="x", pady=(0, 4))
        guessed = dev.guess_capture_device()
        if guessed is not None:
            for i, d in enumerate(self.capture_devices):
                if d.index == guessed.index:
                    self.combo_capture.current(i)
                    break

        ttk.Label(f, text="Output", style="Dim.TLabel").pack(anchor="w")
        self.combo_output = ttk.Combobox(
            f, state="readonly", values=[d.name for d in self.output_devices])
        self.combo_output.pack(fill="x")
        default_out = dev.default_output_device()
        if default_out is not None:
            for i, d in enumerate(self.output_devices):
                if d.index == default_out.index:
                    self.combo_output.current(i)
                    break

        self.var_route = tk.BooleanVar(value=False)
        self.check_route = ttk.Checkbutton(
            f, text="Route Apple Music to the capture cable",
            variable=self.var_route, command=self._on_route_toggle)
        self.check_route.pack(anchor="w", pady=(6, 0))
        if self.router is None:
            self.check_route.state(["disabled"])

    def _build_footer(self) -> None:
        f = self._section()
        self.btn_start = ttk.Button(f, text="▶ Start processing",
                                    command=self._toggle_pipeline)
        self.btn_start.pack(fill="x")
        self.var_status = tk.StringVar(value="stopped")
        ttk.Label(f, textvariable=self.var_status, style="Dim.TLabel").pack(
            anchor="w", pady=(4, 0))

    # -- seek bar ----------------------------------------------------------

    def _on_seek_press(self, _evt) -> None:
        self._seek_dragging = True

    def _on_seek_release(self, _evt) -> None:
        self._seek_dragging = False
        self._seek_suppress_until = time.time() + SEEK_SUPPRESS_S
        self.seeker.seek(self.var_seek.get())

    # -- routing toggle ----------------------------------------------------

    def _selected_capture_name(self) -> str | None:
        index = self.combo_capture.current()
        if index < 0:
            return None
        return self.capture_devices[index].name

    def _init_route_state(self) -> None:
        if self.router is None:
            return
        try:
            self.var_route.set(bool(self.router.current_endpoint()))
        except Exception:
            pass  # e.g. Apple Music not running yet

    def _on_route_toggle(self) -> None:
        if self.router is None:
            return
        try:
            if self.var_route.get():
                capture_name = self._selected_capture_name()
                if capture_name is None:
                    raise routing.RoutingError("Select a capture device first")
                hint = routing.capture_driver_hint(capture_name)
                endpoint = routing.find_render_endpoint_by_driver(hint)
                if endpoint is None:
                    raise routing.RoutingError(
                        f"No render endpoint matching '{hint}' found")
                self.router.route_to(endpoint[0])
                self.var_status.set(f"Apple Music → {endpoint[1]}")
            else:
                self.router.reset()
                self.var_status.set("Apple Music → system default")
        except Exception as exc:
            self.var_route.set(not self.var_route.get())  # revert
            messagebox.showerror("Routing", str(exc))

    # -- lyrics ------------------------------------------------------------

    def _poll_lyrics(self, np_) -> None:
        if not (np_.found and np_.title):
            self._current_lyrics = None
            self.btn_lyrics.state(["disabled"])
            return
        result = self.lyrics_client.poll(
            np_.title, np_.artist, np_.duration.total_seconds())
        self._current_lyrics = result if isinstance(result, str) else None
        self.btn_lyrics.state(
            ["!disabled"] if self._current_lyrics else ["disabled"])

        # Follow track changes while the viewer is open.
        track = (np_.title, np_.artist)
        if (self._current_lyrics
                and self._lyrics_window is not None
                and self._lyrics_window.winfo_exists()
                and self._shown_lyrics_track != track):
            self._lyrics_window.show(np_.title, self._current_lyrics)
            self._shown_lyrics_track = track

    def _open_lyrics(self) -> None:
        if self._current_lyrics is None:
            return
        np_ = self.smtc.now_playing
        if self._lyrics_window is None or not self._lyrics_window.winfo_exists():
            self._lyrics_window = LyricsWindow(
                self.root, self.root.winfo_width(), self.root.winfo_height())
        self._lyrics_window.show(np_.title, self._current_lyrics)
        self._shown_lyrics_track = (np_.title, np_.artist)

    # -- pipeline ----------------------------------------------------------

    def _toggle_pipeline(self) -> None:
        if self.pipeline is not None:
            self.pipeline.stop()
            self.pipeline = None
            self.btn_start.config(text="▶ Start processing")
            self.var_status.set("stopped")
            return

        cap_i = self.combo_capture.current()
        out_i = self.combo_output.current()
        if cap_i < 0 or out_i < 0:
            messagebox.showwarning(
                "Devices", "Select both a capture device and an output device.")
            return
        capture = self.capture_devices[cap_i]
        output = self.output_devices[out_i]
        try:
            self.pipeline = AudioPipeline(
                self.engine,
                input_device=capture.index,
                output_device=output.index,
                channels=min(2, capture.max_input_channels),
            )
            self.pipeline.start()
        except Exception as exc:
            self.pipeline = None
            messagebox.showerror("Audio error", str(exc))
            return
        self.btn_start.config(text="■ Stop processing")

    # -- polling -----------------------------------------------------------

    def _poll(self) -> None:
        np_ = self.smtc.now_playing
        if np_.found:
            self.label_title.set_text(np_.title or "—")
            artist = np_.artist
            if np_.album:
                artist = f"{artist} — {np_.album}" if artist else np_.album
            self.label_artist.set_text(artist)
            self.var_time.set(
                f"{format_timedelta(np_.position)} / {format_timedelta(np_.duration)}"
                + ("" if np_.is_playing else f"  ({np_.status})"))
            duration_s = np_.duration.total_seconds()
            if (duration_s > 0 and not self._seek_dragging
                    and time.time() > self._seek_suppress_until):
                self.seek_scale.configure(to=duration_s)
                self.var_seek.set(min(np_.position.total_seconds(), duration_s))
        else:
            self.label_title.set_text("Apple Music not detected")
            self.label_artist.set_text("")
            self.var_time.set("-:-- / -:--")
        self._poll_lyrics(np_)

        if self.pipeline is not None:
            s = self.pipeline.stats
            self.var_status.set(
                f"running  latency {s['latency_seconds']*1000:4.0f} ms"
                f"  underruns {s['underruns']:.0f}  skips {s['skips']:.0f}")
        self.root.after(POLL_MS, self._poll)

    def _on_close(self) -> None:
        if self.pipeline is not None:
            self.pipeline.stop()
        self.smtc.stop()
        self.root.destroy()


def main() -> None:
    root = tk.Tk()
    App(root)
    root.mainloop()


if __name__ == "__main__":
    main()
