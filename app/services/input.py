import ctypes
import time
import random
import math
from typing import Tuple

from app.services.window import (
    WindowService,
    WM_LBUTTONDOWN,
    WM_LBUTTONUP,
    WM_MOUSEMOVE,
    MK_LBUTTON,
    WM_MOUSEWHEEL,
    WHEEL_DELTA,
)
from app.utils.logger import setup_logger

logger = setup_logger("InputService")


class InputService:
    def __init__(self, window_service, stop_event=None):
        self.window_service = window_service
        self.stop_event = stop_event
        self.user32 = ctypes.windll.user32

    def _clamp_to_capture(self, x, y):
        sz = self.window_service.get_outer_pixel_size()
        if not sz:
            return (int(x), int(y))
        w, h = sz
        if w <= 1 or h <= 1:
            return (int(x), int(y))
        cx = max(0, min(w - 1, int(x)))
        cy = max(0, min(h - 1, int(y)))
        return (cx, cy)

    def _make_lparam(self, x, y):
        xc, yc = self._clamp_to_capture(x, y)
        return (yc << 16) | (xc & 0xFFFF)

    def _client_to_screen(self, x, y):
        hwnd = self.window_service.hwnd
        if not hwnd:
            return self._clamp_to_capture(x, y)
        xc, yc = self._clamp_to_capture(x, y)

        class POINT(ctypes.Structure):
            _fields_ = [("x", ctypes.c_long), ("y", ctypes.c_long)]

        pt = POINT(xc, yc)
        if not self.user32.ClientToScreen(hwnd, ctypes.byref(pt)):
            return (xc, yc)
        return (int(pt.x), int(pt.y))

    def _make_wheel_lparam(self, screen_x, screen_y):
        sx = int(screen_x) & 0xFFFF
        sy = int(screen_y) & 0xFFFF
        return (sy << 16) | sx

    def _unpack_coords(self, x, y=None):
        if isinstance(x, (tuple, list)) and len(x) >= 2:
            return (x[0], x[1])
        return (x, y)

    def click(self, x, y=None, pause=0.2, rand=True):
        if isinstance(x, (tuple, list)):
            if len(x) >= 2:
                if y is not None and isinstance(y, (int, float)) and pause == 0.2:
                    pause = float(y)
                x, y = x[0], x[1]
        else:
            x, y = self._unpack_coords(x, y)
        if y is None:
            logger.warning(f"click called with invalid coordinates: x={x}, y={y}")
            return
        if rand:
            x += random.randint(-2, 2)
            y += random.randint(-2, 2)
        self._inject_click(x, y)
        sleep_time = random.uniform(pause - pause * 0.2, pause + pause * 0.2)
        if self.stop_event:
            self.stop_event.wait(max(0.05, sleep_time))
        else:
            time.sleep(max(0.05, sleep_time))

    def _inject_click(self, x, y):
        hwnd = self.window_service.hwnd
        if not hwnd:
            return
        lparam = self._make_lparam(int(x), int(y))
        self.user32.SendMessageW(hwnd, WM_LBUTTONDOWN, MK_LBUTTON, lparam)
        dwell = random.uniform(0.045, 0.085)
        if self.stop_event:
            self.stop_event.wait(dwell)
        else:
            time.sleep(dwell)
        self.user32.SendMessageW(hwnd, WM_LBUTTONUP, 0, lparam)

    def click_at(self, x, y=None, rand=True):
        if isinstance(x, (tuple, list)):
            if len(x) >= 2:
                x, y = x[0], x[1]
        if y is None:
            return
        if rand:
            x += random.randint(-2, 2)
            y += random.randint(-2, 2)
        self._inject_click(int(x), int(y))

    def mouse_down(self, x, y):
        hwnd = self.window_service.hwnd
        if not hwnd:
            return
        self.user32.SendMessageW(hwnd, WM_LBUTTONDOWN, MK_LBUTTON, self._make_lparam(x, y))

    def mouse_up(self, x, y):
        hwnd = self.window_service.hwnd
        if not hwnd:
            return
        self.user32.SendMessageW(hwnd, WM_LBUTTONUP, 0, self._make_lparam(x, y))

    def move(self, x, y, wparam=0):
        hwnd = self.window_service.hwnd
        if not hwnd:
            return
        self.user32.SendMessageW(hwnd, WM_MOUSEMOVE, wparam, self._make_lparam(x, y))

    def human_move(self, x1, y1, x2, y2, duration=0.3):
        mx = (x1 + x2) / 2
        my = (y1 + y2) / 2
        dist = ((x2 - x1) ** 2 + (y2 - y1) ** 2) ** 0.5
        offset = dist * random.uniform(0.02, 0.15)
        cx = mx + random.uniform(-offset, offset)
        cy = my + random.uniform(-offset, offset)
        start_time = time.perf_counter()

        while True:
            if self.stop_event and self.stop_event.is_set():
                break
            current_time = time.perf_counter()
            elapsed = current_time - start_time
            if elapsed >= duration:
                break
            t = elapsed / duration
            ease = -(math.cos(math.pi * t) - 1) / 2
            u = 1 - ease
            x = (u**2) * x1 + 2 * u * ease * cx + (ease**2) * x2
            y = (u**2) * y1 + 2 * u * ease * cy + (ease**2) * y2
            self.move(int(x), int(y), MK_LBUTTON)
            if self.stop_event:
                self.stop_event.wait(0.005)
            else:
                time.sleep(0.005)

        self.move(x2, y2, MK_LBUTTON)

    def scroll(self, x, y, amount, upward=False):
        hwnd = self.window_service.hwnd
        if not hwnd:
            return
        delta = int(WHEEL_DELTA if upward else -WHEEL_DELTA)
        wparam = delta << 16
        sx, sy = self._client_to_screen(x, y)
        lparam = self._make_wheel_lparam(sx, sy)
        for _ in range(amount):
            if self.stop_event and self.stop_event.is_set():
                break
            self.user32.SendMessageW(hwnd, WM_MOUSEWHEEL, wparam, lparam)
            if self.stop_event:
                self.stop_event.wait(0.02)
            else:
                time.sleep(0.02)
