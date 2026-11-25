"""统计面板页（/dashboard）。本地 Plotly，无 CDN 依赖；板块按启用的数据源自动显示。"""

import html

from .config import settings

_TEMPLATE = """<!doctype html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>__TITLE__ · 统计面板</title>
<meta name="description" content="__DESCRIPTION__">
<style>
  :root { --blue:#2456e6; --ink:#1f2733; --muted:#77808f; --line:#e6eaf2; --bg:#f4f6fa; }
  * { box-sizing: border-box; }
  body { margin:0; background:var(--bg); color:var(--ink);
         font-family: system-ui, -apple-system, "PingFang SC", "Microsoft YaHei", sans-serif; }
  .topbar { display:flex; align-items:center; justify-content:space-between; gap:16px;
            padding:18px 26px; background:#fff; border-bottom:1px solid var(--line);
            position:sticky; top:0; z-index:10; }
  .brand h1 { font-size:19px; margin:0; }
  .brand .sub { color:var(--muted); font-size:12.5px; margin-top:3px; }
  .actions { display:flex; align-items:center; gap:12px; color:var(--muted); font-size:12.5px; }
  .actions button { border:1px solid var(--line); background:#fff; color:var(--ink);
                    border-radius:7px; padding:7px 14px; font-size:13px; cursor:pointer; }
  .actions button:hover { border-color:#b9c6e8; color:var(--blue); }
  main { max-width:1280px; margin:0 auto; padding:22px 20px 40px; }
  .cards { display:grid; grid-template-columns:repeat(auto-fit, minmax(160px, 1fr)); gap:12px; }
  .card { background:#fff; border:1px solid var(--line); border-radius:10px; padding:14px 16px; }
  .card .k { color:var(--muted); font-size:12.5px; }
  .card .v { font-size:24px; font-weight:650; margin-top:6px; letter-spacing:.2px; }
  .card .h { color:var(--muted); font-size:11.5px; margin-top:4px; }
  .card.alt .v { color:var(--blue); }
  section.block { margin-top:26px; }
  section.block > h2 { font-size:16px; margin:0 0 12px; }
  section.block > h2 a { font-size:12px; font-weight:400; color:var(--blue); text-decoration:none; margin-left:6px; }
  .grid2 { display:grid; grid-template-columns:1fr 1fr; gap:14px; }
  .panel { background:#fff; border:1px solid var(--line); border-radius:10px; padding:14px 16px; margin-bottom:14px; }
  .panel h3 { font-size:13px; color:var(--muted); font-weight:600; margin:0 0 8px; }
  .chart { width:100%; height:320px; }
  .chart.tall { height:420px; }
  .empty { color:var(--muted); font-size:13px; padding:24px 0; text-align:center; }
  table { width:100%; border-collapse:collapse; font-size:13px; }
  th { text-align:left; color:var(--muted); font-weight:600; border-bottom:1px solid var(--line);
       padding:8px 8px; white-space:nowrap; }
  td { border-bottom:1px solid #f1f3f8; padding:8px 8px; vertical-align:top; }
  tr:last-child td { border-bottom:0; }
  td a { color:var(--blue); text-decoration:none; }
  .tag { display:inline-block; background:#eef2fb; color:#4160a8; border-radius:5px;
         font-size:11px; padding:1px 7px; margin:0 4px 2px 0; }
  footer { margin-top:34px; color:var(--muted); font-size:12px; text-align:center; line-height:1.8; }
  .login { max-width:360px; margin:80px auto; background:#fff; border:1px solid var(--line);
           border-radius:12px; padding:26px; }
  .login h2 { margin:0 0 6px; font-size:17px; }
  .login p { color:var(--muted); font-size:12.5px; margin:0 0 16px; }
  .login input { width:100%; padding:9px 10px; border:1px solid #ccd4e4; border-radius:6px; font-size:14px; }
  .login button { width:100%; margin-top:12px; padding:10px; border:0; border-radius:6px;
                  background:var(--blue); color:#fff; font-size:14px; cursor:pointer; }
  .login .err { color:#b42318; font-size:12.5px; margin-top:8px; min-height:16px; }
  @media (max-width: 860px) { .grid2 { grid-template-columns:1fr; } .topbar { padding:14px 16px; } }
</style>
<script src="/static/plotly.min.js"></script>
</head>
<body>
<div class="topbar">
  <div class="brand">
    <h1>__TITLE__</h1>
    <div class="sub">__SUBTITLE__</div>
  </div>
  <div class="actions">
    <span id="computed"></span>
    <button id="refresh" type="button">刷新</button>
  </div>
</div>

<div class="login" id="login" hidden>
  <h2>管理面板</h2>
  <p>请输入管理员令牌（config.yaml → site.admin_token）。</p>
  <input type="password" id="token" placeholder="X-Admin-Token">
  <button type="button" id="login-btn">进入面板</button>
  <div class="err" id="login-err"></div>
</div>

<main id="app" hidden>
  <div class="cards" id="cards"></div>

  <section class="block" id="sec-downloads" hidden>
    <h2>下载量</h2>
    <div class="grid2">
      <div class="panel"><h3>累计下载趋势</h3><div id="ch-trend" class="chart"></div></div>
      <div class="panel"><h3>数据集 Top 15（跨平台合并）</h3><div id="ch-topds" class="chart"></div></div>
    </div>
  </section>

  <section class="block" id="sec-papers" hidden>
    <h2>论文引用 <a id="seed-link" target="_blank" rel="noopener" hidden>查看种子论文 ↗</a></h2>
    <div class="grid2">
      <div class="panel"><h3>引用论文年份分布</h3><div id="ch-pyear" class="chart"></div></div>
      <div class="panel"><h3>种子论文被引趋势</h3><div id="ch-pcite" class="chart"></div></div>
    </div>
    <div class="panel"><h3>被引最高的引用论文</h3><table id="tbl-papers"></table></div>
  </section>

  <section class="block" id="sec-github" hidden>
    <h2>GitHub <a id="gh-link" target="_blank" rel="noopener">仓库主页 ↗</a></h2>
    <div class="panel" id="gh-panel" hidden><h3>Stars 趋势</h3><div id="ch-gh" class="chart"></div></div>
    <div class="panel"><h3>Open Issues</h3><table id="tbl-issues"></table></div>
  </section>

  <section class="block" id="sec-community">
    <h2>使用登记分布</h2>
    <div class="grid2">
      <div class="panel"><h3>世界地图（去重主体数）</h3><div id="ch-map" class="chart tall"></div></div>
      <div class="panel"><h3>国家 / 地区 Top 10</h3><div id="ch-ctop" class="chart tall"></div></div>
    </div>
    <div class="grid2">
      <div class="panel"><h3>月度登记趋势</h3><div id="ch-monthly" class="chart"></div></div>
      <div class="panel"><h3>单位分布（机构类型 → 单位）</h3><div id="ch-org" class="chart"></div></div>
    </div>
    <div class="panel"><h3>单位明细</h3><div id="org-list" class="empty">暂无登记</div></div>
  </section>

  <footer id="footer"></footer>
</main>

<script>
const AUTH = __AUTH__;
const TOKEN_KEY = 'anystats_token';
const AFF = {university:'高校', institute:'科研院所', company:'企业', personal:'个人', other:'其他'};
const COLORS = ['#2456e6', '#00a887', '#f2994a', '#9b51e0', '#eb5757', '#2d9cdb'];

function token() { return localStorage.getItem(TOKEN_KEY) || ''; }
function fmt(n) { return (n === null || n === undefined) ? '—' : Number(n).toLocaleString('zh-CN'); }
function esc(v) { return String(v === null || v === undefined ? '' : v)
  .replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;')
  .replace(/"/g,'&quot;').replace(/'/g,'&#39;'); }
function labelOf(source) {
  const meta = (window.__DATA__ && window.__DATA__.features) || {};
  return (meta[source] && meta[source].label) || source;
}
function plot(id, traces, layout) {
  const el = document.getElementById(id);
  if (!el) return;
  if (!window.Plotly) { el.innerHTML = '<div class="empty">Plotly 未加载，数值可查看 JSON 接口</div>'; return; }
  const base = {
    margin: {l: 56, r: 20, t: 8, b: 42},
    paper_bgcolor: 'rgba(0,0,0,0)', plot_bgcolor: 'rgba(0,0,0,0)',
    font: {family: 'system-ui, "PingFang SC", "Microsoft YaHei", sans-serif', size: 12, color: '#445'},
    hoverlabel: {font: {size: 12}}, showlegend: traces.length > 1
  };
  const merged = Object.assign({}, base, layout || {});
  Plotly.newPlot(id, traces, merged, {responsive: true, displayModeBar: false});
}

function setComputed(iso) {
  const el = document.getElementById('computed');
  if (!iso) { el.textContent = ''; return; }
  const d = new Date(iso);
  el.textContent = '更新于 ' + d.toLocaleString('zh-CN', {hour12: false});
}

function renderCards(data) {
  const o = data.overview || {};
  const cards = [];
  cards.push({k: '登记主体', v: o.subjects_unique, h: '去重后'});
  cards.push({k: '覆盖国家 / 地区', v: o.countries});
  cards.push({k: '登记单位', v: o.organizations_unique});
  (o.downloads_latest || []).forEach(function (item) {
    cards.push({k: labelOf(item.source) + ' 累计下载', v: item.downloads, cls: 'alt'});
  });
  if (o.paper) {
    cards.push({k: '种子论文被引', v: o.paper.seed_citations,
                h: '引用论文 ' + fmt(o.paper.citing_papers) + ' 篇', cls: 'alt'});
  }
  if (o.github) {
    cards.push({k: 'GitHub Stars', v: o.github.stars, h: o.github.repo});
    cards.push({k: 'Forks', v: o.github.forks});
  }
  const rows = cards.filter(function (c) { return c.v !== null && c.v !== undefined; });
  document.getElementById('cards').innerHTML = rows.map(function (c) {
    return '<div class="card ' + (c.cls || '') + '">' +
      '<div class="k">' + esc(c.k) + '</div>' +
      '<div class="v">' + fmt(c.v) + '</div>' +
      (c.h ? '<div class="h">' + esc(c.h) + '</div>' : '') + '</div>';
  }).join('');
}

function renderDownloads(data) {
  const hasData = data.features && (
    (data.features.huggingface && data.features.huggingface.has_data) ||
    (data.features.modelscope && data.features.modelscope.has_data));
  const sec = document.getElementById('sec-downloads');
  if (!hasData) { sec.hidden = true; return; }
  sec.hidden = false;

  const series = (data.downloads && data.downloads.trend && data.downloads.trend.series) || {};
  const traces = [];
  Object.keys(series).forEach(function (source, i) {
    const points = series[source] || [];
    if (!points.length) return;
    traces.push({
      type: 'scatter', mode: 'lines+markers', name: labelOf(source),
      x: points.map(function (p) { return p.date; }),
      y: points.map(function (p) { return p.downloads; }),
      line: {width: 2.4, color: COLORS[i % COLORS.length]},
      marker: {size: 4}
    });
  });
  if (traces.length) {
    plot('ch-trend', traces, {yaxis: {tickformat: ',', rangemode: 'tozero'}});
  } else {
    document.getElementById('ch-trend').innerHTML = '<div class="empty">暂无下载快照</div>';
  }

  const ds = ((data.downloads && data.downloads.top_datasets) || []).slice(0, 15).reverse();
  if (ds.length) {
    plot('ch-topds', [{
      type: 'bar', orientation: 'h', marker: {color: '#4c79ff'},
      y: ds.map(function (d) { return d.name; }),
      x: ds.map(function (d) { return d.total; }),
      customdata: ds.map(function (d) {
        return Object.keys(d.platforms).map(function (k) {
          return labelOf(k) + ': ' + fmt(d.platforms[k]);
        }).join(' | ');
      }),
      hovertemplate: '%{y}<br>总下载 %{x:,}<br>%{customdata}<extra></extra>'
    }], {margin: {l: 220, r: 24, t: 8, b: 42}, xaxis: {tickformat: ','}});
  } else {
    document.getElementById('ch-topds').innerHTML = '<div class="empty">暂无数据</div>';
  }
}

function renderPapers(data) {
  const p = data.papers;
  const sec = document.getElementById('sec-papers');
  if (!p || !p.citing_papers) { sec.hidden = true; return; }
  sec.hidden = false;

  const seed = p.seed || {};
  if (seed.url) {
    const link = document.getElementById('seed-link');
    link.href = seed.url; link.hidden = false;
    link.textContent = (seed.title ? seed.title : seed.arxiv_id) + ' ↗';
  }

  const years = (p.by_year || []).filter(function (x) { return x.year; });
  if (years.length) {
    plot('ch-pyear', [{
      type: 'bar', marker: {color: '#00a887'},
      x: years.map(function (x) { return x.year; }),
      y: years.map(function (x) { return x.count; }),
      hovertemplate: '%{x} 年<br>引用论文 %{y} 篇<extra></extra>'
    }], {yaxis: {title: '篇数'}});
  } else {
    document.getElementById('ch-pyear').innerHTML = '<div class="empty">暂无数据</div>';
  }

  const snaps = (p.snapshots || []).filter(function (s) { return s.date; });
  if (snaps.length) {
    plot('ch-pcite', [{
      type: 'scatter', mode: 'lines+markers', fill: 'tozeroy',
      line: {color: '#f2994a', width: 2.4}, marker: {size: 5},
      x: snaps.map(function (s) { return s.date; }),
      y: snaps.map(function (s) { return s.seed_citations; }),
      hovertemplate: '%{x}<br>被引 %{y}<extra></extra>'
    }], {yaxis: {rangemode: 'tozero'}});
  } else if (seed.citation_count) {
    plot('ch-pcite', [{
      type: 'bar', x: ['当前'], y: [seed.citation_count],
      marker: {color: '#f2994a'}
    }]);
  } else {
    document.getElementById('ch-pcite').innerHTML = '<div class="empty">暂无快照</div>';
  }

  const rows = (p.top_cited || []).map(function (paper) {
    const title = paper.url
      ? '<a href="' + esc(paper.url) + '" target="_blank" rel="noopener">' + esc(paper.title) + '</a>'
      : esc(paper.title);
    const authors = (paper.authors || []).slice(0, 4).join(', ') +
      ((paper.authors || []).length > 4 ? ' 等' : '');
    return '<tr><td>' + title + '<div class="muted">' + esc(authors) + '</div></td>' +
      '<td>' + esc(paper.year || '—') + '</td>' +
      '<td>' + esc(paper.venue || '—') + '</td>' +
      '<td>' + fmt(paper.citation_count) + '</td></tr>';
  });
  document.getElementById('tbl-papers').innerHTML =
    '<thead><tr><th>标题 / 作者</th><th>年份</th><th>期刊 / 会议</th><th>被引</th></tr></thead>' +
    '<tbody>' + (rows.join('') || '<tr><td colspan="4" class="empty">暂无数据</td></tr>') + '</tbody>';
}

function renderGithub(data) {
  const gh = data.github;
  const sec = document.getElementById('sec-github');
  if (!gh) { sec.hidden = true; return; }
  sec.hidden = false;
  if (gh.html_url) document.getElementById('gh-link').href = gh.html_url;

  const snaps = gh.snapshots || [];
  document.getElementById('gh-panel').hidden = snaps.length < 1;
  if (snaps.length) {
    plot('ch-gh', [{
      type: 'scatter', mode: 'lines+markers', line: {color: '#9b51e0', width: 2.4},
      x: snaps.map(function (s) { return s.date; }),
      y: snaps.map(function (s) { return s.stars; }),
      hovertemplate: '%{x}<br>%{y} stars<extra></extra>'
    }], {yaxis: {rangemode: 'tozero'}});
  }

  const rows = (gh.issues || []).map(function (issue) {
    const labels = (issue.labels || []).map(function (l) {
      return '<span class="tag">' + esc(l) + '</span>';
    }).join('');
    return '<tr><td>' + esc(issue.number) + '</td>' +
      '<td><a href="' + esc(issue.html_url) + '" target="_blank" rel="noopener">' +
      esc(issue.title) + '</a><div>' + labels + '</div></td>' +
      '<td>' + esc(issue.user || '—') + '</td>' +
      '<td>' + esc((issue.created_at || '').slice(0, 10)) + '</td></tr>';
  });
  document.getElementById('tbl-issues').innerHTML =
    '<thead><tr><th>#</th><th>标题</th><th>提出人</th><th>创建时间</th></tr></thead>' +
    '<tbody>' + (rows.join('') || '<tr><td colspan="4" class="empty">暂无 open issues</td></tr>') + '</tbody>';
}

function renderCommunity(data) {
  const rows = data.by_country || [];
  const names = data.country_names || {};
  if (rows.length) {
    const mapped = rows.filter(function (r) { return r.iso3; });
    plot('ch-map', [{
      type: 'choropleth', locations: mapped.map(function (r) { return r.iso3; }),
      z: mapped.map(function (r) { return r.subjects; }),
      text: mapped.map(function (r) { return names[r.country] || r.country; }),
      colorscale: 'Blues', marker: {line: {color: '#fff', width: 0.6}},
      colorbar: {thickness: 10, outlinewidth: 0},
      hovertemplate: '%{text}<br>主体 %{z} 人<extra></extra>'
    }], {
      margin: {l: 0, r: 0, t: 0, b: 0},
      geo: {showframe: false, showcoastlines: false, showland: false,
            showcountries: false, projection: {type: 'natural earth'},
            bgcolor: 'rgba(0,0,0,0)'}
    });

    const top = rows.slice(0, 10).reverse();
    plot('ch-ctop', [{
      type: 'bar', orientation: 'h', marker: {color: '#2456e6'},
      y: top.map(function (r) { return names[r.country] || r.country; }),
      x: top.map(function (r) { return r.subjects; }),
      hovertemplate: '%{y}<br>主体 %{x} 人<extra></extra>'
    }], {margin: {l: 120, r: 16, t: 8, b: 42}});
  } else {
    document.getElementById('ch-map').innerHTML = '<div class="empty">暂无登记</div>';
    document.getElementById('ch-ctop').innerHTML = '<div class="empty">暂无登记</div>';
  }

  const monthly = data.registration_trend || [];
  if (monthly.length) {
    plot('ch-monthly', [{
      type: 'bar', marker: {color: '#2d9cdb'},
      x: monthly.map(function (m) { return m.month; }),
      y: monthly.map(function (m) { return m.count; }),
      hovertemplate: '%{x}<br>登记 %{y} 条<extra></extra>'
    }], {yaxis: {title: '条数'}});
  } else {
    document.getElementById('ch-monthly').innerHTML = '<div class="empty">暂无登记</div>';
  }

  const tree = data.org_tree || [];
  if (tree.length) {
    const ids = [], labels = [], parents = [], values = [];
    tree.forEach(function (group) {
      const type = AFF[group.affiliation_type] || group.affiliation_type;
      const rootId = 'type::' + group.affiliation_type;
      ids.push(rootId);
      labels.push(type + '（' + group.total_subjects + '）');
      parents.push('');
      values.push(group.total_subjects);
      (group.organizations || []).forEach(function (org) {
        ids.push(rootId + '::' + org.organization);
        labels.push(org.organization);
        parents.push(rootId);
        values.push(org.subjects);
      });
    });
    plot('ch-org', [{
      type: 'treemap', ids: ids, labels: labels, parents: parents, values: values,
      branchvalues: 'total', textinfo: 'label+value',
      marker: {colorscale: 'Blues'}
    }], {margin: {l: 0, r: 0, t: 0, b: 0}});

    const detail = tree.map(function (group) {
      const type = AFF[group.affiliation_type] || group.affiliation_type;
      const orgs = (group.organizations || []).map(function (org) {
        return esc(org.organization) + '（' + org.subjects + '）';
      }).join('、');
      return '<div><b>' + type + '</b>：' + orgs + '</div>';
    }).join('');
    const el = document.getElementById('org-list');
    el.className = '';
    el.innerHTML = detail;
  } else {
    document.getElementById('ch-org').innerHTML = '<div class="empty">暂无登记</div>';
    const el = document.getElementById('org-list');
    el.className = 'empty';
    el.textContent = '暂无登记';
  }
}

function render(data) {
  window.__DATA__ = data;
  document.getElementById('app').hidden = false;
  document.getElementById('login').hidden = true;
  const site = data.site || {};
  if (site.title) {
    document.querySelector('.brand h1').textContent = site.title;
    document.title = site.title + ' · 统计面板';
  }
  if (site.subtitle) document.querySelector('.brand .sub').textContent = site.subtitle;
  const footer = document.getElementById('footer');
  footer.innerHTML = (site.footer ? esc(site.footer) + '<br>' : '') +
    '版本 ' + esc(site.version || '') + ' · 数据更新于 ' +
    esc((data.computed_at || '').replace('T', ' ').replace('Z', ' UTC'));
  setComputed(data.computed_at);
  renderCards(data);
  renderDownloads(data);
  renderPapers(data);
  renderGithub(data);
  renderCommunity(data);
}

async function load() {
  const headers = {};
  const t = token();
  if (t) headers['X-Admin-Token'] = t;
  const resp = await fetch('/api/v1/dashboard?days=90', {headers: headers});
  if (resp.status === 401) { showLogin('令牌无效，请重新输入'); return; }
  if (!resp.ok) { alert('加载失败：HTTP ' + resp.status); return; }
  const payload = await resp.json();
  render(payload.data);
}

function showLogin(error) {
  document.getElementById('app').hidden = true;
  document.getElementById('login').hidden = false;
  document.getElementById('login-err').textContent = error || '';
}

document.getElementById('refresh').addEventListener('click', function () { load(); });
document.getElementById('login-btn').addEventListener('click', function () {
  const value = document.getElementById('token').value.trim();
  if (!value) { document.getElementById('login-err').textContent = '请输入令牌'; return; }
  localStorage.setItem(TOKEN_KEY, value);
  load();
});
document.getElementById('token').addEventListener('keydown', function (e) {
  if (e.key === 'Enter') document.getElementById('login-btn').click();
});

if (AUTH && !token()) {
  showLogin('');
} else {
  load().catch(function (err) { showLogin('加载失败：' + err.message); });
}
</script>
</body>
</html>
"""


def dashboard_html() -> str:
    return (
        _TEMPLATE.replace("__TITLE__", html.escape(settings.SITE_TITLE))
        .replace("__SUBTITLE__", html.escape(settings.SITE_SUBTITLE))
        .replace("__DESCRIPTION__", html.escape(settings.SITE_DESCRIPTION))
        .replace("__FOOTER__", html.escape(settings.FOOTER))
        .replace("__AUTH__", "true" if settings.DASHBOARD_AUTH else "false")
    )
