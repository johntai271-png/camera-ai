"""
track_registry.py — Gắn DANH TÍNH (khuôn mặt) vào TỪNG NGƯỜI đang được theo dõi.

Vấn đề nó giải quyết: nhận diện mặt chỉ chạy được khi thấy mặt. Người quay lưng
là "mất danh tính" -> trước đây nhãn nhấp nháy quen/lạ liên tục.

Cách làm: skill person cho mỗi người 1 track_id ổn định. Khi mặt xuất hiện,
tìm xem khuôn mặt nằm trong khung người nào -> gắn tên vào track_id đó.
Từ đó về sau, dù người này quay lưng, track vẫn nhớ họ là ai.

Trạng thái danh tính của 1 track:
    "unknown"  — chưa thấy mặt lần nào (thận trọng: coi như người lạ)
    "stranger" — đã thấy mặt nhưng không khớp người nhà
    "known"    — đã khớp người nhà (kèm tên). MỘT LẦN quen là quen CẢ track.
"""

from __future__ import annotations


def _center(box) -> tuple[float, float]:
    x1, y1, x2, y2 = box
    return (x1 + x2) / 2, (y1 + y2) / 2


def _inside(point, box) -> bool:
    x, y = point
    x1, y1, x2, y2 = box
    return x1 <= x <= x2 and y1 <= y <= y2


class TrackRegistry:
    def __init__(self, forget_after: float = 30.0):
        # track vắng mặt quá forget_after giây thì quên (dọn bộ nhớ)
        self.forget_after = forget_after
        # track_id -> {"identity": "unknown"|"stranger"|"known",
        #              "name": str|None, "last_seen": float}
        self._tracks: dict[int, dict] = {}

    def update(self, detections, now: float) -> None:
        """Gọi mỗi khung với TẤT CẢ detections. Gắn danh tính vào person dets."""
        persons = [d for d in detections
                   if d.skill == "person" and d.extra.get("track_id") is not None]
        faces = [d for d in detections if d.skill == "face"]

        # 1) làm mới last_seen cho các track đang hiện diện
        for p in persons:
            tid = p.extra["track_id"]
            st = self._tracks.setdefault(
                tid, {"identity": "unknown", "name": None, "last_seen": now})
            st["last_seen"] = now

        # 2) khớp mặt -> người: tâm khuôn mặt nằm trong khung người nào thì
        #    gắn danh tính cho track của người đó
        for f in faces:
            f_center = _center(f.box)
            owner = None
            for p in persons:
                if _inside(f_center, p.box):
                    # mặt lọt trong nhiều khung người (đứng chồng) -> chọn khung NHỎ nhất
                    if owner is None or _area(p.box) < _area(owner.box):
                        owner = p
            if owner is None:
                continue
            st = self._tracks[owner.extra["track_id"]]
            if f.extra.get("kind") == "known":
                # một lần nhận ra là NHỚ LUÔN cho cả track (kể cả sau đó quay lưng)
                st["identity"] = "known"
                st["name"] = f.label
            elif st["identity"] == "unknown":
                # thấy mặt mà không khớp ai -> đánh dấu lạ (có thể nâng lên known sau)
                st["identity"] = "stranger"

        # 3) ghi danh tính ngược vào person detections (cho dwell + vẽ nhãn)
        for p in persons:
            st = self._tracks[p.extra["track_id"]]
            p.extra["identity"] = st["identity"]
            p.extra["name"] = st["name"]
            tid = p.extra["track_id"]
            if st["identity"] == "known":
                p.label = f"{st['name']} #{tid}"
                p.color = (0, 255, 0)          # người nhà: xanh lá
            elif st["identity"] == "stranger":
                p.label = f"Nguoi la #{tid}"
                p.color = (0, 0, 255)          # người lạ: đỏ
            else:
                p.label = f"Nguoi #{tid}"      # chưa rõ: giữ cam

        # 4) quên các track đã biến mất lâu
        for tid in list(self._tracks):
            if now - self._tracks[tid]["last_seen"] > self.forget_after:
                del self._tracks[tid]


def _area(box) -> float:
    x1, y1, x2, y2 = box
    return max(0, x2 - x1) * max(0, y2 - y1)
