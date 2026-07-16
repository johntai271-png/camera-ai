"""
dashboard.py — Giao diện web: xem camera + quản lý hệ thống từ trình duyệt.

Mở:  http://localhost:8090  (máy này)
     http://<IP-máy-này>:8090  (điện thoại CÙNG WiFi)

Có gì:
    - Trực tiếp : xem live mọi camera (MJPEG, không cần cài gì)
    - Cảnh báo  : lịch sử ảnh cảnh báo, mới nhất trước
    - Video     : phát lại video sự kiện ngay trong trình duyệt
    - Người nhà : xem/xoá người đã đăng ký
    - Hệ thống  : đổi chế độ Ở NHÀ/VẮNG/NGỦ, dung lượng, gửi tin thử, TẮT app

Bảo mật: đặt dashboard.password trong config nếu mạng WiFi có người lạ dùng chung.
Dashboard chỉ phục vụ trong mạng nội bộ — KHÔNG tự mở ra internet.
"""

from __future__ import annotations
import os
import threading
import time

import cv2
from flask import (Flask, Response, jsonify, request, send_from_directory,
                   abort)

from core.alert_manager import MODE_LABEL

# ------------------------------------------------------------------ HTML ----
PAGE = """<!doctype html>
<html lang="vi"><head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Camera AI</title>
<style>
  :root { --bg:#111418; --card:#1b2027; --line:#2a313b; --txt:#e8eaed;
          --dim:#9aa4b2; --acc:#4da3ff; --red:#ff5252; --green:#4caf50; }
  * { box-sizing:border-box; margin:0; }
  body { background:var(--bg); color:var(--txt);
         font-family:system-ui,Segoe UI,Roboto,sans-serif; }
  header { display:flex; flex-wrap:wrap; gap:8px; align-items:center;
           padding:10px 14px; border-bottom:1px solid var(--line);
           position:sticky; top:0; background:var(--bg); z-index:5; }
  header h1 { font-size:18px; margin-right:auto; }
  .mode-btn { padding:7px 14px; border-radius:8px; border:1px solid var(--line);
              background:var(--card); color:var(--txt); cursor:pointer; font-size:14px; }
  .mode-btn.on { background:var(--acc); border-color:var(--acc); color:#fff; }
  .mode-btn.on.danger { background:var(--red); border-color:var(--red); }
  nav { display:flex; gap:4px; padding:8px 14px; border-bottom:1px solid var(--line);
        overflow-x:auto; }
  nav button { padding:8px 14px; background:none; border:none; color:var(--dim);
               cursor:pointer; font-size:15px; border-bottom:2px solid transparent; }
  nav button.on { color:var(--txt); border-color:var(--acc); }
  main { padding:14px; max-width:1100px; margin:0 auto; }
  .tab { display:none; } .tab.on { display:block; }
  .grid { display:grid; gap:12px; grid-template-columns:repeat(auto-fit,minmax(320px,1fr)); }
  .card { background:var(--card); border:1px solid var(--line); border-radius:12px;
          overflow:hidden; }
  .card img, .card video { width:100%; display:block; }
  .card .cap { padding:8px 10px; font-size:13px; color:var(--dim);
               display:flex; justify-content:space-between; }
  .rec { color:var(--red); font-weight:600; }
  button.act { padding:8px 14px; border-radius:8px; border:1px solid var(--line);
               background:var(--card); color:var(--txt); cursor:pointer; }
  button.danger { color:var(--red); border-color:var(--red); }
  input, select { padding:8px 10px; border-radius:8px; border:1px solid var(--line);
                  background:var(--bg); color:var(--txt); font-size:14px; }
  table { width:100%; border-collapse:collapse; }
  td, th { padding:8px 10px; border-bottom:1px solid var(--line); text-align:left;
           font-size:14px; }
  .muted { color:var(--dim); font-size:13px; }
  #toast { position:fixed; bottom:16px; left:50%; transform:translateX(-50%);
           background:var(--acc); color:#fff; padding:10px 18px; border-radius:10px;
           display:none; z-index:9; }
</style></head>
<body>
<header>
  <h1>📷 Camera AI</h1>
  <button class="mode-btn" id="m-home"  onclick="setMode('home')">🏠 Ở nhà</button>
  <button class="mode-btn danger" id="m-away"  onclick="setMode('away')">🚪 Vắng nhà</button>
  <button class="mode-btn danger" id="m-sleep" onclick="setMode('sleep')">🌙 Ngủ</button>
</header>
<nav>
  <button class="on" onclick="tab(event,'live')">Trực tiếp</button>
  <button onclick="tab(event,'alerts')">Cảnh báo</button>
  <button onclick="tab(event,'videos')">Video</button>
  <button onclick="tab(event,'people')">Người nhà</button>
  <button onclick="tab(event,'system')">Hệ thống</button>
</nav>
<main>
  <div class="tab on" id="live"><div class="grid" id="cams"></div></div>
  <div class="tab" id="alerts"><div class="grid" id="alert-list"></div></div>
  <div class="tab" id="videos"><div class="grid" id="video-list"></div></div>
  <div class="tab" id="people">
    <div class="card" style="padding:14px; margin-bottom:14px">
      <b>📸 Đăng ký người đang đứng trước camera</b>
      <p class="muted" style="margin:6px 0 10px">Người đó đứng MỘT MÌNH trong khung,
        nhìn vào camera → gõ tên (không dấu, viết liền) → bấm nút.
        Bấm thêm 2-3 lần với các góc mặt khác nhau càng chuẩn. Hiệu lực NGAY.</p>
      <p style="display:flex; gap:8px; flex-wrap:wrap">
        <input id="en-name" placeholder="Ten (vd: ThienVan)">
        <select id="en-cam"></select>
        <button class="act" onclick="enrollNow()">📸 Chụp &amp; đăng ký</button>
        <button class="act" onclick="reloadFaces()">🔄 Nạp lại từ thư mục</button>
      </p>
    </div>
    <table id="people-table"><tr><th>Tên</th><th>Số ảnh</th><th></th></tr></table>
    <p class="muted" style="margin-top:10px">Cách khác (từ ảnh có sẵn):
      <code>python enroll.py Ten --from thu-muc-anh</code> rồi bấm "Nạp lại từ thư mục" —
      không cần khởi động lại.</p>
  </div>
  <div class="tab" id="system">
    <div class="card" style="padding:14px">
      <p id="sys-info" class="muted">Đang tải...</p>
      <table id="storage-table"></table>
      <p style="margin-top:14px; display:flex; gap:10px; flex-wrap:wrap">
        <button class="act" onclick="testAlert()">📲 Gửi tin nhắn thử</button>
        <button class="act danger" onclick="quitApp()">⏻ Tắt hệ thống</button>
      </p>
    </div>
  </div>
</main>
<div id="toast"></div>
<script>
function toast(m){ const t=document.getElementById('toast'); t.textContent=m;
  t.style.display='block'; setTimeout(()=>t.style.display='none', 2500); }
function tab(e,id){ document.querySelectorAll('.tab').forEach(x=>x.classList.remove('on'));
  document.querySelectorAll('nav button').forEach(x=>x.classList.remove('on'));
  document.getElementById(id).classList.add('on'); e.target.classList.add('on');
  if(id==='alerts') loadAlerts(); if(id==='videos') loadVideos();
  if(id==='people') loadPeople(); if(id==='system') loadSystem(); }
async function setMode(m){ await fetch('/api/mode/'+m,{method:'POST'});
  toast('Đã chuyển chế độ'); refresh(); }
async function refresh(){
  const s = await (await fetch('/api/status')).json();
  ['home','away','sleep'].forEach(m=>document.getElementById('m-'+m)
    .classList.toggle('on', s.mode===m));
  const c = document.getElementById('cams');
  if(c.children.length !== s.cameras.length){
    c.innerHTML = s.cameras.map(cam =>
      `<div class="card"><img src="/stream/${cam.name}">
       <div class="cap"><span>📹 ${cam.name}</span>
       <span id="fps-${cam.name}"></span></div></div>`).join('');
  }
  s.cameras.forEach(cam=>{
    const el=document.getElementById('fps-'+cam.name);
    if(el) el.innerHTML = (cam.recording?'<span class="rec">● REC </span>':'')
      + cam.fps.toFixed(0)+' fps';});
  const sel = document.getElementById('en-cam');
  if(sel && sel.children.length !== s.cameras.length)
    sel.innerHTML = s.cameras.map(c=>`<option value="${c.name}">📹 ${c.name}</option>`).join('');
}
async function loadAlerts(){
  const items = await (await fetch('/api/alerts')).json();
  document.getElementById('alert-list').innerHTML = items.length ? items.map(a=>
    `<div class="card"><img src="/alerts/${a.file}" loading="lazy">
     <div class="cap"><span>${a.label}</span><span>${a.time}</span></div></div>`
   ).join('') : '<p class="muted">Chưa có cảnh báo nào.</p>';
}
async function loadVideos(){
  const items = await (await fetch('/api/recordings')).json();
  document.getElementById('video-list').innerHTML = items.length ? items.map(v=>
    `<div class="card"><video controls preload="none" src="/recordings/${v.file}"></video>
     <div class="cap"><span>${v.label}</span><span>${v.time} · ${v.mb} MB</span></div></div>`
   ).join('') : '<p class="muted">Chưa có video sự kiện nào.</p>';
}
async function loadPeople(){
  const items = await (await fetch('/api/people')).json();
  const t = document.getElementById('people-table');
  t.innerHTML = '<tr><th>Tên</th><th>Số ảnh</th><th></th></tr>' + items.map(p=>
    `<tr><td>${p.name}</td><td>${p.photos}</td>
     <td><button class="act danger" onclick="delPerson('${p.name}')">Xoá</button></td></tr>`
   ).join('');
}
async function delPerson(name){
  if(!confirm('Xoá "'+name+'"? Người này sẽ bị coi là NGƯỜI LẠ.')) return;
  await fetch('/api/people/'+encodeURIComponent(name), {method:'DELETE'});
  await fetch('/api/reload-faces', {method:'POST'});
  toast('Đã xoá — hiệu lực ngay'); loadPeople();
}
async function enrollNow(){
  const name = document.getElementById('en-name').value.trim();
  const cam  = document.getElementById('en-cam').value;
  if(!name){ toast('Nhập tên trước đã'); return; }
  const r = await (await fetch('/api/enroll', {method:'POST',
    headers:{'Content-Type':'application/json'},
    body: JSON.stringify({name: name, camera: cam})})).json();
  toast(r.msg); if(r.ok) loadPeople();
}
async function reloadFaces(){
  const r = await (await fetch('/api/reload-faces', {method:'POST'})).json();
  toast(r.msg); loadPeople();
}
async function loadSystem(){
  const s = await (await fetch('/api/status')).json();
  document.getElementById('sys-info').textContent =
    `Chế độ: ${s.mode_label} · ${s.cameras.length} camera · phần cứng: ${s.device}`;
  const st = document.getElementById('storage-table');
  st.innerHTML = '<tr><th>Thư mục</th><th>Số file</th><th>Dung lượng</th></tr>' +
    Object.entries(s.storage).map(([d,v]) =>
      `<tr><td>${d}</td><td>${v.files}</td><td>${v.mb} MB</td></tr>`).join('');
}
async function testAlert(){ await fetch('/api/test-alert',{method:'POST'});
  toast('Đã gửi — kiểm tra điện thoại!'); }
async function quitApp(){ if(!confirm('Tắt toàn bộ hệ thống camera?')) return;
  await fetch('/api/quit',{method:'POST'}); toast('Đang tắt...'); }
refresh(); setInterval(refresh, 3000);
</script>
</body></html>"""


# ------------------------------------------------------------ Flask app ----

def create_app(state) -> Flask:
    """state cần có: cameras (list Camera), alerts (AlertManager),
    cleaner (StorageCleaner), notifier, cfg (dict), quit_flag (Event), device (str)."""
    app = Flask("camera-ai")
    dcfg = state.cfg.get("dashboard", {})
    password = dcfg.get("password") or ""

    @app.before_request
    def _auth():
        if not password:
            return
        auth = request.authorization
        if auth is None or auth.password != password:
            return Response("Cần mật khẩu", 401,
                            {"WWW-Authenticate": 'Basic realm="camera-ai"'})

    def _cam(name):
        for c in state.cameras:
            if c.name == name:
                return c
        abort(404)

    # ---------- trang chính ----------
    @app.get("/")
    def index():
        return PAGE

    # ---------- live MJPEG ----------
    @app.get("/stream/<name>")
    def stream(name):
        cam = _cam(name)

        def gen():
            while not state.quit_flag.is_set():
                frame = cam.display
                if frame is None:
                    time.sleep(0.1)
                    continue
                ok, jpg = cv2.imencode(".jpg", frame,
                                       [cv2.IMWRITE_JPEG_QUALITY, 75])
                if ok:
                    yield (b"--frame\r\nContent-Type: image/jpeg\r\n\r\n"
                           + jpg.tobytes() + b"\r\n")
                time.sleep(0.1)   # ~10 fps cho web là mượt, đỡ tốn mạng

        return Response(gen(), mimetype="multipart/x-mixed-replace; boundary=frame")

    # ---------- API trạng thái ----------
    @app.get("/api/status")
    def status():
        now = time.time()
        mode = state.alerts.effective_mode(now)
        return jsonify({
            "mode": mode,
            "mode_label": MODE_LABEL.get(mode, mode),
            "device": state.device,
            "cameras": [{"name": c.name, "fps": round(c.fps, 1),
                         "recording": c.recorder.active} for c in state.cameras],
            "storage": state.cleaner.stats(),
        })

    @app.post("/api/mode/<mode>")
    def set_mode(mode):
        if mode not in MODE_LABEL:
            abort(400)
        state.alerts.set_mode(mode)
        return jsonify({"ok": True, "mode": mode})

    # ---------- cảnh báo & video ----------
    def _listing(dir_path, exts):
        items = []
        if os.path.isdir(dir_path):
            for f in os.listdir(dir_path):
                if not f.lower().endswith(exts):
                    continue
                p = os.path.join(dir_path, f)
                try:
                    st = os.stat(p)
                except OSError:
                    continue
                items.append({
                    "file": f,
                    "label": f.rsplit("_", 2)[0].replace("-", " "),
                    "time": time.strftime("%d/%m %H:%M", time.localtime(st.st_mtime)),
                    "mb": round(st.st_size / 1e6, 1),
                    "_m": st.st_mtime,
                })
        items.sort(key=lambda x: -x["_m"])
        for it in items:
            it.pop("_m")
        return items[:60]

    @app.get("/api/alerts")
    def alerts_list():
        return jsonify(_listing(state.cfg.get("alert", {}).get("save_dir", "data/alerts"),
                                (".jpg", ".jpeg", ".png")))

    @app.get("/alerts/<path:fname>")
    def alert_image(fname):
        return send_from_directory(
            os.path.abspath(state.cfg.get("alert", {}).get("save_dir", "data/alerts")),
            fname)

    @app.get("/api/recordings")
    def recordings_list():
        return jsonify(_listing(state.cfg.get("recording", {}).get("dir", "data/recordings"),
                                (".mp4",)))

    @app.get("/recordings/<path:fname>")
    def recording_file(fname):
        return send_from_directory(
            os.path.abspath(state.cfg.get("recording", {}).get("dir", "data/recordings")),
            fname, conditional=True)   # conditional=True: tua video được

    # ---------- người nhà ----------
    @app.get("/api/people")
    def people():
        faces_dir = state.cfg.get("skills", {}).get("face", {}).get(
            "faces_dir", "data/faces")
        out = []
        if os.path.isdir(faces_dir):
            for name in sorted(os.listdir(faces_dir)):
                pdir = os.path.join(faces_dir, name)
                if os.path.isdir(pdir):
                    n = len([f for f in os.listdir(pdir)
                             if f.lower().endswith((".jpg", ".jpeg", ".png"))])
                    out.append({"name": name, "photos": n})
        return jsonify(out)

    @app.delete("/api/people/<name>")
    def delete_person(name):
        import shutil
        faces_dir = state.cfg.get("skills", {}).get("face", {}).get(
            "faces_dir", "data/faces")
        pdir = os.path.join(faces_dir, name)
        # chống thoát thư mục kiểu ../..
        if not os.path.abspath(pdir).startswith(os.path.abspath(faces_dir)):
            abort(400)
        if not os.path.isdir(pdir):
            abort(404)
        shutil.rmtree(pdir)
        return jsonify({"ok": True})

    # ---------- đăng ký người NGAY khi camera đang chạy ----------
    def _face_skills():
        for c in state.cameras:
            for s in c.skills:
                if s.name == "face":
                    yield s

    def _reload_all_faces() -> int:
        n = 0
        for s in _face_skills():
            try:
                n = s.reload_known()
            except Exception as e:
                print(f"[dashboard] Lỗi nạp lại mặt: {e}")
        return n

    @app.post("/api/enroll")
    def enroll_live():
        data = request.get_json(force=True, silent=True) or {}
        name = (data.get("name") or "").strip()
        cam_name = data.get("camera") or ""
        if (not name or not name.isascii()
                or any(ch in name for ch in '\\/:*?"<>| ')):
            return jsonify({"ok": False,
                            "msg": "Tên phải là chữ KHÔNG DẤU, viết liền (vd: ThienVan)"}), 400
        cam = next((c for c in state.cameras if c.name == cam_name),
                   state.cameras[0] if state.cameras else None)
        if cam is None:
            return jsonify({"ok": False, "msg": "Không có camera nào"}), 400
        skill = next((s for s in cam.skills if s.name == "face"), None)
        if skill is None or skill.app is None:
            return jsonify({"ok": False, "msg": "Skill nhận diện mặt đang tắt"}), 400
        ok, frame = cam.grabber.latest()
        if not ok or frame is None:
            return jsonify({"ok": False, "msg": "Camera chưa có hình"}), 400
        faces = skill.app.get(frame)
        if len(faces) != 1:
            return jsonify({"ok": False,
                            "msg": f"Cần ĐÚNG 1 người trước camera (đang thấy {len(faces)} mặt)"}), 400

        faces_dir = state.cfg.get("skills", {}).get("face", {}).get(
            "faces_dir", "data/faces")
        pdir = os.path.join(faces_dir, name)
        os.makedirs(pdir, exist_ok=True)
        n = len([f for f in os.listdir(pdir)
                 if f.lower().endswith((".jpg", ".jpeg", ".png"))]) + 1
        cv2.imwrite(os.path.join(pdir, f"{n}.jpg"), frame)
        _reload_all_faces()   # hiệu lực NGAY, không cần khởi động lại
        return jsonify({"ok": True,
                        "msg": f"Đã đăng ký {name} (ảnh thứ {n}) — hiệu lực ngay! "
                               f"Chụp thêm vài góc mặt càng tốt."})

    @app.post("/api/reload-faces")
    def reload_faces():
        """Sau khi thêm ảnh bằng tay / enroll.py — nạp lại không cần restart."""
        n = _reload_all_faces()
        return jsonify({"ok": True, "msg": f"Đã nạp lại: {n} khuôn mặt"})

    # ---------- tiện ích ----------
    @app.post("/api/test-alert")
    def test_alert():
        if state.notifier:
            state.notifier.send("Camera AI", "Tin nhan thu tu dashboard 👋",
                                priority=3, tags=["wave"])
        return jsonify({"ok": True})

    @app.post("/api/quit")
    def quit_app():
        state.quit_flag.set()
        return jsonify({"ok": True})

    return app


def start_dashboard(state) -> None:
    """Chạy dashboard trong thread nền. Gọi 1 lần từ main.py."""
    dcfg = state.cfg.get("dashboard", {})
    if not dcfg.get("enabled", True):
        return
    host = dcfg.get("host", "0.0.0.0")
    port = int(dcfg.get("port", 8090))
    app = create_app(state)

    def run():
        # server nhỏ của Flask đủ cho mạng nội bộ vài người xem
        app.run(host=host, port=port, threaded=True, use_reloader=False)

    threading.Thread(target=run, daemon=True).start()
    print(f"[dashboard] Mở trình duyệt:  http://localhost:{port}"
          f"   (điện thoại cùng WiFi: http://<IP-máy-này>:{port})")
