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
from pathlib import Path
from tkinter import messagebox, ttk
from typing import Any


APP_DIR = Path(__file__).resolve().parent
CONFIG_PATH = APP_DIR / "config.json"
EXAMPLE_CONFIG_PATH = APP_DIR / "config.example.json"
MONITOR_PATH = APP_DIR / "price_monitor.py"
STATE_PATH = APP_DIR / "monitor_state.json"
MIN_INTERVAL_SECONDS = 60


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
        renotify = float(values["renotify_hours"])
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
    if renotify < 0:
        raise SettingsError("重复提醒间隔不能小于 0。")

    return {
        "max_price": max_price,
        "min_price": min_price,
        "check_interval_seconds": interval,
        "min_stock": min_stock,
        "fresh_within_minutes": freshness,
        "renotify_hours": renotify,
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
        self.root.geometry("820x760")
        self.root.minsize(720, 650)
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
        self.renotify = tk.StringVar(value=str(self.config.get("renotify_hours", 24)))
        notifications = self.config.get("notifications")
        if not isinstance(notifications, dict):
            notifications = {}
        self.windows_toast = tk.BooleanVar(value=bool(notifications.get("windows_toast", True)))
        self.status = tk.StringVar(value="未启动")

        self._placeholders: dict[tk.Text, str] = {}
        self._build_ui()
        self._set_keywords()
        self.root.after(100, self._drain_events)

    def _build_ui(self) -> None:
        outer = ttk.Frame(self.root, padding=14)
        outer.pack(fill="both", expand=True)

        ttk.Label(outer, text="PriceAI 账号价格监控", font=("Microsoft YaHei UI", 16, "bold")).pack(anchor="w")
        ttk.Label(
            outer,
            text="官方 Price Radar：ChatGPT Plus 试用订阅 → 已接码成品号 → Top 5",
            foreground="#555555",
        ).pack(anchor="w", pady=(3, 10))

        target = ttk.LabelFrame(outer, text="固定监控目标", padding=10)
        target.pack(fill="x", pady=(0, 10))
        ttk.Label(target, text="商品").grid(row=0, column=0, sticky="w", padx=(0, 10))
        ttk.Label(target, text="ChatGPT Plus 试用订阅（chatgpt-plus）").grid(row=0, column=1, sticky="w")
        ttk.Label(target, text="分类").grid(row=1, column=0, sticky="w", padx=(0, 10), pady=(5, 0))
        ttk.Label(target, text="已接码成品号（account_verified）").grid(row=1, column=1, sticky="w", pady=(5, 0))

        rules = ttk.LabelFrame(outer, text="监控条件", padding=10)
        rules.pack(fill="x", pady=(0, 10))
        rules.columnconfigure(1, weight=1)
        rules.columnconfigure(4, weight=1)
        self._entry_row(rules, 0, "最高监控价格（报价 ≤ 此值）", self.max_price, "元", 0)
        self._entry_row(rules, 0, "刷新间隔", self.interval, "秒（至少 60）", 3)
        self._entry_row(rules, 1, "最低价格（排除异常低价）", self.min_price, "元", 0)
        self._entry_row(rules, 1, "最低库存", self.min_stock, "个", 3)
        self._entry_row(rules, 2, "报价有效时间", self.freshness, "分钟；0 为不限", 0)
        self._entry_row(rules, 2, "重复提醒间隔", self.renotify, "小时；0 为不重复", 3)

        keywords = ttk.LabelFrame(outer, text="关键词过滤（一行一个，也可用逗号分隔）", padding=10)
        keywords.pack(fill="both", pady=(0, 10))
        keywords.columnconfigure(0, weight=1)
        keywords.columnconfigure(1, weight=1)
        ttk.Label(keywords, text="包含").grid(row=0, column=0, sticky="w")
        ttk.Label(keywords, text="排除").grid(row=0, column=1, sticky="w", padx=(10, 0))
        self.required_text = self._make_keyword_text(keywords, "关键词\n渠道\n商品名")
        self.excluded_text = self._make_keyword_text(keywords, "网页\n无质保\n日抛")
        self.required_text.grid(row=1, column=0, sticky="nsew", pady=(4, 0))
        self.excluded_text.grid(row=1, column=1, sticky="nsew", padx=(10, 0), pady=(4, 0))

        options = ttk.Frame(outer)
        options.pack(fill="x", pady=(0, 8))
        ttk.Checkbutton(options, text="启用 Windows 桌面通知", variable=self.windows_toast).pack(side="left")
        ttk.Label(options, textvariable=self.status, foreground="#245c3c").pack(side="right")

        buttons = ttk.Frame(outer)
        buttons.pack(fill="x", pady=(0, 10))
        self.save_button = ttk.Button(buttons, text="保存设置", command=self.save_settings)
        self.test_button = ttk.Button(buttons, text="测试扫描", command=self.test_scan)
        self.start_button = ttk.Button(buttons, text="保存并启动监控", command=self.start_monitor)
        self.stop_button = ttk.Button(buttons, text="停止监控", command=self.stop_monitor, state="disabled")
        self.clear_button = ttk.Button(buttons, text="清空日志", command=self.clear_log)
        for button in (self.save_button, self.test_button, self.start_button, self.stop_button, self.clear_button):
            button.pack(side="left", padx=(0, 8))

        log_frame = ttk.LabelFrame(outer, text="运行日志", padding=6)
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
            "renotify_hours": self.renotify.get().strip(),
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
            else:
                notifications = dict(notifications)
            notifications["windows_toast"] = self.windows_toast.get()
            updated["notifications"] = notifications
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
            sys.executable,
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
        command = [
            sys.executable,
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
        self.stop_button.configure(state="normal")
        self._append_log("\n--- 监控已启动 ---\n")
        threading.Thread(target=self._monitor_reader, args=(self.monitor_process,), daemon=True).start()

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
                    self._append_log(str(value))
                elif kind == "test_done":
                    return_code, output = value
                    self._append_log(output or "测试扫描没有输出。\n")
                    self.test_running = False
                    self.test_button.configure(state="normal")
                    self.start_button.configure(state="normal")
                    self.status.set("测试完成" if return_code == 0 else "测试失败")
                elif kind == "monitor_done":
                    self._append_log(f"--- 监控已停止（退出码 {value}）---\n")
                    self.monitor_process = None
                    self.start_button.configure(state="normal")
                    self.test_button.configure(state="normal")
                    self.stop_button.configure(state="disabled")
                    self.status.set("已停止")
        except queue.Empty:
            pass
        self.root.after(100, self._drain_events)

    def _append_log(self, text: str) -> None:
        self.log.configure(state="normal")
        self.log.insert("end", text)
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
    def _child_env() -> dict[str, str]:
        env = dict(os.environ)
        env["PYTHONUTF8"] = "1"
        return env

    def on_close(self) -> None:
        if self.monitor_process is not None:
            close = messagebox.askyesno(
                "停止监控？",
                "关闭设置窗口会同时停止正在运行的监控，确定关闭吗？",
                parent=self.root,
            )
            if not close:
                return
            try:
                self.monitor_process.terminate()
            except OSError:
                pass
        self.root.destroy()


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
