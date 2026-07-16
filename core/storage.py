"""
storage.py — Tự dọn dung lượng: xoá ảnh/video cũ để không bao giờ đầy ổ.

Luật dọn (chạy nền mỗi giờ, và một lần lúc khởi động):
    1. File cũ hơn 'max_days' ngày -> xoá.
    2. Tổng dung lượng vẫn vượt 'max_gb' -> xoá dần file CŨ NHẤT tới khi đủ chỗ.

Chỉ dọn các thư mục sinh ra tự động (alerts, recordings, fire_review).
KHÔNG BAO GIỜ đụng vào data/faces (ảnh người nhà là dữ liệu bạn tạo).
"""

from __future__ import annotations
import os
import threading
import time


class StorageCleaner:
    def __init__(self, config: dict | None = None, dirs: list[str] | None = None):
        config = config or {}
        self.enabled = config.get("enabled", True)
        self.max_days = float(config.get("max_days", 14))
        self.max_gb = float(config.get("max_gb", 10))
        self.check_every = float(config.get("check_every", 3600))  # giây
        self.dirs = dirs or ["data/alerts", "data/recordings", "data/fire_review"]
        self._stop = False

    # ---------- lõi (tách riêng để test được) ----------

    def _list_files(self) -> list[tuple[float, int, str]]:
        """Mọi file trong các thư mục quản lý: [(mtime, size, path)] cũ nhất trước."""
        out = []
        for d in self.dirs:
            if not os.path.isdir(d):
                continue
            for f in os.listdir(d):
                p = os.path.join(d, f)
                if os.path.isfile(p):
                    try:
                        st = os.stat(p)
                        out.append((st.st_mtime, st.st_size, p))
                    except OSError:
                        pass
        out.sort()
        return out

    def run_once(self, now: float | None = None) -> int:
        """Dọn một lượt. Trả về số file đã xoá."""
        if not self.enabled:
            return 0
        now = now if now is not None else time.time()
        deleted = 0
        files = self._list_files()

        # 1) xoá file quá hạn
        cutoff = now - self.max_days * 86400
        kept = []
        for mtime, size, path in files:
            if mtime < cutoff:
                if self._delete(path):
                    deleted += 1
            else:
                kept.append((mtime, size, path))

        # 2) vẫn vượt trần dung lượng -> xoá dần từ cũ nhất
        total = sum(s for _, s, _ in kept)
        limit = self.max_gb * (1024 ** 3)
        i = 0
        while total > limit and i < len(kept):
            mtime, size, path = kept[i]
            if self._delete(path):
                deleted += 1
                total -= size
            i += 1

        if deleted:
            print(f"[storage] Đã dọn {deleted} file cũ.")
        return deleted

    @staticmethod
    def _delete(path: str) -> bool:
        try:
            os.remove(path)
            return True
        except OSError:
            return False

    def stats(self) -> dict:
        """Thống kê cho dashboard: {thư_mục: {"files": n, "mb": x}}."""
        out = {}
        for d in self.dirs:
            n, size = 0, 0
            if os.path.isdir(d):
                for f in os.listdir(d):
                    p = os.path.join(d, f)
                    if os.path.isfile(p):
                        n += 1
                        try:
                            size += os.path.getsize(p)
                        except OSError:
                            pass
            out[d] = {"files": n, "mb": round(size / 1e6, 1)}
        return out

    # ---------- chạy nền ----------

    def start(self) -> None:
        if not self.enabled:
            return
        threading.Thread(target=self._loop, daemon=True).start()

    def _loop(self) -> None:
        while not self._stop:
            try:
                self.run_once()
            except Exception as e:
                print(f"[storage] Lỗi khi dọn: {e}")
            # ngủ từng giây để dừng được nhanh
            for _ in range(int(self.check_every)):
                if self._stop:
                    return
                time.sleep(1)

    def stop(self) -> None:
        self._stop = True
