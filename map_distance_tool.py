"""Small clickable PUBG map distance floating window."""

import ctypes
import json
import math
import os
import tkinter as tk
from tkinter import messagebox

import keyboard
import pyautogui


REFERENCE = (2560, 1600)
MODES = {
    "8x8": (20.0, 42.1, 80.0, 160.0, 320.0),
    "4x4": (40.0, 84.0, 160.0, 320.0, 640.0),
    "3x3": (53.3, 112.3, 220.7, 426.7, 855.6),
    "2x2": (80.0, 168.4, 320.0, 640.0, 1280.0),
}
ZOOMS = ("未放大", "放大1次", "放大2次", "放大3次", "放大4次")
BG, PANEL, CARD, BLUE, CYAN, TEXT, MUTED, RED, GREEN = (
    "#17202d", "#27354a", "#34445c", "#2f75df", "#52d5ff", "#f3f6fb", "#aab8ca", "#ef5350", "#29c477"
)


class MapDistanceTool:
    def __init__(self):
        if hasattr(ctypes, "windll"):
            try:
                ctypes.windll.user32.SetProcessDPIAware()
            except Exception:
                pass
        self.width, self.height = 0, 0
        self.screen_scale = 1.0
        self.update_screen_metrics()
        self.mode, self.zoom = "8x8", 0
        self.measure_hotkey, self.cycle_hotkey = "ctrl+h", "f6"
        self.keys_down, self.measuring, self.start = set(), False, None
        self.hotkey_hook = None
        self.config_path = os.path.join(os.environ.get("APPDATA", os.path.expanduser("~")), "PUBGMapDistanceTool", "settings.json")
        self.load_config()

        self.root = tk.Tk()
        self.root.overrideredirect(True)
        self.root.attributes("-topmost", True)
        self.root.attributes("-alpha", 0.90)
        self.root.configure(bg=BG)
        self.root.geometry("260x170+30+80")
        self.build_panel()
        self.build_overlay()
        self.install_hotkey_hook()
        self.root.protocol("WM_DELETE_WINDOW", self.close)

    def load_config(self):
        try:
            with open(self.config_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            self.mode = data.get("mode", self.mode) if data.get("mode", self.mode) in MODES else self.mode
            self.zoom = max(0, min(4, int(data.get("zoom", self.zoom))))
            self.measure_hotkey = data.get("measure_hotkey", self.measure_hotkey)
            self.cycle_hotkey = data.get("cycle_hotkey", self.cycle_hotkey)
        except (OSError, ValueError, TypeError):
            pass

    def save_config(self):
        try:
            os.makedirs(os.path.dirname(self.config_path), exist_ok=True)
            with open(self.config_path, "w", encoding="utf-8") as f:
                json.dump({"mode": self.mode, "zoom": self.zoom, "measure_hotkey": self.measure_hotkey, "cycle_hotkey": self.cycle_hotkey}, f, ensure_ascii=False, indent=2)
        except OSError:
            pass

    def build_panel(self):
        self.panel = tk.Frame(self.root, bg=PANEL, highlightthickness=0, bd=0)
        self.panel.pack(fill="both", expand=True, padx=2, pady=2)
        header = tk.Frame(self.panel, bg=PANEL)
        header.pack(fill="x", padx=9, pady=(5, 0))
        header.bind("<Button-1>", self.begin_drag)
        header.bind("<B1-Motion>", self.drag)
        tk.Label(header, text="PUBG 地图测距", bg=PANEL, fg=TEXT, font=("Microsoft YaHei UI", 10, "bold")).pack(side="left")
        tk.Button(header, text="×", command=self.close, bg=RED, fg="white", bd=0, width=2, font=("Arial", 11, "bold")).pack(side="right")
        if header.winfo_children():
            header.winfo_children()[0].bind("<Button-1>", self.begin_drag)
            header.winfo_children()[0].bind("<B1-Motion>", self.drag)
        self.mode_var = tk.StringVar(value=self.mode)
        self.zoom_var = tk.StringVar(value=ZOOMS[self.zoom])
        row = tk.Frame(self.panel, bg=PANEL)
        row.pack(fill="x", padx=9, pady=5)
        tk.Label(row, text="倍率", bg=PANEL, fg=MUTED).pack(side="left")
        self.mode_menu = tk.OptionMenu(row, self.mode_var, *MODES, command=self.set_mode)
        self.mode_menu.config(bg=CARD, fg=TEXT, activebackground=BLUE, activeforeground="white", bd=0, highlightthickness=0, width=5)
        self.mode_menu.pack(side="left", padx=5)
        self.zoom_menu = tk.OptionMenu(row, self.zoom_var, *ZOOMS, command=self.set_zoom_name)
        self.zoom_menu.config(bg=CARD, fg=TEXT, activebackground=BLUE, activeforeground="white", bd=0, highlightthickness=0, width=7)
        self.zoom_menu.pack(side="left")
        controls = tk.Frame(self.panel, bg=PANEL)
        controls.pack(fill="x", padx=9)
        self.status = tk.Label(controls, text="就绪", bg=PANEL, fg=CYAN, anchor="w")
        self.status.pack(side="left", fill="x", expand=True)
        tk.Button(controls, text="设置", command=self.open_settings, bg=CARD, fg=TEXT, bd=0, padx=7).pack(side="right")
        self.ratio = tk.Label(self.panel, bg=PANEL, fg=MUTED, anchor="w")
        self.ratio.pack(fill="x", padx=9, pady=(5, 7))
        self.refresh_panel()

    def build_overlay(self):
        self.overlay = tk.Toplevel(self.root)
        self.overlay.overrideredirect(True)
        self.overlay.attributes("-topmost", True)
        self.transparent = "#010101"
        self.overlay.configure(bg=self.transparent)
        self.overlay.attributes("-transparentcolor", self.transparent)
        self.overlay.geometry(f"{self.width}x{self.height}+0+0")
        self.canvas = tk.Canvas(self.overlay, bg=self.transparent, highlightthickness=0)
        self.canvas.pack(fill="both", expand=True)
        self.overlay.withdraw()
        self.overlay.update_idletasks()
        hwnd = ctypes.windll.user32.GetParent(self.overlay.winfo_id()) if hasattr(ctypes, "windll") else 0
        if hwnd:
            style = ctypes.windll.user32.GetWindowLongW(hwnd, -20)
            ctypes.windll.user32.SetWindowLongW(hwnd, -20, style | 0x80000 | 0x20 | 0x8000000 | 0x80)

    def install_hotkey_hook(self):
        self.hotkey_hook = keyboard.hook(self.on_key_event)

    @staticmethod
    def normalize_key(name):
        return {"left ctrl": "ctrl", "right ctrl": "ctrl", "left shift": "shift", "right shift": "shift", "left alt": "alt", "right alt": "alt"}.get(name.lower(), name.lower())

    def combo_keys(self, combo):
        return {self.normalize_key(key.strip()) for key in combo.split("+") if key.strip()}

    def on_key_event(self, event):
        key = self.normalize_key(event.name)
        required = self.combo_keys(self.measure_hotkey)
        cycle = self.combo_keys(self.cycle_hotkey)
        if event.event_type == "down":
            was_ready = required.issubset(self.keys_down)
            cycle_ready = cycle.issubset(self.keys_down)
            self.keys_down.add(key)
            if required.issubset(self.keys_down) and not was_ready:
                self.root.after(0, self.start_measurement)
            if cycle.issubset(self.keys_down) and not cycle_ready:
                self.root.after(0, lambda: self.set_zoom_name(ZOOMS[(self.zoom + 1) % len(ZOOMS)]))
        elif event.event_type == "up":
            was_measuring = self.measuring
            self.keys_down.discard(key)
            if was_measuring and not required.issubset(self.keys_down):
                self.root.after(0, self.stop_measurement)

    def current_pp100(self):
        self.update_screen_metrics()
        return MODES[self.mode][self.zoom] * self.screen_scale

    def update_screen_metrics(self):
        width, height = pyautogui.size()
        if (width, height) == (self.width, self.height):
            return
        self.width, self.height = width, height
        # Use the geometric mean so both landscape and non-16:10 screens
        # receive a stable automatic correction from the 2560x1600 reference.
        width_scale = width / REFERENCE[0]
        height_scale = height / REFERENCE[1]
        self.screen_scale = math.sqrt(width_scale * height_scale)
        if hasattr(self, "overlay"):
            self.overlay.geometry(f"{width}x{height}+0+0")

    def set_mode(self, value):
        self.mode = value
        self.save_config()
        self.refresh_panel()

    def set_zoom_name(self, value):
        self.zoom = ZOOMS.index(value)
        self.save_config()
        self.refresh_panel()

    def refresh_panel(self):
        self.ratio.config(text=f"{self.mode} · {ZOOMS[self.zoom]}    {self.current_pp100():.1f}px / 100m")
        self.status.config(text="测距中" if self.measuring else f"按住 {self.measure_hotkey} 测距")

    def start_measurement(self):
        if self.measuring:
            return
        p = pyautogui.position()
        self.start, self.measuring = (int(p.x), int(p.y)), True
        self.overlay.deiconify()
        self.overlay.lift()
        self.refresh_panel()
        self.animate()

    def stop_measurement(self):
        self.measuring, self.start = False, None
        self.canvas.delete("all")
        self.overlay.withdraw()
        self.refresh_panel()

    def animate(self):
        if not self.measuring or not self.start:
            return
        p = pyautogui.position()
        end = (int(p.x), int(p.y))
        pixels = math.hypot(end[0] - self.start[0], end[1] - self.start[1])
        meters = pixels * 100 / self.current_pp100()
        x, y = (self.start[0] + end[0]) / 2, (self.start[1] + end[1]) / 2
        self.canvas.delete("all")
        self.canvas.create_line(*self.start, *end, fill=CYAN, width=4)
        for px, py in (self.start, end):
            self.canvas.create_oval(px - 7, py - 7, px + 7, py + 7, fill=RED, outline="white", width=2)
        self.canvas.create_rectangle(x - 117, y - 30, x + 117, y + 30, fill=BG, outline=CYAN, width=2)
        self.canvas.create_text(x, y, text=f"{meters:.1f} m  |  {self.mode} {self.zoom}x\n{pixels:.0f} px", fill=TEXT, font=("Microsoft YaHei UI", 11, "bold"))
        self.root.after(16, self.animate)

    def open_settings(self):
        win = tk.Toplevel(self.root)
        win.title("快捷键设置")
        win.configure(bg=PANEL)
        win.resizable(False, False)
        win.attributes("-topmost", True)
        tk.Label(win, text="快捷键设置", bg=PANEL, fg=TEXT, font=("Microsoft YaHei UI", 12, "bold")).pack(anchor="w", padx=14, pady=(12, 8))
        fields = []
        for label, value in (("按住测距", self.measure_hotkey), ("循环倍率", self.cycle_hotkey)):
            row = tk.Frame(win, bg=PANEL)
            row.pack(fill="x", padx=14, pady=4)
            tk.Label(row, text=label, width=10, anchor="w", bg=PANEL, fg=MUTED).pack(side="left")
            entry = tk.Entry(row, width=18, bg=CARD, fg=TEXT, insertbackground=TEXT, relief="flat")
            entry.insert(0, value)
            entry.pack(side="left")
            record = tk.Button(row, text="录制", command=lambda e=entry: self.capture_hotkey(e), bg=CARD, fg=TEXT, bd=0, padx=6)
            record.pack(side="left", padx=(5, 0))
            fields.append(entry)
        tk.Label(win, text="格式示例：ctrl+h、alt+z、shift+f6", bg=PANEL, fg=MUTED).pack(anchor="w", padx=14, pady=(4, 9))
        def save():
            measure, cycle = fields[0].get().strip().lower(), fields[1].get().strip().lower()
            if not self.combo_keys(measure) or not self.combo_keys(cycle):
                messagebox.showerror("快捷键设置", "快捷键不能为空。", parent=win)
                return
            self.measure_hotkey, self.cycle_hotkey = measure, cycle
            self.save_config()
            self.refresh_panel()
            win.destroy()
        tk.Button(win, text="保存", command=save, bg=BLUE, fg="white", bd=0, padx=18, pady=5).pack(pady=(0, 12))

    def capture_hotkey(self, entry):
        entry.delete(0, tk.END)
        entry.insert(0, "请按键")
        entry.focus_set()
        entry.bind("<KeyPress>", lambda event: self.finish_capture(event, entry), add="+")

    def finish_capture(self, event, entry):
        modifier_names = {"Control_L", "Control_R", "Alt_L", "Alt_R", "Shift_L", "Shift_R"}
        if event.keysym in modifier_names:
            return "break"
        keys = []
        if event.state & 0x4:
            keys.append("ctrl")
        alt_down = False
        if hasattr(ctypes, "windll"):
            try:
                alt_down = bool(ctypes.windll.user32.GetAsyncKeyState(0x12) & 0x8000)
            except Exception:
                alt_down = False
        else:
            alt_down = bool(event.state & 0x8)
        if alt_down:
            keys.append("alt")
        if event.state & 0x1:
            keys.append("shift")
        key = event.keysym.lower()
        key = {"space": "space", "left": "left", "right": "right", "up": "up", "down": "down"}.get(key, key)
        keys.append(key)
        entry.delete(0, tk.END)
        entry.insert(0, "+".join(keys))
        entry.unbind("<KeyPress>")
        return "break"

    def begin_drag(self, event):
        self.drag_x, self.drag_y = event.x_root - self.root.winfo_x(), event.y_root - self.root.winfo_y()

    def drag(self, event):
        self.root.geometry(f"+{event.x_root - self.drag_x}+{event.y_root - self.drag_y}")

    def close(self):
        try:
            keyboard.unhook(self.hotkey_hook)
        except Exception:
            pass
        self.root.destroy()

    def run(self):
        self.root.mainloop()


if __name__ == "__main__":
    MapDistanceTool().run()
