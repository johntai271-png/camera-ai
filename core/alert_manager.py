"""
alert_manager.py — Bộ não quyết định KHI NÀO đáng làm phiền bạn.

Nguyên tắc chống "mệt vì cảnh báo": báo = việc cần hành động, không phải nhật ký.

3 TẦNG xử lý:
    urgent  (khẩn)     -> nhắn điện thoại ưu tiên 5 + yêu cầu GHI HÌNH,
                          lặp lại mỗi 'urgent_repeat' giây chừng nào còn tiếp diễn
    notable (đáng chú ý)-> nhắn 1 LẦN cho mỗi "lượt xuất hiện" (session)
    log     (nhật ký)  -> chỉ lưu ảnh + in console, KHÔNG nhắn

"Lượt xuất hiện" (session): cùng một sự việc diễn ra liên tục chỉ tính 1 lượt.
Vắng quá 'session_gap' giây rồi xuất hiện lại -> lượt mới. (Bạn ngồi làm việc
2 tiếng = 1 lượt "Tai xuất hiện", không phải 480 tin nhắn.)

3 CHẾ ĐỘ (đổi bằng phím trên cửa sổ video):
    home  (ở nhà)   : chỉ cháy + người lạ ở lì là khẩn; người/quen = nhật ký
    away  (vắng nhà): BẤT KỲ người nào = khẩn ngay lập tức + ghi hình
    sleep (ngủ)     : như away; tự bật theo giờ 'sleep_hours' khi đang ở home
"""

from __future__ import annotations
import os
import time

import cv2


# tầng của từng nhóm sự kiện, theo chế độ
TIERS_HOME = {
    "fire": "urgent",
    "stranger_dwell": "urgent",
    "face_stranger": "notable",
    "person": "log",
    "face_known": "log",
    "object": "log",
}
TIERS_AWAY = {**TIERS_HOME, "person": "urgent", "face_stranger": "urgent"}

# (tiêu đề, tags ntfy) cho từng nhóm
GROUP_INFO = {
    "fire":           ("CHAY / KHOI!",              ["fire", "rotating_light"]),
    "stranger_dwell": ("NGUOI LA O LI TRONG VUNG!", ["rotating_light", "video_camera"]),
    "face_stranger":  ("Nguoi la!",                 ["rotating_light"]),
    "person":         ("Phat hien nguoi",           ["walking"]),
    "object":         ("Phat hien vat/thu",         ["dog"]),
    "face_known":     ("Nguoi quen",                ["bust_in_silhouette"]),
}

MODE_LABEL = {"home": "O NHA", "away": "VANG NHA", "sleep": "NGU"}


class AlertManager:
    def __init__(self, config: dict | None = None, notifier=None):
        config = config or {}
        self.notifier = notifier
        self.save_dir = config.get("save_dir", "data/alerts")
        self.fire_review_dir = config.get("fire_review_dir", "data/fire_review")
        self.session_gap = float(config.get("session_gap", 300))    # 5 phút
        self.urgent_repeat = float(config.get("urgent_repeat", 60)) # khẩn: nhắc lại mỗi 60s
        self.mode = config.get("mode", "home")
        self.sleep_hours = config.get("sleep_hours")   # vd [23, 6]; null = tắt tự động
        # session theo khoá sự kiện: key -> {"last_seen", "last_notified", "notified"}
        self._sessions: dict[str, dict] = {}
        os.makedirs(self.save_dir, exist_ok=True)

    # ---------- chế độ ----------

    def set_mode(self, mode: str) -> None:
        if mode in MODE_LABEL:
            self.mode = mode
            print(f"[alert] Chế độ: {MODE_LABEL[mode]}")
            if self.notifier:
                self.notifier.send("Camera AI", f"Da chuyen che do: {MODE_LABEL[mode]}",
                                   priority=2, tags=["gear"])

    def effective_mode(self, now: float) -> str:
        """home + đang trong khung giờ ngủ -> tự coi là sleep."""
        if self.mode == "home" and self.sleep_hours:
            h = time.localtime(now).tm_hour
            start, end = self.sleep_hours
            in_window = (start <= h or h < end) if start > end else (start <= h < end)
            if in_window:
                return "sleep"
        return self.mode

    # ---------- khởi động ----------

    def startup(self) -> None:
        msg = f"He thong da bat. Che do: {MODE_LABEL[self.mode]}."
        print(f"[alert] {msg}")
        if self.notifier:
            self.notifier.send("Camera AI da bat", msg, priority=3,
                               tags=["white_check_mark"])

    # ---------- sự kiện dwell (từ DwellTracker) ----------

    def dwell_alert(self, frame, zone: str, duration: float, now: float,
                    recording: bool = True, camera: str = "") -> None:
        title, tags = GROUP_INFO["stranger_dwell"]
        cam_prefix = f"[{camera}] " if camera else ""
        message = f"{cam_prefix}Nguoi la o trong vung '{zone}' qua {int(duration)} giay!"
        if recording:
            message += " Dang ghi hinh lai."
        self._urgent(f"{camera}|dwell_{zone}", "stranger_dwell", title, tags,
                     message, frame, now)

    # ---------- dòng sự kiện chính ----------

    def handle(self, frame, detections, now: float, raw_frame=None,
               camera: str = "") -> list[str]:
        """Xử lý detections 1 khung hình. Trả về danh sách tag cần GHI HÌNH."""
        alerting = [d for d in detections if d.is_alert]
        mode = self.effective_mode(now)
        tiers = TIERS_HOME if mode == "home" else TIERS_AWAY

        # vắng nhà/ngủ: MỌI người phát hiện được đều là sự kiện (kể cả chưa is_alert)
        if mode in ("away", "sleep"):
            persons = [d for d in detections if d.skill == "person"]
            alerting = alerting + [d for d in persons if d not in alerting]

        record_tags: list[str] = []
        by_group: dict[str, list] = {}
        for d in alerting:
            by_group.setdefault(d.extra.get("group", d.skill), []).append(d)

        for group, dets in by_group.items():
            tier = tiers.get(group, "notable")
            key = f"{camera}|{group}"   # lượt tính RIÊNG từng camera
            if group == "face_known":   # mỗi người quen 1 lượt riêng (Tai khác Me)
                key = f"{key}:{sorted({d.label for d in dets})}"

            title, tags = GROUP_INFO.get(group, (f"Canh bao ({group})", ["warning"]))
            message = self._message(group, dets, mode)
            if camera:
                message = f"[{camera}] {message}"

            if tier == "urgent":
                if self._urgent(key, group, title, tags, message, frame, now,
                                raw_frame=raw_frame):
                    record_tags.append(group)
            elif tier == "notable":
                self._once_per_session(key, group, title, tags, message, frame,
                                       now, notify=True)
            else:  # log
                self._once_per_session(key, group, title, tags, message, frame,
                                       now, notify=False)
        return record_tags

    # ---------- nội bộ ----------

    def _message(self, group, dets, mode) -> str:
        if group == "person":
            n = len({d.extra.get("track_id") for d in dets})
            extra = " (dang VANG NHA!)" if mode in ("away", "sleep") else ""
            return f"Phat hien {n} nguoi truoc camera{extra}."
        if group == "face_stranger":
            return "Co nguoi la (khong nhan ra) truoc camera!"
        if group == "face_known":
            names = ", ".join(sorted({d.label for d in dets}))
            return f"{names} vua xuat hien."
        if group == "fire":
            what = ", ".join(sorted({d.label for d in dets}))
            return f"KHAN CAP: phat hien {what}!"
        if group == "object":
            what = ", ".join(sorted({d.label for d in dets}))
            return f"Co {what} di vao camera."
        return ", ".join(sorted({d.label for d in dets}))

    def _session(self, key: str, now: float) -> tuple[dict, bool]:
        """Trả về (session, là_lượt_mới)."""
        st = self._sessions.get(key)
        if st is None or now - st["last_seen"] > self.session_gap:
            st = {"start": now, "last_seen": now, "last_notified": 0.0}
            self._sessions[key] = st
            return st, True
        st["last_seen"] = now
        return st, False

    def _urgent(self, key, group, title, tags, message, frame, now,
                raw_frame=None) -> bool:
        """Tầng khẩn: báo ngay lượt mới + nhắc lại mỗi urgent_repeat. Trả về True nếu vừa báo."""
        st, is_new = self._session(key, now)
        if not is_new and now - st["last_notified"] < self.urgent_repeat:
            return True   # vẫn đang khẩn (giữ ghi hình) nhưng chưa tới lúc nhắc lại
        st["last_notified"] = now
        image_path = self._save_image(group, frame, now)
        if group == "fire" and raw_frame is not None:
            self._save_fire_review(raw_frame, now)   # ảnh GỐC cho vòng sửa báo nhầm
        print(f"  🚨 [{title}] {message}  |  ảnh: {image_path}")
        if self.notifier:
            self.notifier.send(title, message, priority=5, tags=tags,
                               image_path=image_path)
        return True

    def _once_per_session(self, key, group, title, tags, message, frame, now,
                          notify: bool) -> None:
        st, is_new = self._session(key, now)
        if not is_new:
            return
        image_path = self._save_image(group, frame, now)
        icon = "🔔" if notify else "📝"
        print(f"  {icon} [{title}] {message}  |  ảnh: {image_path}")
        if notify and self.notifier:
            self.notifier.send(title, message, priority=4, tags=tags,
                               image_path=image_path)

    def _save_image(self, group, frame, now) -> str | None:
        stamp = time.strftime("%Y%m%d_%H%M%S", time.localtime(now))
        path = os.path.join(self.save_dir, f"{group}_{stamp}.jpg")
        try:
            os.makedirs(self.save_dir, exist_ok=True)
            if not cv2.imwrite(path, frame):   # imwrite fail = trả False, không raise
                return None
        except Exception:
            return None
        return path

    def _save_fire_review(self, raw_frame, now) -> None:
        """Lưu ảnh GỐC (không vẽ khung) mỗi lần báo cháy — nguyên liệu fine-tune."""
        try:
            os.makedirs(self.fire_review_dir, exist_ok=True)
            stamp = time.strftime("%Y%m%d_%H%M%S", time.localtime(now))
            cv2.imwrite(os.path.join(self.fire_review_dir, f"fire_{stamp}.jpg"),
                        raw_frame)
        except Exception:
            pass
