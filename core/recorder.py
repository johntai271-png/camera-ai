"""
recorder.py — Ghi video khi có sự kiện, KÈM cả vài giây TRƯỚC sự kiện (pre-roll).

Cách hoạt động:
    - feed(frame, now) được gọi mỗi vòng lặp: luôn giữ một "băng đệm" các khung
      hình gần nhất (nén JPEG cho nhẹ RAM), dài 'pre_roll' giây.
    - Khi có sự kiện -> start(): mở file .mp4, ghi TOÀN BỘ băng đệm (nhìn thấy
      cả lúc kẻ lạ bước vào), rồi tiếp tục ghi các khung mới.
    - keep_alive() được gọi chừng nào người lạ còn đó -> gia hạn ghi thêm.
    - Tự dừng khi: hết 'post_roll' giây sau lần keep_alive cuối, hoặc chạm
      'max_seconds' (chống đầy ổ cứng).

Video lưu ở data/recordings/<vùng>_<thời điểm>.mp4 (khung hình ĐÃ vẽ nhãn).
"""

from __future__ import annotations
import os
import subprocess
import threading
import time
from collections import deque

import cv2


def _transcode_h264(path: str) -> None:
    """Chuyển video sang H.264 (chạy nền sau khi ghi xong). Lỗi thì giữ file gốc."""
    try:
        import imageio_ffmpeg
        ffmpeg = imageio_ffmpeg.get_ffmpeg_exe()
        tmp = path + ".h264.tmp.mp4"
        r = subprocess.run(
            [ffmpeg, "-y", "-i", path, "-c:v", "libx264", "-preset", "veryfast",
             "-crf", "23", "-movflags", "+faststart", "-an", tmp],
            capture_output=True, timeout=300,
        )
        if r.returncode == 0 and os.path.getsize(tmp) > 1000:
            os.replace(tmp, path)
            print(f"[recorder] Đã nén H.264 (xem được trên trình duyệt): {path}")
        else:
            if os.path.exists(tmp):
                os.remove(tmp)
    except Exception:
        pass   # không có ffmpeg / lỗi -> giữ nguyên file mp4v, vẫn tải về xem được


class EventRecorder:
    def __init__(self, config: dict | None = None):
        config = config or {}
        self.enabled = config.get("enabled", True)
        self.dir = config.get("dir", "data/recordings")
        self.pre_roll = float(config.get("pre_roll", 5))
        self.post_roll = float(config.get("post_roll", 5))
        self.max_seconds = float(config.get("max_seconds", 60))
        self.fps = float(config.get("fps", 15))
        self.jpeg_quality = int(config.get("jpeg_quality", 80))

        self._buffer: deque[tuple[float, bytes]] = deque()  # (thời điểm, ảnh JPEG)
        self._last_stored = 0.0
        self._writer: cv2.VideoWriter | None = None
        self._pending_tag: str | None = None   # start() gọi khi buffer trống -> mở file ở feed() sau
        self._started_at = 0.0
        self._stop_after = 0.0
        self.active = False
        self.last_path: str | None = None

    # ---------- gọi mỗi vòng lặp ----------

    def feed(self, frame, now: float) -> None:
        if not self.enabled:
            return
        # lấy mẫu theo fps cấu hình (không lưu 60 khung/s cho phí RAM)
        if now - self._last_stored < 1.0 / self.fps:
            return
        self._last_stored = now

        ok, jpg = cv2.imencode(".jpg", frame,
                               [cv2.IMWRITE_JPEG_QUALITY, self.jpeg_quality])
        if not ok:
            return
        self._buffer.append((now, jpg.tobytes()))
        # cắt băng đệm về đúng pre_roll giây
        while self._buffer and now - self._buffer[0][0] > self.pre_roll:
            self._buffer.popleft()

        # có lệnh start đang chờ (lúc gọi buffer còn trống) -> mở file bây giờ
        if self._pending_tag is not None and self._writer is None:
            self._open_writer(self._pending_tag, frame.shape)
            self._pending_tag = None

        if self.active and self._writer is not None:
            self._writer.write(frame)
            if now >= self._stop_after or now - self._started_at >= self.max_seconds:
                self.stop()

    # ---------- điều khiển ----------

    def start(self, now: float, tag: str = "su-kien") -> str | None:
        """Bắt đầu ghi (kèm pre-roll). Đang ghi rồi thì chỉ gia hạn."""
        if not self.enabled:
            return None
        if self.active:
            self._stop_after = max(self._stop_after, now + self.post_roll)
            return self.last_path

        self._started_at = now
        self._stop_after = now + self.post_roll
        self.active = True
        if self._buffer:
            # mở file ngay và đổ băng đệm vào
            shape = self._decode(self._buffer[0][1]).shape
            self._open_writer(tag, shape)
        else:
            # chưa có khung nào trong đệm (vừa khởi động) -> mở ở feed() kế tiếp
            self._pending_tag = tag
        return self.last_path

    def keep_alive(self, now: float) -> None:
        """Gọi chừng nào đối tượng còn trong vùng -> ghi tiếp."""
        if self.active:
            self._stop_after = max(self._stop_after, now + self.post_roll)

    def stop(self) -> None:
        if self._writer is not None:
            self._writer.release()
            print(f"[recorder] Đã lưu video: {self.last_path}")
            # chuyển sang H.264 nền (mp4v trình duyệt không phát được;
            # H.264 xem thẳng trên dashboard/điện thoại + file nhỏ hơn ~nửa)
            if self.last_path:
                threading.Thread(target=_transcode_h264,
                                 args=(self.last_path,), daemon=True).start()
        self._writer = None
        self.active = False
        self._pending_tag = None

    # ---------- nội bộ ----------

    def _open_writer(self, tag: str, shape) -> None:
        os.makedirs(self.dir, exist_ok=True)
        h, w = shape[:2]
        stamp = time.strftime("%Y%m%d_%H%M%S")
        safe_tag = "".join(c if c.isalnum() or c in "-_" else "-" for c in tag)
        self.last_path = os.path.join(self.dir, f"{safe_tag}_{stamp}.mp4")
        fourcc = cv2.VideoWriter_fourcc(*"mp4v")
        self._writer = cv2.VideoWriter(self.last_path, fourcc, self.fps, (w, h))
        # đổ pre-roll: những gì xảy ra TRƯỚC sự kiện
        for _, jpg in self._buffer:
            img = self._decode(jpg)
            if img is not None and img.shape[:2] == (h, w):
                self._writer.write(img)
        print(f"[recorder] BẮT ĐẦU ghi hình -> {self.last_path} "
              f"(kèm {self.pre_roll:.0f}s trước sự kiện)")

    @staticmethod
    def _decode(jpg_bytes: bytes):
        import numpy as np
        return cv2.imdecode(np.frombuffer(jpg_bytes, dtype=np.uint8), cv2.IMREAD_COLOR)
