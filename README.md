# 🎥 Camera AI — Hệ thống giám sát nhà thông minh chạy 100% trên máy của bạn

Camera an ninh AI **tự host**: không phí thuê bao, không đẩy video lên cloud,
dữ liệu không rời khỏi nhà. Nguồn hình là webcam, **điện thoại cũ**, hoặc camera
IP (RTSP) — chạy được từ máy có GPU NVIDIA mạnh tới **máy không có GPU**.

> Nhận diện **AI là ai** (người nhà / người lạ), phát hiện **cháy & khói**, canh
> **người lạ ở lì trong vùng cấm**, tự **ghi video bằng chứng** (kèm 5 giây trước
> sự kiện), báo về điện thoại qua **Zalo** — và chỉ báo khi thật sự đáng báo.

---

## Mục lục
1. [Tính năng](#1-tính-năng)
2. [Kiến trúc & cấu trúc thư mục](#2-kiến-trúc--cấu-trúc-thư-mục)
3. [Cài đặt](#3-cài-đặt)
4. [Chạy app](#4-chạy-app)
5. [Dashboard web](#5-dashboard-web)
6. [Đăng ký người nhà](#6-đăng-ký-người-nhà)
7. [Vùng giám sát](#7-vùng-giám-sát)
8. [Camera: điện thoại / camera IP / nhiều camera](#8-camera)
9. [Đăng ký bot Zalo (chi tiết)](#9-đăng-ký-bot-zalo)
10. [Model cháy: train & sửa báo nhầm](#10-model-cháy)
11. [Bảng config](#11-bảng-config)
12. [⚠️ Hạn chế — đọc trước khi tin tưởng hệ thống](#12-hạn-chế)
13. [Lỗi hay gặp](#13-lỗi-hay-gặp)

---

## 1. Tính năng

### Nhận diện (5 skill, bật/tắt độc lập)
| Skill | Việc | Công nghệ |
|---|---|---|
| `person` | Phát hiện + **theo dõi từng người** (mỗi người 1 ID) | YOLO11 + ByteTrack |
| `face` | Người nhà vs người lạ (1 ảnh là nhận được) | InsightFace (ArcFace) |
| `fire` | Đám cháy, khói thật | YOLO11 tự train trên D-Fire (mAP50 76%) |
| `fire_small` | Lửa nhỏ: bật lửa, nến, bếp | model cộng đồng (bù vùng mù của D-Fire) |
| `object` | Chó, mèo, xe đạp/máy/ô tô | YOLO11 (dùng chung model — 0 VRAM thêm) |

### Trí nhớ danh tính
Nhận mặt **một lần** → track đó được nhớ mãi: **quay lưng vẫn biết là ai**.
Đếm giờ ở lì tính **theo từng người** — chủ nhà đứng cạnh kẻ lạ thì kẻ lạ vẫn bị
báo; hai người thay nhau ra vào không bị cộng dồn giờ oan.

### Cảnh báo 3 tầng × 3 chế độ (chống spam)
| Tầng | Sự kiện | Hành động |
|---|---|---|
| 🚨 KHẨN | cháy · người lạ ở lì ≥10s trong vùng · *bất kỳ ai* khi VẮNG NHÀ | Zalo ngay + nhắc lại mỗi 30s + **tự ghi hình** |
| 🔔 CHÚ Ý | người lạ thoáng qua | Zalo **1 lần mỗi lượt** xuất hiện |
| 📝 NHẬT KÝ | người quen, chó mèo xe | chỉ lưu ảnh — không làm phiền |

Chế độ **Ở NHÀ / VẮNG NHÀ / NGỦ**: phím `O`/`V`/`N` trên cửa sổ hoặc nút trên
dashboard (đổi được từ điện thoại). 23h–6h tự chuyển chế độ Ngủ.

### Ghi hình sự kiện
Video kèm **5 giây TRƯỚC khi sự kiện xảy ra** (pre-roll), tự nén H.264 để phát
thẳng trên trình duyệt, xâm nhập dài tự tách nhiều file, có trần dung lượng.

### Dashboard web + chạy nền
Xem live, lịch sử cảnh báo, phát lại video, quản lý người nhà, đổi chế độ —
tất cả trên trình duyệt (cả điện thoại cùng WiFi). Chạy nền không cần cửa sổ,
tự khởi động cùng Windows.

### Tự bảo trì
- Ảnh/video cũ quá 14 ngày hoặc vượt 10GB → tự xoá dần (không đụng ảnh người nhà)
- Báo nhầm cháy → gom ảnh → `train_fire.py --with-feedback` → model càng dùng càng khôn

---

## 2. Kiến trúc & cấu trúc thư mục

```
Camera (điện thoại / webcam / RTSP — mỗi cam 1 thread đọc riêng)
   │ khung hình sạch
   ▼
5 Skills (person→face→fire→fire_small→object; skill nặng chạy cách quãng)
   ▼
TrackRegistry (gắn tên vào từng người)  →  ZoneSet (ai trong vùng nào)
   ▼                                          ▼
AlertManager (3 tầng × 3 chế độ)  ←  DwellTracker (người lạ ở lì? theo từng người)
   │                    │
   ▼                    ▼
Notifier (Zalo/ntfy/    EventRecorder (mp4 + pre-roll + H.264)
Telegram, thread nền)
   ▼
Dashboard web (Flask) + cửa sổ hiển thị + StorageCleaner
```

```
camera-ai/
├── main.py               # vòng lặp chính, hỗ trợ nhiều camera
├── config.yaml           # TẤT CẢ cài đặt (tạo từ config.example.yaml)
├── enroll.py             # quản lý người nhà (thêm/xem/xoá, từ cam hoặc ảnh)
├── zone_editor.py        # vẽ vùng giám sát bằng chuột
├── zalo_setup.py         # nối bot Zalo (lấy chat_id + test)
├── train_fire.py         # train model cháy + học lại từ ảnh báo nhầm
├── check_env.py          # khám máy, in lệnh cài đúng cho từng loại máy
├── test_logic.py         # 40+ test tự động
├── CHAY-CAMERA.bat       # chạy CÓ cửa sổ (demo/debug)
├── CHAY-NEN.bat          # chạy NỀN (xem qua dashboard)      ← dùng hằng ngày
├── TAT-CAMERA.bat        # tắt bản chạy nền
├── BAT-TU-DONG-CHAY.bat  # mở máy là tự chạy (gỡ: TAT-TU-DONG-CHAY.bat)
├── core/                 # hạ tầng
│   ├── skill_base.py     #   khuôn chung của mọi skill + Detection
│   ├── video_source.py   #   webcam/file/RTSP + tự kết nối lại
│   ├── frame_grabber.py  #   thread đọc cam (nhiều cam không nghẽn nhau)
│   ├── track_registry.py #   trí nhớ danh tính theo track
│   ├── zones.py          #   vùng đa giác + điểm neo
│   ├── dwell.py          #   đếm giờ người lạ theo từng người
│   ├── alert_manager.py  #   3 tầng × 3 chế độ, báo theo lượt
│   ├── notifier.py       #   Zalo / ntfy / Telegram (thread nền)
│   ├── recorder.py       #   ghi video pre-roll + nén H.264
│   ├── dashboard.py      #   web UI (Flask)
│   ├── storage.py        #   tự dọn dung lượng
│   ├── device.py         #   tự chọn GPU NVIDIA / Mac / CPU
│   ├── model_cache.py    #   model YOLO dùng chung giữa các skill/cam
│   ├── cuda_dll.py       #   giúp InsightFace thấy GPU trên Windows
│   └── imgio.py          #   đọc ảnh trong thư mục có dấu tiếng Việt
├── skills/               # 5 tính năng nhận diện (mỗi cái 1 file)
├── models/               # fire.pt, fire_small.pt (không kèm repo — xem mục 10)
└── data/                 # faces/ alerts/ recordings/ fire_review/ zones*.json logs/
```

**Thêm tính năng nhận diện mới** = viết 1 file trong `skills/` theo khuôn
`Skill` + thêm 1 dòng vào `SKILL_REGISTRY` trong main.py. Không sửa gì khác.

---

## 3. Cài đặt

Cần: Python ≥ 3.10, webcam/điện thoại/camera IP. GPU NVIDIA là tuỳ chọn (không
có vẫn chạy, chậm hơn).

```powershell
git clone https://github.com/johntai271-png/camera-ai.git
cd camera-ai
python -m venv .venv
.\.venv\Scripts\Activate.ps1        # Linux/Mac: source .venv/bin/activate

pip install -r requirements.txt
python check_env.py                  # <-- khám máy, IN ĐÚNG LỆNH CÀI cho máy bạn
# ...chạy các lệnh torch/onnxruntime mà check_env đưa...

copy config.example.yaml config.yaml # rồi điền phần notify (mục 9)
python main.py
```

Tóm tắt lệnh torch theo máy (check_env tự chọn giúp):
| Máy | torch | onnxruntime |
|---|---|---|
| NVIDIA RTX 40/50 | index `cu128` | `onnxruntime-gpu` (index CUDA-12) |
| NVIDIA cũ hơn | index `cu126` | `onnxruntime-gpu` (index CUDA-12) |
| Không GPU / Mac | `pip install torch` | `pip install onnxruntime` |

> ⚠️ torch và onnxruntime-gpu **phải cùng đời CUDA** (12.x) — lệch nhau là hai
> bên tranh cuDNN, nhận diện mặt hỏng âm thầm. Cứ theo lệnh check_env in ra.

---

## 4. Chạy app

| Cách | Lệnh | Dùng khi |
|---|---|---|
| **Nền** (khuyên dùng) | nhấp đúp `CHAY-NEN.bat` | dùng hằng ngày — xem qua dashboard, log ở `data/logs/` |
| Có cửa sổ | nhấp đúp `CHAY-CAMERA.bat` | demo, chỉnh vùng, debug |
| Dòng lệnh | `python main.py` (`--headless` = không cửa sổ) | dev |
| Tự chạy cùng Windows | nhấp `BAT-TU-DONG-CHAY.bat` một lần | máy giám sát 24/7 |
| Tắt bản chạy nền | `TAT-CAMERA.bat` hoặc nút ⏻ trên dashboard | |

Phím trên cửa sổ video: `Q` thoát · `O` ở nhà · `V` vắng nhà · `N` ngủ.

---

## 5. Dashboard web

Mở **http://localhost:8090** — điện thoại cùng WiFi: `http://<IP-máy>:8090`
(xem IP máy: `ipconfig`, dòng IPv4).

| Tab | Có gì |
|---|---|
| Trực tiếp | live mọi camera (MJPEG ~10fps), chấm REC khi đang ghi |
| Cảnh báo | ảnh cảnh báo mới nhất trước |
| Video | phát lại video sự kiện ngay trên trình duyệt |
| Người nhà | **📸 đăng ký người đang đứng trước cam (hiệu lực ngay)**, xem/xoá |
| Hệ thống | đổi chế độ, dung lượng, gửi tin thử, ⏻ tắt hệ thống |

Bảo mật: đặt `dashboard.password` trong config nếu WiFi có người ngoài dùng
chung. **Không mở port này ra internet** (xem mục Hạn chế).

---

## 6. Đăng ký người nhà

3 cách — người được đăng ký sẽ hiện **viền xanh + tên**, không bao giờ bị báo
"người lạ ở lì":

**Cách 1 — Trên dashboard, lúc app đang chạy (nhanh nhất):**
tab *Người nhà* → người đó đứng MỘT MÌNH trước cam → gõ tên → **📸 Chụp & đăng ký**
→ hiệu lực ngay, không cần khởi động lại. Bấm thêm 2-3 lần với các góc mặt.

**Cách 2 — Từ ảnh có sẵn:**
```powershell
python enroll.py TenNguoi --from "C:\duong\dan\thu-muc-anh"
```
Ảnh phải có **đúng 1 mặt** (ảnh chụp chung bị từ chối — tránh học nhầm).
App đang chạy? Bấm "🔄 Nạp lại từ thư mục" trên dashboard là nhận.

**Cách 3 — Quét bằng cửa sổ riêng:**
```powershell
python enroll.py TenNguoi --source http://IP-DIEN-THOAI:8080/video
```
SPACE chụp, Q xong.

Quản lý: `python enroll.py --list` · `python enroll.py --remove Ten`

Quy tắc tên: **không dấu, viết liền** (`ThienVan`, không phải `Thiên Vân`) —
OpenCV không vẽ được chữ có dấu lên hình.

---

## 7. Vùng giám sát

Vùng = khu vực bạn quan tâm (cửa ra vào, sân, két...). Người lạ ở **trong vùng**
quá `dwell.seconds` (10s) → báo khẩn + ghi hình. Không vẽ vùng nào → cả khung
hình được coi là một vùng.

```powershell
# vẽ trên hình camera điện thoại, lưu vào file vùng của cam đó:
python zone_editor.py --source http://IP:8080/video --out data/zones_dienthoai.json
# hoặc vẽ trên ảnh chụp sẵn (đỡ rung):
python zone_editor.py --image anh.jpg --out data/zones_dienthoai.json
```
Chuột trái = đỉnh · N = chốt vùng · U = lùi · D = xoá vùng · **S = lưu** · Q = thoát.
Vẽ xong **chạy lại app**. Đổi tên vùng: sửa chữ `"name"` trong file json.

Điểm xét trong/ngoài vùng (`zones.anchor`):
- `"center"` — giữa người: cho webcam/điện thoại kê bàn (chỉ thấy nửa người)
- `"bottom"` — vị trí chân: cho camera treo cao nhìn toàn thân

---

## 8. Camera

### Điện thoại cũ làm camera (0 đồng)
Cài app **IP Webcam** (Android) → Start server → lấy URL trên màn hình:
```yaml
cameras:
  - name: "dien-thoai"
    source: "http://192.168.1.191:8080/video"
```
Mẹo: cắm sạc; vào router đặt DHCP reservation để IP không đổi.

### Camera IP thật (RTSP)
```yaml
cameras:
  - name: "cong"
    source: "rtsp://user:pass@192.168.1.100:554/stream2"   # stream2 = bản nhẹ, hợp AI
    zones_file: "data/zones_cong.json"
```
| Hãng | path RTSP |
|---|---|
| Tapo | `/stream1` (nét) · `/stream2` (nhẹ) — tạo **Camera Account** trong app trước |
| Hikvision | `/Streaming/Channels/102` |
| Dahua/Imou | `/cam/realmonitor?channel=1&subtype=1` |

Kiểm tra cam có RTSP: `Test-NetConnection <IP> -Port 554`, thử link bằng VLC,
hoặc ONVIF Device Manager. Cam giá rẻ chỉ-dùng-app (Kabe View, V380...) thường
không có RTSP → không dùng được.

### Nhiều camera
Thêm nhiều mục vào `cameras:` — mỗi cam có thread đọc, vùng, đếm giờ, ghi hình
riêng; model AI dùng chung. Cảnh báo ghi rõ `[tên-cam]`. GPU tầm trung chạy
thoải mái 4–6 cam; máy CPU nên 1 cam.

---

## 9. Đăng ký bot Zalo

Nhận cảnh báo (kèm ảnh) thẳng vào Zalo — 5 phút, miễn phí:

**Bước 1 — Tạo bot (trên điện thoại):**
1. Mở app Zalo → ô tìm kiếm gõ **"Zalo Bot Manager"** → mở OA đó
2. Trong khung chat bấm **Create bot** (Tạo bot)
3. Tên bot **bắt buộc bắt đầu bằng "Bot"**, vd `Bot Camera Nha`
4. Tạo xong Zalo **nhắn cho bạn BOT TOKEN** — copy lại

**Bước 2 — Lấy chat_id + test (máy tính):**
```powershell
python zalo_setup.py DAN_TOKEN_VAO_DAY
```
Script kiểm tra token → bảo bạn **nhắn "hi" cho bot** trong Zalo → tự bắt
chat_id → gửi tin thử → **in sẵn khối config để dán**.

**Bước 3 — Dán vào `config.yaml`:**
```yaml
notify:
  channels: ["zalo"]           # thêm "ntfy"/"telegram" nếu muốn nhiều kênh
  zalo:
    token: "TOKEN_CUA_BAN"
    chat_id: "CHAT_ID_LAY_DUOC"
    send_photo: true
```

**Về ảnh trong tin Zalo:** Zalo Bot API không nhận upload file — chỉ nhận URL
công khai. App xử lý bằng cách đẩy ảnh lên **host tạm ntfy.sh** (link ngẫu nhiên
khó đoán, **tự xoá sau ~3 giờ**) rồi đưa link cho Zalo. Không cần cài app ntfy —
chỉ cần GIỮ dòng `ntfy.topic` trong config (địa chỉ kho tạm). Không muốn ảnh đi
qua dịch vụ ngoài: `send_photo: false` (Zalo chỉ nhận chữ; ảnh xem trên dashboard).

Kênh khác: **ntfy** (miễn phí, kèm ảnh trực tiếp, cần cài app) và **Telegram**
(tạo bot qua @BotFather) — cấu hình tương tự trong `notify`.

---

## 10. Model cháy

Repo **không kèm** file model (file nhị phân). 2 lựa chọn:

**Tự train từ D-Fire (khuyên — model xịn, mAP50 ~76%):**
```powershell
# cần token Kaggle miễn phí: kaggle.com -> Settings -> API -> Create New Token
# -> đặt kaggle.json vào %USERPROFILE%\.kaggle\
python train_fire.py --download    # tải 21k ảnh (~3GB) + train (~2-3h GPU) + tự thay models/fire.pt
```

**Hoặc dùng model cộng đồng:** tìm "YOLO fire smoke .pt" trên HuggingFace,
đặt vào `models/fire.pt` và `models/fire_small.pt`. Không có model → 2 skill
fire tự tắt, app vẫn chạy đầy đủ phần còn lại.

**Vòng sửa báo nhầm (càng dùng càng khôn):**
1. Mỗi lần báo cháy, ảnh GỐC tự lưu vào `data/fire_review/`
2. Ảnh nào là báo nhầm (nắng, đèn đỏ, tóc...) → chuyển vào `data/fire_review/false/`
3. `python train_fire.py --with-feedback` → model học "mấy cái này KHÔNG phải lửa"

---

## 11. Bảng config

| Mục | Ý nghĩa | Mặc định |
|---|---|---|
| `cameras[]` | danh sách camera (name/source/zones_file) | 1 cam từ mục `video` |
| `alert.mode` | chế độ khởi động: home/away/sleep | home |
| `alert.session_gap` | vắng bao lâu thì tính "lượt mới" | 300s |
| `alert.urgent_repeat` | sự kiện khẩn nhắc lại mỗi | 30s |
| `alert.sleep_hours` | khung giờ tự chuyển chế độ ngủ | [23, 6] |
| `dwell.seconds` | người lạ ở lì bao lâu thì báo | 10s |
| `zones.anchor` | điểm xét vùng: center/bottom | center |
| `recording.pre_roll` | ghi kèm bao nhiêu giây trước sự kiện | 5s |
| `recording.max_seconds` | trần độ dài 1 video | 60s |
| `notify.channels` | kênh báo: zalo/ntfy/telegram | — |
| `dashboard.port` / `password` | cổng web / mật khẩu | 8090 / trống |
| `storage.max_days` / `max_gb` | tự xoá file cũ | 14 ngày / 10GB |
| `skills.*.enabled/conf/interval` | bật tắt, độ nhạy, tần suất từng skill | — |

---

## 12. Hạn chế

**Đọc kỹ — biết hệ thống KHÔNG làm được gì quan trọng ngang với biết nó làm được gì.**

### An toàn tính mạng
- **KHÔNG thay thế thiết bị báo cháy vật lý.** Model chỉ thấy lửa/khói TRONG
  khung hình, khi đủ sáng, đủ gần. Cháy sau lưng camera, trong đêm tối, sau vật
  cản → mù. Nhà cần đầu báo khói thật.
- Phát hiện cháy có thể **báo nhầm** (nắng vàng, đèn đỏ, bếp) và **bỏ sót**
  (khói mỏng, lửa xa). Dùng vòng feedback (mục 10) để cải thiện dần.

### Nhận diện khuôn mặt
- Cần mặt **rõ, đủ sáng, không che**: đeo khẩu trang/kính râm/mũ sụp, ngược sáng,
  hoặc quay lưng ngay từ đầu (chưa từng thấy mặt trong lượt đó) → bị coi là người lạ.
- **Không có chống giả mạo (liveness)**: giơ ảnh in khuôn mặt người nhà trước
  camera có thể đánh lừa hệ thống. Đây là giới hạn của camera thường (Face ID
  điện thoại chống được nhờ cảm biến 3D).
- Anh em sinh đôi / người rất giống nhau có thể nhận nhầm.

### Theo dõi & vùng
- Track ID có thể **đổi** khi người bị che khuất lâu hoặc ra khỏi khung rồi quay
  lại → bộ đếm ở-lì tính lại từ đầu (thà sót hơn báo oan, nhưng vẫn là sót).
- Kẻ lạ đi qua vùng **nhanh hơn 10 giây** không kích hoạt dwell (chỉnh
  `dwell.seconds` nhỏ hơn nếu cần, đổi lại dễ báo nhầm người giao hàng).
- Vùng vẽ theo góc camera — **dời camera là phải vẽ lại**.

### Thông báo
- **Zalo Bot API không nhận upload ảnh** → ảnh đi qua host tạm ntfy.sh (link khó
  đoán, tự xoá ~3h). Khó tính về riêng tư → `send_photo: false`.
- Zalo Bot là nền tảng mới của Zalo — API có thể thay đổi; nếu ngưng hoạt động
  thì chuyển kênh `ntfy`/`telegram` (đổi 1 dòng config).
- Tin nhắn phụ thuộc internet — **mất mạng là mất cảnh báo từ xa** (video vẫn
  ghi trong máy).

### Hệ thống & bảo mật
- Dashboard dùng server dev của Flask + mật khẩu Basic Auth — **đủ cho mạng nhà,
  KHÔNG được mở port ra internet**. Muốn xem từ xa an toàn: dùng VPN (vd Tailscale).
- Nguồn HTTP của IP Webcam **không mã hoá** trong LAN; ai cùng WiFi + biết IP có
  thể xem stream điện thoại — đặt password trong app IP Webcam nếu cần.
- Máy tính tắt/ngủ = hệ thống dừng. Máy giám sát 24/7 nên tắt chế độ Sleep.
- Điện thoại làm camera: ngốn pin (phải cắm sạc), nóng máy khi chạy lâu, IP có
  thể đổi khi vào lại WiFi.
- Máy không GPU: nhận mặt chậm (~1-2s/lần quét dù đã tự giảm tải) — nên tăng
  `interval` các skill và dùng 1 camera.

### Pháp lý & riêng tư
- Camera quay được người khác (khách, hàng xóm, người giúp việc) — bạn có trách
  nhiệm dùng đúng pháp luật về quyền riêng tư nơi mình sống, đặc biệt khi chia
  sẻ ảnh/video ghi được.

---

## 13. Lỗi hay gặp

| Triệu chứng | Nguyên nhân & cách sửa |
|---|---|
| `Không mở được nguồn http://...` | Điện thoại chưa Start server, hoặc IP đổi → sửa `source` trong config |
| `torch.cuda.is_available() = False` | Cài nhầm torch bản CPU → chạy `python check_env.py` làm theo |
| Nhận mặt chậm ~6s/khung | onnxruntime rơi về CPU → cài đúng bản CUDA-12 (check_env) |
| Nhận mặt hỏng khi chạy chung YOLO | torch & onnxruntime lệch đời CUDA → cùng CUDA 12 |
| Không add được người từ ảnh | Đường dẫn có `\` cuối, tên có dấu/khoảng trắng, thư mục có dấu → xem mục 6 |
| Webcam đen | App khác đang chiếm cam (Zoom/Teams) |
| Video dashboard không phát | Thiếu `imageio-ffmpeg` → `pip install imageio-ffmpeg` (file cũ vẫn tải về xem được) |
| Train hết RAM (WinError 1455) | Để `workers=0` trong train_fire.py (mặc định đã vậy) |
| Báo "người lạ" chính mình | Chụp thêm 2-3 góc mặt (dashboard tab Người nhà, bấm 📸 nhiều lần) |
| Cửa sổ/hình giật lag | Tăng `interval` của face/fire/object trong config |

Chạy bộ test tự động: `python test_logic.py` (mọi dòng phải OK).

---

*Dự án cá nhân, theo triết lý: đơn giản, hiểu từ gốc, ít phụ thuộc.
Video và dữ liệu của bạn ở lại trong máy bạn. PRs/issues chào đón.*
