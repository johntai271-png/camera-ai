"""
video_source.py — Lớp bọc nguồn video, giấu đi khác biệt giữa các nguồn.

Nhờ file này, phần còn lại của app KHÔNG cần biết video đến từ đâu:
    - Webcam laptop:   VideoSource(0)
    - File mp4:        VideoSource("test_fire.mp4")
    - Camera IP/RTSP:  VideoSource("rtsp://user:pass@192.168.1.100:554/stream1")

Khi có camera RTSP thật, bạn CHỈ đổi 1 dòng trong config.yaml, code không đổi.
Có sẵn cơ chế tự kết nối lại khi camera IP rớt mạng.
"""

from __future__ import annotations
import time
import cv2


class VideoSource:
    def __init__(self, source, reconnect: bool = True, width: int | None = None,
                 height: int | None = None):
        # "0" (chuỗi) hay 0 (số) đều hiểu là webcam index 0
        if isinstance(source, str) and source.isdigit():
            source = int(source)
        self.source = source
        self.reconnect = reconnect
        self.width = width
        self.height = height
        self.cap: cv2.VideoCapture | None = None

    @property
    def is_stream(self) -> bool:
        """True nếu là RTSP/HTTP (nguồn mạng, có thể rớt)."""
        return isinstance(self.source, str) and self.source.lower().startswith(
            ("rtsp://", "http://", "https://"))

    @property
    def is_file(self) -> bool:
        """True nếu là file video trên đĩa (khác webcam và stream mạng)."""
        return isinstance(self.source, str) and not self.is_stream

    @property
    def fps(self) -> float:
        """FPS gốc của nguồn (dùng để phát file đúng tốc độ thật). 0 nếu chưa mở."""
        if self.cap is None:
            return 0.0
        try:
            return float(self.cap.get(cv2.CAP_PROP_FPS)) or 0.0
        except Exception:
            return 0.0

    def open(self) -> None:
        # Với RTSP nên ưu tiên TCP cho ổn định (đỡ vỡ hình)
        if self.is_stream:
            self.cap = cv2.VideoCapture(self.source, cv2.CAP_FFMPEG)
        else:
            self.cap = cv2.VideoCapture(self.source)

        if self.width:
            self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, self.width)
        if self.height:
            self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, self.height)
        # Giảm buffer để bớt trễ với camera IP
        try:
            self.cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
        except Exception:
            pass

        if not self.cap.isOpened():
            raise RuntimeError(
                f"Không mở được nguồn video: {self.source!r}. "
                f"Kiểm tra webcam có đang bị app khác chiếm, hoặc link RTSP đúng chưa."
            )
        print(f"[VideoSource] Đã mở: {self.source!r}")

    def read(self):
        """Đọc 1 khung hình. Trả về (ok, frame). Tự kết nối lại nếu stream rớt."""
        if self.cap is None:
            self.open()

        ok, frame = self.cap.read()
        if not ok:
            if self.is_stream and self.reconnect:
                print("[VideoSource] Mất kết nối, thử kết nối lại sau 2s...")
                self.release()
                time.sleep(2)
                try:
                    self.open()
                    ok, frame = self.cap.read()
                except RuntimeError as e:
                    print(f"[VideoSource] {e}")
                    return False, None
            return ok, frame
        return ok, frame

    def release(self) -> None:
        if self.cap is not None:
            self.cap.release()
            self.cap = None

    # Cho phép dùng cú pháp: with VideoSource(0) as src:
    def __enter__(self):
        self.open()
        return self

    def __exit__(self, *args):
        self.release()
