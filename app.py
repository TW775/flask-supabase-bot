# -*- coding: utf-8 -*-
from flask import Flask, request, render_template_string, redirect, url_for, session
import json, os, time
from datetime import datetime
from werkzeug.utils import secure_filename
from supabase import create_client, Client
from flask import jsonify
import pytz


# ✅ Render 专用配置（不使用 .env 文件）
app = Flask(__name__)
app.config["DEBUG"] = True  # 添加这一行
app.secret_key = os.getenv("FLASK_SECRET_KEY", "default-secret-key")
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "tw223322")
app.config['UPLOAD_FOLDER'] = '.'

MAX_TIMES = 3
INTERVAL_SECONDS = 6 * 3600

# 初始化 Supabase 客户端
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")

# 环境变量检查
print(f"环境变量检查:")
print(f"SUPABASE_URL: {SUPABASE_URL}")
print(f"SUPABASE_KEY: {SUPABASE_KEY and '*****' + SUPABASE_KEY[-4:] if SUPABASE_KEY else '未设置'}")
print(f"FLASK_SECRET_KEY: {app.secret_key and '*****' + app.secret_key[-4:]}")
print(f"ADMIN_PASSWORD: {ADMIN_PASSWORD and '*****' + ADMIN_PASSWORD[-4]}")

if not SUPABASE_URL or not SUPABASE_KEY:
    print("致命错误: SUPABASE_URL 或 SUPABASE_KEY 未设置!")
    exit(1)

supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

# ===== Supabase 工具函数 =====
def load_whitelist():
    response = supabase.table("whitelist").select("*").execute()
    return [item["id"] for item in response.data]

def load_user_status():
    response = supabase.table("user_status").select("*").execute()
    return {item["uid"]: {"count": item["count"], "last": item["last"], "index": item["index"]}
             for item in response.data}

def load_phone_groups():
    response = supabase.table("phone_groups").select("phones").execute()
    print("📦 Supabase 数据:", response.data)

    groups = []
    for item in response.data:
        phones = item.get("phones")
        if phones:  # 防止空值
            groups.append(phones)
    return groups

def load_upload_logs():
    logs = {}
    try:
        response = supabase.table("upload_logs").select("user_id, phone, upload_time").execute()
        for item in sorted(response.data, key=lambda x: x.get("upload_time", ""), reverse=True):
            uid = item.get("user_id")  # ← 注意字段名要改成 Supabase 中真实存在的
            if uid not in logs:
                logs[uid] = []

            # 获取上传时间，处理为字符串格式
            time_value = item.get("upload_time")
            if isinstance(time_value, datetime):
                time_str = time_value.strftime("%Y-%m-%d %H:%M:%S")
            else:
                time_str = str(time_value)

            logs[uid].append({
                "phone": item.get("phone"),
                "time": time_str
            })
    except Exception as e:
        print(f"❌ 加载上传记录失败: {e}")

    return logs


def load_marks():
    response = supabase.table("mark_status").select("*").execute()
    return {item["phone"]: item["status"] for item in response.data}

def load_blacklist():
    response = supabase.table("blacklist").select("phone").execute()
    return {item["phone"] for item in response.data}

def save_whitelist(ids):
    # 先清空表
    supabase.table("whitelist").delete().neq("id", "").execute()
    # 插入新数据
    if ids:
        data = [{"id": id_val} for id_val in ids]
        supabase.table("whitelist").insert(data).execute()

def save_user_status(uid, data):
    # 检查是否存在
    existing = supabase.table("user_status").select("*").eq("uid", uid).execute()
    if existing.data:
        # 更新
        supabase.table("user_status").update(data).eq("uid", uid).execute()
    else:
        # 插入
        data["uid"] = uid
        supabase.table("user_status").insert(data).execute()

def save_phone_groups(groups):
    # 清空表
    supabase.table("phone_groups").delete().neq("group_id", 0).execute()
    # 插入新分组
    data = [{"group_id": idx, "phones": group} for idx, group in enumerate(groups)]
    if data:
            supabase.table("phone_groups").insert(data).execute()

def add_upload_log(uid, phone):
    # 检查是否已经上传过
    existing = supabase.table("upload_logs").select("phone").eq("user_id", uid).eq("phone", phone).execute()
    if existing.data:
        print(f"已存在记录: {uid} - {phone}，跳过上传")
        return False  # 返回 False 表示重复

    tz = pytz.timezone("Asia/Shanghai")
    china_time = datetime.now(tz).strftime("%Y-%m-%d %H:%M:%S")

    data = {
        "user_id": uid,
        "phone": phone,
        "upload_time": china_time
    }
    supabase.table("upload_logs").insert(data).execute()
    return True  # 插入成功

def toggle_mark(phone):
    # 读取当前状态
    response = supabase.table("mark_status").select("*").eq("phone", phone).execute()
    data = response.data

    # 默认未标记
    current_status = "未领"
    if data:
        current_status = data[0]["status"]

    # 切换状态
    new_status = "已领" if current_status == "未领" else "未领"

    # 写入 mark_status 表
    if data:
        supabase.table("mark_status").update({"status": new_status}).eq("phone", phone).execute()
    else:
        supabase.table("mark_status").insert({"phone": phone, "status": new_status}).execute()

    # 黑名单操作
    if new_status == "已领":
        supabase.table("blacklist").insert({"phone": phone}).execute()
    else:
        supabase.table("blacklist").delete().eq("phone", phone).execute()

    return new_status


def save_blacklist(phones):
    # 清空表
    supabase.table("blacklist").delete().neq("phone", "").execute()
    # 插入新数据
    if phones:
        data = [{"phone": phone} for phone in phones]
        supabase.table("blacklist").insert(data).execute()

def blacklist_count():
    response = supabase.table("blacklist").select("phone", count="exact").execute()
    return response.count

def blacklist_preview(n=10):
    response = supabase.table("blacklist").select("phone").limit(n).execute()
    return [item["phone"] for item in response.data]

# ===== 路由处理 =====
@app.route("/mark", methods=["POST"])
def mark_phone():
    phone = request.form.get("phone")
    if not phone:
        return "No phone", 400
    new_status = toggle_mark(phone)
    return jsonify({"status": new_status})  # 👈 返回 JSON 状态


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
        return True
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
    supabase.table("user_status").delete().eq("uid", uid).execute()
    return redirect("/admin")

@app.route("/admin", methods=["GET", "POST"])
def admin():
    if not session.get("admin_logged_in"):
        return redirect("/login")

    logs = load_upload_logs()
    marks = load_marks()

    query_date = request.args.get("date", "")
    query_id = request.args.get("uid", "").strip()

    # 构建管理后台 HTML
    result_html = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <title>管理后台</title>
        <meta name="viewport" content="width=device-width, initial-scale=1">
        <style>
            body {{
                font-family: 'Segoe UI', sans-serif;
                background: linear-gradient(135deg, #eef2f3, #dfe9f3);
                margin: 0;
                padding: 0;
            }}
            .container {{
                max-width: 1000px;
                margin: 0 auto;
                padding: 20px;
            }}
            .header {{
                background-color: #2e89ff;
                color: white;
                padding: 20px;
                border-radius: 0 0 10px 10px;
                box-shadow: 0 4px 8px rgba(0,0,0,0.1);
                display: flex;
                justify-content: space-between;
                align-items: center;
            }}
            .card {{
                background: white;
                padding: 20px;
                margin: 30px 0;
                border-radius: 10px;
                box-shadow: 0 4px 16px rgba(0,0,0,0.08);
            }}
            table {{
                width: 100%;
                border-collapse: collapse;
                margin-top: 10px;
            }}
            th, td {{
                border: 1px solid #ddd;
                padding: 10px;
                text-align: left;
            }}
            th {{
                background-color: #f8f8f8;
                font-weight: 600;
            }}
            button {{
                padding: 8px 16px;
                background-color: #2e89ff;
                color: white;
                border: none;
                border-radius: 6px;
                cursor: pointer;
                transition: background 0.3s ease;
            }}
            button:hover {{
                background-color: #1a6fe0;
            }}
            input[type="file"], input[type="text"], input[type="date"] {{
                padding: 8px;
                border: 1px solid #ccc;
                border-radius: 6px;
                margin-right: 10px;
            }}
            a.logout {{
                color: white;
                text-decoration: none;
                font-size: 14px;
            }}
            h2 {{
                margin-top: 0;
                color: #333;
            }}
        </style>

        <script>
            async function markPhone(phone) {{
                const res = await fetch("/mark", {{
                    method: "POST",
                    headers: {{ "Content-Type": "application/x-www-form-urlencoded" }},
                    body: `phone=${{phone}}`
                }});

                if (res.ok) {{
                    const data = await res.json();
                    const isMarked = data.status === "已领";
                    document.getElementById(`status-${{phone}}`).innerText = isMarked ? "✅ 已领" : "❌ 未标记";
                    const btn = document.querySelector(`button[onclick="markPhone('${{phone}}')"]`);
                    if (btn) btn.innerText = isMarked ? "取消标记" : "标记已领";
                }}
            }}
        </script>
    </head>
    <body>
        <div class="header">
            <div><strong>📊 管理后台</strong></div>
            <div><a href="/logout" class="logout">🚪 退出</a></div>
        </div>
        <div class="container">
    """



    # 黑名单预览部分
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

    # 查询表单
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

    # 显示上传记录
    for uid, records in logs.items():
        # 应用查询筛选
        if query_id and uid != query_id:
            continue

        # 过滤日期匹配的记录
        filtered_records = []
        for record in records:
            # 将时间值转换为日期字符串
            time_value = record['time']
            if isinstance(time_value, str):
                # 如果是字符串，提取前10个字符 (YYYY-MM-DD)
                record_date = time_value[:10]
            else:
                # 如果是datetime对象，格式化为字符串
                record_date = time_value.strftime("%Y-%m-%d")

            # 应用日期筛选
            if not query_date or record_date == query_date:
                filtered_records.append(record)

        if not filtered_records:
            continue

        result_html += f"""
        <h2>用户 ID: {uid}</h2>
        <form method="POST" action="/reset_status" style="margin-bottom:10px;">
            <input type="hidden" name="uid" value="{uid}">
            <button type="submit" onclick="return confirm('确认重置此用户的领取记录？')">🔄 重置领取记录</button>
        </form>
        """

        result_html += "<table><tr><th>手机号</th><th>上传时间</th><th>状态</th><th>操作</th></tr>"
        for record in filtered_records:
            phone = record['phone']
            # 确保时间字符串正确显示
            time_str = record['time'] if isinstance(record['time'], str) else record['time'].strftime("%Y-%m-%d %H:%M:%S")
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

    # 文件上传区域
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

    # 处理上传文件请求（只保留一份）
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

def process_id_list(file_path):
    with open(file_path, "r") as f:
        ids = [line.strip() for line in f if line.strip()]
    save_whitelist(ids)

def process_phones(file_path):
    with open(file_path, "r") as f:
        phones = [line.strip() for line in f if line.strip()]
    blacklist = load_blacklist()
    phones = [p for p in phones if p not in blacklist]  # 跳过黑名单
    groups = []
    for i in range(0, len(phones), 10):
        groups.append(phones[i:i+10])
    save_phone_groups(groups)

# ===== 用户资料领取页面 =====
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

</body>
</html>
'''

@app.route("/", methods=["GET", "POST", "HEAD"])
def index():
    if request.method == "HEAD":
            return "", 200

    whitelist = load_whitelist()
    status = load_user_status()
    groups = load_phone_groups()
    upload_log = load_upload_logs()

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
                    # 从白名单中移除
                    new_whitelist = [id for id in whitelist if id != uid]
                    save_whitelist(new_whitelist)
                    error = "❌ 已达到最大领取次数，请联系管理员"
                elif now - record["last"] < INTERVAL_SECONDS:
                    wait_min = int((INTERVAL_SECONDS - (now - record["last"])) / 60)
                    error = f"⏱ 请在 {wait_min} 分钟后再领取"
                else:
                    for i, group in enumerate(groups):
                        if i not in used_index:
                            phones = group
                            new_status = {
                                "count": record["count"] + 1,
                                "last": now,
                                "index": i
                            }
                            save_user_status(uid, new_status)
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

                # 检查用户状态以确定分配的组
                user_status = status.get(uid, {})
                if "index" not in user_status:
                    upload_msg = "❌ 您尚未领取任何资料"
                else:
                    group_index = user_status["index"]
                    assigned_group = groups[group_index] if group_index < len(groups) else []

                    # 验证上传的手机号是否在分配的组中
                    invalid_phones = [p for p in all_phones if p not in assigned_group]

                    if invalid_phones:
                        upload_msg = f"❌ 以下号码不在您的分配组中: {', '.join(invalid_phones[:3])}{'...' if len(invalid_phones) > 3 else ''}"
                    else:
                        # 添加上传记录
                        for phone in all_phones:
                            add_upload_log(uid, phone)
                        upload_msg = f"✅ 成功上传 {len(all_phones)} 条资料"
                        upload_success = True

    return render_template_string(
        HTML_TEMPLATE,
        phones=phones,
        error=error,
        upload_msg=upload_msg,
        upload_success=upload_success
    )

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port)