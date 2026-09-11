"""Attack strategies and troop placement algorithms."""

from __future__ import annotations

import math
import random
import time
from typing import Any, List, Optional, Tuple

from app.config import ASPECT_16_9, Config
from app.services.input import InputService
from app.services.vision import VisionService
from app.utils.logger import setup_logger
from app.utils.profile_settings_store import (
    EARTHQUAKE_METHOD_CURVE,
    EARTHQUAKE_METHOD_RANDOM,
)

logger = setup_logger("Strategies")

_EARTHQUAKE_REGION_ARC_SAMPLES = 49
_EARTHQUAKE_RANDOM_LINE_FROM_BOTTOM = (4, 10)
_EDRAG_COUNT = 12
_EDRAG_DELAY = 0.2
_EDRAG_CORNER_MARGIN = 100
_DIAMOND_EDGES = (("left", "top"), ("top", "right"))


class AttackStrategy:
    def __init__(
        self,
        input_service: InputService,
        vision_service: VisionService,
        config: Config,
        stop_event: Optional[Any] = None,
        earthquake_method: str = EARTHQUAKE_METHOD_CURVE,
    ) -> None:
        self.input = input_service
        self.vision = vision_service
        self.config = config
        self.stop_event = stop_event
        self.earthquake_method = earthquake_method
        self.CORNER_ORDER = ["left", "top", "right", "bottom"]

    def execute(self, frame: Any, stop_event: Optional[Any] = None) -> bool:
        raise NotImplementedError

    def _expand_loc(self, x: int, y: int) -> Tuple[int, int]:
        return (x + random.randint(-10, 10), y + random.randint(-10, 10))

    def _sync_frame_size(self, frame: Any) -> None:
        self.config.set_target_size_from_frame(frame)

    def _point(self, key: str) -> Tuple[int, int]:
        return self.config.get_point(key)

    def _scaled_deployment_data(self) -> dict[str, Tuple[int, int]]:
        return {key: self._point(key) for key in self.CORNER_ORDER}

    def deploy_multi_wave(
        self,
        troop_x: int,
        troop_y: int,
        p1: Tuple[int, int],
        p2: Tuple[int, int],
        count_per_wave: int = 5,
        num_waves: int = 2,
        delay: float = 0.09,
    ) -> None:
        """Surgically deploys troops in rapid multi-finger waves along a boundary line."""
        self.input.click(troop_x, troop_y, pause=0.2, rand=False)
        x1, y1 = p1
        x2, y2 = p2

        for _ in range(num_waves):
            if self.stop_event and self.stop_event.is_set():
                break
            for i in range(count_per_wave):
                if self.stop_event and self.stop_event.is_set():
                    break
                t = (i + random.uniform(-0.08, 0.08)) / max(1, count_per_wave - 1)
                t = max(0.0, min(1.0, t))
                dx = int(x1 + (x2 - x1) * t + random.randint(-8, 8))
                dy = int(y1 + (y2 - y1) * t + random.randint(-8, 8))
                self.input.click(dx, dy, pause=delay, rand=False)

    def deploy_heroes(self, frame: Any) -> List[Tuple[int, int]]:
        heroes = ["king", "queen", "warden", "RC", "prince"]
        deployed_heroes = []
        roi = self.vision.bottom_half_region(frame)

        ix, iy = self.vision.find_template(frame, "loglauncher.png", threshold=0.68, region=roi)
        if not ix:
            ix, iy = self.vision.find_template(frame, "siegebarracks.png", threshold=0.68, region=roi)

        if ix:
            deploy_point = self._get_hero_deploy_point(frame)
            self.input.click(ix, iy, pause=0.2, rand=False)
            self.input.click(*deploy_point, pause=0.2, rand=False)

        for hero in heroes:
            bx, by = self.vision.find_template(frame, f"{hero}.png", threshold=0.68, region=roi)
            if not bx:
                continue
            deploy_point = self._get_hero_deploy_point(frame)
            self.input.click(bx, by, pause=0.2, rand=False)
            self.input.click(*deploy_point, pause=0.2, rand=False)
            deployed_heroes.append((bx, by))
            if self.stop_event and self.stop_event.wait(0.12):
                break

        return deployed_heroes

    def activate_hero_abilities(self, deployed_heroes: List[Tuple[int, int]]) -> None:
        """Activates abilities for previously deployed heroes."""
        for hx, hy in deployed_heroes:
            if self.stop_event and self.stop_event.is_set():
                break
            self.input.click(hx, hy, pause=0.15, rand=False)
            if self.stop_event:
                self.stop_event.wait(random.uniform(0.12, 0.25))
            else:
                time.sleep(random.uniform(0.12, 0.25))

    def _hero_corner_xy(self, corner: str) -> Tuple[int, int]:
        """Corner used when building hero deploy lines; on ``16_9``, ``top`` is nudge-scaled."""
        px, py = self.config.get_point(corner)
        if self.config.aspect_key == ASPECT_16_9 and corner == "top":
            py -= self.config.scale_scalar(70)
        return (int(px), int(py))

    @staticmethod
    def _quantize_deploy_to_frame(px: float, py: float, fw: int, fh: int) -> Tuple[int, int]:
        """Clamp to ``[0, fw-1]`` x ``[0, fh-1]``, round to nearest pixels."""
        if fw <= 0 or fh <= 0:
            return (int(round(px)), int(round(py)))
        cx = max(0.0, min(float(fw - 1), float(px)))
        cy = max(0.0, min(float(fh - 1), float(py)))
        return (int(round(cx)), int(round(cy)))

    def _get_hero_deploy_point(self, frame: Any) -> Tuple[int, int]:
        c_name = random.choice(["top", "right", "left"])
        c1x, c1y = self._hero_corner_xy(c_name)
        if c_name in ("left", "right"):
            c2x, c2y = self._hero_corner_xy("top")
        else:
            corner = random.choice(["left", "right"])
            c2x, c2y = self._hero_corner_xy(corner)

        t = random.uniform(0, 1)
        xf = c1x + (c2x - c1x) * t
        yf = c1y + (c2y - c1y) * t

        if frame is not None and getattr(frame, "size", 0):
            fh, fw = frame.shape[:2]
            return self._quantize_deploy_to_frame(xf, yf, fw, fh)
        return (int(round(xf)), int(round(yf)))

    @staticmethod
    def _earthquake_anchor_triplet(
        data: dict[str, Tuple[int, int]], offset: int
    ) -> Tuple[Tuple[int, int], Tuple[int, int], Tuple[int, int]]:
        """Left / top / right drop anchors (same nudge as legacy earthquake logic)."""
        lx, ly = data["left"]
        tx, ty = data["top"]
        rx, ry = data["right"]
        return (
            (lx + int(offset * 1.3), ly),
            (tx, ty + offset),
            (rx - int(offset * 1.3), ry),
        )

    def _sample_arc_through_three(
        self,
        ltr: Tuple[Tuple[int, int], Tuple[int, int], Tuple[int, int]],
        n: int,
    ) -> List[Tuple[int, int]]:
        """``n`` points along a circular arc from L to R that passes through T.

        If L,T,R are collinear, uses a quadratic Bezier with control point chosen so t=0.5 hits T.
        """
        L, T, R = ltr
        ax, ay = float(L[0]), float(L[1])
        bx, by = float(T[0]), float(T[1])
        cx, cy = float(R[0]), float(R[1])

        d = 2.0 * (ax * (by - cy) + bx * (cy - ay) + cx * (ay - by))
        if abs(d) < 1e-06:
            p1x = 2.0 * bx - 0.5 * (ax + cx)
            p1y = 2.0 * by - 0.5 * (ay + cy)
            out = []
            for i in range(n):
                t = i / (n - 1)
                u = 1.0 - t
                x = u * u * ax + 2.0 * u * t * p1x + t * t * cx
                y = u * u * ay + 2.0 * u * t * p1y + t * t * cy
                out.append((int(round(x)), int(round(y))))
            return out

        a2 = ax * ax + ay * ay
        b2 = bx * bx + by * by
        c2 = cx * cx + cy * cy
        ox = (a2 * (by - cy) + b2 * (cy - ay) + c2 * (ay - by)) / d
        oy = (a2 * (cx - bx) + b2 * (ax - cx) + c2 * (bx - ax)) / d
        r = math.hypot(ax - ox, ay - oy)

        def ang(p: Tuple[float, float]) -> float:
            return math.atan2(p[1] - oy, p[0] - ox)

        phi_l = ang((ax, ay))
        phi_t = ang((bx, by))
        phi_r = ang((cx, cy))
        two_pi = 2.0 * math.pi
        ccw_span = (phi_r - phi_l) % two_pi
        t_ccw = (phi_t - phi_l) % two_pi
        if t_ccw <= ccw_span:
            sweep = ccw_span
        else:
            sweep = ccw_span - two_pi

        out = []
        for i in range(n):
            t = i / (n - 1)
            phi = phi_l + t * sweep
            x = ox + r * math.cos(phi)
            y = oy + r * math.sin(phi)
            out.append((int(round(x)), int(round(y))))
        return out

    @staticmethod
    def _earthquake_horizontal_y(
        frame_h: int, from_bottom_num: int, from_bottom_den: int
    ) -> int:
        """Row ``y`` for a line ``from_bottom_num/from_bottom_den`` of the way from bottom to top."""
        if frame_h <= 0 or from_bottom_den <= 0:
            return 0
        f = from_bottom_num / from_bottom_den
        return int(round(frame_h * (1.0 - f)))

    @staticmethod
    def _earthquake_fill_polygon(
        arc_pts: List[Tuple[int, int]], y_line: int
    ) -> List[Tuple[int, int]]:
        """Closed polygon: arc polyline (left->right) then segment along ``y=y_line`` back to start."""
        if len(arc_pts) < 2:
            return list(arc_pts)
        x0, y0 = arc_pts[0]
        x1, y1 = arc_pts[-1]
        return list(arc_pts) + [(x1, y_line), (x0, y_line)]

    @staticmethod
    def _polygon_double_area(poly: List[Tuple[int, int]]) -> float:
        a = 0.0
        n = len(poly)
        if n < 3:
            return 0.0
        for i in range(n):
            x1, y1 = poly[i]
            x2, y2 = poly[(i + 1) % n]
            a += x1 * y2 - x2 * y1
        return a

    @staticmethod
    def _point_in_polygon(px: int, py: int, poly: List[Tuple[int, int]]) -> bool:
        """Even-odd ray test; ``poly`` closed implicitly (last vertex -> first not repeated)."""
        n = len(poly)
        if n < 3:
            return False
        inside = False
        j = n - 1
        for i in range(n):
            ix, iy = poly[i]
            jx, jy = poly[j]
            if ((iy > py) != (jy > py)):
                x_at = (jx - ix) * (py - iy) / (jy - iy) + ix
                if px < x_at:
                    inside = not inside
            j = i
        return inside

    @staticmethod
    def _random_points_in_polygon(
        poly: List[Tuple[int, int]], frame_w: int, frame_h: int, n_points: int
    ) -> List[Tuple[int, int]]:
        if not poly:
            return []
        xs = [p[0] for p in poly]
        ys = [p[1] for p in poly]
        min_x = max(0, min(xs))
        max_x = min(frame_w - 1, max(xs))
        min_y = max(0, min(ys))
        max_y = min(frame_h - 1, max(ys))
        out = []
        if max_x < min_x or max_y < min_y:
            return out
        for _ in range(n_points):
            for _try in range(1000):
                rx = random.randint(min_x, max_x)
                ry = random.randint(min_y, max_y)
                if AttackStrategy._point_in_polygon(rx, ry, poly):
                    out.append((rx, ry))
                    break
            else:
                ax, ay = poly[max(1, len(poly) // 4)]
                out.append((max(0, min(frame_w - 1, ax)), max(0, min(frame_h - 1, ay))))
        return out

    def _earthquake_curve_points_with_jitter(
        self, ltr: Tuple[Tuple[int, int], Tuple[int, int], Tuple[int, int]]
    ) -> List[Tuple[int, int]]:
        points = self._sample_arc_through_three(ltr, 11)
        if random.choice((True, False)):
            points.reverse()
        jitter_px = 100
        return [
            (
                cx + random.randint(-jitter_px, jitter_px),
                cy + random.randint(-jitter_px, jitter_px),
            )
            for cx, cy in points
        ]

    def _random_diamond_perimeter_point(self, frame: Any) -> Tuple[int, int]:
        c1, c2 = random.choice(_DIAMOND_EDGES)
        x1, y1 = self._point(c1)
        x2, y2 = self._point(c2)
        edge_len = math.hypot(x2 - x1, y2 - y1)
        margin = self.config.scale_scalar(_EDRAG_CORNER_MARGIN)
        if edge_len > 0 and 2 * margin < edge_len:
            t_min = margin / edge_len
            t_max = 1.0 - t_min
        else:
            t_min, t_max = 0.0, 1.0
        t = random.uniform(t_min, t_max)
        xf = x1 + (x2 - x1) * t
        yf = y1 + (y2 - y1) * t
        if frame is not None and getattr(frame, "size", 0):
            fh, fw = frame.shape[:2]
            return self._quantize_deploy_to_frame(xf, yf, fw, fh)
        return (int(round(xf)), int(round(yf)))

    def _point_on_polyline_at_distance(
        self, vertices: Sequence[Tuple[float, float]], distance: float
    ) -> Tuple[float, float]:
        """Point ``distance`` pixels along a polyline from the first vertex."""
        if not vertices:
            return (0.0, 0.0)
        if distance <= 0.0:
            return (float(vertices[0][0]), float(vertices[0][1]))
        remaining = float(distance)
        x0, y0 = float(vertices[0][0]), float(vertices[0][1])
        for i in range(len(vertices) - 1):
            x1, y1 = float(vertices[i + 1][0]), float(vertices[i + 1][1])
            seg_len = math.hypot(x1 - x0, y1 - y0)
            if seg_len <= 0.0:
                continue
            if remaining <= seg_len:
                t = remaining / seg_len
                return (x0 + (x1 - x0) * t, y0 + (y1 - y0) * t)
            remaining -= seg_len
            x0, y0 = x1, y1
        return (x0, y0)

    def _even_diamond_top_perimeter_points(
        self,
        frame: Any,
        count: int,
        deviation_frac: float = 0.0,
        reserve_top_corner_slot: bool = False,
        reverse: bool = False,
    ) -> List[Tuple[int, int]]:
        """Evenly spaced deploy clicks along left->top->right diamond edges (Edrag front)."""
        if count <= 0:
            return []
        corners = ("right", "top", "left") if reverse else ("left", "top", "right")
        vertices = [tuple(self._point(corner)) for corner in corners]
        seg_lens = [
            math.hypot(vertices[i + 1][0] - vertices[i][0], vertices[i + 1][1] - vertices[i][1])
            for i in range(len(vertices) - 1)
        ]
        total_len = sum(seg_lens)
        margin = self.config.scale_scalar(_EDRAG_CORNER_MARGIN)
        start_d = min(margin, total_len / 2.0)
        end_d = max(start_d, total_len - margin)
        span = end_d - start_d
        fh, fw = frame.shape[:2]
        if span <= 0:
            mid = self._point_on_polyline_at_distance(vertices, total_len / 2.0)
            return [self._quantize_deploy_to_frame(mid[0], mid[1], fw, fh)]

        slot_count = count + 1 if reserve_top_corner_slot else count
        spacing = span / slot_count
        slot_distances = []
        for i in range(slot_count):
            d = start_d + (i + 0.5) * spacing
            d += random.uniform(-deviation_frac, deviation_frac) * spacing
            d = max(start_d, min(end_d, d))
            slot_distances.append(d)

        skip_idx = None
        if reserve_top_corner_slot and slot_count > 1:
            top_d = seg_lens[0]
            skip_idx = min(range(slot_count), key=lambda i: abs(slot_distances[i] - top_d))

        out = []
        for i, d in enumerate(slot_distances):
            if i == skip_idx:
                continue
            xf, yf = self._point_on_polyline_at_distance(vertices, d)
            out.append(self._quantize_deploy_to_frame(xf, yf, fw, fh))
        return out

    def _random_diamond_top_perimeter_points(
        self, frame: Any, count: int
    ) -> List[Tuple[int, int]]:
        """Random deploy clicks along left->top->right diamond edges (front arc)."""
        if count <= 0:
            return []
        corners = ("left", "top", "right")
        vertices = [tuple(self._point(corner)) for corner in corners]
        seg_lens = [
            math.hypot(vertices[i + 1][0] - vertices[i][0], vertices[i + 1][1] - vertices[i][1])
            for i in range(len(vertices) - 1)
        ]
        total_len = sum(seg_lens)
        margin = self.config.scale_scalar(_EDRAG_CORNER_MARGIN)
        start_d = min(margin, total_len / 2.0)
        end_d = max(start_d, total_len - margin)
        span = end_d - start_d
        fh, fw = frame.shape[:2]
        if span <= 0:
            mid = self._point_on_polyline_at_distance(vertices, total_len / 2.0)
            return [self._quantize_deploy_to_frame(mid[0], mid[1], fw, fh)]
        out = []
        for _ in range(count):
            d = random.uniform(start_d, end_d)
            xf, yf = self._point_on_polyline_at_distance(vertices, d)
            out.append(self._quantize_deploy_to_frame(xf, yf, fw, fh))
        return out

    def _deploy_diamond_perimeter_troop(
        self,
        frame: Any,
        template_name: str,
        stop_event: Optional[Any] = None,
        *,
        count: int = _EDRAG_COUNT,
        delay: float = _EDRAG_DELAY,
    ) -> bool:
        """Select troop in the bottom bar and click ``count`` points on the diamond perimeter."""
        ev = stop_event if stop_event else self.stop_event
        roi = self.vision.bottom_half_region(frame)
        tx, ty = self.vision.find_template(frame, template_name, region=roi)
        if tx is None:
            return False
        self.input.click(tx, ty, pause=0.3, rand=False)
        if ev and ev.wait(0.2):
            return True
        for _ in range(count):
            if ev and ev.is_set():
                return True
            px, py = self._random_diamond_perimeter_point(frame)
            self.input.click(px, py, delay, rand=False)
        return True

    def deploy_golden_drags_if_present(self, frame: Any, stop_event: Optional[Any] = None) -> bool:
        """Optional Super Dragon deploy after main troops, before heroes."""
        ev = stop_event if stop_event else self.stop_event
        if self._deploy_diamond_perimeter_troop(frame, "goldendrag.png", ev):
            logger.info("Deployed golden dragons")
        return bool(ev and ev.is_set())

    def deploy_spells(self, frame: Any) -> None:
        roi = self.vision.bottom_half_region(frame)
        bx, by = self.vision.find_template(frame, "earthquake.png", region=roi)
        if not bx:
            return

        self.input.click(bx, by, pause=0.2)
        offset = int(self.config.get_scaled("earthquake", 400))
        ltr = self._earthquake_anchor_triplet(self._scaled_deployment_data(), offset)
        fh, fw = frame.shape[:2]
        num, den = _EARTHQUAKE_RANDOM_LINE_FROM_BOTTOM
        y_line = self._earthquake_horizontal_y(fh, num, den)

        if self.earthquake_method == EARTHQUAKE_METHOD_RANDOM:
            arc_dense = self._sample_arc_through_three(ltr, _EARTHQUAKE_REGION_ARC_SAMPLES)
            if random.choice((True, False)):
                arc_dense = arc_dense[::-1]
            poly = self._earthquake_fill_polygon(arc_dense, y_line)
            if abs(self._polygon_double_area(poly)) < 2.0:
                logger.warning("Earthquake random region degenerate; using curve placement with jitter.")
                points = self._earthquake_curve_points_with_jitter(ltr)
            else:
                points = self._random_points_in_polygon(poly, fw, fh, 11)
        else:
            points = self._earthquake_curve_points_with_jitter(ltr)

        for cx, cy in points:
            jx = max(0, min(fw - 1, cx))
            jy = max(0, min(fh - 1, cy))
            self.input.click_at(jx, jy, rand=False)
            delay = random.uniform(0.1, 0.3)
            if self.stop_event:
                self.stop_event.wait(delay)
            else:
                time.sleep(delay)


class TroopSpamStrategy(AttackStrategy):
    def __init__(
        self,
        input_service: InputService,
        vision_service: VisionService,
        config: Config,
        stop_event: Optional[Any] = None,
        troop_name: str = "sneaky",
        duration: int = 5,
        status_callback: Optional[Any] = None,
        earthquake_method: str = EARTHQUAKE_METHOD_CURVE,
    ) -> None:
        super().__init__(
            input_service,
            vision_service,
            config,
            stop_event,
            earthquake_method=earthquake_method,
        )
        self.troop_name = troop_name
        self.duration = duration
        self.status_callback = status_callback

    def execute(self, frame: Any, stop_event: Optional[Any] = None) -> bool:
        ev = stop_event if stop_event else self.stop_event
        self._sync_frame_size(frame)
        logger.info(f"Executing {self.troop_name} strategy")
        roi = self.vision.bottom_half_region(frame)
        tx, ty = self.vision.find_template(frame, f"{self.troop_name}.png", threshold=0.68, region=roi)

        # Smart fallback if selected troop template isn't matched
        if tx is None:
            fallback_troops = ["sneaky", "valkyrie", "superminion", "edrag", "babydragon", "goldendrag"]
            for fb_name in fallback_troops:
                if fb_name == self.troop_name:
                    continue
                tx, ty = self.vision.find_template(frame, f"{fb_name}.png", threshold=0.68, region=roi)
                if tx is not None:
                    logger.info(f"Primary troop template '{self.troop_name}' not found; auto-selected fallback troop '{fb_name}'")
                    break

        # If still not found, use slot 1 in the bottom troop bar
        if tx is None:
            fh, fw = frame.shape[:2]
            tx, ty = int(fw * 0.16), int(fh * 0.90)
            logger.info(f"Using default slot 1 troop coordinates: ({tx}, {ty})")

        # Select troop
        self.input.click(tx, ty, pause=0.25, rand=False)
        if ev and ev.wait(0.15):
            return True

        # Masterclass 4-segment multi-wave perimeter deployment
        p_left = self._point("left")
        p_top = self._point("top")
        p_right = self._point("right")
        p_bottom = self._point("bottom")

        segments = [
            (p_left, p_top),
            (p_top, p_right),
            (p_right, p_bottom),
            (p_bottom, p_left),
        ]

        # Wave 1: Rapid boundary coverage across all 4 quadrants
        for p1, p2 in segments:
            if ev and ev.is_set():
                return True
            self.deploy_multi_wave(tx, ty, p1, p2, count_per_wave=4, num_waves=1, delay=0.08)

        # Deploy second wave or secondary troops
        if ev and ev.wait(0.3):
            return True

        # Wave 2: Surgical concentrated penetration on top & sides
        for p1, p2 in segments[:2]:
            if ev and ev.is_set():
                return True
            self.deploy_multi_wave(tx, ty, p1, p2, count_per_wave=3, num_waves=1, delay=0.08)

        # Deploy Heroes
        frame = self.input.window_service.screenshot()
        deployed_heroes = []
        if frame is not None:
            self._sync_frame_size(frame)
            if self.deploy_golden_drags_if_present(frame, ev):
                return True
            deployed_heroes = self.deploy_heroes(frame)

        # Deploy Spells (Earthquake / Rage / Freeze)
        frame = self.input.window_service.screenshot()
        if frame is not None:
            self._sync_frame_size(frame)
            self.deploy_spells(frame)

        # Tactical delay before triggering hero abilities
        if deployed_heroes:
            if ev:
                ev.wait(8.0)
            else:
                time.sleep(8.0)
            self.activate_hero_abilities(deployed_heroes)

        return True


class EdragStrategy(AttackStrategy):
    def __init__(
        self,
        input_service: InputService,
        vision_service: VisionService,
        config: Config,
        stop_event: Optional[Any] = None,
        status_callback: Optional[Any] = None,
        earthquake_method: str = EARTHQUAKE_METHOD_CURVE,
    ) -> None:
        super().__init__(
            input_service,
            vision_service,
            config,
            stop_event,
            earthquake_method=earthquake_method,
        )
        self.status_callback = status_callback

    def execute(self, frame: Any, stop_event: Optional[Any] = None) -> bool:
        ev = stop_event if stop_event else self.stop_event
        self._sync_frame_size(frame)
        logger.info("Executing edrag strategy")
        roi = self.vision.bottom_half_region(frame)

        tx, ty = self.vision.find_template(frame, "edrag.png", threshold=0.68, region=roi)
        if tx is None:
            for fb in ("goldendrag.png", "babydragon.png"):
                tx, ty = self.vision.find_template(frame, fb, threshold=0.68, region=roi)
                if tx:
                    break
        if tx is None:
            fh, fw = frame.shape[:2]
            tx, ty = int(fw * 0.16), int(fh * 0.90)
            logger.info(f"Edrag template not found; falling back to slot 1: ({tx}, {ty})")

        self.input.click(tx, ty, pause=0.25, rand=False)
        if ev and ev.wait(0.15):
            return True

        # Deploy E-Drags in an evenly spaced wide arc along the front perimeter
        deploy_points = self._even_diamond_top_perimeter_points(frame, count=8, deviation_frac=0.05)
        if not deploy_points:
            deploy_points = self._random_diamond_top_perimeter_points(frame, count=8)

        for px, py in deploy_points:
            if ev and ev.is_set():
                return True
            self.input.click(px, py, pause=0.18, rand=False)

        # Deploy Golden / Super Dragons if present
        frame = self.input.window_service.screenshot()
        if frame is not None:
            self._sync_frame_size(frame)
            if self.deploy_golden_drags_if_present(frame, ev):
                return True

        # Deploy Heroes
        frame = self.input.window_service.screenshot()
        deployed_heroes = []
        if frame is not None:
            self._sync_frame_size(frame)
            deployed_heroes = self.deploy_heroes(frame)

        # Deploy Spells
        frame = self.input.window_service.screenshot()
        if frame is not None:
            self._sync_frame_size(frame)
            self.deploy_spells(frame)

        # Tactical delay before activating hero abilities
        if deployed_heroes:
            if ev:
                ev.wait(10.0)
            else:
                time.sleep(10.0)
            self.activate_hero_abilities(deployed_heroes)

        return True
