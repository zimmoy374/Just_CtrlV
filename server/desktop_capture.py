from __future__ import annotations

import base64
import ctypes
from ctypes import wintypes
import math
import os
import queue
import random
import re
import subprocess
import time
from datetime import date, datetime
from pathlib import Path
from threading import Lock, Thread
from typing import Any
from uuid import uuid4

from . import db, settings
from .config import UPLOAD_DIR


_status_lock = Lock()
_status: dict[str, Any] = {
    "running": False,
    "registered": False,
    "hotkey": None,
    "error": None,
    "platform": os.name,
}
_started = False


def normalize_hotkey(value: str) -> str:
    aliases = {
        "control": "ctrl",
        "ctl": "ctrl",
        "option": "alt",
        "meta": "win",
        "cmd": "win",
        "command": "win",
        "windows": "win",
    }
    parts = [aliases.get(part, part) for part in re.split(r"\s*\+\s*", value.strip().lower()) if part]
    modifiers = [part for part in ["ctrl", "alt", "shift", "win"] if part in parts]
    keys = [part for part in parts if part not in {"ctrl", "alt", "shift", "win"}]
    if not modifiers or len(keys) != 1:
        raise ValueError("快捷键需要至少一个 Ctrl、Alt、Shift 或 Win 修饰键，并且只能有一个主按键")
    key = keys[0]
    if not (len(key) == 1 and key.isalnum()) and not re.fullmatch(r"f(?:[1-9]|1[0-2])", key):
        raise ValueError("主按键仅支持字母、数字或 F1–F12")
    return "+".join([*modifiers, key])


def capture_status() -> dict[str, Any]:
    with _status_lock:
        return dict(_status)


def start_desktop_capture() -> None:
    global _started
    if _started:
        return
    _started = True
    if os.name != "nt":
        _set_status(error="全局截图助手当前仅支持 Windows")
        return
    Thread(target=_run_ui, name="ctrlv-desktop-capture", daemon=True).start()


def _run_ui() -> None:
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(2)
    except Exception:
        try:
            ctypes.windll.user32.SetProcessDPIAware()
        except Exception:
            pass

    import tkinter as tk
    from PIL import Image, ImageDraw, ImageEnhance, ImageFilter, ImageGrab, ImageTk

    commands: queue.Queue[str] = queue.Queue()
    root = tk.Tk()
    root.withdraw()
    root.title("CtrlV 截图助手")
    overlay: dict[str, Any] = {"window": None}
    _set_status(running=True)
    Thread(target=_hotkey_loop, args=(commands,), name="ctrlv-hotkey", daemon=True).start()

    def poll_commands() -> None:
        try:
            while True:
                command = commands.get_nowait()
                if command == "capture" and overlay["window"] is None:
                    open_overlay()
        except queue.Empty:
            pass
        root.after(60, poll_commands)

    def open_overlay() -> None:
        window_snapshots, foreground_handle, source_captured_at = _window_snapshots()
        try:
            screenshot = ImageGrab.grab(all_screens=True).convert("RGBA")
        except Exception as exc:
            _set_status(error=f"截图失败：{exc}")
            return

        user32 = ctypes.windll.user32
        virtual_x = user32.GetSystemMetrics(76)
        virtual_y = user32.GetSystemMetrics(77)
        width, height = screenshot.size
        dimmed = ImageEnhance.Brightness(screenshot).enhance(0.43)
        window = tk.Toplevel(root)
        overlay["window"] = window
        window.overrideredirect(True)
        window.attributes("-topmost", True)
        window.configure(background="#151613")
        window.geometry(f"{width}x{height}+0+0")
        window.update_idletasks()
        try:
            user32.SetWindowPos(window.winfo_id(), -1, virtual_x, virtual_y, width, height, 0x0040)
        except Exception:
            pass

        canvas = tk.Canvas(window, width=width, height=height, highlightthickness=0, cursor="none")
        canvas.pack(fill="both", expand=True)
        background_photo = ImageTk.PhotoImage(dimmed)
        image_item = canvas.create_image(0, 0, image=background_photo, anchor="nw")
        canvas.background_photo = background_photo
        scissors_icon = _make_scissors_icon(Image, ImageDraw)
        scissors_photos = {
            angle: ImageTk.PhotoImage(
                scissors_icon.rotate(
                    -angle,
                    resample=Image.Resampling.BICUBIC,
                    expand=False,
                )
            )
            for angle in range(0, 360, 5)
        }
        pointer_x = max(0, min(width, window.winfo_pointerx() - virtual_x))
        pointer_y = max(0, min(height, window.winfo_pointery() - virtual_y))
        initial_scissors = scissors_photos[45]
        scissors_item = canvas.create_image(pointer_x, pointer_y, image=initial_scissors, anchor="center")
        state: dict[str, Any] = {
            "points": [],
            "drawing": False,
            "line": None,
            "mask": None,
            "cursor_point": (pointer_x, pointer_y),
            "heading_trail": [(pointer_x, pointer_y)],
            "scissors_angle": 45.0,
            "scissors_frame": 45,
            "scissors_photos": scissors_photos,
            "fragment_distance": 0.0,
            "fragments": [],
        }

        toolbar = tk.Frame(window, background="#20211e", padx=9, pady=8, highlightthickness=1, highlightbackground="#62635c")
        status_label = tk.Label(toolbar, text="按住鼠标，绕着想保留的内容画一圈", background="#20211e", foreground="#d8d8d1", font=("Microsoft YaHei UI", 9))
        action_frame = tk.Frame(toolbar, background="#20211e")
        retry_button = tk.Button(action_frame, text="重新画", state="disabled", command=lambda: reset_selection())
        cancel_button = tk.Button(action_frame, text="取消", command=lambda: close_overlay())
        save_button = tk.Button(action_frame, text="剪下并贴到白板", state="disabled", command=lambda: save_selection())
        status_label.pack(side="left", padx=(0, 10))
        retry_button.pack(side="left", padx=3)
        cancel_button.pack(side="left", padx=3)
        save_button.pack(side="left", padx=3)

        def set_toolbar_actions(visible: bool) -> None:
            if visible:
                if not action_frame.winfo_manager():
                    action_frame.pack(side="left")
            else:
                action_frame.pack_forget()

        def place_toolbar_near_point(x: int, y: int) -> None:
            toolbar.update_idletasks()
            left, top = _point_toolbar_position(
                (x, y),
                (toolbar.winfo_reqwidth(), toolbar.winfo_reqheight()),
                (width, height),
            )
            toolbar.place(x=left, y=top, anchor="nw")

        def place_toolbar_near_selection(bounds: tuple[int, int, int, int]) -> None:
            toolbar.update_idletasks()
            left, top = _selection_toolbar_position(
                bounds,
                (toolbar.winfo_reqwidth(), toolbar.winfo_reqheight()),
                (width, height),
            )
            toolbar.place(x=left, y=top, anchor="nw")

        set_toolbar_actions(False)
        place_toolbar_near_point(pointer_x, pointer_y)
        window.after(
            1800,
            lambda: toolbar.place_forget()
            if not state["drawing"] and not state["points"]
            else None,
        )

        def on_down(event: Any) -> None:
            reset_selection(show_hint=False)
            toolbar.place_forget()
            state["drawing"] = True
            state["points"] = [(event.x, event.y)]
            state["line"] = canvas.create_line(event.x, event.y, event.x, event.y, fill="white", width=2, dash=(7, 6), smooth=True)
            state["fragment_distance"] = 0.0
            move_scissors(event.x, event.y)
            retry_button.configure(state="normal")
            status_label.configure(text="继续绕着内容画…")

        def on_move(event: Any) -> None:
            move_scissors(event.x, event.y)
            if not state["drawing"]:
                return
            last_x, last_y = state["points"][-1]
            if ((event.x - last_x) ** 2 + (event.y - last_y) ** 2) ** 0.5 < 3:
                return
            state["points"].append((event.x, event.y))
            canvas.coords(state["line"], *[coordinate for point in state["points"] for coordinate in point])
            canvas.tag_raise(scissors_item)

        def move_scissors(x: int, y: int) -> None:
            previous_x, previous_y = state["cursor_point"]
            delta_x, delta_y = x - previous_x, y - previous_y
            distance = math.hypot(delta_x, delta_y)
            if distance >= 1.5:
                trail = state["heading_trail"]
                trail.append((x, y))
                if len(trail) > 48:
                    del trail[:-48]
                travel = 0.0
                anchor_x, anchor_y = trail[-1]
                for index in range(len(trail) - 1, 0, -1):
                    current_x, current_y = trail[index]
                    candidate_x, candidate_y = trail[index - 1]
                    travel += math.hypot(current_x - candidate_x, current_y - candidate_y)
                    anchor_x, anchor_y = candidate_x, candidate_y
                    if travel >= 26:
                        del trail[: max(0, index - 2)]
                        break
                heading_x, heading_y = x - anchor_x, y - anchor_y
                if travel >= 12 and heading_x * heading_x + heading_y * heading_y >= 64:
                    target_angle = math.degrees(math.atan2(heading_y, heading_x)) + 45
                    state["scissors_angle"] = _approach_angle(
                        state["scissors_angle"],
                        target_angle,
                    )
                    render_scissors()
            if state["drawing"] and distance:
                state["fragment_distance"] += distance
                if state["fragment_distance"] >= random.uniform(30, 46):
                    state["fragment_distance"] = 0.0
                    spawn_fragment(x, y, state["scissors_angle"] - 45)
            state["cursor_point"] = (x, y)
            canvas.coords(scissors_item, x, y)
            canvas.tag_raise(scissors_item)

        def render_scissors() -> None:
            frame = round(state["scissors_angle"] / 5) * 5 % 360
            if frame == state["scissors_frame"]:
                return
            state["scissors_frame"] = frame
            canvas.itemconfigure(scissors_item, image=state["scissors_photos"][frame])
            canvas.tag_raise(scissors_item)

        def spawn_fragment(x: int, y: int, travel_angle: float) -> None:
            if len(state["fragments"]) >= 22:
                oldest = state["fragments"].pop(0)
                canvas.delete(oldest["item"])
            radians = math.radians(travel_angle + random.choice([-1, 1]) * random.uniform(72, 112))
            distance = random.uniform(5, 9)
            origin_x = x + math.cos(radians) * distance
            origin_y = y + math.sin(radians) * distance
            size = random.uniform(2.2, 4.8)
            item = canvas.create_polygon(
                origin_x,
                origin_y - size,
                origin_x + size * 0.8,
                origin_y + size * 0.6,
                origin_x - size * 0.75,
                origin_y + size * 0.45,
                fill=random.choice(["#f6f6f0", "#deded7", "#bfc0ba"]),
                outline="#555650",
                width=1,
            )
            state["fragments"].append(
                {
                    "item": item,
                    "vx": math.cos(radians) * random.uniform(0.8, 1.8),
                    "vy": math.sin(radians) * random.uniform(0.8, 1.8) - 0.45,
                    "life": random.randint(9, 14),
                }
            )
            canvas.tag_raise(scissors_item)

        def animate_fragments() -> None:
            if overlay["window"] is not window or not window.winfo_exists():
                return
            survivors = []
            fade_colors = ["#666761", "#858680", "#a4a59f", "#c4c4bd", "#e3e3dc"]
            for fragment in state["fragments"]:
                fragment["vy"] += 0.12
                canvas.move(fragment["item"], fragment["vx"], fragment["vy"])
                fragment["life"] -= 1
                if fragment["life"] <= 0:
                    canvas.delete(fragment["item"])
                    continue
                canvas.itemconfigure(
                    fragment["item"],
                    fill=fade_colors[min(len(fade_colors) - 1, fragment["life"] // 3)],
                )
                survivors.append(fragment)
            state["fragments"] = survivors
            window.after(85, animate_fragments)

        def on_up(_event: Any) -> None:
            if not state["drawing"]:
                return
            state["drawing"] = False
            points = state["points"]
            if len(points) < 4 or _polygon_area(points) < 600:
                status_label.configure(text="选区太小，请重新画")
                save_button.configure(state="disabled")
                set_toolbar_actions(True)
                point_bounds = (
                    min((point[0] for point in points), default=_event.x),
                    min((point[1] for point in points), default=_event.y),
                    max((point[0] for point in points), default=_event.x),
                    max((point[1] for point in points), default=_event.y),
                )
                place_toolbar_near_selection(point_bounds)
                return
            canvas.coords(state["line"], *[coordinate for point in [*points, points[0]] for coordinate in point])
            mask = Image.new("L", screenshot.size, 0)
            ImageDraw.Draw(mask).polygon(points, fill=255)
            state["mask"] = mask
            preview = Image.composite(screenshot, dimmed, mask)
            preview_photo = ImageTk.PhotoImage(preview)
            canvas.itemconfigure(image_item, image=preview_photo)
            canvas.background_photo = preview_photo
            save_button.configure(state="normal")
            status_label.configure(text="选区已合拢")
            set_toolbar_actions(True)
            bounds = mask.getbbox()
            if bounds:
                place_toolbar_near_selection(bounds)

        def reset_selection(show_hint: bool = True) -> None:
            if state.get("line"):
                canvas.delete(state["line"])
            for fragment in state["fragments"]:
                canvas.delete(fragment["item"])
            state.update({"points": [], "drawing": False, "line": None, "mask": None})
            state["heading_trail"] = [state["cursor_point"]]
            state["fragments"] = []
            canvas.itemconfigure(image_item, image=background_photo)
            canvas.background_photo = background_photo
            canvas.tag_raise(scissors_item)
            retry_button.configure(state="disabled")
            save_button.configure(state="disabled")
            status_label.configure(text="按住鼠标，绕着想保留的内容画一圈")
            set_toolbar_actions(False)
            if show_hint:
                place_toolbar_near_point(*state["cursor_point"])
            else:
                toolbar.place_forget()

        def save_selection() -> None:
            mask = state.get("mask")
            if mask is None:
                return
            bounds = mask.getbbox()
            if not bounds:
                return
            save_button.configure(state="disabled")
            retry_button.configure(state="disabled")
            status_label.configure(text="正在贴到白板…")
            try:
                soft_mask = mask.filter(ImageFilter.GaussianBlur(0.55))
                piece = screenshot.crop(bounds)
                piece.putalpha(soft_mask.crop(bounds))
                source = _source_context_for_selection(
                    window_snapshots,
                    foreground_handle,
                    bounds,
                    virtual_x,
                    virtual_y,
                    source_captured_at,
                )
                _save_piece(piece, source)
                status_label.configure(text="已贴到 CtrlV 白板")
                window.after(700, close_overlay)
            except Exception as exc:
                save_button.configure(state="normal")
                retry_button.configure(state="normal")
                status_label.configure(text=f"保存失败：{exc}")

        def close_overlay() -> None:
            if overlay["window"] is not None:
                overlay["window"].destroy()
                overlay["window"] = None

        canvas.bind("<ButtonPress-1>", on_down)
        canvas.bind("<Motion>", on_move)
        canvas.bind("<ButtonRelease-1>", on_up)
        window.bind("<Escape>", lambda _event: close_overlay())
        window.bind("<Return>", lambda _event: save_selection())
        window.bind("<KeyPress-r>", lambda _event: reset_selection())
        window.bind("<KeyPress-R>", lambda _event: reset_selection())
        window.focus_force()
        animate_fragments()

    poll_commands()
    root.mainloop()


def _approach_angle(current: float, target: float, *, responsiveness: float = 0.34, max_step: float = 12.0) -> float:
    difference = (target - current + 180) % 360 - 180
    step = max(-max_step, min(max_step, difference * responsiveness))
    return (current + step) % 360


def _selection_toolbar_position(
    bounds: tuple[int, int, int, int],
    toolbar_size: tuple[int, int],
    screen_size: tuple[int, int],
    *,
    gap: int = 12,
    margin: int = 16,
) -> tuple[int, int]:
    left, top, right, bottom = bounds
    toolbar_width, toolbar_height = toolbar_size
    screen_width, screen_height = screen_size
    center_x = (left + right) / 2
    center_y = (top + bottom) / 2
    candidates = [
        (center_x - toolbar_width / 2, bottom + gap),
        (center_x - toolbar_width / 2, top - toolbar_height - gap),
        (right + gap, center_y - toolbar_height / 2),
        (left - toolbar_width - gap, center_y - toolbar_height / 2),
    ]
    for candidate_x, candidate_y in candidates:
        if (
            margin <= candidate_x
            and candidate_x + toolbar_width <= screen_width - margin
            and margin <= candidate_y
            and candidate_y + toolbar_height <= screen_height - margin
        ):
            return round(candidate_x), round(candidate_y)
    return (
        round(max(margin, min(screen_width - toolbar_width - margin, center_x - toolbar_width / 2))),
        round(max(margin, min(screen_height - toolbar_height - margin, bottom + gap))),
    )


def _point_toolbar_position(
    point: tuple[int, int],
    toolbar_size: tuple[int, int],
    screen_size: tuple[int, int],
    *,
    gap: int = 28,
    margin: int = 16,
) -> tuple[int, int]:
    x, y = point
    toolbar_width, toolbar_height = toolbar_size
    screen_width, screen_height = screen_size
    left = x + gap
    top = y + gap
    if left + toolbar_width > screen_width - margin:
        left = x - toolbar_width - gap
    if top + toolbar_height > screen_height - margin:
        top = y - toolbar_height - gap
    return (
        round(max(margin, min(screen_width - toolbar_width - margin, left))),
        round(max(margin, min(screen_height - toolbar_height - margin, top))),
    )


def _make_scissors_icon(Image: Any, ImageDraw: Any) -> Any:
    scale = 4
    size = 52
    icon = Image.new("RGBA", (size * scale, size * scale), (0, 0, 0, 0))
    draw = ImageDraw.Draw(icon)
    pivot = (26.0, 26.0)
    spread = 0.0

    def point(x: float, y: float) -> tuple[int, int]:
        return round(x * scale), round(y * scale)

    def rotate(value: tuple[float, float], angle: float) -> tuple[float, float]:
        radians = math.radians(angle)
        delta_x, delta_y = value[0] - pivot[0], value[1] - pivot[1]
        return (
            pivot[0] + delta_x * math.cos(radians) - delta_y * math.sin(radians),
            pivot[1] + delta_x * math.sin(radians) + delta_y * math.cos(radians),
        )

    def shape(color: tuple[int, int, int, int], width: float) -> None:
        stroke = max(1, round(width * scale))
        upper_tip = rotate((41.5, 18.1), spread)
        lower_tip = rotate((33.9, 10.6), -spread)
        upper_ring = rotate((18.7, 24.8), spread)
        lower_ring = rotate((26.6, 33.6), -spread)
        draw.line([point(*upper_ring), point(*pivot), point(*upper_tip)], fill=color, width=stroke, joint="curve")
        draw.line([point(*lower_ring), point(*pivot), point(*lower_tip)], fill=color, width=stroke, joint="curve")
        ring_radius = 4.55
        draw.ellipse(
            [
                *point(upper_ring[0] - ring_radius, upper_ring[1] - ring_radius),
                *point(upper_ring[0] + ring_radius, upper_ring[1] + ring_radius),
            ],
            outline=color,
            width=stroke,
        )
        draw.ellipse(
            [
                *point(lower_ring[0] - ring_radius, lower_ring[1] - ring_radius),
                *point(lower_ring[0] + ring_radius, lower_ring[1] + ring_radius),
            ],
            outline=color,
            width=stroke,
        )

    shape((255, 255, 255, 205), 4.7)
    shape((24, 24, 22, 255), 2.8)
    return icon.resize((size, size), Image.Resampling.LANCZOS)


def _hotkey_loop(commands: queue.Queue[str]) -> None:
    user32 = ctypes.windll.user32
    message = wintypes.MSG()
    user32.PeekMessageW(ctypes.byref(message), None, 0, 0, 0)
    current: tuple[bool, str] | None = None
    registered = False
    while True:
        preferences = settings.get_capture_settings()
        desired = (bool(preferences.get("enabled")), str(preferences.get("hotkey") or "ctrl+shift+x"))
        if desired != current:
            if registered:
                user32.UnregisterHotKey(None, 1)
                registered = False
            current = desired
            if desired[0]:
                try:
                    modifiers, virtual_key = _hotkey_codes(normalize_hotkey(desired[1]))
                    registered = bool(user32.RegisterHotKey(None, 1, modifiers | 0x4000, virtual_key))
                    _set_status(
                        registered=registered,
                        hotkey=normalize_hotkey(desired[1]),
                        error=None if registered else "快捷键已被其他程序占用",
                    )
                except ValueError as exc:
                    _set_status(registered=False, hotkey=desired[1], error=str(exc))
            else:
                _set_status(registered=False, hotkey=desired[1], error=None)

        while user32.PeekMessageW(ctypes.byref(message), None, 0, 0, 1):
            if message.message == 0x0312 and message.wParam == 1:
                commands.put("capture")
            user32.TranslateMessage(ctypes.byref(message))
            user32.DispatchMessageW(ctypes.byref(message))
        time.sleep(0.08)


def _hotkey_codes(hotkey: str) -> tuple[int, int]:
    parts = hotkey.split("+")
    modifiers = 0
    modifier_codes = {"alt": 0x0001, "ctrl": 0x0002, "shift": 0x0004, "win": 0x0008}
    for part in parts[:-1]:
        modifiers |= modifier_codes[part]
    key = parts[-1]
    if len(key) == 1:
        virtual_key = ord(key.upper())
    else:
        virtual_key = 0x70 + int(key[1:]) - 1
    return modifiers, virtual_key


def _save_piece(image: Any, source: dict[str, Any] | str | None) -> str:
    preferences = settings.get_capture_settings()
    today = date.today().isoformat()
    day_key = preferences.get("lastDay") if preferences.get("dayMode") == "current" else today
    if not day_key:
        day_key = today
    card_id = str(uuid4())
    filename = f"cutout-{uuid4().hex}.png"
    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    image.save(UPLOAD_DIR / filename, "PNG", optimize=True)
    if isinstance(source, str):
        source = {"source_title": source}
    source = source or {}
    try:
        db.insert_card(
            {
                "id": card_id,
                "day_key": day_key,
                "type": "image",
                "image_filename": filename,
                "media_width": image.width,
                "media_height": image.height,
                "source_url": _limited(source.get("source_url"), 2000),
                "source_title": _limited(source.get("source_title"), 500),
                "source_app": _limited(source.get("source_app"), 160),
                "source_file": _limited(source.get("source_file"), 2000),
                "source_kind": _limited(source.get("source_kind"), 40),
                "source_captured_at": _limited(source.get("source_captured_at"), 80),
                "source_confidence": _limited(source.get("source_confidence"), 40),
                "x": 3000,
                "y": 2000,
                "position_space": "world",
                "style_seed": uuid4().hex[:10],
                "ai_status": "done",
                "ai_error": None,
                "keywords": [],
            }
        )
    except Exception:
        (UPLOAD_DIR / filename).unlink(missing_ok=True)
        raise
    return card_id


def _window_snapshots() -> tuple[list[dict[str, Any]], int, str]:
    user32 = ctypes.windll.user32
    foreground = int(user32.GetForegroundWindow() or 0)
    captured_at = datetime.now().astimezone().isoformat(timespec="seconds")
    snapshots: list[dict[str, Any]] = []

    callback_type = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)

    @callback_type
    def collect(handle: int, _parameter: int) -> bool:
        try:
            if not user32.IsWindowVisible(handle) or user32.IsIconic(handle):
                return True
            rectangle = wintypes.RECT()
            if not user32.GetWindowRect(handle, ctypes.byref(rectangle)):
                return True
            if rectangle.right - rectangle.left < 2 or rectangle.bottom - rectangle.top < 2:
                return True
            length = user32.GetWindowTextLengthW(handle)
            buffer = ctypes.create_unicode_buffer(length + 1)
            user32.GetWindowTextW(handle, buffer, len(buffer))
            title = buffer.value.strip()
            if not title:
                return True
            snapshots.append(
                {
                    "handle": int(handle),
                    "rect": (rectangle.left, rectangle.top, rectangle.right, rectangle.bottom),
                    "title": title,
                }
            )
        except Exception:
            pass
        return True

    try:
        user32.EnumWindows(collect, 0)
    except Exception:
        pass
    return snapshots, foreground, captured_at


def _source_context_for_selection(
    snapshots: list[dict[str, Any]],
    foreground_handle: int,
    bounds: tuple[int, int, int, int],
    virtual_x: int,
    virtual_y: int,
    captured_at: str,
) -> dict[str, Any]:
    center_x = virtual_x + (bounds[0] + bounds[2]) // 2
    center_y = virtual_y + (bounds[1] + bounds[3]) // 2
    selected = next(
        (
            snapshot
            for snapshot in snapshots
            if snapshot["rect"][0] <= center_x < snapshot["rect"][2]
            and snapshot["rect"][1] <= center_y < snapshot["rect"][3]
        ),
        None,
    )
    if selected is None:
        selected = next(
            (snapshot for snapshot in snapshots if snapshot["handle"] == foreground_handle),
            None,
        )
    if selected is None:
        return {
            "source_captured_at": captured_at,
            "source_kind": "unknown",
            "source_confidence": "unknown",
        }
    return _window_source_context(selected, captured_at)


def _window_source_context(snapshot: dict[str, Any], captured_at: str) -> dict[str, Any]:
    handle = int(snapshot["handle"])
    title = str(snapshot.get("title") or "").strip() or None
    executable = _window_executable(handle)
    process_name = Path(executable).stem.lower() if executable else ""
    friendly_apps = {
        "chrome": "Google Chrome",
        "msedge": "Microsoft Edge",
        "firefox": "Mozilla Firefox",
        "explorer": "文件资源管理器",
        "photos": "Microsoft 照片",
        "code": "Visual Studio Code",
        "wechat": "微信",
        "weixin": "微信",
    }
    app_name = friendly_apps.get(process_name) or (Path(executable).stem if executable else None)
    browser_names = {"chrome", "msedge", "firefox", "brave", "opera"}
    source_kind = "webpage" if process_name in browser_names else "file" if process_name == "explorer" else "application"
    context: dict[str, Any] = {
        "source_title": title,
        "source_app": app_name,
        "source_kind": source_kind,
        "source_captured_at": captured_at,
        "source_confidence": "window",
    }

    if process_name in browser_names:
        url = _read_browser_url(handle)
        if url:
            context["source_url"] = url
            context["source_confidence"] = "exact"
    elif process_name == "explorer":
        selected_file = _read_explorer_selection(handle)
        if selected_file:
            context["source_file"] = selected_file
            context["source_confidence"] = "exact"
    return context


def _window_executable(handle: int) -> str | None:
    process_id = wintypes.DWORD()
    try:
        user32 = ctypes.windll.user32
        kernel32 = ctypes.windll.kernel32
        user32.GetWindowThreadProcessId(handle, ctypes.byref(process_id))
        kernel32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
        kernel32.OpenProcess.restype = wintypes.HANDLE
        process = kernel32.OpenProcess(0x1000, False, process_id.value)
        if not process:
            return None
        try:
            size = wintypes.DWORD(32768)
            buffer = ctypes.create_unicode_buffer(size.value)
            if kernel32.QueryFullProcessImageNameW(process, 0, buffer, ctypes.byref(size)):
                return buffer.value
        finally:
            kernel32.CloseHandle(process)
    except Exception:
        pass
    return None


def _read_browser_url(handle: int) -> str | None:
    script = rf"""
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
Add-Type -AssemblyName UIAutomationClient
$root = [System.Windows.Automation.AutomationElement]::FromHandle([IntPtr]{handle})
$condition = New-Object System.Windows.Automation.PropertyCondition(
  [System.Windows.Automation.AutomationElement]::ControlTypeProperty,
  [System.Windows.Automation.ControlType]::Edit
)
$elements = $root.FindAll([System.Windows.Automation.TreeScope]::Descendants, $condition)
$fallback = ""
foreach ($element in $elements) {{
  try {{
    $pattern = $element.GetCurrentPattern([System.Windows.Automation.ValuePattern]::Pattern)
    $value = $pattern.Current.Value.Trim()
    $name = $element.Current.Name
    if (($value -match '^(https?://|file://|chrome://|edge://|about:)') -or ($value -match '^[A-Za-z0-9.-]+\.[A-Za-z]{{2,}}([/:]|$)') -or ($value -match '^(localhost|(\d{{1,3}}\.){{3}}\d{{1,3}})(:\d+)?(/|$)')) {{
      if ($name -match '地址|Address|搜索|Search|网址|URL') {{
        [Console]::Write($value)
        exit 0
      }}
      if (-not $fallback) {{ $fallback = $value }}
    }}
  }} catch {{}}
}}
[Console]::Write($fallback)
"""
    value = _run_hidden_powershell(script, timeout=2.4)
    if not value:
        return None
    value = value.strip()
    if re.fullmatch(r"[A-Za-z0-9.-]+\.[A-Za-z]{2,}(?::\d+)?(?:/.*)?", value):
        value = f"https://{value}"
    elif re.fullmatch(r"(?:localhost|(?:\d{1,3}\.){3}\d{1,3})(?::\d+)?(?:/.*)?", value):
        value = f"http://{value}"
    return value[:2000] if re.match(r"^(https?://|file://|chrome://|edge://|about:)", value) else None


def _read_explorer_selection(handle: int) -> str | None:
    script = rf"""
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$shell = New-Object -ComObject Shell.Application
$window = $shell.Windows() | Where-Object {{ [int64]$_.HWND -eq {handle} }} | Select-Object -First 1
if ($window) {{
  $items = @($window.Document.SelectedItems())
  if ($items.Count -eq 1) {{ [Console]::Write($items[0].Path) }}
}}
"""
    value = _run_hidden_powershell(script, timeout=2.0)
    return value.strip()[:2000] if value else None


def _run_hidden_powershell(script: str, *, timeout: float) -> str | None:
    encoded = base64.b64encode(script.encode("utf-16-le")).decode("ascii")
    startup = subprocess.STARTUPINFO()
    startup.dwFlags |= subprocess.STARTF_USESHOWWINDOW
    startup.wShowWindow = 0
    try:
        result = subprocess.run(
            ["powershell.exe", "-NoProfile", "-NonInteractive", "-EncodedCommand", encoded],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
            startupinfo=startup,
            creationflags=0x08000000,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    return result.stdout.strip() or None


def _limited(value: Any, length: int) -> str | None:
    text = str(value).strip() if value is not None else ""
    return text[:length] if text else None


def _polygon_area(points: list[tuple[int, int]]) -> float:
    return abs(sum(
        point[0] * points[(index + 1) % len(points)][1] - points[(index + 1) % len(points)][0] * point[1]
        for index, point in enumerate(points)
    ) / 2)


def _set_status(**changes: Any) -> None:
    with _status_lock:
        _status.update(changes)
