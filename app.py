# -*- coding: utf-8 -*-
from flask import Flask, request, render_template_string, redirect, url_for, session
import json, os, time
from datetime import datetime
from werkzeug.utils import secure_filename

app = Flask(__name__)
app.secret_key = "a8b7c6-secret-key-abc"
ADMIN_PASSWORD = "tw223322"
app.config['UPLOAD_FOLDER'] = '.'

MAX_TIMES = 3
INTERVAL_SECONDS = 6 * 3600

WHITELIST_FILE = "id_whitelist.json"
STATUS_FILE = "user_status.json"
GROUP_FILE = "phone_groups.json"
UPLOAD_LOG = "upload_logs.json"
MARK_FILE = "mark_status.json"
BLACKLIST_FILE = "blacklist.json"


# ===== 工具函数 =====
def load_json(file):
    if os.path.exists(file):
        with open(file, "r") as f:
            return json.load(f)
    return {}

def load_blacklist():
    return set(load_json(BLACKLIST_FILE))

def save_blacklist(blacklist):
    save_json(BLACKLIST_FILE, list(blacklist))

def save_json(file, data):
    with open(file, "w") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def load_blacklist():
    return set(load_json(BLACKLIST_FILE))

def blacklist_count():
    return len(load_blacklist())

def blacklist_preview(n=10):
    return list(load_blacklist())[:n]

def load_marks():
    return load_json(MARK_FILE)

def save_marks(data):
    save_json(MARK_FILE, data)

def toggle_mark(phone):
    marked = load_marks()
    if phone in marked:
        marked[phone] = not marked[phone]
    else:
        marked[phone] = True
    save_marks(marked)
    return marked[phone]

def process_id_list(file_path):
    with open(file_path, "r") as f:
        ids = [line.strip() for line in f if line.strip()]
    save_json(WHITELIST_FILE, ids)

def process_phones(file_path):
    with open(file_path, "r") as f:
        phones = [line.strip() for line in f if line.strip()]
    blacklist = load_blacklist()
    phones = [p for p in phones if p not in blacklist]  # ❗跳过黑名单
    groups = []
    for i in range(0, len(phones), 10):
        groups.append(phones[i:i+10])
    save_json(GROUP_FILE, groups)


@app.route("/mark", methods=["POST"])
def mark_phone():
    phone = request.form.get("phone")
    if not phone:
        return "No phone", 400
    new_status = toggle_mark(phone)
    return "✅ 已标记" if new_status else "❌ 已取消"

@app.route("/export_marked")
def export_marked():
    marked = load_marks()
    marked_phones = [phone for phone, status in marked.items() if status]

    # 保存为 TXT 文件
    with open("marked_phones.txt", "w") as f:
        for phone in marked_phones:
            f.write(phone + "\n")

    # 加入黑名单
    blacklist = load_blacklist()
    blacklist.update(marked_phones)
    save_blacklist(blacklist)

    return "\n".join(marked_phones), 200, {
        'Content-Type': 'text/plain',
        'Content-Disposition': 'attachment; filename=marked_phones.txt'
    }


@app.route("/login", methods=["GET", "POST"])
def login():
    message = ""
    if request.method == "POST":
        pwd = request.form.get("password", "")
        if pwd == ADMIN_PASSWORD:
            session["admin_logged_in"] = True
            return redirect("/admin")
        else:
            message = "❌ 密码错误，请重试"

    return f'''
    <h2>🔐 管理后台登录</h2>
    <form method="POST">
        <input type="password" name="password" placeholder="请输入密码" required>
        <button type="submit">登录</button>
    </form>
    <p style="color:red;">{message}</p>
    '''

@app.route("/logout")
def logout():
    session.pop("admin_logged_in", None)
    return redirect("/login")

def is_date_match(record_time, target_date):
            if not target_date:
                return True  # 不筛选
            try:
                dt = datetime.strptime(record_time, "%Y-%m-%d %H:%M:%S")
                return dt.strftime("%Y-%m-%d") == target_date
            except:
                return False

@app.route("/reset_status", methods=["POST"])
def reset_status():
    if not session.get("admin_logged_in"):
        return "未授权", 403
    uid = request.form.get("uid", "").strip()
    if not uid:
        return "无效 ID", 400
    status = load_json(STATUS_FILE)
    if uid in status:
        del status[uid]
        save_json(STATUS_FILE, status)
    return redirect("/admin")

@app.route("/admin", methods=["GET", "POST"])
def admin():
    if not session.get("admin_logged_in"):
        return redirect("/login")

    logs = load_json(UPLOAD_LOG)
    marks = load_marks()

    query_date = request.args.get("date", "")
    query_id = request.args.get("uid", "").strip()




    result_html = """
    <!DOCTYPE html>
    <html>
    <head>
        <title>管理后台</title>
        <meta name="viewport" content="width=device-width, initial-scale=1">
        <style>
            body { font-family: 'Segoe UI', sans-serif; background-color: #f5f7fa; padding: 20px; margin: 0; }
            .header { background-color: #2e89ff; color: white; padding: 15px 20px; display: flex; justify-content: space-between; align-items: center; }
            .card { background: white; padding: 20px; margin: 20px auto; border-radius: 10px; max-width: 800px; box-shadow: 0 0 8px rgba(0,0,0,0.05); }
            table { width: 100%; border-collapse: collapse; margin-top: 10px; }
            th, td { border: 1px solid #ccc; padding: 8px; text-align: left; }
            th { background: #f0f0f0; }
            h2 { margin-top: 30px; color: #333; }
            input[type="file"] { margin: 10px 0; }
            button { padding: 8px 20px; background-color: #2e89ff; color: white; border: none; border-radius: 6px; cursor: pointer; }
            button:hover { background-color: #256edb; }
            a.logout { color: white; text-decoration: none; font-size: 14px; }
        </style>
        <script>
            async function markPhone(phone) {
                const res = await fetch("/mark", {
                    method: "POST",
                    headers: {"Content-Type": "application/x-www-form-urlencoded"},
                    body: `phone=${phone}`
                });
                if (res.ok) location.reload();
            }
        </script>
    </head>
    <body>
    <div class="header">
        <div><strong>📊 管理后台</strong></div>
        <div><a href="/logout" class="logout">🚪 退出</a></div>
    </div>

    <div class="card">
        <a href="/export_marked" target="_blank">
            <button>📥 导出所有已标记为已领的手机号</button>
        </a>
    </div>
    """

    result_html += f"""
        <div class="card">
            <p>共有 <strong>{blacklist_count()}</strong> 个手机号已被拉黑。</p>
            <div id="blacklist-preview">
                <ul style="font-size: 13px; margin-top: 5px; display: none;" id="blacklist-items">
                    {''.join(f'<li>{p}</li>' for p in blacklist_preview(10))}
                </ul>
                <button onclick="toggleBlacklist()" style="margin-top: 5px;">🔽 展开预览</button>
            </div>
        </div>

        <script>
            function toggleBlacklist() {{
                const list = document.getElementById("blacklist-items");
                const btn = event.target;
                if (list.style.display === "none") {{
                    list.style.display = "block";
                    btn.innerText = "🔼 收起预览";
                }} else {{
                    list.style.display = "none";
                    btn.innerText = "🔽 展开预览";
                }}
            }}
        </script>
        """

    result_html += f"""
        <div class="card">
            <form method="GET" style="display: flex; flex-wrap: wrap; align-items: center; gap: 15px; margin-bottom: 20px;">
                <div>
                    <label for="date">📆 上传日期：</label>
                    <input type="date" name="date" value="{query_date}">
                </div>
                <div>
                    <label for="uid">🔍 用户 ID：</label>
                    <input type="text" name="uid" placeholder="请输入用户 ID" value="{query_id}">
                </div>
                <div>
                    <button type="submit">查找</button>
                </div>
            </form>

            <div style="max-height: 300px; overflow-y: auto; border: 1px solid #ddd; padding: 10px;">
    """


    # 按上传记录中的时间排序，并按日期筛选
    for uid, records in sorted(logs.items(), key=lambda x: max(r["time"] for r in x[1]), reverse=True):
        filtered = [r for r in records if is_date_match(r["time"], query_date)]
        if not filtered:
            continue

        result_html += f"""
            <h2>用户 ID: {uid}</h2>
            <form method="POST" action="/reset_status" style="margin-bottom:10px;">
                <input type="hidden" name="uid" value="{uid}">
                <button type="submit" onclick="return confirm('确认重置此用户的领取记录？')">🔄 重置领取记录</button>
            </form>
            """

        result_html += "<table><tr><th>手机号</th><th>上传时间</th><th>状态</th><th>操作</th></tr>"
        for record in sorted(filtered, key=lambda r: r["time"], reverse=True):
            phone = record['phone']
            time_str = record['time']
            is_marked = marks.get(phone, False)
            status = "✅ 已领" if is_marked else "❌ 未标记"
            btn_text = "取消标记" if is_marked else "标记已领"
            result_html += f"""
            <tr>
                <td>{phone}</td>
                <td>{time_str}</td>
                <td id='status-{phone}'>{status}</td>
                <td><button onclick="markPhone('{phone}')">{btn_text}</button></td>
            </tr>
            """
        result_html += "</table>"


    result_html += "</div></div>"  # 结束滚动区域和上传记录卡片

    # === 添加上传功能区域 ===
    result_html += """
    <div class="card">
        <h2>📤 上传新手机号库 (phones.txt)</h2>
        <form method="POST" enctype="multipart/form-data">
            <input type="file" name="phones" accept=".txt" required><br>
            <button type="submit" name="upload_type" value="phones">上传手机号</button>
        </form>
    </div>

    <div class="card">
        <h2>📤 上传新白名单 (id_list.txt)</h2>
        <form method="POST" enctype="multipart/form-data">
            <input type="file" name="idlist" accept=".txt" required><br>
            <button type="submit" name="upload_type" value="idlist">上传白名单</button>
        </form>
    </div>

    </body>
    </html>
    """

    # === 处理上传文件请求 ===
    if request.method == "POST":
        ftype = request.form.get("upload_type")
        if ftype == "phones" and "phones" in request.files:
            file = request.files["phones"]
            path = os.path.join(app.config['UPLOAD_FOLDER'], secure_filename("phones.txt"))
            file.save(path)
            process_phones(path)
        elif ftype == "idlist" and "idlist" in request.files:
            file = request.files["idlist"]
            path = os.path.join(app.config['UPLOAD_FOLDER'], secure_filename("id_list.txt"))
            file.save(path)
            process_id_list(path)
        return redirect(url_for("admin"))

    return result_html


# ===== 用户资料领取页面 HTML 模板 =====
HTML_TEMPLATE = '''
<!DOCTYPE html>
<html>
<head>
    <title>资料领取</title>
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <style>
        body { font-family:sans-serif;background:#f0f2f5;display:flex;align-items:center;justify-content:center;flex-direction:column;padding:30px; }
        .card { background:white;padding:30px;border-radius:10px;box-shadow:0 0 10px rgba(0,0,0,0.1);width:90%;max-width:500px;margin-bottom:30px; }
        input, textarea { padding:10px;width:90%;margin:10px 0;font-size:16px;border:1px solid #ccc;border-radius:8px; }
        button { padding:12px 24px;background:#2e89ff;color:white;border:none;border-radius:8px;font-size:16px;cursor:pointer; }
        button:hover { background:#1a6fe0; }
        .error { color:red;margin-top:10px; }
        .success { color:green;margin-top:10px; }
        ul { list-style:none;padding:0;margin-top:10px;text-align:left; }
        li { padding:5px 0;border-bottom:1px dashed #ddd; }
        textarea { height:80px; resize: vertical; }
    </style>
</head>
<!-- ✅ 弹窗结构 -->
<div id="popup" style="display:none; position:fixed; top:0; left:0; width:100%; height:100%; background:rgba(0,0,0,0.4); z-index:999;">
  <div style="background:white; max-width:400px; margin:100px auto; padding:20px; border-radius:10px; box-shadow:0 0 10px rgba(0,0,0,0.3); position:relative;">
    <h3 style="color:green;">✅ 以下是你的资料</h3>
    <pre id="popup-content" style="font-size:16px; white-space:pre-wrap; max-height:300px; overflow-y:auto;">{% for phone in phones %}{{ phone }}{% if not loop.last %}
{% endif %}{% endfor %}</pre>
    <div style="text-align:right; margin-top:10px;">
      <button onclick="copyPopupText()">📋 一键复制</button>
      <button onclick="closePopup()" style="margin-left:10px;">❌ 关闭</button>
    </div>
  </div>
</div>

<script>
  function showPopup() {
    document.getElementById("popup").style.display = "block";
  }

  function closePopup() {
    document.getElementById("popup").style.display = "none";
  }

  function copyPopupText() {
    const content = document.getElementById("popup-content").innerText;
    navigator.clipboard.writeText(content).then(() => {
      alert("✅ 已复制到剪贴板");
    });
  }
</script>

<body>

    <div class="card">
        <h2>📥 资料领取</h2>
        <form method="POST">
            <input type="hidden" name="action" value="get">
            <input name="userid" placeholder="请输入您的 ID" required><br>
            <button type="submit">领取资料</button>
        </form>


        {% if error %}
            <div class="error">{{ error }}</div>
        {% elif phones %}
            <div class="success">✅ 领取成功，点击查看资料：</div>
            <button onclick="showPopup()">📋 查看资料</button>
        {% endif %}
    </div>

    <div class="card">
        <h2>📤 上传领取成功的资料</h2>
        <form method="POST" action="/">
            <input type="hidden" name="action" value="upload">
            <input name="userid" placeholder="请输入您的 ID" required><br>
            <textarea name="phones" placeholder="粘贴你领取的手机号，每行一个" required></textarea><br>
            <button type="submit">上传资料</button>
        </form>

        {% if upload_msg %}
            <div class="{{ 'success' if upload_success else 'error' }}">{{ upload_msg }}</div>
        {% endif %}
    </div>

<script>
function copyPhones() {
    const area = document.getElementById("copyArea");
    area.select();
    document.execCommand("copy");
    alert("✅ 已复制到剪贴板");
}
</script>

</body>
</html>
'''

# ===== 资料领取逻辑 =====
@app.route("/", methods=["GET", "POST"])
def index():
    whitelist = load_json(WHITELIST_FILE)
    status = load_json(STATUS_FILE)
    groups = load_json(GROUP_FILE)
    upload_log = load_json(UPLOAD_LOG)

    phones = []
    error = ""
    upload_msg = ""
    upload_success = False
    used_index = [v["index"] for v in status.values() if "index" in v]

    if request.method == "POST":
        action = request.form.get("action")
        uid = request.form.get("userid", "").strip()
        now = time.time()

        if action == "get":
            if not uid:
                error = "请输入 ID"
            elif uid not in whitelist:
                error = "❌ 该 ID 不在名单内，请联系管理员"
            else:
                record = status.get(uid, {"count": 0, "last": 0})
                if record["count"] >= MAX_TIMES:
                    whitelist.remove(uid)
                    save_json(WHITELIST_FILE, whitelist)
                    error = "❌ 已达到最大领取次数，请联系管理员"
                elif now - record["last"] < INTERVAL_SECONDS:
                    wait_min = int((INTERVAL_SECONDS - (now - record["last"])) / 60)
                    error = f"⏱ 请在 {wait_min} 分钟后再领取"
                else:
                    for i, group in enumerate(groups):
                        if i not in used_index:
                            phones = group
                            status[uid] = {
                                "count": record["count"] + 1,
                                "last": now,
                                "index": i
                            }
                            save_json(STATUS_FILE, status)
                            break
                    else:
                        error = "❌ 资料已发放完，请联系管理员"

        elif action == "upload":
            raw_data = request.form.get("phones", "").strip()
            if not uid or not raw_data:
                upload_msg = "❌ ID 和资料不能为空"
            else:
                all_phones = [p.strip() for p in raw_data.splitlines() if p.strip()]
                now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                already_uploaded = set([log["phone"] for log in upload_log.get(uid, [])])
                valid_uploads = []
                for phone in all_phones:
                    found = False
                    latest_owner = None
                    latest_time = 0
                    for user_id, info in status.items():
                        index = info.get("index")
                        if index is None or index >= len(groups): continue
                        if phone in groups[index]:
                            if info.get("last", 0) > latest_time:
                                latest_owner = user_id
                                latest_time = info["last"]
                    if latest_owner == uid and phone not in already_uploaded:
                        valid_uploads.append(phone)
                    elif latest_owner and latest_owner != uid:
                        upload_msg = f"❌ 号码 {phone} 当前归属 {latest_owner}，你无法上传"
                        break
                    elif latest_owner is None:
                        upload_msg = f"❌ 号码 {phone} 不存在于任何分配组中"
                        break
                    elif phone in already_uploaded:
                        upload_msg = f"❌ 号码 {phone} 已上传过"
                        break

                if upload_msg == "" and valid_uploads:
                    logs = upload_log.get(uid, [])
                    for phone in valid_uploads:
                        logs.append({"phone": phone, "time": now_str})
                    upload_log[uid] = logs
                    save_json(UPLOAD_LOG, upload_log)
                    upload_msg = f"✅ 成功上传 {len(valid_uploads)} 条资料"
                    upload_success = True
                elif upload_msg == "":
                    upload_msg = "❌ 没有可上传的有效资料"

    return render_template_string(
        HTML_TEMPLATE,
        phones=phones,
        error=error,
        upload_msg=upload_msg,
        upload_success=upload_success
    )


if __name__ == "__main__":
    import os
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)

