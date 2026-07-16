"""
frame_grabber.py — Đọc camera trong THREAD RIÊNG, luôn giữ khung hình MỚI NHẤT.

Vì sao cần: read() của camera là lệnh CHỜ (blocking). Chạy nhiều camera mà đọc
tuần tự thì cam này chờ cam kia -> tất cả cùng giật + hình RTSP bị dồn độ trễ
(xem hình của 5 giây trước). Mỗi camera một thread đọc liên tục, vòng lặp chính
chỉ việc lấy khung mới nhất — không chờ ai.

Dùng:
    g = FrameGrabber(VideoSource("rtsp://..."))
    g.start()
    ok, frame = g.latest()   # không chờ; frame=None nếu chưa có khung nào
    g.stop()
"""

from __future__ import annotations
import threading
import time


class FrameGrabber:
    def __init__(self, source):
        self.source = source            # core.video_source.VideoSource
        self._lock = threading.Lock()
        self._frame = None
        self._ok = False
        self._stop = False
        self._thread: threading.Thread | None = None

    def start(self) -> "FrameGrabber":
        self.source.open()
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()
        return self

    def _run(self) -> None:
        # file video: phát đúng tốc độ thật (không đọc hết veo trong 1 giây);
        # webcam/RTSP: read() tự chờ theo nhịp khung hình, khỏi cần ngủ thêm
        file_delay = 0.0
        if getattr(self.source, "is_file", False):
            fps = self.source.fps or 25.0
            file_delay = 1.0 / fps

        while not self._stop:
            ok, frame = self.source.read()   # VideoSource tự lo kết nối lại RTSP
            with self._lock:
                self._ok = ok
                if ok:
                    self._frame = frame
            if not ok:
                if getattr(self.source, "is_file", False):
                    with self._lock:
                        self._frame = None   # file hết -> báo cho main biết để dừng
                    break
                time.sleep(0.5)   # stream đang lỗi — nghỉ chút, đừng quay cuồng CPU
            elif file_delay:
                time.sleep(file_delay)

    def latest(self):
        """Khung hình mới nhất (không chờ). Trả về (ok, frame|None)."""
        with self._lock:
            if self._frame is None:
                return False, None
            return self._ok, self._frame

    def stop(self) -> None:
        self._stop = True
        if self._thread is not None:
            self._thread.join(timeout=2)
        self.source.release()
