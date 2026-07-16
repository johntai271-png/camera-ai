"""
dwell.py — Đếm thời gian TỪNG NGƯỜI LẠ ở lì trong vùng, quá ngưỡng thì báo.

Phiên bản 2 (theo track): mỗi người có track_id + danh tính từ track_registry:
    - "known" (người nhà)        -> KHÔNG BAO GIỜ báo, kể cả đứng cả ngày
    - "stranger" / "unknown"     -> đếm giờ; đủ 'seconds' giây trong vùng -> báo
      (unknown = chưa thấy mặt — thận trọng coi như lạ, thà báo nhầm còn hơn sót)

Khác bản 1: đếm theo (vùng, track_id) — 2 người thay nhau ra vào không bị cộng
dồn giờ của nhau; và người quen đứng cạnh người lạ KHÔNG che chắn cho người lạ
(bản 1 hễ thấy người quen là miễn trừ cả khung hình).

update() trả về sự kiện: [{"zone", "track_id", "duration"}] — mỗi (vùng, người)
báo đúng MỘT lần cho tới khi họ rời khỏi vùng quá 'grace' giây.
"""

from __future__ import annotations


class DwellTracker:
    def __init__(self, config: dict | None = None):
        config = config or {}
        self.enabled = config.get("enabled", True)
        self.threshold = float(config.get("seconds", 10))
        self.grace = float(config.get("grace", 2.0))
        # (zone, track_id) -> {start, last_seen, triggered}
        self._state: dict[tuple, dict] = {}

    def update(self, detections, now: float) -> list[dict]:
        if not self.enabled:
            return []

        events: list[dict] = []
        seen_keys: set[tuple] = set()

        for d in detections:
            if d.skill != "person":
                continue
            tid = d.extra.get("track_id")
            if tid is None:
                continue
            if d.extra.get("identity") == "known":
                # người nhà: xoá mọi bộ đếm của track này (nếu có) rồi bỏ qua
                for key in list(self._state):
                    if key[1] == tid:
                        del self._state[key]
                continue
            for zone in d.extra.get("zones", []):
                key = (zone, tid)
                seen_keys.add(key)
                st = self._state.get(key)
                if st is None or now - st["last_seen"] > self.grace:
                    st = {"start": now, "last_seen": now, "triggered": False}
                    self._state[key] = st
                st["last_seen"] = now
                duration = now - st["start"]
                if not st["triggered"] and duration >= self.threshold:
                    st["triggered"] = True
                    events.append({"zone": zone, "track_id": tid,
                                   "duration": duration})

        # dọn trạng thái các (vùng, người) đã vắng quá grace
        for key in list(self._state):
            if key not in seen_keys and \
                    now - self._state[key]["last_seen"] > self.grace:
                del self._state[key]

        return events

    def alerting_zones(self, now: float) -> list[str]:
        """Các vùng ĐANG có người lạ đã-báo-động còn ở đó (giữ máy quay chạy)."""
        return sorted({key[0] for key, st in self._state.items()
                       if st["triggered"] and now - st["last_seen"] <= self.grace})
