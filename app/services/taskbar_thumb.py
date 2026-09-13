"""
Windows taskbar thumbnail toolbar - adds Start/Stop buttons to the taskbar preview.
Uses Pillow to generate play/stop icons and ITaskbarList3 for the toolbar.
Windows 7+ only.
"""

import ctypes
from ctypes import wintypes
import tempfile
import os
from typing import Optional, Callable
from PIL import Image, ImageDraw

from app.utils.logger import setup_logger

logger = setup_logger("TaskbarThumb")

WM_COMMAND = 273
THBN_CLICKED = 6144
GWLP_WNDPROC = -4
GA_ROOT = 2
GA_ROOTOWNER = 3
IMAGE_ICON = 1
LR_LOADFROMFILE = 16
LR_DEFAULTSIZE = 64

THB_ICON = 2
THB_TOOLTIP = 4
THB_FLAGS = 8
THBF_ENABLED = 0
THBF_DISABLED = 1
THBF_DISMISSONCLICK = 2

BTN_START = 1
BTN_STOP = 2

CLSCTX_INPROC_SERVER = 1


def _create_play_icon(size: int = 20) -> wintypes.HICON:
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    margin = size // 5
    left, top, bottom, right = margin, margin, size - margin, size - margin
    mid_y = (top + bottom) // 2
    draw.polygon([(left, top), (left, bottom), (right, mid_y)], fill=(255, 255, 255))
    return _pil_to_hicon(img)


def _create_stop_icon(size: int = 20) -> wintypes.HICON:
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    margin = size // 5
    draw.rectangle([margin, margin, size - margin, size - margin], fill=(255, 255, 255))
    return _pil_to_hicon(img)


def _pil_to_hicon(img: Image.Image) -> wintypes.HICON:
    user32 = ctypes.windll.user32
    fd, path = tempfile.mkstemp(suffix=".ico")
    os.close(fd)
    img.save(path, format="ICO", sizes=[(img.width, img.height)])
    path_w = os.path.abspath(path)
    hicon = user32.LoadImageW(
        None, path_w, IMAGE_ICON, img.width, img.height, LR_LOADFROMFILE | LR_DEFAULTSIZE
    )
    if not hicon:
        raise RuntimeError("LoadImageW failed")
    try:
        os.unlink(path)
    except OSError:
        pass
    return wintypes.HICON(hicon)


class GUID(ctypes.Structure):
    _fields_ = [
        ("Data1", ctypes.c_ulong),
        ("Data2", ctypes.c_ushort),
        ("Data3", ctypes.c_ushort),
        ("Data4", ctypes.c_ubyte * 8),
    ]


def _guid_from_str(s: str) -> GUID:
    s = s.replace("{", "").replace("}", "").replace("-", "")
    return GUID(
        int(s[0:8], 16),
        int(s[8:12], 16),
        int(s[12:16], 16),
        (ctypes.c_ubyte * 8)(*(int(s[16 + i * 2 : 18 + i * 2], 16) for i in range(8))),
    )


class THUMBBUTTON(ctypes.Structure):
    _fields_ = [
        ("dwMask", wintypes.DWORD),
        ("iId", wintypes.UINT),
        ("iBitmap", wintypes.UINT),
        ("hIcon", wintypes.HANDLE),
        ("szTip", wintypes.WCHAR * 260),
        ("dwFlags", wintypes.DWORD),
    ]


VTIDX_HRINIT = 3
VTIDX_THUMBBAR_ADD = 15
VTIDX_THUMBBAR_UPDATE = 16

ThumbBarAddButtons_t = ctypes.WINFUNCTYPE(
    ctypes.c_long,
    ctypes.c_void_p,
    wintypes.HWND,
    wintypes.UINT,
    ctypes.POINTER(THUMBBUTTON),
)

ThumbBarUpdateButtons_t = ctypes.WINFUNCTYPE(
    ctypes.c_long,
    ctypes.c_void_p,
    wintypes.HWND,
    wintypes.UINT,
    ctypes.POINTER(THUMBBUTTON),
)

HrInit_t = ctypes.WINFUNCTYPE(ctypes.c_long, ctypes.c_void_p)


class TaskbarThumb:
    def __init__(self, on_start: Callable, on_stop: Callable):
        self.on_start = on_start
        self.on_stop = on_stop
        self._taskbar_ptr = None
        self._play_icon = None
        self._stop_icon = None
        self._original_wndproc = None
        self._wndproc_ref = None
        self._polling = False
        self.hwnd = 0

    def setup(self, hwnd=None, title=None) -> bool:
        ole32 = ctypes.windll.ole32
        user32 = ctypes.windll.user32
        self.hwnd = int(hwnd) if hwnd else 0
        if not self.hwnd:
            logger.warning("Could not find valid HWND for taskbar")
            return False

        try:
            self._play_icon = _create_play_icon()
            self._stop_icon = _create_stop_icon()
        except Exception as e:
            logger.warning(f"Failed to create taskbar icons: {e}")
            return False

        ole32.CoInitializeEx(None, 0)
        if not self._setup_com():
            return False
        if not self._add_buttons():
            return False
        self._start_message_hook()
        logger.info("Taskbar thumbnail toolbar initialized (hwnd=%s)", self.hwnd)
        return True

    def _get_vtable(self):
        vtable_pp = ctypes.cast(self._taskbar_ptr, ctypes.POINTER(ctypes.c_void_p))
        return ctypes.cast(vtable_pp[0], ctypes.POINTER(ctypes.c_void_p))

    def _setup_com(self) -> bool:
        ole32 = ctypes.windll.ole32
        clsid = _guid_from_str("56FDF344-FD6D-11d0-958A-006097C9A090")
        iid = _guid_from_str("EA1AFB91-9E28-4B86-90E9-9E9F8A5EEFAF")
        taskbar = ctypes.c_void_p()
        hr = ole32.CoCreateInstance(
            ctypes.byref(clsid),
            None,
            CLSCTX_INPROC_SERVER,
            ctypes.byref(iid),
            ctypes.byref(taskbar),
        )
        if hr != 0:
            logger.warning(f"CoCreateInstance failed: 0x{hr:08X}")
            return False
        self._taskbar_ptr = taskbar
        vtable = self._get_vtable()
        hr_init = ctypes.cast(vtable[VTIDX_HRINIT], HrInit_t)
        hr = hr_init(self._taskbar_ptr)
        if hr != 0:
            logger.warning(f"HrInit failed: 0x{hr:08X}")
            return False
        return True

    def _add_buttons(self) -> bool:
        vtable = self._get_vtable()
        add_buttons_fn = ctypes.cast(vtable[VTIDX_THUMBBAR_ADD], ThumbBarAddButtons_t)
        mask = THB_ICON | THB_TOOLTIP | THB_FLAGS
        btns = (THUMBBUTTON * 2)()

        btns[0].dwMask = mask
        btns[0].iId = BTN_START
        btns[0].hIcon = self._play_icon
        btns[0].szTip = "Start"
        btns[0].dwFlags = THBF_ENABLED | THBF_DISMISSONCLICK

        btns[1].dwMask = mask
        btns[1].iId = BTN_STOP
        btns[1].hIcon = self._stop_icon
        btns[1].szTip = "Stop"
        btns[1].dwFlags = THBF_DISABLED | THBF_DISMISSONCLICK

        hr = add_buttons_fn(self._taskbar_ptr, self.hwnd, 2, btns)
        if hr != 0:
            logger.warning(f"ThumbBarAddButtons failed: 0x{hr:08X}")
            return False
        return True

    def _start_message_hook(self):
        self._flag_start = ctypes.c_long(0)
        self._flag_stop = ctypes.c_long(0)
        user32 = ctypes.windll.user32
        LRESULT = ctypes.c_ssize_t
        WNDPROC = ctypes.WINFUNCTYPE(
            LRESULT,
            wintypes.HWND,
            wintypes.UINT,
            wintypes.WPARAM,
            wintypes.LPARAM,
        )
        CallWindowProcW = user32.CallWindowProcW
        CallWindowProcW.argtypes = [
            ctypes.c_void_p,
            wintypes.HWND,
            wintypes.UINT,
            wintypes.WPARAM,
            wintypes.LPARAM,
        ]
        CallWindowProcW.restype = LRESULT

        flag_start_ptr = ctypes.addressof(self._flag_start)
        flag_stop_ptr = ctypes.addressof(self._flag_stop)
        btn_start = BTN_START
        btn_stop = BTN_STOP
        wm_cmd = WM_COMMAND
        thbn = THBN_CLICKED

        def wndproc(hwnd, msg, wParam, lParam):
            if msg == wm_cmd:
                notif = (wParam >> 16) & 0xFFFF
                btn_id = wParam & 0xFFFF
                if notif == thbn:
                    if btn_id == btn_start:
                        ctypes.c_long.from_address(flag_start_ptr).value = 1
                    elif btn_id == btn_stop:
                        ctypes.c_long.from_address(flag_stop_ptr).value = 1
            return CallWindowProcW(self._original_wndproc, hwnd, msg, wParam, lParam)

        self._wndproc_ref = WNDPROC(wndproc)
        new_proc = ctypes.cast(self._wndproc_ref, ctypes.c_void_p).value
        SetWindowLongPtrW = user32.SetWindowLongPtrW
        SetWindowLongPtrW.argtypes = [wintypes.HWND, ctypes.c_int, ctypes.c_void_p]
        SetWindowLongPtrW.restype = ctypes.c_void_p
        self._original_wndproc = SetWindowLongPtrW(self.hwnd, GWLP_WNDPROC, new_proc)
        self._polling = True

    def poll_once(self):
        if not self._polling:
            return
        if self._flag_start.value:
            self._flag_start.value = 0
            self.on_start()
        if self._flag_stop.value:
            self._flag_stop.value = 0
            self.on_stop()

    def teardown(self):
        try:
            if self._original_wndproc and self.hwnd:
                user32 = ctypes.windll.user32
                SetWindowLongPtrW = user32.SetWindowLongPtrW
                SetWindowLongPtrW.argtypes = [wintypes.HWND, ctypes.c_int, ctypes.c_void_p]
                SetWindowLongPtrW.restype = ctypes.c_void_p
                SetWindowLongPtrW(self.hwnd, GWLP_WNDPROC, self._original_wndproc)
        except Exception:
            pass

        try:
            if self._taskbar_ptr:
                vtable = self._get_vtable()
                release = ctypes.cast(
                    vtable[2], ctypes.WINFUNCTYPE(ctypes.c_ulong, ctypes.c_void_p)
                )
                release(self._taskbar_ptr)
        except Exception:
            pass
        finally:
            self._taskbar_ptr = None
            self._original_wndproc = None

    def update_buttons(self, running: bool):
        if not self._taskbar_ptr:
            return
        vtable = self._get_vtable()
        update_fn = ctypes.cast(vtable[VTIDX_THUMBBAR_UPDATE], ThumbBarUpdateButtons_t)
        mask = THB_FLAGS
        btns = (THUMBBUTTON * 2)()

        btns[0].dwMask = mask
        btns[0].iId = BTN_START
        btns[0].dwFlags = (
            (THBF_DISABLED if running else THBF_ENABLED) | THBF_DISMISSONCLICK
        )

        btns[1].dwMask = mask
        btns[1].iId = BTN_STOP
        btns[1].dwFlags = (
            (THBF_ENABLED if running else THBF_DISABLED) | THBF_DISMISSONCLICK
        )

        update_fn(self._taskbar_ptr, self.hwnd, 2, btns)
