"""
zones.py — Vùng giám sát (khoanh khu vực quan tâm trên khung hình).

Vùng là một đa giác (polygon) vẽ bằng zone_editor.py, lưu ở data/zones.json
dưới dạng toạ độ CHUẨN HOÁ 0..1 (không phụ thuộc độ phân giải):

    {"zones": [{"name": "cong", "points": [[0.1, 0.5], [0.9, 0.5], [0.9, 1.0], [0.1, 1.0]]}]}

Mỗi Detection được gắn thêm extra['zones'] = [tên các vùng chứa nó].
Điểm neo để xét "nằm trong vùng" là GIỮA CẠNH DƯỚI của khung (vị trí chân
người) — chuẩn cho bài toán ai bước vào khu vực sàn/cổng.

Nếu CHƯA vẽ vùng nào: cả khung hình được coi là một vùng tên "toan-khung"
(để tính năng đếm giờ người lạ vẫn hoạt động ngay, không bắt buộc vẽ vùng).
"""

from __future__ import annotations
import json
import os

import cv2
import numpy as np

WHOLE_FRAME = "toan-khung"


def point_in_polygon(x: float, y: float, points: list[list[float]]) -> bool:
    """Kiểm tra điểm (x, y) có nằm trong đa giác không (thuật toán bắn tia)."""
    n = len(points)
    if n < 3:
        return False
    inside = False
    j = n - 1
    for i in range(n):
        xi, yi = points[i]
        xj, yj = points[j]
        # cạnh (i, j) có cắt tia ngang từ điểm ra vô cực bên phải không?
        if (yi > y) != (yj > y):
            x_cat = (xj - xi) * (y - yi) / (yj - yi) + xi
            if x < x_cat:
                inside = not inside
        j = i
    return inside


class ZoneSet:
    def __init__(self, config: dict | None = None):
        config = config or {}
        self.enabled = config.get("enabled", True)
        self.file = config.get("file", "data/zones.json")
        # chưa vẽ vùng -> coi cả khung là 1 vùng (bật/tắt được)
        self.whole_frame_if_empty = config.get("whole_frame_if_empty", True)
        # điểm neo xét trong/ngoài vùng: "bottom" = giữa cạnh đáy (vị trí chân —
        # hợp camera nhìn toàn thân), "center" = tâm khung (hợp webcam để bàn
        # chỉ thấy nửa người, chân không bao giờ lọt khung hình)
        self.anchor = config.get("anchor", "bottom")
        self.zones: list[dict] = []
        self.load()

    def load(self) -> None:
        """Nạp + KIỂM TRA KỸ file vùng. File hỏng kiểu gì cũng không được làm sập app."""
        self.zones = []
        if os.path.exists(self.file):
            try:
                with open(self.file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                raw = data.get("zones", []) if isinstance(data, dict) else []
                for z in raw:
                    # chỉ nhận vùng đúng dạng: có tên chuỗi + >=3 đỉnh [x, y] số
                    if not isinstance(z, dict):
                        continue
                    name, pts = z.get("name"), z.get("points")
                    if not isinstance(name, str) or not name:
                        continue
                    if not isinstance(pts, list) or len(pts) < 3:
                        continue
                    if not all(isinstance(p, (list, tuple)) and len(p) == 2
                               and all(isinstance(c, (int, float)) for c in p)
                               for p in pts):
                        continue
                    self.zones.append({"name": name,
                                       "points": [[float(x), float(y)] for x, y in pts]})
                print(f"[zones] Đã nạp {len(self.zones)} vùng từ {self.file}: "
                      f"{[z['name'] for z in self.zones]}")
            except Exception as e:
                self.zones = []   # file hỏng -> chắc chắn không giữ vùng rác
                print(f"[zones] File vùng lỗi ({e}) — bỏ qua, coi như chưa có vùng.")
        if not self.zones:
            print(f"[zones] Chưa có vùng nào"
                  + (f" — cả khung hình là vùng '{WHOLE_FRAME}'." if self.whole_frame_if_empty else "."))

    def annotate(self, detections, frame_shape) -> None:
        """Gắn extra['zones'] cho từng detection (danh sách tên vùng chứa nó)."""
        if not self.enabled:
            return
        h, w = frame_shape[:2]
        for d in detections:
            x1, y1, x2, y2 = d.box
            # điểm neo theo config (bottom = chân, center = tâm người).
            # Kẹp vào TRONG khung: người đứng sát mép (box chạm đáy, y2 == h)
            # mà không kẹp thì ay = 1.0 rơi đúng biên đa giác -> bị tính là NGOÀI vùng.
            anchor_y = (y1 + y2) / 2 if self.anchor == "center" else y2
            ax = min(max((x1 + x2) / 2, 0), w - 1) / w
            ay = min(max(anchor_y, 0), h - 1) / h
            if self.zones:
                d.extra["zones"] = [z["name"] for z in self.zones
                                    if point_in_polygon(ax, ay, z["points"])]
            elif self.whole_frame_if_empty:
                d.extra["zones"] = [WHOLE_FRAME]
            else:
                d.extra["zones"] = []

    def draw(self, frame):
        """Vẽ ranh giới các vùng lên khung hình."""
        if not self.enabled or not self.zones:
            return frame
        h, w = frame.shape[:2]
        for z in self.zones:
            pts = np.array([[int(x * w), int(y * h)] for x, y in z["points"]],
                           dtype=np.int32)
            cv2.polylines(frame, [pts], isClosed=True, color=(255, 200, 0), thickness=2)
            # tên vùng đặt ở đỉnh đầu tiên
            cv2.putText(frame, z["name"], (pts[0][0] + 4, pts[0][1] - 6),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.55, (255, 200, 0), 2)
        return frame
