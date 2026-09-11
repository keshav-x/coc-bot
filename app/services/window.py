import ctypes
from ctypes import wintypes
from dataclasses import dataclass
import numpy as np
import cv2
from PIL import Image
from typing import List, Optional, Tuple

from app.utils.logger import setup_logger
from app.utils.window_settings_store import WindowSelection, load_window_selection

logger = setup_logger("WindowService")

WM_LBUTTONDOWN = 0x0201
WM_LBUTTONUP = 0x0202
WM_MOUSEMOVE = 0x0200
MK_LBUTTON = 0x0001
WM_MOUSEWHEEL = 0x020A
WHEEL_DELTA = 120

_CHILD_CLASS_PREFIX = "CROSVM"


@dataclass
class WindowCandidate:
    """A visible top-level window plus its resolved Google Play Games game surface (if any)."""

    top_hwnd: int
    title: str
    top_class: str
    child_hwnd: int
    child_class: str

    @property
    def is_game(self) -> bool:
        return self.child_hwnd != 0

    def to_selection(self) -> WindowSelection:
        return WindowSelection(
            title=self.title,
            top_class=self.top_class,
            child_class=self.child_class,
        )

    def display_label(self) -> str:
        title = self.title if self.title else "(no title)"
        if self.is_game:
            return f"{title}  —  surface: {self.child_class}"
        return f"{title}  —  no game surface ({self.top_class})"


@dataclass
class DescendantInfo:
    """A single descendant window under a top-level window (for the Info diagnostics view)."""

    hwnd: int
    cls: str
    title: str
    width: int
    height: int
    depth: int
    is_surface: bool

    def display_label(self) -> str:
        indent = "    " * self.depth
        marker = "[surface] " if self.is_surface else ""
        size = f"{self.width}x{self.height}" if self.width and self.height else "—"
        title = f'  "{self.title}"' if self.title else ""
        return f"{indent}{marker}{self.cls}  ({size})  hwnd={self.hwnd}{title}"


class WindowService:
    def __init__(self, window_name: str = "Google Play Games", child_class: Optional[str] = None):
        self.window_name = window_name
        self.child_class = child_class
        self.hwnd = 0
        self.user32 = ctypes.windll.user32
        self.gdi32 = ctypes.windll.gdi32

        try:
            ctypes.windll.shcore.SetProcessDpiAwareness(2)
        except Exception:
            self.user32.SetProcessDPIAware()

        self.find_window()

    def find_window(self) -> bool:
        selection = load_window_selection()
        self.hwnd = self._resolve_hwnd(selection)
        if self.hwnd:
            how = "pinned selection" if selection.is_set() else "auto-detect"
            logger.info(f"Window found via {how} (HWND: {self.hwnd})")
            return True

        if selection.is_set():
            logger.warning(
                f"Pinned game window not found (title={selection.title!r}, child={selection.child_class!r}); falling back to auto-detect."
            )
            self.hwnd = self._auto_detect_child()
            if self.hwnd:
                logger.info(f"Window found via auto-detect fallback (HWND: {self.hwnd})")
                return True

        logger.warning(
            f"Window not found: {self.window_name} (expect a titled window with a {_CHILD_CLASS_PREFIX!r}* surface, either as the top-level window itself or a descendant — Google Play Games). Open Settings → Game window to pick it manually."
        )
        return False

    def _get_class(self, hwnd: int) -> str:
        buf = ctypes.create_unicode_buffer(256)
        self.user32.GetClassNameW(hwnd, buf, 256)
        return buf.value

    def _get_title(self, hwnd: int) -> str:
        length = self.user32.GetWindowTextLengthW(hwnd)
        if length == 0:
            return ""
        buff = ctypes.create_unicode_buffer(length + 1)
        self.user32.GetWindowTextW(hwnd, buff, length + 1)
        return buff.value

    def _find_descendant(self, root_hwnd: int, predicate) -> Tuple[int, str]:
        EnumChildWindows = self.user32.EnumChildWindows
        EnumWindowsProc = ctypes.WINFUNCTYPE(ctypes.c_bool, wintypes.HWND, wintypes.LPARAM)
        found = {"hwnd": 0, "class": ""}

        def enum_child_cb(child_hwnd, _):
            cls = self._get_class(child_hwnd)
            if predicate(cls):
                found["hwnd"] = child_hwnd
                found["class"] = cls
                return False
            EnumChildWindows(child_hwnd, EnumWindowsProc(enum_child_cb), 0)
            return True

        EnumChildWindows(root_hwnd, EnumWindowsProc(enum_child_cb), 0)
        return (found["hwnd"], found["class"])

    def _find_crosvm_descendant(
        self, root_hwnd: int, preferred_class: Optional[str] = None
    ) -> Tuple[int, str]:
        if preferred_class:
            hwnd, cls = self._find_descendant(root_hwnd, lambda c: c == preferred_class)
            if hwnd:
                return (hwnd, cls)
        return self._find_descendant(
            root_hwnd, lambda c: c.upper().startswith(_CHILD_CLASS_PREFIX)
        )

    def _resolve_surface(
        self, top_hwnd: int, top_class: str, preferred_class: Optional[str] = None
    ) -> Tuple[int, str]:
        hwnd, cls = self._find_crosvm_descendant(top_hwnd, preferred_class)
        if hwnd:
            return (hwnd, cls)
        if top_class.upper().startswith(_CHILD_CLASS_PREFIX):
            return (top_hwnd, top_class)
        # Check for common emulator render surfaces (BlueStacks, LDPlayer, MuMu)
        emulator_prefixes = ("RENDERWINDOW", "SUBWIN", "OPENGLLINK", "QT5QWINDOWICON")
        for pref in emulator_prefixes:
            ehwnd, ecls = self._find_descendant(top_hwnd, lambda c: pref in c.upper())
            if ehwnd:
                return (ehwnd, ecls)
        return (0, "")

    def enumerate_windows(self) -> List[WindowCandidate]:
        EnumWindows = self.user32.EnumWindows
        EnumWindowsProc = ctypes.WINFUNCTYPE(ctypes.c_bool, wintypes.HWND, wintypes.LPARAM)
        IsWindowVisible = self.user32.IsWindowVisible
        candidates = []

        def enum_top_cb(hwnd, _):
            if IsWindowVisible(hwnd):
                title = self._get_title(hwnd)
                if title:
                    top_class = self._get_class(hwnd)
                    child_hwnd, child_class = self._resolve_surface(hwnd, top_class)
                    candidates.append(
                        WindowCandidate(
                            top_hwnd=hwnd,
                            title=title,
                            top_class=top_class,
                            child_hwnd=child_hwnd,
                            child_class=child_class,
                        )
                    )
            return True

        EnumWindows(EnumWindowsProc(enum_top_cb), 0)
        candidates.sort(key=lambda c: (not c.is_game, c.title.lower()))
        return candidates

    def enumerate_descendants(self, root_hwnd: int) -> List[DescendantInfo]:
        EnumChildWindows = self.user32.EnumChildWindows
        EnumWindowsProc = ctypes.WINFUNCTYPE(ctypes.c_bool, wintypes.HWND, wintypes.LPARAM)
        results = []
        seen = set()

        def walk(parent_hwnd, depth):
            def cb(child_hwnd, _):
                if child_hwnd not in seen:
                    seen.add(child_hwnd)
                    cls = self._get_class(child_hwnd)
                    size = self.window_pixel_size(child_hwnd)
                    results.append(
                        DescendantInfo(
                            hwnd=child_hwnd,
                            cls=cls,
                            title=self._get_title(child_hwnd),
                            width=size[0] if size else 0,
                            height=size[1] if size else 0,
                            depth=depth,
                            is_surface=cls.upper().startswith(_CHILD_CLASS_PREFIX),
                        )
                    )
                    walk(child_hwnd, depth + 1)
                return True

            EnumChildWindows(parent_hwnd, EnumWindowsProc(cb), 0)

        walk(root_hwnd, 0)
        return results

    def window_pixel_size(self, hwnd: int) -> Optional[Tuple[int, int]]:
        if not hwnd:
            return None
        try:
            rect = wintypes.RECT()
            self.user32.GetWindowRect(hwnd, ctypes.byref(rect))
            w = rect.right - rect.left
            h = rect.bottom - rect.top
            if w <= 0 or h <= 0:
                return None
            return (int(w), int(h))
        except Exception:
            return None

    def _resolve_hwnd(self, selection: WindowSelection) -> int:
        if not selection.is_set():
            return self._auto_detect_child()

        wanted_title = selection.title.strip().lower()
        for cand in self.enumerate_windows():
            if wanted_title and cand.title.strip().lower() != wanted_title:
                continue
            if selection.top_class and cand.top_class != selection.top_class:
                continue
            surface_hwnd, _ = self._resolve_surface(
                cand.top_hwnd, cand.top_class, selection.child_class
            )
            if surface_hwnd:
                return surface_hwnd

        return 0

    def _auto_detect_child(self) -> int:
        candidates = self.enumerate_windows()

        # Tier 1: Windows whose title specifically contains "clash of clans" with a game surface
        for cand in candidates:
            if cand.is_game and "clash of clans" in cand.title.lower():
                return cand.child_hwnd

        # Tier 2: Windows titled "google play games" with a game surface
        name = self.window_name.lower()
        for cand in candidates:
            if cand.is_game and (name in cand.title.lower() or "google play" in cand.title.lower()):
                return cand.child_hwnd

        # Tier 3: Any window with an active game surface
        for cand in candidates:
            if cand.is_game:
                return cand.child_hwnd

        # Tier 4: Top-level window titled "clash of clans" (direct window handle)
        for cand in candidates:
            if "clash of clans" in cand.title.lower():
                return cand.child_hwnd if cand.child_hwnd else cand.top_hwnd

        # Tier 5: Common emulator windows (BlueStacks, LDPlayer, MuMu, Nox)
        for cand in candidates:
            t_low = cand.title.lower()
            if any(emu in t_low for emu in ("bluestacks", "ldplayer", "mumu", "nox")):
                return cand.child_hwnd if cand.child_hwnd else cand.top_hwnd

        return 0

    def get_outer_pixel_size(self) -> Optional[Tuple[int, int]]:
        if not self.hwnd and not self.find_window():
            return None

        try:
            client_rect = wintypes.RECT()
            if self.user32.GetClientRect(self.hwnd, ctypes.byref(client_rect)):
                cw = client_rect.right - client_rect.left
                ch = client_rect.bottom - client_rect.top
                if cw > 0 and ch > 0:
                    return (int(cw), int(ch))

            rect = wintypes.RECT()
            self.user32.GetWindowRect(self.hwnd, ctypes.byref(rect))
            w = rect.right - rect.left
            h = rect.bottom - rect.top
            if w <= 0 or h <= 0:
                return None
            return (int(w), int(h))
        except Exception:
            return None

    def screenshot(self):
        if not self.hwnd and not self.find_window():
            return None

        hwndDC = None
        mfcDC = None
        hbitmap = None
        old_bitmap = None

        try:
            rect = wintypes.RECT()
            self.user32.GetWindowRect(self.hwnd, ctypes.byref(rect))
            width = rect.right - rect.left
            height = rect.bottom - rect.top
            if width <= 0 or height <= 0:
                return None

            client_rect = wintypes.RECT()
            self.user32.GetClientRect(self.hwnd, ctypes.byref(client_rect))
            client_w = client_rect.right - client_rect.left
            client_h = client_rect.bottom - client_rect.top

            class POINT(ctypes.Structure):
                _fields_ = [("x", ctypes.c_long), ("y", ctypes.c_long)]

            pt = POINT(0, 0)
            self.user32.ClientToScreen(self.hwnd, ctypes.byref(pt))
            offset_x = max(0, pt.x - rect.left)
            offset_y = max(0, pt.y - rect.top)

            hwndDC = self.user32.GetWindowDC(self.hwnd)
            if not hwndDC:
                return None
            mfcDC = self.gdi32.CreateCompatibleDC(hwndDC)
            if not mfcDC:
                return None
            hbitmap = self.gdi32.CreateCompatibleBitmap(hwndDC, width, height)
            if not hbitmap:
                return None
            old_bitmap = self.gdi32.SelectObject(mfcDC, hbitmap)

            PW_RENDERFULLCONTENT = 2
            self.user32.PrintWindow(self.hwnd, mfcDC, PW_RENDERFULLCONTENT)

            class BITMAPINFOHEADER(ctypes.Structure):
                _fields_ = [
                    ("biSize", wintypes.DWORD),
                    ("biWidth", ctypes.c_long),
                    ("biHeight", ctypes.c_long),
                    ("biPlanes", wintypes.WORD),
                    ("biBitCount", wintypes.WORD),
                    ("biCompression", wintypes.DWORD),
                    ("biSizeImage", wintypes.DWORD),
                    ("biXPelsPerMeter", ctypes.c_long),
                    ("biYPelsPerMeter", ctypes.c_long),
                    ("biClrUsed", wintypes.DWORD),
                    ("biClrImportant", wintypes.DWORD),
                ]

            bmi = BITMAPINFOHEADER()
            bmi.biSize = ctypes.sizeof(BITMAPINFOHEADER)
            bmi.biWidth = width
            bmi.biHeight = -height
            bmi.biPlanes = 1
            bmi.biBitCount = 32
            bmi.biCompression = 0

            buf_size = width * height * 4
            buffer = (ctypes.c_byte * buf_size)()
            self.gdi32.GetDIBits(
                hwndDC, hbitmap, 0, height, ctypes.byref(buffer), ctypes.byref(bmi), 0
            )

            img = Image.frombuffer(
                "RGBA", (width, height), bytes(buffer), "raw", "BGRA", 0, 1
            )
            frame = np.array(img)

            if frame.shape[2] == 4:
                frame = cv2.cvtColor(frame, cv2.COLOR_RGBA2BGR)
            else:
                frame = cv2.cvtColor(frame, cv2.COLOR_RGB2BGR)

            if client_w > 0 and client_h > 0:
                end_y = min(frame.shape[0], offset_y + client_h)
                end_x = min(frame.shape[1], offset_x + client_w)
                if offset_y < end_y and offset_x < end_x:
                    frame = frame[offset_y:end_y, offset_x:end_x]

            return frame
        except Exception as e:
            logger.error(f"Screenshot failed: {e}")
            return None
        finally:
            if mfcDC:
                if old_bitmap:
                    self.gdi32.SelectObject(mfcDC, old_bitmap)
                self.gdi32.DeleteDC(mfcDC)
            if hbitmap:
                self.gdi32.DeleteObject(hbitmap)
            if hwndDC and self.hwnd:
                self.user32.ReleaseDC(self.hwnd, hwndDC)
