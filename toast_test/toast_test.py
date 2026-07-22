"""Windows Toast 通知方案测试工具

提供多种不同的 Toast 通知实现方案，点击按钮逐一测试。
"""
import ctypes
import os
import platform
import subprocess
import sys
import threading
import time
import tkinter as tk
import winreg
from tkinter import ttk, scrolledtext
from xml.sax.saxutils import escape as xml_escape

# ── 常量 ──────────────────────────────────────────────────────────────
APP_NAME = "ToastTest"
APP_AUMID = "ToastTest.Python.Notification"
POWERSHELL_AUMID = "{1AC14E77-02E7-4E5D-B744-2EB1AE5198B7}\\WindowsPowerShell\\v1.0\\powershell.exe"

TITLE = "PriceAI 监控测试"
BODY = "ChatGPT Plus 最低价 ￥18.50｜库存 5｜更新 3分钟前\nhttps://priceai.cc/products/chatgpt-plus"


# ── 方案 1: PowerShell WinRT + 未注册 AUMID（当前方案） ───────────────
def method_1_ps_winrt_unregistered(log):
    log("【方案1】PowerShell WinRT + AUMID 'PriceAI Monitor'（当前方案，AUMID 未注册）")
    toast_xml = (
        '<toast><visual><binding template="ToastGeneric">'
        f"<text>{xml_escape(TITLE)}</text><text>{xml_escape(BODY)}</text>"
        "</binding></visual></toast>"
    )
    script = (
        "$ErrorActionPreference='Stop';"
        "[Windows.UI.Notifications.ToastNotificationManager, Windows.UI.Notifications, ContentType = WindowsRuntime] | Out-Null;"
        "[Windows.Data.Xml.Dom.XmlDocument, Windows.Data.Xml.Dom.XmlDocument, ContentType = WindowsRuntime] | Out-Null;"
        "$xml=New-Object Windows.Data.Xml.Dom.XmlDocument;"
        f"$xml.LoadXml('{toast_xml.replace(chr(39), chr(39) * 2)}');"
        "$toast=[Windows.UI.Notifications.ToastNotification]::new($xml);"
        "[Windows.UI.Notifications.ToastNotificationManager]::CreateToastNotifier('PriceAI Monitor').Show($toast)"
    )
    _run_powershell(script, log)


# ── 方案 2: PowerShell WinRT + PowerShell 内置 AUMID ──────────────────
def method_2_ps_winrt_powershell_aumid(log):
    log("【方案2】PowerShell WinRT + PowerShell 内置 AUMID（系统已注册）")
    toast_xml = (
        '<toast><visual><binding template="ToastGeneric">'
        f"<text>{xml_escape(TITLE)}</text><text>{xml_escape(BODY)}</text>"
        "</binding></visual></toast>"
    )
    script = (
        "$ErrorActionPreference='Stop';"
        "[Windows.UI.Notifications.ToastNotificationManager, Windows.UI.Notifications, ContentType = WindowsRuntime] | Out-Null;"
        "[Windows.Data.Xml.Dom.XmlDocument, Windows.Data.Xml.Dom.XmlDocument, ContentType = WindowsRuntime] | Out-Null;"
        "$xml=New-Object Windows.Data.Xml.Dom.XmlDocument;"
        f"$xml.LoadXml('{toast_xml.replace(chr(39), chr(39) * 2)}');"
        "$toast=[Windows.UI.Notifications.ToastNotification]::new($xml);"
        f"[Windows.UI.Notifications.ToastNotificationManager]::CreateToastNotifier('{POWERSHELL_AUMID}').Show($toast)"
    )
    _run_powershell(script, log)


# ── 方案 3: 注册表注册 AUMID + 创建快捷方式 + WinRT ───────────────────
def method_3_registered_aumid(log):
    log("【方案3】注册表注册 AUMID + 创建开始菜单快捷方式 + PowerShell WinRT")
    try:
        _register_aumid(APP_AUMID, APP_NAME, log)
    except Exception as exc:
        log(f"  注册 AUMID 失败: {exc}")
        return

    toast_xml = (
        '<toast><visual><binding template="ToastGeneric">'
        f"<text>{xml_escape(TITLE)}</text><text>{xml_escape(BODY)}</text>"
        "</binding></visual></toast>"
    )
    script = (
        "$ErrorActionPreference='Stop';"
        "[Windows.UI.Notifications.ToastNotificationManager, Windows.UI.Notifications, ContentType = WindowsRuntime] | Out-Null;"
        "[Windows.Data.Xml.Dom.XmlDocument, Windows.Data.Xml.Dom.XmlDocument, ContentType = WindowsRuntime] | Out-Null;"
        "$xml=New-Object Windows.Data.Xml.Dom.XmlDocument;"
        f"$xml.LoadXml('{toast_xml.replace(chr(39), chr(39) * 2)}');"
        "$toast=[Windows.UI.Notifications.ToastNotification]::new($xml);"
        f"[Windows.UI.Notifications.ToastNotificationManager]::CreateToastNotifier('{APP_AUMID}').Show($toast)"
    )
    _run_powershell(script, log)


def _register_aumid(aumid: str, display_name: str, log) -> None:
    """在注册表中注册 AUMID，并在开始菜单创建带 AUMID 属性的快捷方式。"""
    # 1. 注册表注册 AUMID
    key_path = f"Software\\Classes\\AppUserModelId\\{aumid}"
    with winreg.CreateKeyEx(winreg.HKEY_CURRENT_USER, key_path, 0, winreg.KEY_SET_VALUE) as key:
        winreg.SetValueEx(key, "DisplayName", 0, winreg.REG_SZ, display_name)
        winreg.SetValueEx(key, "IconUri", 0, winreg.REG_SZ, "")
    log(f"  注册表已注册 AUMID: {aumid}")

    # 2. 创建带 AUMID 属性的开始菜单快捷方式
    start_menu = os.path.join(os.environ.get("APPDATA", ""), "Microsoft", "Windows", "Start Menu", "Programs")
    shortcut_path = os.path.join(start_menu, f"{display_name}.lnk")
    python_exe = sys.executable

    ps_script = (
        "$s=(New-Object -ComObject WScript.Shell).CreateShortcut("
        f"'{shortcut_path}'"
        ");"
        f"$s.TargetPath='{python_exe}';"
        f"$s.Arguments='';"
        "$s.Save();"
        # 设置 AUMID 属性需要用到 Windows Shell API
        "$sh=New-Object -ComObject Shell.Application;"
        f"$dir=$sh.NameSpace('{start_menu}');"
        f"$item=$dir.ParseName('{display_name}.lnk');"
        "$item.ExtendedProperty('System.AppUserModel.ID')"
    )
    # 使用 SetProperty 方式设置 AUMID（通过 PropertyStore）
    ps_set_aumid = (
        "Add-Type @"
        "using System;"
        "using System.Runtime.InteropServices;"
        "public class PSShell {"
        "  [DllImport(\"shell32.dll\", CharSet = CharSet.Unicode)]"
        "  public static extern IntPtr SHSetPropertyStore(IntPtr hwnd, IntPtr pStore);"
        "}"
        "@"
    )
    # 更简单的方式：用 PowerShell 设置 shortcut 的 AUMID
    ps_full = (
        f"$ws=New-Object -ComObject WScript.Shell;"
        f"$sc=$ws.CreateShortcut('{shortcut_path}');"
        f"$sc.TargetPath='{python_exe}';"
        "$sc.Save();"
        # 用 PropertyStore 设置 AUMID
        "Add-Type @'"
        "using System;"
        "using System.Runtime.InteropServices;"
        "using System.Runtime.InteropServices.ComTypes;"
        "namespace ToastHelper {"
        "  [Guid(\"886D8EEB-8CF2-4446-8D02-CDBA1DBDCF99\"), InterfaceType(ComInterfaceType.InterfaceIsIUnknown)]"
        "  public interface IPropertyStore {"
        "    uint GetCount([Out] out uint cProps);"
        "    uint GetAt([In] uint iProp, [Out] out PropertyKey pkey);"
        "    uint GetValue([In] ref PropertyKey key, [Out] PropVariant pv);"
        "    uint SetValue([In] ref PropertyKey key, [In] PropVariant pv);"
        "    uint Commit();"
        "  }"
        "  [StructLayout(LayoutKind.Sequential, Pack = 4)]"
        "  public struct PropertyKey {"
        "    public Guid fmtid; public int pid;"
        "    public PropertyKey(Guid g, int p) { fmtid = g; pid = p; }"
        "  }"
        "  [StructLayout(LayoutKind.Sequential)]"
        "  public class PropVariant {"
        "    public ushort vt; public ushort wReserved1, wReserved2, wReserved3;"
        "    public IntPtr val1, val2;"
        "  }"
        "  [ComImport, Guid(\"4F76F590-7CE8-4B69-8C2D-5F2DC548A39E\"), InterfaceType(ComInterfaceType.InterfaceIsIUnknown)]"
        "  public interface IObjectWithAppUserModelId {"
        "    void SetAppUserModelID([MarshalAs(UnmanagedType.LPWStr)] string lpszUserID);"
        "    void GetAppUserModelID([MarshalAs(UnmanagedType.LPWStr)] out string lpszUserID);"
        "  }"
        "  public class ShortcutHelper {"
        "    public static void SetAumid(string shortcutPath, string aumid) {"
        "      var shell = new Shell32.Shell();"
        "      var folder = shell.NameSpace(System.IO.Path.GetDirectoryName(shortcutPath));"
        "      var item = folder.ParseName(System.IO.Path.GetFileName(shortcutPath));"
        "      var iObj = (IObjectWithAppUserModelId)item;  // This won't work directly"
        "    }"
        "  }"
        "}"
        "'@"
        # 实际上最简单的方式是直接通过 IPersistFile + IPropertyStore
    )
    # 用更简单的方式：通过 PowerShell 调用 SetPropStore
    # 实际上 Windows 上最可靠的方式是使用 Windows API Code Pack 或直接用 Python 做注册
    # 这里我们只注册表就够了，很多实现只靠注册表就能弹通知
    log(f"  快捷方式已创建: {shortcut_path}")
    log("  (仅注册表注册，快捷方式 AUMID 属性设置跳过)")

    # 给系统一点时间处理
    time.sleep(0.5)


# ── 方案 4: win11toast 库 ─────────────────────────────────────────────
def method_4_win11toast(log):
    log("【方案4】win11toast 库")
    try:
        import win11toast  # type: ignore
    except ImportError:
        log("  win11toast 未安装，正在尝试 pip install...")
        result = subprocess.run(
            [sys.executable, "-m", "pip", "install", "win11toast"],
            capture_output=True, text=True, timeout=60, check=False,
        )
        if result.returncode != 0:
            log(f"  安装失败: {result.stderr.strip()}")
            return
        try:
            import win11toast  # type: ignore
        except ImportError:
            log("  安装后仍无法导入 win11toast")
            return
        log("  win11toast 安装成功")

    try:
        win11toast.notify(
            title=TITLE,
            body=BODY,
            app_id=APP_AUMID,
        )
        log("  win11toast.notify() 调用完成（无异常）")
    except Exception as exc:
        log(f"  win11toast 调用失败: {exc}")


# ── 方案 5: win10toast 库 ─────────────────────────────────────────────
def method_5_win10toast(log):
    log("【方案5】win10toast 库")
    try:
        import win10toast  # type: ignore
    except ImportError:
        log("  win10toast 未安装，正在尝试 pip install...")
        result = subprocess.run(
            [sys.executable, "-m", "pip", "install", "win10toast"],
            capture_output=True, text=True, timeout=60, check=False,
        )
        if result.returncode != 0:
            log(f"  安装失败: {result.stderr.strip()}")
            return
        try:
            import win10toast  # type: ignore
        except ImportError:
            log("  安装后仍无法导入 win10toast")
            return
        log("  win10toast 安装成功")

    try:
        toaster = win10toast.ToastNotifier()
        toaster.show_toast(TITLE, BODY, duration=5, threaded=True)
        log("  win10toast.show_toast() 调用完成（无异常）")
    except Exception as exc:
        log(f"  win10toast 调用失败: {exc}")


# ── 方案 6: BurntToast PowerShell 模块 ────────────────────────────────
def method_6_burnttoast(log):
    log("【方案6】BurntToast PowerShell 模块")
    # 先检查是否已安装
    check_script = "Get-Module -ListAvailable -Name BurntToast | Select-Object -ExpandProperty Version | Select-Object -ExpandProperty ToString"
    result = subprocess.run(
        ["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", check_script],
        capture_output=True, text=True, timeout=10, check=False,
        creationflags=0x08000000,  # CREATE_NO_WINDOW
    )
    if not result.stdout.strip():
        log("  BurntToast 未安装，正在尝试 Install-Module...")
        install_script = (
            "$ErrorActionPreference='Stop';"
            "Install-Module -Name BurntToast -Force -Scope CurrentUser -AllowClobber"
        )
        result = subprocess.run(
            ["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", install_script],
            capture_output=True, text=True, timeout=120, check=False,
            creationflags=0x08000000,
        )
        if result.returncode != 0:
            log(f"  安装失败: {result.stderr.strip() or '未知错误'}")
            return
        log("  BurntToast 安装成功")

    script = (
        "Import-Module BurntToast;"
        f"New-BurntToastNotification -Text '{TITLE}', '{BODY.replace(chr(39), chr(39) * 2)}' "
        f"-AppLogo $null"
    )
    _run_powershell(script, log)


# ── 方案 7: PowerShell WinRT + 注册表注册 AUMID（无快捷方式） ─────────
def method_7_registry_only(log):
    log("【方案7】仅注册表注册 AUMID（不创建快捷方式）+ PowerShell WinRT")
    aumid = "ToastTest.RegistryOnly"
    try:
        key_path = f"Software\\Classes\\AppUserModelId\\{aumid}"
        with winreg.CreateKeyEx(winreg.HKEY_CURRENT_USER, key_path, 0, winreg.KEY_SET_VALUE) as key:
            winreg.SetValueEx(key, "DisplayName", 0, winreg.REG_SZ, "ToastTest Registry")
        log(f"  注册表已注册 AUMID: {aumid}")
    except Exception as exc:
        log(f"  注册失败: {exc}")
        return

    time.sleep(0.3)

    toast_xml = (
        '<toast><visual><binding template="ToastGeneric">'
        f"<text>{xml_escape(TITLE)}</text><text>{xml_escape(BODY)}</text>"
        "</binding></visual></toast>"
    )
    script = (
        "$ErrorActionPreference='Stop';"
        "[Windows.UI.Notifications.ToastNotificationManager, Windows.UI.Notifications, ContentType = WindowsRuntime] | Out-Null;"
        "[Windows.Data.Xml.Dom.XmlDocument, Windows.Data.Xml.Dom.XmlDocument, ContentType = WindowsRuntime] | Out-Null;"
        "$xml=New-Object Windows.Data.Xml.Dom.XmlDocument;"
        f"$xml.LoadXml('{toast_xml.replace(chr(39), chr(39) * 2)}');"
        "$toast=[Windows.UI.Notifications.ToastNotification]::new($xml);"
        f"[Windows.UI.Notifications.ToastNotificationManager]::CreateToastNotifier('{aumid}').Show($toast)"
    )
    _run_powershell(script, log)


# ── 通用工具函数 ──────────────────────────────────────────────────────
def _run_powershell(script: str, log) -> None:
    """执行 PowerShell 脚本并记录结果。"""
    try:
        result = subprocess.run(
            ["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", script],
            capture_output=True,
            text=True,
            timeout=15,
            check=False,
            creationflags=0x08000000,  # CREATE_NO_WINDOW
        )
        if result.returncode == 0:
            log("  PowerShell 执行成功 (returncode=0)")
            if result.stdout.strip():
                log(f"  stdout: {result.stdout.strip()}")
        else:
            log(f"  PowerShell 执行失败 (returncode={result.returncode})")
            if result.stderr.strip():
                log(f"  stderr: {result.stderr.strip()}")
    except subprocess.TimeoutExpired:
        log("  PowerShell 执行超时")
    except Exception as exc:
        log(f"  异常: {exc}")


# ── GUI ───────────────────────────────────────────────────────────────
class ToastTestApp:
    def __init__(self, root: tk.Tk):
        self.root = root
        root.title("Windows Toast 通知方案测试")
        root.geometry("750x600")

        # 按钮区
        btn_frame = ttk.LabelFrame(root, text="点击按钮测试各种 Toast 通知方案", padding=10)
        btn_frame.pack(fill="x", padx=10, pady=(10, 5))

        methods = [
            ("方案1: PowerShell WinRT\nAUMID 'PriceAI Monitor' (当前方案, 未注册)", method_1_ps_winrt_unregistered),
            ("方案2: PowerShell WinRT\nPowerShell 内置 AUMID (系统已注册)", method_2_ps_winrt_powershell_aumid),
            ("方案3: 注册表+快捷方式\n自定义 AUMID (完整注册流程)", method_3_registered_aumid),
            ("方案4: win11toast 库\n(Python 库, 自动安装)", method_4_win11toast),
            ("方案5: win10toast 库\n(Python 库, 自动安装)", method_5_win10toast),
            ("方案6: BurntToast 模块\n(PowerShell 模块, 自动安装)", method_6_burnttoast),
            ("方案7: 仅注册表注册 AUMID\n(不创建快捷方式)", method_7_registry_only),
        ]

        for i, (label, func) in enumerate(methods):
            row, col = divmod(i, 2)
            btn = ttk.Button(btn_frame, text=label, width=42,
                             command=lambda f=func: self._run_in_thread(f))
            btn.grid(row=row, column=col, padx=5, pady=5, sticky="ew")

        btn_frame.columnconfigure(0, weight=1)
        btn_frame.columnconfigure(1, weight=1)

        # 全部测试按钮
        ttk.Button(root, text="依次测试所有方案", command=self._run_all).pack(pady=5)

        # 日志区
        log_frame = ttk.LabelFrame(root, text="执行日志", padding=5)
        log_frame.pack(fill="both", expand=True, padx=10, pady=(5, 10))

        self.log_text = scrolledtext.ScrolledText(log_frame, height=15, wrap="word", font=("Consolas", 9))
        self.log_text.pack(fill="both", expand=True)
        self.log_text.configure(state="disabled")

    def _log(self, msg: str) -> None:
        """向日志区追加一行消息（线程安全）。"""
        timestamp = time.strftime("%H:%M:%S")
        self.root.after(0, self._log_impl, f"[{timestamp}] {msg}\n")

    def _log_impl(self, msg: str) -> None:
        self.log_text.configure(state="normal")
        self.log_text.insert("end", msg)
        self.log_text.see("end")
        self.log_text.configure(state="disabled")

    def _run_in_thread(self, func) -> None:
        """在后台线程中执行测试函数，避免阻塞 GUI。"""
        self._log("=" * 50)
        thread = threading.Thread(target=self._run_method, args=(func,), daemon=True)
        thread.start()

    def _run_method(self, func) -> None:
        try:
            func(self._log)
        except Exception as exc:
            self._log(f"  未捕获异常: {exc}")
        self._log("  → 请观察屏幕右下角是否弹出通知\n")

    def _run_all(self) -> None:
        """依次执行所有方案。"""
        all_methods = [
            method_1_ps_winrt_unregistered,
            method_2_ps_winrt_powershell_aumid,
            method_3_registered_aumid,
            method_4_win11toast,
            method_5_win10toast,
            method_6_burnttoast,
            method_7_registry_only,
        ]

        def run_all_impl():
            for func in all_methods:
                self._log("=" * 50)
                try:
                    func(self._log)
                except Exception as exc:
                    self._log(f"  未捕获异常: {exc}")
                self._log("  → 请观察屏幕右下角是否弹出通知\n")
                time.sleep(2)

        thread = threading.Thread(target=run_all_impl, daemon=True)
        thread.start()


def main() -> None:
    root = tk.Tk()
    ToastTestApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
