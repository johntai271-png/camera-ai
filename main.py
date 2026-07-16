"""
main.py — Điểm khởi động của app. Hỗ trợ MỘT hoặc NHIỀU camera.

Cấu hình 1 camera (kiểu cũ, vẫn chạy):        Nhiều camera:
    video:                                        cameras:
      source: 0                                     - name: "cong"
                                                      source: "rtsp://user:pass@ip:554/stream2"
                                                      zones_file: "data/zones_cong.json"
                                                    - name: "phong-khach"
                                                      source: 0

Mỗi camera có: luồng đọc hình riêng (không nghẽn nhau), vùng giám sát riêng,
bộ đếm người lạ riêng, máy ghi hình riêng. Model AI nặng (YOLO cháy/vật,
InsightFace) DÙNG CHUNG giữa các camera cho tiết kiệm GPU.

Chạy:   python main.py
Phím:   Q thoát · O ở nhà · V vắng nhà · N ngủ
"""

from __future__ import annotations
import sys
import threading
import time
from types import SimpleNamespace

import yaml
import cv2

# Ép in UTF-8: tránh lỗi khi console Windows dùng bảng mã khác (chữ tiếng Việt có dấu)
for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

from core.video_source import VideoSource
from core.frame_grabber import FrameGrabber
from core.alert_manager import AlertManager, MODE_LABEL
from core.notifier import Notifier
from core.zones import ZoneSet
from core.dwell import DwellTracker
from core.recorder import EventRecorder
from core.track_registry import TrackRegistry
from core.device import describe as describe_device
from core.storage import StorageCleaner
from core.dashboard import start_dashboard
from skills.person_detector import PersonDetector
from skills.face_recognizer import FaceRecognizer
from skills.fire_detector import FireDetector
from skills.object_detector import ObjectDetector

# Đăng ký skill: tên trong config -> class tương ứng.
# Thêm skill mới => thêm 1 dòng ở đây, không sửa gì khác.
SKILL_REGISTRY = {
    "person": PersonDetector,
    "face": FaceRecognizer,
    "fire": FireDetector,        # model D-Fire: đám cháy thật, khói
    "fire_small": FireDetector,  # model cộng đồng: lửa NHỎ (bật lửa, nến) mà D-Fire mù
    "object": ObjectDetector,
}


def load_config(path: str = "config.yaml") -> dict:
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def build_skills(cfg: dict, quiet: bool = False) -> list:
    """Tạo bộ skill theo config. Skill nào hỏng (thiếu thư viện, thiếu model...)
    thì TẮT RIÊNG skill đó và đi tiếp — không cho sập cả app."""
    skills = []
    for name, klass in SKILL_REGISTRY.items():
        sk_cfg = cfg.get("skills", {}).get(name, {})
        if not sk_cfg.get("enabled", False):
            if not quiet:
                print(f"[main] Skill '{name}' đang TẮT trong config, bỏ qua.")
            continue
        skill = klass(sk_cfg)
        skill.name = name          # tên theo key config (phân biệt fire / fire_small)
        try:
            skill.load()           # nạp model (có thể mất vài giây lần đầu)
        except Exception as e:
            print(f"[main] ⚠️ Skill '{name}' lỗi khi nạp ({type(e).__name__}: "
                  f"{str(e)[:90]}) -> TẮT skill này, app vẫn chạy tiếp.")
            continue
        if skill.enabled:          # skill có thể tự tắt (vd fire thiếu model)
            skills.append(skill)
    return skills


class Camera:
    """Một camera = nguồn hình + bộ skill + vùng + đếm giờ + ghi hình RIÊNG."""

    def __init__(self, cam_cfg: dict, cfg: dict, quiet: bool = False):
        self.name = cam_cfg.get("name", "cam")
        self.source = VideoSource(
            cam_cfg.get("source", 0),
            reconnect=cam_cfg.get("reconnect", True),
            width=cam_cfg.get("width"),
            height=cam_cfg.get("height"),
        )
        self.grabber = FrameGrabber(self.source)

        zcfg = dict(cfg.get("zones", {}))
        if cam_cfg.get("zones_file"):        # mỗi cam có thể có file vùng riêng
            zcfg["file"] = cam_cfg["zones_file"]
        self.zones = ZoneSet(zcfg)
        self.dwell = DwellTracker(cfg.get("dwell", {}))
        self.registry = TrackRegistry()
        self.recorder = EventRecorder(cfg.get("recording", {}))
        # skill riêng cho từng cam (person cần tracker riêng, fire cần chuỗi xác
        # nhận riêng) — nhưng model nặng bên dưới đã được cache DÙNG CHUNG
        self.skills = build_skills(cfg, quiet=quiet)

        self.frame_idx = 0
        self.fps = 0.0
        self.prev = time.time()
        self.ever_ok = False
        self.dead = False
        self._last_frame = None   # để biết grabber đã có khung MỚI chưa
        self.display = None       # khung ĐÃ VẼ nhãn gần nhất — dashboard lấy để stream

    def poll(self):
        """Lấy khung MỚI nếu có. Trả về frame gốc (đừng vẽ lên!) hoặc None."""
        ok, frame = self.grabber.latest()
        if not ok or frame is None:
            # CHỈ file-hết mới coi là chết (grabber xoá frame khi file cạn).
            # Webcam/RTSP trục trặc thoáng qua thì chờ khung sau, không giết cam.
            if self.ever_ok and self.source.is_file and frame is None:
                self.dead = True
            return None
        self.ever_ok = True
        if frame is self._last_frame:
            return None            # chưa có khung mới — khỏi xử lý lại khung cũ
        self._last_frame = frame
        return frame

    def stop(self):
        self.recorder.stop()
        self.grabber.stop()


def main():
    cfg = load_config()
    print(f"[main] Phần cứng: {describe_device()}")

    # danh sách camera: mục 'cameras' (nhiều cam) hoặc 'video' (1 cam, kiểu cũ)
    cams_cfg = cfg.get("cameras")
    if not cams_cfg:
        cams_cfg = [{"name": "cam", **cfg.get("video", {})}]

    notifier = Notifier(cfg.get("notify", {}))
    alerts = AlertManager(cfg.get("alert", {}), notifier=notifier)

    print(f"[main] Đang khởi động {len(cams_cfg)} camera...")
    cameras: list[Camera] = []
    for i, c in enumerate(cams_cfg):
        cam = Camera(c, cfg, quiet=(i > 0))   # log skill 1 lần cho đỡ ồn
        if not cam.skills:
            print("[main] Không có skill nào bật. Kiểm tra config.yaml.")
            return
        cameras.append(cam)
        print(f"[main] Camera '{cam.name}': {len(cam.skills)} skill "
              f"({[s.name for s in cam.skills]})")

    dcfg = cfg.get("display", {})
    show_window = dcfg.get("show_window", True)
    if "--headless" in sys.argv:      # chạy nền: không cửa sổ, xem qua dashboard
        show_window = False
    show_fps = dcfg.get("show_fps", True)

    # dọn dung lượng định kỳ (ảnh/video cũ) + dashboard web
    acfg = cfg.get("alert", {})
    cleaner = StorageCleaner(cfg.get("storage", {}), dirs=[
        acfg.get("save_dir", "data/alerts"),
        cfg.get("recording", {}).get("dir", "data/recordings"),
        acfg.get("fire_review_dir", "data/fire_review"),
    ])
    cleaner.run_once()
    cleaner.start()

    state = SimpleNamespace(cameras=cameras, alerts=alerts, cleaner=cleaner,
                            notifier=notifier, cfg=cfg,
                            quit_flag=threading.Event(),
                            device=describe_device())
    start_dashboard(state)    # http://localhost:8090 (tắt được trong config)

    for cam in cameras:
        cam.grabber.start()
    alerts.startup()          # "báo chạy" — thông báo hệ thống đã bật

    try:
        while True:
            now = time.time()
            got_any = False

            for cam in cameras:
                orig = cam.poll()
                if orig is None:
                    continue
                got_any = True

                # 1) CHẠY skill trên ảnh GỐC sạch (chưa vẽ) — vẽ đè rồi mới xử lý
                #    là khung/chữ đè lên mặt người làm nhận diện sai.
                all_dets = []
                for skill in cam.skills:
                    if cam.frame_idx % skill.interval == 0:
                        skill._cache = skill.process(orig)
                    all_dets.extend(skill._cache)
                cam.frame_idx += 1

                # 2) danh tính từng người + vùng
                cam.registry.update(all_dets, now)
                cam.zones.annotate(all_dets, orig.shape)

                # 3) vẽ lên BẢN SAO (giữ orig sạch cho khung sau + fire_review)
                frame = orig.copy()
                for skill in cam.skills:
                    frame = skill.draw(frame, skill._cache)
                frame = cam.zones.draw(frame)

                # 4) người lạ ở lì trong vùng -> báo + ghi hình
                for ev in cam.dwell.update(all_dets, now):
                    cam.recorder.start(now, tag=f"{cam.name}-{ev['zone']}")
                    alerts.dwell_alert(frame, ev["zone"], ev["duration"], now,
                                       recording=cam.recorder.enabled,
                                       camera=cam.name)
                alerting = cam.dwell.alerting_zones(now)
                if alerting:
                    if cam.recorder.active:
                        cam.recorder.keep_alive(now)
                    else:   # video trước chạm trần max_seconds -> mở file mới
                        cam.recorder.start(now, tag=f"{cam.name}-{alerting[0]}")

                # 5) cảnh báo phân tầng; sự kiện khẩn -> ghi hình luôn
                for tag in alerts.handle(frame, all_dets, now, raw_frame=orig,
                                         camera=cam.name):
                    if cam.recorder.active:
                        cam.recorder.keep_alive(now)
                    else:
                        cam.recorder.start(now, tag=f"{cam.name}-{tag}")

                # 6) trang trí + ghi hình + hiển thị
                if cam.recorder.active:
                    cv2.circle(frame, (frame.shape[1] - 30, 25), 9, (0, 0, 255), -1)
                    cv2.putText(frame, "REC", (frame.shape[1] - 75, 32),
                                cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 0, 255), 2)
                mode = alerts.effective_mode(now)
                mode_color = (0, 200, 0) if mode == "home" else (0, 0, 255)
                cv2.putText(frame, f"Che do: {MODE_LABEL[mode]}  [O/V/N]", (10, 56),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.6, mode_color, 2)

                cam.recorder.feed(frame, now)

                dt = now - cam.prev
                cam.prev = now
                if dt > 0:
                    cam.fps = 0.9 * cam.fps + 0.1 * (1.0 / dt)
                if show_fps:
                    cv2.putText(frame, f"FPS: {cam.fps:4.1f}", (10, 28),
                                cv2.FONT_HERSHEY_SIMPLEX, 0.8, (255, 255, 0), 2)
                cam.display = frame   # dashboard stream khung này
                if show_window:
                    cv2.imshow(f"Camera AI [{cam.name}]  q:thoat o/v/n:che-do", frame)

            # tất cả nguồn dạng FILE đã hết -> dừng (dùng cho test)
            if all(cam.dead for cam in cameras):
                print("[main] Hết video.")
                break

            # nút "Tắt hệ thống" trên dashboard
            if state.quit_flag.is_set():
                print("[main] Tắt từ dashboard.")
                break

            if not got_any:
                time.sleep(0.005)   # chưa cam nào có khung mới — nghỉ 5ms đỡ tốn CPU

            key = (cv2.waitKey(1) & 0xFF) if show_window else 255
            if key == ord("q"):
                break
            elif key == ord("o"):
                alerts.set_mode("home")
            elif key == ord("v"):
                alerts.set_mode("away")
            elif key == ord("n"):
                alerts.set_mode("sleep")
    except KeyboardInterrupt:
        print("\n[main] Dừng bởi người dùng (Ctrl+C).")
    finally:
        for cam in cameras:
            cam.stop()           # chốt file đang quay + tắt luồng đọc
        cv2.destroyAllWindows()
        print("[main] Đã thoát sạch.")


if __name__ == "__main__":
    main()
