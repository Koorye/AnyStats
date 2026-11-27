"""首页与 /submit 登记页（文案全部来自 config.yaml）。"""

import html

from .config import settings
from .countries import COUNTRY_NAMES

_COMMON = ["CN", "US", "GB", "DE", "FR", "JP", "KR", "SG", "IN", "CA", "AU", "RU", "BR"]


def _country_options() -> str:
    codes = [c for c in _COMMON if c in COUNTRY_NAMES]
    codes += [c for c in COUNTRY_NAMES if c not in codes]
    return "".join(
        f'<option value="{code}">{html.escape(COUNTRY_NAMES[code])}</option>'
        for code in codes
    )


def _page(title: str, body: str) -> str:
    return f"""<!doctype html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{html.escape(title)}</title>
<style>
  * {{ box-sizing: border-box; }}
  body {{ font-family: system-ui, -apple-system, "PingFang SC", "Microsoft YaHei", sans-serif;
         background: #f5f6f8; margin: 0; padding: 24px 12px; color: #222; }}
  .card {{ max-width: 560px; margin: 0 auto; background: #fff; border-radius: 12px;
          padding: 30px 28px; box-shadow: 0 2px 14px rgba(0,0,0,.07); }}
  h1 {{ font-size: 22px; margin: 0 0 6px; }}
  .sub {{ color: #666; font-size: 13.5px; margin: 0 0 18px; line-height: 1.7; }}
  .links {{ list-style: none; padding: 0; margin: 0; }}
  .links li {{ margin: 10px 0; }}
  .links a {{ display: block; padding: 12px 14px; border: 1px solid #e3e8f0; border-radius: 8px;
             color: #2456e6; text-decoration: none; font-size: 14px; }}
  .links a:hover {{ background: #f3f6ff; }}
  .muted {{ color: #888; font-size: 12px; }}
</style>
</head>
<body>
{body}
</body>
</html>"""


def index_html() -> str:
    body = f"""
<div class="card">
  <h1>{html.escape(settings.SITE_TITLE)}</h1>
  <p class="sub">{html.escape(settings.SITE_SUBTITLE)}<br>{html.escape(settings.SITE_DESCRIPTION)}</p>
  <ul class="links">
    <li><a href="/submit">使用登记表单</a></li>
    <li><a href="/dashboard">统计面板</a></li>
    <li><a href="/docs">API 文档（Swagger）</a></li>
    <li><a href="/api/v1/stats/summary">统计摘要 JSON</a></li>
    <li><a href="/healthz">健康检查</a></li>
  </ul>
  <p class="muted">{html.escape(settings.FOOTER)}</p>
</div>"""
    return _page(settings.SITE_TITLE, body)


def submit_html() -> str:
    license_html = ""
    if settings.SUBMIT_LICENSE_TEXT:
        license_html = f"""
    <div class="license">
      <input type="checkbox" id="license">
      <span>{html.escape(settings.SUBMIT_LICENSE_TEXT)}</span>
    </div>"""
    body = f"""
<div class="card">
  <h1>{html.escape(settings.SUBMIT_TITLE)}</h1>
  <p class="sub">{html.escape(settings.SUBMIT_DESCRIPTION)}</p>
  <form id="f" novalidate>
    <label>姓名 / 昵称 <span class="req">*</span>
      <input type="text" name="name" maxlength="100" required></label>
    <label>国家 / 地区 <span class="req">*</span>
      <select name="country" required>
        <option value="">请选择</option>
        __COUNTRY_OPTIONS__
      </select></label>
    <label>机构类型 <span class="req">*</span>
      <select name="affiliation_type" required>
        <option value="">请选择</option>
        <option value="university">高校</option>
        <option value="institute">科研院所</option>
        <option value="company">企业</option>
        <option value="personal">个人</option>
        <option value="other">其他</option>
      </select></label>
    <label>单位 <span class="req">*</span>
      <input type="text" name="organization" maxlength="200" required
             placeholder="{html.escape(settings.SUBMIT_ORG_EXAMPLE)}"></label>
    <label>补充说明
      <textarea name="info" maxlength="500"
                placeholder="选填，如具体研究方向、项目名称等"></textarea></label>
    <label>邮箱
      <input type="email" name="email" placeholder="选填，用于接收项目更新通知"></label>
    <div class="hp"><input type="text" name="website" tabindex="-1" autocomplete="off"></div>
    {license_html}
    <button type="submit" id="btn">提交登记</button>
    <div class="msg" id="msg"></div>
  </form>
</div>
<style>
  label {{ display: block; font-size: 14px; margin: 14px 0 0; }}
  .req {{ color: #d33; }}
  input[type=text], input[type=email], select, textarea {{
      width: 100%; margin-top: 6px; padding: 9px 10px;
      border: 1px solid #ccc; border-radius: 6px; font-size: 14px; background: #fff; }}
  textarea {{ min-height: 64px; resize: vertical; }}
  .license {{ display: flex; gap: 8px; align-items: flex-start; font-size: 13px; margin-top: 18px; }}
  .license input {{ margin-top: 2px; }}
  button {{ width: 100%; margin-top: 18px; padding: 11px; border: 0; border-radius: 6px;
           background: #2456e6; color: #fff; font-size: 15px; cursor: pointer; }}
  button:disabled {{ background: #9db1e8; }}
  .msg {{ margin-top: 14px; padding: 10px 12px; border-radius: 6px; font-size: 13px; display: none; }}
  .msg.err {{ background: #fdecec; color: #b42318; display: block; }}
  .msg.okmsg {{ background: #e8f7ee; color: #1a7f37; display: block; }}
  .hp {{ position: absolute; left: -9999px; }}
</style>
<script>
var form = document.getElementById('f');
var msg = document.getElementById('msg');
var btn = document.getElementById('btn');

function show(kind, text) {{
  msg.className = 'msg ' + kind;
  msg.textContent = text;
}}

function errMsg(j) {{
  if (!j) return '提交失败，请检查填写内容';
  if (j.message) {{
    var errors = (j.data && j.data.errors) || null;
    if (errors && errors.length) {{
      return errors.map(function (d) {{
        var loc = (d.loc || []).filter(function (x) {{ return x !== 'body'; }}).join('.');
        return loc ? loc + '：' + d.msg : d.msg;
      }}).join('；');
    }}
    return j.message;
  }}
  if (!j.detail) return '提交失败，请检查填写内容';
  if (typeof j.detail === 'string') return j.detail;
  return j.detail.map(function (d) {{
    var loc = (d.loc || []).filter(function (x) {{ return x !== 'body'; }}).join('.');
    return loc ? loc + '：' + d.msg : d.msg;
  }}).join('；');
}}

form.addEventListener('submit', function (e) {{
  e.preventDefault();
  msg.className = 'msg';
  var license = document.getElementById('license');
  if (license && !license.checked) {{
    show('err', '请先勾选同意条款');
    return;
  }}
  var f = new FormData(form);
  var data = {{
    name: (f.get('name') || '').trim(),
    country: f.get('country') || '',
    affiliation_type: f.get('affiliation_type') || '',
    organization: (f.get('organization') || '').trim()
  }};
  var info = (f.get('info') || '').trim();
  if (info) data.info = info;
  var email = (f.get('email') || '').trim();
  if (email) data.email = email;
  var website = f.get('website');
  if (website) data.website = website;

  btn.disabled = true;
  fetch('/api/v1/submissions', {{
    method: 'POST',
    headers: {{ 'Content-Type': 'application/json' }},
    body: JSON.stringify(data)
  }}).then(function (res) {{
    if (res.ok) {{
      show('okmsg', '提交成功，感谢登记！');
      form.reset();
    }} else {{
      res.json().then(function (j) {{ show('err', errMsg(j)); }}, function () {{
        show('err', '提交失败，请稍后重试');
      }});
    }}
  }}).catch(function () {{
    show('err', '网络错误，请稍后重试');
  }}).finally(function () {{ btn.disabled = false; }});
}});
</script>"""
    return _page(settings.SUBMIT_TITLE, body).replace("__COUNTRY_OPTIONS__", _country_options())
