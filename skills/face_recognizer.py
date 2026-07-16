"""
face_recognizer.py — SKILL 2: Nhận diện khuôn mặt (người nhà vs người lạ).

Dùng InsightFace (buffalo_l): vừa dò mặt, vừa tạo "vân tay số" 512 chiều cho mỗi mặt.
So sánh vân tay của mặt trong khung hình với thư viện mặt người nhà đã lưu.
    - Giống 1 người nhà  => hiện tên (xanh lá)
    - Không giống ai     => "Nguoi la" (đỏ) + có thể cảnh báo

CÁCH THÊM NGƯỜI NHÀ:
    Bỏ ảnh vào  data/faces/<Ten>/  (mỗi người 1 thư mục, 5-20 ảnh nhiều góc mặt).
    Ví dụ:  data/faces/Nam/1.jpg, data/faces/Nam/2.jpg, data/faces/Mẹ/1.jpg ...
    Lần chạy đầu app sẽ tự học các khuôn mặt này.
"""

from __future__ import annotations
import os
import numpy as np
from core.skill_base import Skill, Detection

# InsightFace nặng (~300MB VRAM) — nhiều camera thì DÙNG CHUNG 1 bản,
# cache theo (det_size, ctx_id). FaceAnalysis không giữ trạng thái giữa
# các lần get() nên chia sẻ giữa các camera là an toàn.
_APP_CACHE: dict = {}


def _get_face_app(det_size: tuple, ctx_id: int):
    key = (det_size, ctx_id)
    if key not in _APP_CACHE:
        from insightface.app import FaceAnalysis
        providers = (["CUDAExecutionProvider", "CPUExecutionProvider"]
                     if ctx_id >= 0 else ["CPUExecutionProvider"])
        app = FaceAnalysis(name="buffalo_l", providers=providers)
        app.prepare(ctx_id=ctx_id, det_size=det_size)
        _APP_CACHE[key] = app
    return _APP_CACHE[key]


class FaceRecognizer(Skill):
    name = "face"

    def __init__(self, config: dict | None = None):
        super().__init__(config)
        self.faces_dir = self.config.get("faces_dir", "data/faces")
        self.threshold = self.config.get("threshold", 0.5)   # >0.5 coi là cùng người
        self.det_size = tuple(self.config.get("det_size", [640, 640]))
        self.ctx_id = self.config.get("ctx_id", "auto")      # auto = tự chọn GPU/CPU
        self.alert_on_stranger = self.config.get("alert_on_stranger", True)
        self.alert_on_known = self.config.get("alert_on_known", False)  # báo cả người quen?
        self.app = None
        self.known_names: list[str] = []
        self.known_embeds: np.ndarray | None = None   # ma trận vân tay người nhà

    def load(self) -> None:
        from core.device import face_ctx_id
        self.ctx_id = face_ctx_id(self.ctx_id)   # "auto" -> 0 (GPU) | -1 (CPU)

        if self.ctx_id >= 0:
            # Nạp sẵn DLL CUDA để InsightFace chạy GPU (không thì rớt về CPU, chậm ~70x)
            from core.cuda_dll import preload_cuda_dlls
            preload_cuda_dlls()
        elif self.det_size == (640, 640):
            # máy chỉ có CPU: tự giảm độ phân giải dò mặt cho đỡ ì
            # (640 -> 320 nhanh ~4 lần, vẫn dò tốt mặt ở tầm gần)
            self.det_size = (320, 320)
            print("[face] ⚠️ Máy không có GPU — giảm det_size xuống 320 cho đỡ chậm. "
                  "Vẫn chậm quá thì tăng skills.face.interval hoặc tắt skill face.")

        print(f"[face] Đang nạp InsightFace (buffalo_l, ctx_id={self.ctx_id})...")
        self.app = _get_face_app(self.det_size, self.ctx_id)   # nhiều camera dùng chung
        used = self.app.models["recognition"].session.get_providers()[0]
        print(f"[face] Provider: {used}" + ("  ⚠️ đang chạy CPU (chậm)!" if "CPU" in used else "  ✅ GPU"))
        self._build_known_faces()
        self._loaded = True
        print(f"[face] Sẵn sàng. Đã học {len(self.known_names)} khuôn mặt người nhà.")

    def _build_known_faces(self) -> None:
        """Quét thư mục data/faces/ và tạo vân tay cho từng người."""
        from core.imgio import imread_unicode
        embeds, names = [], []
        if not os.path.isdir(self.faces_dir):
            print(f"[face] Chưa có thư mục {self.faces_dir} — bỏ qua, mọi mặt sẽ là 'Nguoi la'.")
            self.known_embeds = None
            return

        for person in sorted(os.listdir(self.faces_dir)):
            pdir = os.path.join(self.faces_dir, person)
            if not os.path.isdir(pdir):
                continue
            for fname in os.listdir(pdir):
                path = os.path.join(pdir, fname)
                img = imread_unicode(path)
                if img is None:
                    continue
                faces = self.app.get(img)
                if not faces:
                    print(f"[face] Không thấy mặt trong {path}, bỏ qua.")
                    continue
                # lấy mặt to nhất trong ảnh
                face = max(faces, key=lambda f: (f.bbox[2] - f.bbox[0]) * (f.bbox[3] - f.bbox[1]))
                embeds.append(face.normed_embedding)
                names.append(person)

        if embeds:
            self.known_embeds = np.array(embeds, dtype=np.float32)
            self.known_names = names
        else:
            self.known_embeds = None

    def reload_known(self) -> int:
        """Nạp lại người nhà từ thư mục NGAY khi đang chạy (không cần restart).
        Dashboard gọi hàm này sau khi đăng ký người mới. Trả về số mặt đã học."""
        self._build_known_faces()
        n = len(self.known_names)
        print(f"[face] Đã nạp lại danh sách: {n} khuôn mặt người nhà.")
        return n

    def _match(self, embedding: np.ndarray) -> tuple[str, float]:
        """So vân tay mặt với người nhà. Trả về (tên, độ_giống)."""
        embeds, names = self.known_embeds, self.known_names   # chụp 1 lần (an toàn khi reload)
        if embeds is None or not len(names):
            return "Nguoi la", 0.0
        # cosine similarity (embedding đã chuẩn hoá => chỉ cần tích vô hướng)
        sims = embeds @ embedding
        i = int(np.argmax(sims))
        best = float(sims[i])
        if best >= self.threshold and i < len(names):
            return names[i], best
        return "Nguoi la", best

    def process(self, frame) -> list[Detection]:
        if not self.enabled or self.app is None:
            return []

        detections: list[Detection] = []
        for face in self.app.get(frame):
            x1, y1, x2, y2 = map(int, face.bbox)
            name, score = self._match(face.normed_embedding)
            is_stranger = name == "Nguoi la"
            if is_stranger:
                alert = self.alert_on_stranger
                group = "face_stranger"    # nhóm cảnh báo riêng cho người lạ
            else:
                alert = self.alert_on_known
                group = "face_known"       # nhóm riêng cho người quen (ưu tiên thấp)
            detections.append(Detection(
                label=name,
                confidence=score if not is_stranger else 1.0 - score,
                box=(x1, y1, x2, y2),
                skill=self.name,
                is_alert=alert,
                color=(0, 0, 255) if is_stranger else (0, 255, 0),  # đỏ / xanh
                extra={"group": group, "kind": "stranger" if is_stranger else "known"},
            ))
        return detections
