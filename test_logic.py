"""
test_logic.py — Kiểm tra các phần logic thuần (KHÔNG cần GPU/webcam/model).

Chạy:  python test_logic.py
Mọi dòng phải ra OK. Có lỗi sẽ in FAIL kèm lý do và thoát mã 1.
"""

from __future__ import annotations
import os
import sys
import tempfile

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from core.skill_base import Detection
from core.zones import ZoneSet, point_in_polygon, WHOLE_FRAME
from core.dwell import DwellTracker
from core.recorder import EventRecorder

FAILS = []


def check(name: str, cond: bool, why: str = ""):
    if cond:
        print(f"  OK   {name}")
    else:
        print(f"  FAIL {name}  {why}")
        FAILS.append(name)


def det(skill="person", box=(400, 300, 500, 600), kind=None, zones_=None,
        track_id=None, identity=None):
    d = Detection(label="x", confidence=0.9, box=box, skill=skill)
    if kind:
        d.extra["kind"] = kind
    if zones_ is not None:
        d.extra["zones"] = zones_
    if track_id is not None:
        d.extra["track_id"] = track_id
    if identity is not None:
        d.extra["identity"] = identity
    return d


# ---------- 1. point_in_polygon ----------
print("== zones: point_in_polygon ==")
square = [[0.2, 0.2], [0.8, 0.2], [0.8, 0.8], [0.2, 0.8]]
check("tam hinh vuong: trong", point_in_polygon(0.5, 0.5, square))
check("ngoai hinh vuong: ngoai", not point_in_polygon(0.9, 0.9, square))
check("goc xa: ngoai", not point_in_polygon(0.05, 0.5, square))
tri = [[0.0, 0.0], [1.0, 0.0], [0.5, 1.0]]
check("tam tam giac: trong", point_in_polygon(0.5, 0.4, tri))
check("2 dinh: da giac <3 dinh khong hop le", not point_in_polygon(0.5, 0.5, [[0, 0], [1, 1]]))

# ---------- 2. ZoneSet.annotate ----------
print("== zones: annotate ==")
with tempfile.TemporaryDirectory() as td:
    zf = os.path.join(td, "zones.json")
    import json
    json.dump({"zones": [{"name": "cong", "points": square}]}, open(zf, "w"))
    zs = ZoneSet({"file": zf})
    # khung 1000x1000; box có đáy-giữa tại (450, 600) -> chuẩn hoá (0.45, 0.6) -> TRONG vùng
    d1 = det(box=(400, 300, 500, 600))
    # box đáy-giữa tại (950, 950) -> (0.95, 0.95) -> NGOÀI
    d2 = det(box=(900, 900, 1000, 950))
    zs.annotate([d1, d2], (1000, 1000, 3))
    check("chan trong vung -> gan 'cong'", d1.extra["zones"] == ["cong"])
    check("chan ngoai vung -> rong", d2.extra["zones"] == [])

    # không có file vùng -> cả khung là 1 vùng
    zs2 = ZoneSet({"file": os.path.join(td, "khong-ton-tai.json")})
    d3 = det()
    zs2.annotate([d3], (1000, 1000, 3))
    check("chua ve vung -> toan-khung", d3.extra["zones"] == [WHOLE_FRAME])

    # HỒI QUY lỗi 4: chân chạm đúng mép dưới khung (y2 == h) vẫn phải TRONG vùng đáy
    zday = ZoneSet({"file": zf})   # vùng 'cong' = hình vuông 0.2..0.8
    json.dump({"zones": [{"name": "day", "points": [[0.1, 0.5], [0.9, 0.5], [0.9, 1.0], [0.1, 1.0]]}]},
              open(zf, "w"))
    zday.load()
    d4 = det(box=(400, 300, 500, 1000))   # y2 = 1000 = h (người sát camera, box bị cắt)
    zday.annotate([d4], (1000, 1000, 3))
    check("HOI QUY: chan cham day khung van trong vung", d4.extra["zones"] == ["day"])

    # HỒI QUY lỗi 3: zones.json hỏng đủ kiểu -> không sập, coi như không có vùng
    json.dump([1, 2, 3], open(zf, "w"))                     # top-level là list
    zbad1 = ZoneSet({"file": zf})
    check("HOI QUY: json top-level sai -> zones rong", zbad1.zones == [])
    json.dump({"zones": [{"points": [[0, 0], [1, 0], [1, 1]]}]}, open(zf, "w"))  # thiếu name
    zbad2 = ZoneSet({"file": zf})
    check("HOI QUY: vung thieu 'name' -> bi loai", zbad2.zones == [])
    zbad2.draw(np.zeros((100, 100, 3), np.uint8))            # không được nổ
    check("HOI QUY: draw sau file hong khong sap", True)
    json.dump({"zones": [{"name": "x", "points": [[0, 0], ["a", 1], [1, 1]]}]}, open(zf, "w"))
    zbad3 = ZoneSet({"file": zf})
    check("HOI QUY: dinh khong phai so -> bi loai", zbad3.zones == [])

# ---------- 3. DwellTracker v2 (theo từng người/track) ----------
print("== dwell v2: dem gio TUNG nguoi la ==")
dw = DwellTracker({"seconds": 10, "grace": 2.0})
t = 100.0
# người lạ (track 1) đứng 9.9s: chưa báo
evs = []
for i in range(100):
    evs += dw.update([det(zones_=["cong"], track_id=1, identity="stranger")], t + i * 0.1)
check("9.9s: chua bao", evs == [])
# giây 10.1: báo đúng 1 lần, kèm track_id
evs = dw.update([det(zones_=["cong"], track_id=1, identity="stranger")], t + 10.1)
check("10.1s: bao 1 lan dung nguoi", len(evs) == 1 and evs[0]["track_id"] == 1)
# vẫn đứng tiếp: không báo lặp
evs = []
for i in range(30):
    evs += dw.update([det(zones_=["cong"], track_id=1, identity="stranger")], t + 10.2 + i * 0.1)
check("van dung do: khong bao lai", evs == [])
# rời ~7s rồi quay lại đứng liên tục 10.5s: báo lượt mới
evs = dw.update([det(zones_=["cong"], track_id=1, identity="stranger")], t + 20.0)
check("quay lai sau khi vang: chua bao ngay", evs == [])
for i in range(1, 106):
    evs += dw.update([det(zones_=["cong"], track_id=1, identity="stranger")], t + 20.0 + i * 0.1)
check("luot moi du 10s: bao lai", len(evs) == 1)

# NGƯỜI QUEN (track 2) đứng cả ngày: không bao giờ báo
dw2 = DwellTracker({"seconds": 10, "grace": 2.0})
t = 200.0
evs = []
for i in range(150):
    evs += dw2.update([det(zones_=["cong"], track_id=2, identity="known")], t + i * 0.1)
check("nguoi quen dung 15s: khong bao", evs == [])

# QUAN TRỌNG (khác bản 1): người quen đứng CẠNH người lạ -> người lạ VẪN bị báo
dw3 = DwellTracker({"seconds": 10, "grace": 2.0})
t = 300.0
evs = []
for i in range(110):
    evs += dw3.update([
        det(zones_=["cong"], track_id=3, identity="known"),      # chủ nhà
        det(zones_=["cong"], track_id=4, identity="stranger"),   # kẻ lạ
    ], t + i * 0.1)
check("quen dung canh la: la VAN bi bao", len(evs) == 1 and evs[0]["track_id"] == 4)

# 2 người lạ thay nhau ra vào: KHÔNG cộng dồn giờ của nhau
dw4 = DwellTracker({"seconds": 10, "grace": 2.0})
t = 400.0
evs = []
for i in range(60):   # track 5 đứng 6s rồi đi
    evs += dw4.update([det(zones_=["cong"], track_id=5, identity="stranger")], t + i * 0.1)
for i in range(60):   # track 6 vào đứng 6s (nếu cộng dồn sẽ báo sai)
    evs += dw4.update([det(zones_=["cong"], track_id=6, identity="stranger")], t + 6.0 + i * 0.1)
check("2 nguoi la thay nhau 6s+6s: khong bao", evs == [])

# ---------- 3b. TrackRegistry: nho danh tinh khi quay lung ----------
print("== track registry ==")
from core.track_registry import TrackRegistry
reg = TrackRegistry()
t = 500.0
# khung 1: người track 7 + mặt "Tai" nằm trong khung người -> gắn known
p = det(box=(100, 100, 400, 700), track_id=7)
f = det(skill="face", box=(200, 150, 300, 280), kind="known")
f.label = "Tai"
reg.update([p, f], t)
check("mat Tai trong khung nguoi -> known", p.extra["identity"] == "known" and p.extra["name"] == "Tai")
# khung 2: QUAY LƯNG (không còn mặt) -> track 7 vẫn là Tai
p2 = det(box=(120, 100, 420, 700), track_id=7)
reg.update([p2], t + 1)
check("quay lung van nho la Tai", p2.extra["identity"] == "known" and p2.extra["name"] == "Tai")
# mặt lạ trong khung người khác -> stranger
p3 = det(box=(600, 100, 900, 700), track_id=8)
f2 = det(skill="face", box=(700, 150, 800, 280), kind="stranger")
reg.update([p3, f2], t + 2)
check("mat la -> track stranger", p3.extra["identity"] == "stranger")
# chưa từng thấy mặt -> unknown
p4 = det(box=(1000, 100, 1200, 700), track_id=9)
reg.update([p4], t + 3)
check("chua thay mat -> unknown", p4.extra["identity"] == "unknown")

# ---------- 3c. AlertManager: phan tang + luot + che do ----------
print("== alert manager v2 ==")
from core.alert_manager import AlertManager


class FakeNotifier:
    def __init__(self):
        self.sent = []

    def send(self, title, message, priority=3, tags=None, image_path=None):
        self.sent.append((title, priority))


import numpy as _np
_frame = _np.zeros((100, 100, 3), _np.uint8)
with tempfile.TemporaryDirectory() as td:
    fn = FakeNotifier()
    am = AlertManager({"save_dir": td, "session_gap": 300, "urgent_repeat": 60,
                       "mode": "home", "sleep_hours": None,
                       "fire_review_dir": os.path.join(td, "fr")}, notifier=fn)
    t = 1000.0
    # người quen xuất hiện 20 lần liên tiếp -> tier log: KHÔNG nhắn tin nào
    known = det(skill="face", kind="known")
    known.label = "Tai"; known.is_alert = True
    known.extra["group"] = "face_known"
    for i in range(20):
        am.handle(_frame, [known], t + i)
    check("nguoi quen 20 khung: 0 tin nhan", len(fn.sent) == 0)
    # người lạ thoáng qua -> notable: nhắn đúng 1 lần cho cả lượt
    stranger = det(skill="face", kind="stranger")
    stranger.is_alert = True; stranger.extra["group"] = "face_stranger"
    for i in range(20):
        am.handle(_frame, [stranger], t + 30 + i)
    check("nguoi la 20 khung: dung 1 tin", len(fn.sent) == 1)
    # cháy -> urgent: nhắn ngay, và nhắc lại sau urgent_repeat
    fire = det(skill="fire"); fire.is_alert = True
    fire.label = "FIRE"; fire.extra["group"] = "fire"
    tags = am.handle(_frame, [fire], t + 100)
    check("chay: nhan ngay + yeu cau ghi hinh", len(fn.sent) == 2 and tags == ["fire"])
    am.handle(_frame, [fire], t + 130)   # 30s sau: chưa nhắc lại
    check("chay 30s sau: chua nhac lai", len(fn.sent) == 2)
    am.handle(_frame, [fire], t + 161)   # 61s sau: nhắc lại
    check("chay 61s sau: nhac lai", len(fn.sent) == 3)
    # chế độ VẮNG NHÀ: người thường (không is_alert) cũng thành KHẨN
    fn2 = FakeNotifier()
    am2 = AlertManager({"save_dir": td, "mode": "away", "sleep_hours": None},
                       notifier=fn2)
    person = det(track_id=1)   # is_alert=False
    tags = am2.handle(_frame, [person], t + 200)
    check("vang nha: nguoi thuong -> khan + ghi hinh",
          len(fn2.sent) == 1 and fn2.sent[0][1] == 5 and "person" in tags)
    # cùng người đó ở chế độ Ở NHÀ: chỉ log, không nhắn
    fn3 = FakeNotifier()
    am3 = AlertManager({"save_dir": td, "mode": "home", "sleep_hours": None},
                       notifier=fn3)
    am3.handle(_frame, [person], t + 300)
    check("o nha: nguoi thuong -> khong nhan", len(fn3.sent) == 0)

# ---------- 4. EventRecorder ----------
print("== recorder: ghi hinh pre-roll ==")
with tempfile.TemporaryDirectory() as td:
    rec = EventRecorder({"dir": td, "pre_roll": 2, "post_roll": 1,
                         "max_seconds": 10, "fps": 10})
    frame = np.random.randint(0, 255, (240, 320, 3), np.uint8)
    t = 1000.0
    # nuôi băng đệm 3 giây (30 khung @10fps)
    for i in range(30):
        rec.feed(frame, t + i * 0.1)
    check("chua trigger: khong active", not rec.active)
    # trigger
    rec.start(t + 3.0, tag="cong")
    check("sau start: active", rec.active)
    path = rec.last_path
    check("co duong dan video", path is not None and path.endswith(".mp4"))
    # ghi tiếp 0.5s rồi để quá post_roll -> tự dừng
    for i in range(5):
        rec.feed(frame, t + 3.1 + i * 0.1)
    rec.feed(frame, t + 3.0 + 1.2)  # vượt stop_after (start+1s)
    check("qua post_roll: tu dung", not rec.active)
    # file đọc lại được và có khung hình (pre-roll ~20 khung + phần sau)
    import cv2
    cap = cv2.VideoCapture(path)
    n = 0
    while cap.read()[0]:
        n += 1
    cap.release()
    check(f"video doc lai duoc ({n} khung, can >=15)", n >= 15, f"n={n}")

    # start khi buffer TRỐNG (vừa khởi động) -> mở file ở feed() kế
    rec2 = EventRecorder({"dir": td, "pre_roll": 2, "post_roll": 1, "fps": 10})
    rec2.start(2000.0, tag="som")
    check("start som (buffer trong): active, chua co writer loi", rec2.active)
    rec2.feed(frame, 2000.05)
    rec2.feed(frame, 2000.2)
    check("feed sau do: da mo file", rec2.last_path is not None)
    rec2.stop()

# ---------- 5. Notifier: kênh none không nổ ----------
print("== notifier ==")
from core.notifier import Notifier
n0 = Notifier({"channels": ["none"]})
n0.send("test", "khong lam gi")  # không được ném exception
check("channel none: im lang", True)
n1 = Notifier({"channel": "ntfy"})   # kiểu config cũ vẫn chạy
check("tuong thich config cu (channel don)", n1.channels == ["ntfy"])

# ---------- 6. StorageCleaner ----------
print("== storage: tu don dung luong ==")
from core.storage import StorageCleaner
with tempfile.TemporaryDirectory() as td:
    d1 = os.path.join(td, "alerts"); os.makedirs(d1)
    now = 1_000_000_000.0
    # 3 file: 20 ngày tuổi, 10 ngày tuổi, mới tinh
    for name, age_days in [("cu.jpg", 20), ("vua.jpg", 10), ("moi.jpg", 0)]:
        p = os.path.join(d1, name)
        open(p, "wb").write(b"x" * 1000)
        os.utime(p, (now - age_days * 86400, now - age_days * 86400))
    sc = StorageCleaner({"max_days": 14, "max_gb": 10}, dirs=[d1])
    n = sc.run_once(now)
    left = sorted(os.listdir(d1))
    check("xoa file qua 14 ngay", n == 1 and left == ["moi.jpg", "vua.jpg"])

    # vượt trần GB -> xoá dần từ cũ nhất
    sc2 = StorageCleaner({"max_days": 999, "max_gb": 0.0000015}, dirs=[d1])  # ~1.5KB
    sc2.run_once(now)
    check("vuot tran GB: giu file moi nhat", os.listdir(d1) == ["moi.jpg"])

    # thư mục faces không nằm trong danh sách quản lý -> không bao giờ bị đụng
    check("khong dong den faces", "faces" not in str(sc.dirs))

    stats = sc.stats()
    check("stats co du lieu", d1 in stats and stats[d1]["files"] == 1)

# ---------- 7. Dashboard API ----------
print("== dashboard API ==")
import threading as _th
from types import SimpleNamespace as _NS
from core.dashboard import create_app


class _FakeRecorder:
    active = False


class _FakeCam:
    def __init__(self, name):
        self.name = name
        self.fps = 12.3
        self.display = _np.zeros((60, 80, 3), _np.uint8)
        self.recorder = _FakeRecorder()


class _FakeAlerts:
    def __init__(self):
        self.mode = "home"

    def effective_mode(self, now):
        return self.mode

    def set_mode(self, m):
        self.mode = m


with tempfile.TemporaryDirectory() as td:
    adir = os.path.join(td, "alerts"); os.makedirs(adir)
    rdir = os.path.join(td, "recs"); os.makedirs(rdir)
    fdir = os.path.join(td, "faces"); os.makedirs(os.path.join(fdir, "Tai"))
    open(os.path.join(fdir, "Tai", "1.jpg"), "wb").write(b"x")
    open(os.path.join(adir, "fire_20260101_000000.jpg"), "wb").write(b"x")

    fake_sc = StorageCleaner({}, dirs=[adir, rdir])
    st = _NS(cameras=[_FakeCam("cam1")], alerts=_FakeAlerts(), cleaner=fake_sc,
             notifier=None, quit_flag=_th.Event(), device="test",
             cfg={"dashboard": {}, "alert": {"save_dir": adir},
                  "recording": {"dir": rdir},
                  "skills": {"face": {"faces_dir": fdir}}})
    app = create_app(st)
    client = app.test_client()

    r = client.get("/api/status").get_json()
    check("status: mode + camera + fps", r["mode"] == "home"
          and r["cameras"][0]["name"] == "cam1" and r["cameras"][0]["fps"] == 12.3)
    client.post("/api/mode/away")
    check("doi che do qua API", st.alerts.mode == "away")
    check("che do sai -> 400", client.post("/api/mode/xyz").status_code == 400)
    r = client.get("/api/alerts").get_json()
    check("liet ke canh bao", len(r) == 1 and r[0]["file"].startswith("fire"))
    r = client.get("/api/people").get_json()
    check("liet ke nguoi nha", r == [{"name": "Tai", "photos": 1}])
    check("xoa nguoi qua API", client.delete("/api/people/Tai").status_code == 200
          and not os.path.isdir(os.path.join(fdir, "Tai")))
    check("chan ../ khi xoa nguoi",
          client.delete("/api/people/..%2F..%2Fx").status_code in (400, 404))
    check("trang chu co HTML", b"Camera AI" in client.get("/").data)

    # --- dang ky nguoi TU CAMERA DANG CHAY (enroll live) ---
    class _FakeFaceApp:
        def __init__(self):
            self.n_faces = 1

        def get(self, frame):
            return [object()] * self.n_faces

    class _FakeFaceSkill:
        name = "face"

        def __init__(self):
            self.app = _FakeFaceApp()
            self.reloaded = 0

        def reload_known(self):
            self.reloaded += 1
            return 1

    class _FakeGrabber:
        def latest(self):
            return True, _np.zeros((60, 80, 3), _np.uint8)

    fskill = _FakeFaceSkill()
    st.cameras[0].skills = [fskill]
    st.cameras[0].grabber = _FakeGrabber()

    r = client.post("/api/enroll", json={"name": "NguoiMoi", "camera": "cam1"})
    check("enroll live: dang ky OK + hieu luc ngay",
          r.status_code == 200 and r.get_json()["ok"]
          and os.path.exists(os.path.join(fdir, "NguoiMoi", "1.jpg"))
          and fskill.reloaded == 1)
    r = client.post("/api/enroll", json={"name": "Ten Co Cach", "camera": "cam1"})
    check("enroll live: ten co khoang trang -> tu choi", r.status_code == 400)
    fskill.app.n_faces = 2
    r = client.post("/api/enroll", json={"name": "HaiNguoi", "camera": "cam1"})
    check("enroll live: 2 mat trong hinh -> tu choi", r.status_code == 400)
    r = client.post("/api/reload-faces")
    check("nut nap lai tu thu muc", r.status_code == 200 and fskill.reloaded >= 2)

    client.post("/api/quit")
    check("nut tat: quit_flag bat", st.quit_flag.is_set())

    # co mat khau -> khong dang nhap bi 401
    st2 = _NS(**{**st.__dict__, "cfg": {**st.cfg, "dashboard": {"password": "abc"}},
                 "quit_flag": _th.Event()})
    app2 = create_app(st2)
    check("password: chua dang nhap -> 401",
          app2.test_client().get("/api/status").status_code == 401)
    import base64
    ok_hdr = {"Authorization": "Basic " + base64.b64encode(b"x:abc").decode()}
    check("password dung -> vao duoc",
          app2.test_client().get("/api/status", headers=ok_hdr).status_code == 200)

# ---------- tổng kết ----------
print()
if FAILS:
    print(f"KET QUA: {len(FAILS)} FAIL -> {FAILS}")
    sys.exit(1)
print("KET QUA: TAT CA OK")
