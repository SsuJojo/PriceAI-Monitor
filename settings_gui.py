#!/usr/bin/env python3
"""Tkinter settings and launcher UI for the PriceAI monitor."""

from __future__ import annotations

import json
import os
import queue
import re
import subprocess
import sys
import threading
import tkinter as tk
import webbrowser
from pathlib import Path
from tkinter import messagebox, ttk
from typing import Any, Callable

if os.name == "nt":
    import ctypes
    from ctypes import wintypes

    user32 = ctypes.windll.user32
    shell32 = ctypes.windll.shell32
    kernel32 = ctypes.windll.kernel32

    user32.DefWindowProcW.argtypes = [wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
    user32.DefWindowProcW.restype = ctypes.c_longlong

    WNDPROC = ctypes.WINFUNCTYPE(ctypes.c_longlong, wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM)

    WM_USER = 0x0400
    WM_TRAY = WM_USER + 100
    WM_COMMAND = 0x0111
    WM_DESTROY = 0x0002
    WM_LBUTTONUP = 0x0202
    WM_LBUTTONDBLCLK = 0x0203
    WM_RBUTTONUP = 0x0205

    NIF_MESSAGE = 0x00000001
    NIF_ICON = 0x00000002
    NIF_TIP = 0x00000004
    NIM_ADD = 0x00000000
    NIM_DELETE = 0x00000002

    MF_STRING = 0x00000000
    MF_SEPARATOR = 0x00000800
    TPM_RIGHTBUTTON = 0x0002

    IDI_APPLICATION = 32512

    class WNDCLASSW(ctypes.Structure):
        _fields_ = [
            ("style", wintypes.UINT),
            ("lpfnWndProc", WNDPROC),
            ("cbClsExtra", ctypes.c_int),
            ("cbWndExtra", ctypes.c_int),
            ("hInstance", wintypes.HINSTANCE),
            ("hIcon", wintypes.HICON),
            ("hCursor", wintypes.HICON),
            ("hbrBackground", wintypes.HBRUSH),
            ("lpszMenuName", wintypes.LPCWSTR),
            ("lpszClassName", wintypes.LPCWSTR),
        ]

    class NOTIFYICONDATAW(ctypes.Structure):
        _fields_ = [
            ("cbSize", wintypes.DWORD),
            ("hWnd", wintypes.HWND),
            ("uID", wintypes.UINT),
            ("uFlags", wintypes.UINT),
            ("uCallbackMessage", wintypes.UINT),
            ("hIcon", wintypes.HICON),
            ("szTip", wintypes.WCHAR * 128),
            ("dwState", wintypes.DWORD),
            ("dwStateMask", wintypes.DWORD),
            ("szInfo", wintypes.WCHAR * 256),
            ("uTimeoutOrVersion", wintypes.UINT),
            ("szInfoTitle", wintypes.WCHAR * 64),
            ("dwInfoFlags", wintypes.DWORD),
        ]

    class POINT(ctypes.Structure):
        _fields_ = [("x", ctypes.c_long), ("y", ctypes.c_long)]

    class TrayIconManager:
        def __init__(self, title: str, on_show: Callable[[], None], on_quit: Callable[[], None]) -> None:
            self.title = title
            self.on_show = on_show
            self.on_quit = on_quit
            self.hwnd: wintypes.HWND | None = None
            self.thread: threading.Thread | None = None
            self.running = False
            self._class_name = f"PriceAI_Tray_{id(self)}"
            self._wnd_proc_ref = WNDPROC(self._wnd_proc)

        def start(self) -> None:
            self.running = True
            self.thread = threading.Thread(target=self._run_loop, daemon=True)
            self.thread.start()

        def _run_loop(self) -> None:
            hinst = kernel32.GetModuleHandleW(None)
            wc = WNDCLASSW()
            wc.hInstance = hinst
            wc.lpszClassName = self._class_name
            wc.lpfnWndProc = self._wnd_proc_ref
            user32.RegisterClassW(ctypes.byref(wc))

            self.hwnd = user32.CreateWindowExW(
                0, self._class_name, self.title, 0, 0, 0, 0, 0, 0, 0, hinst, None
            )

            nid = NOTIFYICONDATAW()
            nid.cbSize = ctypes.sizeof(NOTIFYICONDATAW)
            nid.hWnd = self.hwnd
            nid.uID = 1001
            nid.uFlags = NIF_ICON | NIF_MESSAGE | NIF_TIP
            nid.uCallbackMessage = WM_TRAY
            nid.hIcon = user32.LoadIconW(0, IDI_APPLICATION)
            nid.szTip = self.title[:127]

            shell32.Shell_NotifyIconW(NIM_ADD, ctypes.byref(nid))

            msg = wintypes.MSG()
            while self.running and user32.GetMessageW(ctypes.byref(msg), 0, 0, 0) > 0:
                user32.TranslateMessage(ctypes.byref(msg))
                user32.DispatchMessageW(ctypes.byref(msg))

            shell32.Shell_NotifyIconW(NIM_DELETE, ctypes.byref(nid))
            if self.hwnd:
                user32.DestroyWindow(self.hwnd)
            user32.UnregisterClassW(self._class_name, hinst)

        def stop(self) -> None:
            self.running = False
            if self.hwnd:
                user32.PostMessageW(self.hwnd, WM_DESTROY, 0, 0)

        def _show_menu(self) -> None:
            hmenu = user32.CreatePopupMenu()
            user32.AppendMenuW(hmenu, MF_STRING, 1, "显示主窗口")
            user32.AppendMenuW(hmenu, MF_SEPARATOR, 0, "")
            user32.AppendMenuW(hmenu, MF_STRING, 2, "退出程序")

            pt = POINT()
            user32.GetCursorPos(ctypes.byref(pt))
            user32.SetForegroundWindow(self.hwnd)
            user32.TrackPopupMenu(hmenu, TPM_RIGHTBUTTON, pt.x, pt.y, 0, self.hwnd, None)
            user32.DestroyMenu(hmenu)

        def _wnd_proc(self, hwnd: int, msg: int, wparam: int, lparam: int) -> int:
            if msg == WM_TRAY:
                if lparam in (WM_LBUTTONUP, WM_LBUTTONDBLCLK):
                    if self.on_show:
                        self.on_show()
                    return 0
                elif lparam == WM_RBUTTONUP:
                    self._show_menu()
                    return 0
            elif msg == WM_COMMAND:
                cmd_id = wparam & 0xFFFF
                if cmd_id == 1:
                    if self.on_show:
                        self.on_show()
                elif cmd_id == 2:
                    if self.on_quit:
                        self.on_quit()
                return 0
            elif msg == WM_DESTROY:
                user32.PostQuitMessage(0)
                return 0
            return int(user32.DefWindowProcW(hwnd, msg, wparam, lparam))
else:
    class TrayIconManager:  # type: ignore[no-redef]
        def __init__(self, title: str, on_show: Callable[[], None], on_quit: Callable[[], None]) -> None:
            pass
        def start(self) -> None:
            pass
        def stop(self) -> None:
            pass


APP_DIR = Path(__file__).resolve().parent
CONFIG_PATH = APP_DIR / "config.json"
EXAMPLE_CONFIG_PATH = APP_DIR / "config.example.json"
MONITOR_PATH = APP_DIR / "price_monitor.py"
STATE_PATH = APP_DIR / "monitor_state.json"
PAUSE_FLAG = APP_DIR / "monitor_pause.flag"
MIN_INTERVAL_SECONDS = 60
DEFAULT_PYTHON = r"E:\DevTools\Python\envs\default-py312\Scripts\python.exe"


class SettingsError(ValueError):
    """Invalid user-entered setting."""


def parse_keywords(text: str) -> list[str]:
    parts = re.split(r"[\n,，]+", text)
    result: list[str] = []
    seen: set[str] = set()
    for part in parts:
        word = part.strip()
        key = word.casefold()
        if word and key not in seen:
            seen.add(key)
            result.append(word)
    return result


def validate_settings_values(values: dict[str, str]) -> dict[str, int | float]:
    try:
        max_price = float(values["max_price"])
        min_price = float(values["min_price"])
        interval = int(values["check_interval_seconds"])
        min_stock = int(values["min_stock"])
        freshness = int(values["fresh_within_minutes"])
    except (KeyError, TypeError, ValueError) as exc:
        raise SettingsError("价格和时间设置必须填写有效数字。") from exc

    if max_price <= 0:
        raise SettingsError("最高监控价格必须大于 0。")
    if min_price < 0:
        raise SettingsError("最低价格不能小于 0。")
    if min_price > max_price:
        raise SettingsError("最低价格不能高于最高监控价格。")
    if interval < MIN_INTERVAL_SECONDS:
        raise SettingsError(f"刷新间隔不能小于 {MIN_INTERVAL_SECONDS} 秒（PriceAI 官方限制）。")
    if interval > 86400:
        raise SettingsError("刷新间隔不能超过 86400 秒。")
    if min_stock < 0:
        raise SettingsError("最低库存不能小于 0。")
    if freshness < 0:
        raise SettingsError("报价有效时间不能小于 0。")

    return {
        "max_price": max_price,
        "min_price": min_price,
        "check_interval_seconds": interval,
        "min_stock": min_stock,
        "fresh_within_minutes": freshness,
    }


def load_config_file() -> dict[str, Any]:
    source = CONFIG_PATH if CONFIG_PATH.exists() else EXAMPLE_CONFIG_PATH
    try:
        value = json.loads(source.read_text(encoding="utf-8-sig"))
    except FileNotFoundError as exc:
        raise SettingsError("找不到 config.json 或 config.example.json。") from exc
    except json.JSONDecodeError as exc:
        raise SettingsError(f"配置文件 JSON 格式错误（第 {exc.lineno} 行）。") from exc
    if not isinstance(value, dict):
        raise SettingsError("配置文件顶层必须是 JSON 对象。")
    return value


def save_config_file(config: dict[str, Any]) -> None:
    temp = CONFIG_PATH.with_suffix(".json.tmp")
    temp.write_text(json.dumps(config, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    os.replace(temp, CONFIG_PATH)


class SettingsApp:
    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.root.title("PriceAI 账号价格监控")
        self.root.geometry("1430x740")
        self.root.minsize(900, 640)
        self.root.protocol("WM_DELETE_WINDOW", self.on_close)

        self.config = load_config_file()
        self.monitor_process: subprocess.Popen[str] | None = None
        self.test_running = False
        self.events: queue.Queue[tuple[str, Any]] = queue.Queue()

        self.max_price = tk.StringVar(value=str(self.config.get("max_price", 10)))
        self.min_price = tk.StringVar(value=str(self.config.get("min_price", 0)))
        self.interval = tk.StringVar(value=str(self.config.get("check_interval_seconds", 60)))
        self.min_stock = tk.StringVar(value=str(self.config.get("min_stock", 1)))
        self.freshness = tk.StringVar(value=str(self.config.get("fresh_within_minutes", 120)))
        notifications = self.config.get("notifications")
        if not isinstance(notifications, dict):
            notifications = {}
        self.windows_toast = tk.BooleanVar(value=bool(notifications.get("windows_toast", True)))
        simple_cfg = self.config.get("simple_monitor") if isinstance(self.config.get("simple_monitor"), dict) else {}
        self.bark_key = tk.StringVar(value=str(notifications.get("bark_key") or simple_cfg.get("bark_key") or ""))
        self.bark_title = tk.StringVar(value=str(notifications.get("bark_title") or simple_cfg.get("bark_title") or "ChatGPT Plus 价格报警"))
        auto_order_cfg = self.config.get("auto_order")
        if not isinstance(auto_order_cfg, dict):
            auto_order_cfg = {}
        self.auto_order_enabled = tk.BooleanVar(value=bool(auto_order_cfg.get("enabled", False)))
        self.auto_order_contact = tk.StringVar(value=str(auto_order_cfg.get("contact", "")))
        self.auto_order_password = tk.StringVar(value=str(auto_order_cfg.get("query_password", "")))
        self.status = tk.StringVar(value="未启动")

        self._placeholders: dict[tk.Text, str] = {}
        self._link_counter = 0
        self._build_ui()
        self._set_keywords()
        self.root.after(100, self._drain_events)

        # 启动系统托盘图标
        self.tray = TrayIconManager(
            title="PriceAI 账号价格监控",
            on_show=self.show_window,
            on_quit=self.quit_app,
        )
        self.tray.start()

    def _build_ui(self) -> None:
        outer = ttk.Frame(self.root, padding=14)
        outer.pack(fill="both", expand=True)

        # 左右分栏：左侧设置，右侧日志
        left_frame = ttk.Frame(outer, width=600)
        left_frame.pack(side="left", fill="y", expand=False)
        left_frame.pack_propagate(False)
        right_frame = ttk.Frame(outer)
        right_frame.pack(side="left", fill="both", expand=True, padx=(10, 0))

        # ── 左侧底部固定区：状态栏与操作按钮（优先置底，确保任何分辨率下均可见） ──
        buttons = ttk.Frame(left_frame)
        buttons.pack(side="bottom", fill="x", pady=(6, 0))
        self.save_button = ttk.Button(buttons, text="保存设置", command=self.save_settings)
        self.test_button = ttk.Button(buttons, text="测试扫描", command=self.test_scan)
        self.start_button = ttk.Button(buttons, text="保存并启动监控", command=self.start_monitor)
        self.pause_button = ttk.Button(buttons, text="暂停", command=self.toggle_pause, state="disabled")
        self.stop_button = ttk.Button(buttons, text="停止监控", command=self.stop_monitor, state="disabled")
        self.clear_button = ttk.Button(buttons, text="清空日志", command=self.clear_log)
        for button in (self.save_button, self.test_button, self.start_button, self.pause_button, self.stop_button, self.clear_button):
            button.pack(side="left", padx=(0, 6))

        status_bar = ttk.Frame(left_frame)
        status_bar.pack(side="bottom", fill="x", pady=(4, 2))
        ttk.Label(status_bar, text="当前状态：", foreground="#555555").pack(side="left")
        ttk.Label(status_bar, textvariable=self.status, foreground="#245c3c", font=("Microsoft YaHei UI", 9, "bold")).pack(side="left")

        # ── 左侧主体内容区 ──
        content_frame = ttk.Frame(left_frame)
        content_frame.pack(side="top", fill="both", expand=True)

        ttk.Label(content_frame, text="PriceAI 账号价格监控", font=("Microsoft YaHei UI", 13, "bold")).pack(anchor="w")
        ttk.Label(
            content_frame,
            text="官方 Price Radar 快照：ChatGPT Plus 试用订阅（点击 ✕ 最小化到托盘，右键托盘退出）",
            foreground="#555555",
            font=("Microsoft YaHei UI", 8),
        ).pack(anchor="w", pady=(1, 6))

        target = ttk.LabelFrame(content_frame, text="固定监控目标", padding=6)
        target.pack(fill="x", pady=(0, 6))
        ttk.Label(target, text="商品").grid(row=0, column=0, sticky="w", padx=(0, 10))
        ttk.Label(target, text="ChatGPT Plus 试用订阅（chatgpt-plus）").grid(row=0, column=1, sticky="w")
        ttk.Label(target, text="范围").grid(row=1, column=0, sticky="w", padx=(0, 10), pady=(3, 0))
        ttk.Label(target, text="全网最低报价 + Top 报价（支持自动下单与多渠道提醒）").grid(row=1, column=1, sticky="w", pady=(3, 0))

        rules = ttk.LabelFrame(content_frame, text="监控条件", padding=6)
        rules.pack(fill="x", pady=(0, 6))
        rules.columnconfigure(1, weight=1)
        rules.columnconfigure(4, weight=1)
        self._entry_row(rules, 0, "最高价格", self.max_price, "元", 0)
        self._entry_row(rules, 0, "刷新间隔", self.interval, "秒", 3)
        self._entry_row(rules, 1, "最低价格", self.min_price, "元", 0)
        self._entry_row(rules, 1, "最低库存", self.min_stock, "个", 3)
        self._entry_row(rules, 2, "有效时间", self.freshness, "分钟(0不限)", 0)

        keywords = ttk.LabelFrame(content_frame, text="关键词过滤（一行一个，或逗号分隔）", padding=6)
        keywords.pack(fill="x", pady=(0, 6))
        keywords.columnconfigure(0, weight=1)
        keywords.columnconfigure(1, weight=1)
        ttk.Label(keywords, text="包含").grid(row=0, column=0, sticky="w")
        ttk.Label(keywords, text="排除").grid(row=0, column=1, sticky="w", padx=(10, 0))
        self.required_text = self._make_keyword_text(keywords, "关键词\n渠道\n商品名")
        self.excluded_text = self._make_keyword_text(keywords, "网页\n无质保\n日抛")
        self.required_text.grid(row=1, column=0, sticky="nsew", pady=(2, 0))
        self.excluded_text.grid(row=1, column=1, sticky="nsew", padx=(10, 0), pady=(2, 0))

        options = ttk.LabelFrame(content_frame, text="提醒通知设置", padding=6)
        options.pack(fill="x", pady=(0, 6))
        options.columnconfigure(1, weight=1)
        ttk.Checkbutton(options, text="启用 Windows 桌面通知", variable=self.windows_toast).grid(
            row=0, column=0, columnspan=2, sticky="w"
        )
        ttk.Label(options, text="Bark 推送 Key").grid(row=1, column=0, sticky="w", padx=(0, 10), pady=(3, 0))
        ttk.Entry(options, textvariable=self.bark_key).grid(
            row=1, column=1, sticky="ew", pady=(3, 0)
        )
        ttk.Label(options, text="Bark 标题").grid(row=2, column=0, sticky="w", padx=(0, 10), pady=(3, 0))
        ttk.Entry(options, textvariable=self.bark_title).grid(
            row=2, column=1, sticky="ew", pady=(3, 0)
        )

        auto_frame = ttk.LabelFrame(content_frame, text="自动下单（链动小铺）", padding=6)
        auto_frame.pack(fill="x", pady=(0, 4))
        auto_frame.columnconfigure(1, weight=1)
        ttk.Checkbutton(auto_frame, text="启用自动下单", variable=self.auto_order_enabled).grid(
            row=0, column=0, columnspan=2, sticky="w"
        )
        ttk.Label(auto_frame, text="联系方式").grid(row=1, column=0, sticky="w", padx=(0, 10), pady=(3, 0))
        ttk.Entry(auto_frame, textvariable=self.auto_order_contact).grid(
            row=1, column=1, sticky="ew", pady=(3, 0)
        )
        ttk.Label(auto_frame, text="安全密码").grid(row=2, column=0, sticky="w", padx=(0, 10), pady=(3, 0))
        ttk.Entry(auto_frame, textvariable=self.auto_order_password, show="*").grid(
            row=2, column=1, sticky="ew", pady=(3, 0)
        )

        # ── 右侧：日志区 ──
        log_frame = ttk.LabelFrame(right_frame, text="运行日志", padding=6)
        log_frame.pack(fill="both", expand=True)
        log_frame.columnconfigure(0, weight=1)
        log_frame.rowconfigure(0, weight=1)
        self.log = tk.Text(log_frame, height=12, wrap="word", state="disabled", font=("Consolas", 9))
        scrollbar = ttk.Scrollbar(log_frame, orient="vertical", command=self.log.yview)
        self.log.configure(yscrollcommand=scrollbar.set)
        self.log.grid(row=0, column=0, sticky="nsew")
        scrollbar.grid(row=0, column=1, sticky="ns")

    @staticmethod
    def _entry_row(
        parent: ttk.LabelFrame,
        row: int,
        label: str,
        variable: tk.StringVar,
        suffix: str,
        column: int,
    ) -> None:
        ttk.Label(parent, text=label).grid(row=row, column=column, sticky="w", pady=5, padx=(0, 6))
        entry = ttk.Entry(parent, textvariable=variable, width=12)
        entry.grid(row=row, column=column + 1, sticky="ew", pady=5)
        ttk.Label(parent, text=suffix).grid(row=row, column=column + 2, sticky="w", pady=5, padx=(5, 14))
        entry.configure(width=16)

    def _set_keywords(self) -> None:
        required = self.config.get("required_keywords")
        excluded = self.config.get("excluded_keywords")
        required_text = "\n".join(required if isinstance(required, list) else [])
        excluded_text = "\n".join(excluded if isinstance(excluded, list) else [])
        if required_text:
            self.required_text.insert("1.0", required_text)
        else:
            self._show_placeholder(self.required_text)
        if excluded_text:
            self.excluded_text.insert("1.0", excluded_text)
        else:
            self._show_placeholder(self.excluded_text)

    def _make_keyword_text(self, parent: ttk.Frame, placeholder: str) -> tk.Text:
        text = tk.Text(parent, height=5, wrap="word")
        text.tag_configure("placeholder", foreground="#9aa0a6")
        self._placeholders[text] = placeholder
        text.bind("<FocusIn>", lambda _e, t=text: self._clear_placeholder(t))
        text.bind("<FocusOut>", lambda _e, t=text: self._show_placeholder(t))
        return text

    def _show_placeholder(self, text: tk.Text) -> None:
        if not text.get("1.0", "end-1c").strip():
            text.delete("1.0", "end")
            text.insert("1.0", self._placeholders[text])
            text.tag_add("placeholder", "1.0", "end")

    def _clear_placeholder(self, text: tk.Text) -> None:
        if text.get("1.0", "end-1c") == self._placeholders[text]:
            text.delete("1.0", "end")

    def _keyword_value(self, text: tk.Text) -> str:
        content = text.get("1.0", "end-1c")
        if content == self._placeholders[text]:
            return ""
        return content

    def _form_values(self) -> dict[str, str]:
        return {
            "max_price": self.max_price.get().strip(),
            "min_price": self.min_price.get().strip(),
            "check_interval_seconds": self.interval.get().strip(),
            "min_stock": self.min_stock.get().strip(),
            "fresh_within_minutes": self.freshness.get().strip(),
        }

    def save_settings(self, *, show_success: bool = True) -> bool:
        try:
            numeric = validate_settings_values(self._form_values())
            updated = dict(self.config)
            updated.update(numeric)
            updated["price_radar_latest_url"] = "https://data.priceai.cc/latest.json"
            updated["product_id"] = "chatgpt-plus"
            updated["preset_id"] = "account_verified"
            updated["required_keywords"] = parse_keywords(self._keyword_value(self.required_text))
            updated["excluded_keywords"] = parse_keywords(self._keyword_value(self.excluded_text))
            notifications = updated.get("notifications")
            if not isinstance(notifications, dict):
                notifications = {}
            notifications["windows_toast"] = self.windows_toast.get()
            bark_key_val = self.bark_key.get().strip()
            bark_title_val = self.bark_title.get().strip() or "ChatGPT Plus 价格报警"
            notifications["bark_key"] = bark_key_val
            notifications["bark_title"] = bark_title_val
            updated["notifications"] = notifications

            # 同步更新 simple_monitor 保持兼容
            if "simple_monitor" in updated and isinstance(updated["simple_monitor"], dict):
                updated["simple_monitor"]["bark_key"] = bark_key_val
                updated["simple_monitor"]["bark_title"] = bark_title_val

            updated["auto_order"] = {
                "enabled": self.auto_order_enabled.get(),
                "contact": self.auto_order_contact.get().strip(),
                "query_password": self.auto_order_password.get().strip(),
                "preferred_channel": "alipay",
            }
            save_config_file(updated)
            self.config = updated
        except (OSError, SettingsError) as exc:
            messagebox.showerror("无法保存设置", str(exc), parent=self.root)
            return False
        self.status.set("设置已保存")
        self._append_log("设置已保存。价格规则：报价 ≤ ¥{:.2f}\n".format(float(numeric["max_price"])))
        if show_success:
            messagebox.showinfo("保存成功", "监控设置已保存。", parent=self.root)
        return True

    def test_scan(self) -> None:
        if self.test_running or self.monitor_process is not None:
            return
        if not self.save_settings(show_success=False):
            return
        self.test_running = True
        self.test_button.configure(state="disabled")
        self.start_button.configure(state="disabled")
        self.status.set("正在测试扫描…")
        self._append_log("\n--- 测试扫描（不提醒、不写去重状态）---\n")
        threading.Thread(target=self._test_worker, daemon=True).start()

    def _test_worker(self) -> None:
        command = [
            self._python_executable(),
            str(MONITOR_PATH),
            "--config",
            str(CONFIG_PATH),
            "--state",
            str(STATE_PATH),
            "check",
            "--dry-run",
        ]
        try:
            completed = subprocess.run(
                command,
                cwd=APP_DIR,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=60,
                env=self._child_env(),
                creationflags=self._creation_flags(),
                check=False,
            )
            output = (completed.stdout or "") + (completed.stderr or "")
            self.events.put(("test_done", (completed.returncode, output)))
        except (OSError, subprocess.SubprocessError) as exc:
            self.events.put(("test_done", (1, f"测试扫描失败：{exc}\n")))

    def start_monitor(self) -> None:
        if self.monitor_process is not None:
            return
        if not self.save_settings(show_success=False):
            return
        # 每次启动监控都视为全新会话，清空上次的去重状态和暂停标志
        try:
            STATE_PATH.unlink()
        except FileNotFoundError:
            pass
        except OSError:
            pass
        try:
            PAUSE_FLAG.unlink()
        except FileNotFoundError:
            pass
        except OSError:
            pass
        command = [
            self._python_executable(),
            str(MONITOR_PATH),
            "--config",
            str(CONFIG_PATH),
            "--state",
            str(STATE_PATH),
            "watch",
        ]
        try:
            self.monitor_process = subprocess.Popen(
                command,
                cwd=APP_DIR,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                encoding="utf-8",
                errors="replace",
                bufsize=1,
                env=self._child_env(),
                creationflags=self._creation_flags(),
            )
        except OSError as exc:
            self.monitor_process = None
            messagebox.showerror("启动失败", str(exc), parent=self.root)
            return
        self.status.set("监控运行中")
        self.start_button.configure(state="disabled")
        self.test_button.configure(state="disabled")
        self.pause_button.configure(text="暂停", state="normal")
        self.stop_button.configure(state="normal")
        self._append_log("\n--- 监控已启动 ---\n")
        threading.Thread(target=self._monitor_reader, args=(self.monitor_process,), daemon=True).start()

    def toggle_pause(self) -> None:
        if self.monitor_process is None:
            return
        if PAUSE_FLAG.exists():
            # 当前是暂停状态，点击则继续
            try:
                PAUSE_FLAG.unlink()
            except FileNotFoundError:
                pass
            except OSError:
                pass
            self.pause_button.configure(text="暂停")
            self.status.set("监控运行中")
            self._append_log("--- 监控已继续 ---\n")
        else:
            # 当前是运行状态，点击则暂停
            PAUSE_FLAG.touch()
            self.pause_button.configure(text="继续")
            self.status.set("已暂停")
            self._append_log("--- 监控已暂停 ---\n")

    def _monitor_reader(self, process: subprocess.Popen[str]) -> None:
        if process.stdout is not None:
            for line in process.stdout:
                self.events.put(("log", line))
        return_code = process.wait()
        self.events.put(("monitor_done", return_code))

    def stop_monitor(self) -> None:
        process = self.monitor_process
        if process is None:
            return
        self.status.set("正在停止…")
        try:
            process.terminate()
        except OSError:
            pass

    def _drain_events(self) -> None:
        try:
            while True:
                kind, value = self.events.get_nowait()
                if kind == "log":
                    line = str(value)
                    self._append_log(line)
                    # 检测自动下单后的自动暂停
                    if "监控已自动暂停" in line:
                        self.pause_button.configure(text="继续")
                        self.status.set("已暂停（下单后）")
                elif kind == "test_done":
                    return_code, output = value
                    self._append_log(output or "测试扫描没有输出。\n")
                    self.test_running = False
                    self.test_button.configure(state="normal")
                    self.start_button.configure(state="normal")
                    self.status.set("测试完成" if return_code == 0 else "测试失败")
                elif kind == "monitor_done":
                    self._append_log("--- 监控已停止 ---\n")
                    self.monitor_process = None
                    self.start_button.configure(state="normal")
                    self.test_button.configure(state="normal")
                    self.pause_button.configure(text="暂停", state="disabled")
                    self.stop_button.configure(state="disabled")
                    self.status.set("已停止")
        except queue.Empty:
            pass
        self.root.after(100, self._drain_events)

    def _append_log(self, text: str) -> None:
        self.log.configure(state="normal")
        pos = 0
        for match in re.finditer(r"https?://\S+", text):
            if match.start() > pos:
                self.log.insert("end", text[pos:match.start()])
            url = match.group(0)
            start = self.log.index("end-1c")
            self.log.insert("end", url)
            end = self.log.index("end-1c")
            tag = f"link_{self._link_counter}"
            self._link_counter += 1
            self.log.tag_add(tag, start, end)
            self.log.tag_configure(tag, foreground="#2563eb", underline=True)
            self.log.tag_bind(tag, "<Button-1>", lambda e, u=url: webbrowser.open(u))
            self.log.tag_bind(tag, "<Enter>", lambda e: self.log.configure(cursor="hand2"))
            self.log.tag_bind(tag, "<Leave>", lambda e: self.log.configure(cursor=""))
            pos = match.end()
        if pos < len(text):
            self.log.insert("end", text[pos:])
        self.log.see("end")
        self.log.configure(state="disabled")

    def clear_log(self) -> None:
        self.log.configure(state="normal")
        self.log.delete("1.0", "end")
        self.log.configure(state="disabled")

    @staticmethod
    def _creation_flags() -> int:
        return int(getattr(subprocess, "CREATE_NO_WINDOW", 0)) if os.name == "nt" else 0

    @staticmethod
    def _python_executable() -> str:
        if os.path.exists(DEFAULT_PYTHON):
            return DEFAULT_PYTHON
        return sys.executable

    @staticmethod
    def _child_env() -> dict[str, str]:
        env = dict(os.environ)
        env["PYTHONUTF8"] = "1"
        return env

    def show_window(self) -> None:
        def _restore() -> None:
            self.root.deiconify()
            self.root.lift()
            self.root.focus_force()

        self.root.after(0, _restore)

    def on_close(self) -> None:
        # 点击右上角 X：不关闭，而是最小化到系统托盘
        self.root.withdraw()

    def quit_app(self) -> None:
        def _quit() -> None:
            if self.monitor_process is not None:
                # 弹窗询问前如果窗口被隐藏则先恢复展示
                self.root.deiconify()
                close = messagebox.askyesno(
                    "退出程序？",
                    "退出程序将同时停止正在运行的监控后台，确定退出吗？",
                    parent=self.root,
                )
                if not close:
                    return
                try:
                    self.monitor_process.terminate()
                except OSError:
                    pass
            try:
                self.tray.stop()
            except Exception:
                pass
            self.root.destroy()

        self.root.after(0, _quit)


def main() -> int:
    try:
        root = tk.Tk()
        SettingsApp(root)
        root.mainloop()
    except SettingsError as exc:
        try:
            messagebox.showerror("配置错误", str(exc))
        except tk.TclError:
            print(f"配置错误：{exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
