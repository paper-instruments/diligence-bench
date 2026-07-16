"""Generate a standalone HTML report from score JSON files."""

from __future__ import annotations

import html
import json
import logging
import re
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


def generate_report(run_dir: Path, *, output: Path | None = None) -> Path | None:
    scores = _collect_scores(run_dir)
    if not scores:
        logger.debug("No score files found under %s, skipping report", run_dir)
        return None
    for score in scores:
        score["_trajectory"] = _parse_trajectory(score.get("_trajectory_raw", []))
    out_path = output or (run_dir / "report.html")
    report = _build_html(scores, run_dir.name)
    out_path.write_text(report, encoding="utf-8")
    logger.info("HTML report written to %s", out_path)
    return out_path


def _collect_scores(run_dir: Path) -> list[dict]:
    scores: list[dict] = []
    for path in sorted(run_dir.rglob("scores/*.json")):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            traj_path = path.parent.parent / "trajectories" / path.name
            if traj_path.exists():
                data["_trajectory_raw"] = json.loads(traj_path.read_text(encoding="utf-8"))
            scores.append(data)
        except (json.JSONDecodeError, OSError) as exc:
            logger.warning("Skipping %s: %s", path, exc)
    return scores


def _parse_trajectory(raw: list[Any]) -> list[dict[str, str]]:
    timeline: list[dict[str, str]] = []
    for entry in raw:
        if not isinstance(entry, dict):
            continue
        if entry.get("item_type") == "cli_subprocess":
            timeline.append(_parse_cli_item(entry))
        elif "item" in entry:
            parsed = _parse_run_item_repr(entry)
            if parsed:
                timeline.append(parsed)
    return timeline


def _parse_run_item_repr(entry: dict[str, Any]) -> dict[str, str] | None:
    item_str = str(entry.get("item", ""))
    prefix = item_str.split("(")[0] if "(" in item_str else ""
    raw_start = item_str.find("raw_item=")
    raw_tail = item_str[raw_start:] if raw_start >= 0 else item_str

    if "MessageOutputItem" in prefix:
        text = _extract_message_text(raw_tail)
        return {"type": "message", "content": text}
    if "ToolCallItem" in prefix:
        name = _extract_re(r", name='([^']+)', type='function_call'", raw_tail, len(raw_tail))
        args = _extract_re(r"arguments='(.*?)', call_id=", raw_tail, len(raw_tail))
        call_id = _extract_re(r"call_id='([^']+)'", raw_tail, len(raw_tail))
        return {"type": "tool_call", "name": name, "arguments": args, "call_id": call_id}
    if "ToolCallOutputItem" in prefix:
        output = _extract_tool_output(raw_tail)
        call_id = _extract_re(r"'call_id':\s*'([^']+)'", raw_tail, 2000)
        return {"type": "tool_output", "output": output, "call_id": call_id}
    return None


def _parse_cli_item(entry: dict[str, Any]) -> dict[str, str]:
    parts = []
    if entry.get("exit_code") is not None:
        parts.append(f"exit_code={entry['exit_code']}")
    extras = entry.get("extras", {})
    for key in ("session_id", "duration_ms", "total_cost_usd", "num_turns"):
        if extras.get(key):
            parts.append(f"{key}={extras[key]}")
    stdout = entry.get("stdout_preview", "")
    return {
        "type": "cli_result",
        "meta": ", ".join(parts),
        "stdout": stdout,
        "stderr": entry.get("stderr_preview", ""),
        "error": entry.get("error", ""),
    }


def _extract_tool_output(raw_tail: str) -> str:
    # Two output= fields exist: one inside raw_item={...}, one after it.
    # The second (after }, output= or ), output=) is the clean parsed one.
    second = re.search(r"[}\)],\s*output=", raw_tail)
    if second:
        after = raw_tail[second.end() :]
        # MCP format: output={'type': 'text', 'text': '...'}
        m = re.search(r"\{'type':\s*'text',\s*'text':\s*'(.*?)'\}", after, re.DOTALL)
        if m:
            return m.group(1)
        # Shell format: output='Chunk ID: ...\nOutput:\n...'
        m = re.search(r"^'(.*?)'(?:,\s*type=)", after, re.DOTALL)
        if m:
            return m.group(1)
        # Fallback: grab between quotes
        m = re.search(r"^'(.*?)'", after, re.DOTALL)
        if m:
            return m.group(1)
        # Double-quoted string
        m = re.search(r'^"(.*?)"', after, re.DOTALL)
        if m:
            return m.group(1)
    return ""


def _extract_message_text(raw_tail: str) -> str:
    # Message text is in: content=[..TextContent(..text='THE TEXT'..)]
    # or in the second output= field
    m = re.search(r"text='(.*?)',\s*type='output_text'", raw_tail[:5000], re.DOTALL)
    if m:
        return m.group(1)
    m = re.search(r"text='(.*?)'(?:\)|,)", raw_tail[:5000], re.DOTALL)
    if m:
        return m.group(1)
    return ""


def _extract_re(pattern: str, text: str, window: int) -> str:
    m = re.search(pattern, text[:window], re.DOTALL)
    return m.group(1) if m else ""


def _build_html(scores: list[dict], run_name: str) -> str:
    clean_scores = []
    for s in scores:
        c = {k: v for k, v in s.items() if k != "_trajectory_raw"}
        clean_scores.append(c)
    scores_json = json.dumps(clean_scores, default=str)
    return _TEMPLATE.replace("__SCORES_JSON__", html.escape(scores_json, quote=False)).replace(
        "__RUN_NAME__", html.escape(run_name)
    )


_TEMPLATE = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>DiligenceBench — __RUN_NAME__</title>
<style>
:root {
  --bg: #0d1117; --surface: #161b22; --border: #30363d;
  --text: #e6edf3; --text-dim: #8b949e; --text-bright: #f0f6fc;
  --green: #3fb950; --red: #f85149; --yellow: #d29922; --blue: #58a6ff;
  --orange: #d18616; --purple: #a371f7;
}
* { box-sizing: border-box; margin: 0; padding: 0; }
body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Helvetica, Arial, sans-serif;
  background: var(--bg); color: var(--text); line-height: 1.5; padding: 24px; }
h1 { font-size: 20px; color: var(--text-bright); margin-bottom: 4px; }
.subtitle { color: var(--text-dim); font-size: 13px; margin-bottom: 20px; }

.cards { display: flex; gap: 12px; flex-wrap: wrap; margin-bottom: 24px; }
.card { background: var(--surface); border: 1px solid var(--border); border-radius: 8px;
  padding: 16px 20px; min-width: 140px; }
.card-label { font-size: 11px; text-transform: uppercase; letter-spacing: 0.5px;
  color: var(--text-dim); margin-bottom: 4px; }
.card-value { font-size: 28px; font-weight: 600; color: var(--text-bright); }
.card-value.green { color: var(--green); }
.card-value.yellow { color: var(--yellow); }
.card-value.red { color: var(--red); }

.section-bars { display: flex; gap: 12px; flex-wrap: wrap; margin-bottom: 24px; }
.section-bar { background: var(--surface); border: 1px solid var(--border); border-radius: 8px;
  padding: 12px 16px; min-width: 180px; flex: 1; }
.section-bar-label { font-size: 12px; color: var(--text-dim); margin-bottom: 6px; }
.section-bar-track { height: 8px; background: var(--border); border-radius: 4px; overflow: hidden; }
.section-bar-fill { height: 100%; border-radius: 4px; }
.section-bar-value { font-size: 14px; font-weight: 600; margin-top: 4px; }

table { width: 100%; border-collapse: collapse; background: var(--surface);
  border: 1px solid var(--border); border-radius: 8px; overflow: hidden; }
thead th { background: #1c2128; padding: 10px 12px; text-align: left; font-size: 12px;
  text-transform: uppercase; letter-spacing: 0.5px; color: var(--text-dim);
  cursor: pointer; user-select: none; border-bottom: 1px solid var(--border); }
thead th:hover { color: var(--blue); }
thead th.sorted-asc::after { content: ' ▲'; }
thead th.sorted-desc::after { content: ' ▼'; }
tbody tr.task-row { cursor: pointer; border-bottom: 1px solid var(--border); }
tbody tr.task-row:hover { background: #1c2128; }
tbody td { padding: 8px 12px; font-size: 13px; }
.score-cell { font-weight: 600; font-variant-numeric: tabular-nums; }
.error-cell { color: var(--red); font-size: 12px; max-width: 200px;
  overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }

.detail { display: none; background: var(--bg); }
.detail.open { display: table-row; }
.detail-inner { padding: 16px 24px; }
.detail-tabs { display: flex; gap: 2px; margin-bottom: 12px; }
.detail-tab { padding: 6px 16px; font-size: 12px; background: var(--surface); border: 1px solid var(--border);
  border-bottom: none; border-radius: 6px 6px 0 0; cursor: pointer; color: var(--text-dim); }
.detail-tab.active { background: var(--bg); color: var(--text-bright); border-bottom: 1px solid var(--bg); }
.detail-panel { display: none; }
.detail-panel.active { display: block; }

.detail-section { margin-bottom: 16px; }
.detail-section h3 { font-size: 13px; text-transform: uppercase; letter-spacing: 0.5px;
  color: var(--text-dim); margin-bottom: 8px; border-bottom: 1px solid var(--border); padding-bottom: 4px; }

.verdict-table { width: 100%; font-size: 12px; border-collapse: collapse; }
.verdict-table th { text-align: left; padding: 4px 8px; color: var(--text-dim);
  font-weight: normal; border-bottom: 1px solid var(--border); cursor: default; }
.verdict-table td { padding: 4px 8px; border-bottom: 1px solid var(--border); vertical-align: top; }
.verdict-met { color: var(--green); font-weight: 600; }
.verdict-unmet { color: var(--red); font-weight: 600; }
.weight-positive { color: var(--green); }
.weight-negative { color: var(--red); }

.text-block { background: var(--surface); border: 1px solid var(--border); border-radius: 6px;
  padding: 16px; font-size: 13px; line-height: 1.6; white-space: pre-wrap;
  word-wrap: break-word; max-height: 600px; overflow-y: auto; }

.meta-row { display: flex; gap: 24px; flex-wrap: wrap; margin-bottom: 12px; }
.meta-item { font-size: 12px; color: var(--text-dim); }
.meta-item span { color: var(--text); font-weight: 500; }

.filter-bar { display: flex; gap: 12px; align-items: center; margin-bottom: 16px; }
.filter-bar input { background: var(--surface); border: 1px solid var(--border); border-radius: 6px;
  padding: 6px 12px; color: var(--text); font-size: 13px; width: 240px; }
.filter-bar input::placeholder { color: var(--text-dim); }
.filter-bar select { background: var(--surface); border: 1px solid var(--border); border-radius: 6px;
  padding: 6px 12px; color: var(--text); font-size: 13px; }

.traj-timeline { display: flex; flex-direction: column; gap: 4px; }
.traj-item { border-left: 3px solid var(--border); padding: 6px 12px; font-size: 12px; }
.traj-item.msg { border-color: var(--blue); }
.traj-item.tool-group { border-color: var(--orange); }
.traj-item.tool-call { border-color: var(--orange); }
.traj-item.tool-output { border-color: var(--purple); }
.traj-item.cli-result { border-color: var(--green); }
.traj-label { font-weight: 600; font-size: 11px; text-transform: uppercase; letter-spacing: 0.3px; margin-bottom: 2px; }
.traj-label.msg { color: var(--blue); }
.traj-label.tool-call { color: var(--orange); }
.traj-label.tool-output { color: var(--purple); }
.traj-label.cli-result { color: var(--green); }
.traj-output-divider { border-top: 1px solid var(--border); margin: 6px 0; padding-top: 6px; }
.traj-content { color: var(--text-dim); white-space: pre-wrap; word-break: break-word; max-height: 200px; overflow-y: auto; }
.traj-content.expandable { max-height: 80px; cursor: pointer; }
.traj-content.expandable.expanded { max-height: none; }
.traj-tool-name { color: var(--orange); font-weight: 600; }
.traj-args { color: var(--text-dim); font-family: monospace; font-size: 11px; }
.copy-row { margin: 16px 0; padding: 12px 14px; border: 1px solid var(--border); border-radius: 6px; background: var(--surface); }
.copy-row-header { display: flex; align-items: center; justify-content: space-between; margin-bottom: 8px; }
.copy-row-label { font-size: 12px; color: var(--text-dim); text-transform: uppercase; letter-spacing: 0.4px; }
.copy-row pre { margin: 0; padding: 8px 10px; background: var(--bg); border: 1px solid var(--border); border-radius: 4px; font-family: monospace; font-size: 12px; white-space: pre; overflow-x: auto; }
.copy-row button { padding: 4px 12px; font-size: 12px; cursor: pointer; }
</style>
</head>
<body>

<h1>DiligenceBench — __RUN_NAME__</h1>
<div class="subtitle" id="subtitle"></div>
<div class="cards" id="cards"></div>
<div class="section-bars" id="section-bars"></div>

<div class="copy-row">
  <div class="copy-row-header">
    <span class="copy-row-label">Spreadsheet row (errors&nbsp;·&nbsp;mean&nbsp;·&nbsp;median&nbsp;·&nbsp;stddev&nbsp;·&nbsp;section%&nbsp;…)</span>
    <button id="copy-row-btn" type="button">Copy</button>
  </div>
  <pre id="copy-row-value" tabindex="0"></pre>
</div>

<div class="filter-bar">
  <input type="text" id="search" placeholder="Filter by dataset ID or keyword…">
  <select id="verdict-filter">
    <option value="all">All tasks</option>
    <option value="errors">Errors only</option>
    <option value="low">Score &lt; 0.3</option>
    <option value="high">Score &gt; 0.7</option>
  </select>
</div>

<table>
  <thead><tr id="thead-row"></tr></thead>
  <tbody id="tbody"></tbody>
</table>

<script id="_data" type="application/json">__SCORES_JSON__</script>
<script>
const scores = JSON.parse(document.querySelector('#_data').textContent);

const allSections = new Set();
scores.forEach(s => Object.keys(s.section_scores || {}).forEach(k => allSections.add(k)));
const sections = [...allSections].sort();

const isError = s => !!s.error || !(s.answer && String(s.answer).trim());
const valid = scores.filter(s => !isError(s));
const errors = scores.filter(isError);
const mean = valid.length ? valid.reduce((a, s) => a + s.score, 0) / valid.length : 0;
const median = valid.length ? (() => { const sorted = [...valid].sort((a,b) => a.score - b.score); return sorted[Math.floor(sorted.length/2)].score; })() : 0;
const mn = valid.length ? Math.min(...valid.map(s => s.score)) : 0;
const mx = valid.length ? Math.max(...valid.map(s => s.score)) : 0;
const model = scores[0]?.underlying_model || scores[0]?.model || '—';
const harness = scores[0]?.harness || '—';
const judge = scores[0]?.judge_model || '—';

document.getElementById('subtitle').textContent =
  `Model: ${model}  •  Harness: ${harness}  •  Judge: ${judge}  •  ${scores.length} tasks`;

function scoreColor(v) { return v >= 0.7 ? 'green' : v >= 0.4 ? 'yellow' : 'red'; }

const cardsEl = document.getElementById('cards');
[['Mean', mean], ['Median', median], ['Min', mn], ['Max', mx],
 ['Completed', valid.length], ['Errors', errors.length]
].forEach(([label, value]) => {
  const isScore = typeof value === 'number' && value <= 1.01 && label !== 'Completed' && label !== 'Errors';
  const display = isScore ? (value * 100).toFixed(1) + '%' : value;
  const cls = label === 'Errors' ? (value > 0 ? 'red' : 'green') : isScore ? scoreColor(value) : '';
  cardsEl.innerHTML += `<div class="card"><div class="card-label">${label}</div><div class="card-value ${cls}">${display}</div></div>`;
});

const barsEl = document.getElementById('section-bars');
const sectionAverages = {};
sections.forEach(sec => {
  const vals = valid.map(s => (s.section_scores || {})[sec]).filter(v => v != null);
  const avg = vals.length ? vals.reduce((a, b) => a + b, 0) / vals.length : 0;
  sectionAverages[sec] = avg;
  const pct = (avg * 100).toFixed(1);
  const color = avg >= 0.7 ? 'var(--green)' : avg >= 0.4 ? 'var(--yellow)' : 'var(--red)';
  barsEl.innerHTML += `<div class="section-bar">
    <div class="section-bar-label">${sec}</div>
    <div class="section-bar-track"><div class="section-bar-fill" style="width:${pct}%;background:${color}"></div></div>
    <div class="section-bar-value" style="color:${color}">${pct}%</div></div>`;
});

const stdev = (() => {
  if (valid.length < 2) return 0;
  const m = mean;
  const variance = valid.reduce((a, s) => a + (s.score - m) ** 2, 0) / (valid.length - 1);
  return Math.sqrt(variance);
})();
const pct2 = v => (v * 100).toFixed(2) + '%';
const sectionCells = Object.keys(sectionAverages).sort()
  .map(k => pct2(sectionAverages[k]));
const spreadsheetRow = [errors.length, pct2(mean), pct2(median), pct2(stdev), ...sectionCells].join('\t');
document.getElementById('copy-row-value').textContent = spreadsheetRow;
document.getElementById('copy-row-btn').addEventListener('click', () => {
  navigator.clipboard.writeText(spreadsheetRow).then(() => {
    const btn = document.getElementById('copy-row-btn');
    const orig = btn.textContent;
    btn.textContent = 'Copied';
    setTimeout(() => { btn.textContent = orig; }, 1200);
  });
});

const columns = [
  { key: 'dataset_id', label: 'Task' },
  { key: 'score', label: 'Score' },
  ...sections.map(s => ({ key: `sec_${s}`, label: s.replace(/-/g, ' ') })),
  { key: 'num_turns', label: 'Turns' },
  { key: 'input_tokens', label: 'In tok' },
  { key: 'output_tokens', label: 'Out tok' },
  { key: 'total_tokens', label: 'Total tok' },
  { key: 'error', label: 'Error' },
];

const TOKEN_KEYS = new Set(['input_tokens', 'output_tokens', 'total_tokens']);

const theadRow = document.getElementById('thead-row');
columns.forEach((col, i) => {
  const th = document.createElement('th');
  th.textContent = col.label;
  th.addEventListener('click', () => sortTable(i));
  theadRow.appendChild(th);
});

let sortCol = 1, sortDir = -1;

function getValue(s, col) {
  const c = columns[col];
  if (c.key === 'score') return s.score || 0;
  if (c.key === 'num_turns') return s.num_turns || 0;
  if (TOKEN_KEYS.has(c.key)) return s[c.key] || 0;
  if (c.key === 'error') return s.error || '';
  if (c.key === 'dataset_id') return s.dataset_id || '';
  if (c.key.startsWith('sec_')) return (s.section_scores || {})[c.key.slice(4)] ?? -1;
  return '';
}

function renderTable() {
  const tbody = document.getElementById('tbody');
  const search = document.getElementById('search').value.toLowerCase();
  const filter = document.getElementById('verdict-filter').value;

  let filtered = scores.filter(s => {
    if (search && !(s.dataset_id || '').toLowerCase().includes(search) &&
        !(s.answer || '').toLowerCase().includes(search) &&
        !(s.query || '').toLowerCase().includes(search)) return false;
    if (filter === 'errors') return !!s.error;
    if (filter === 'low') return s.score < 0.3;
    if (filter === 'high') return s.score > 0.7;
    return true;
  });

  filtered.sort((a, b) => {
    const va = getValue(a, sortCol), vb = getValue(b, sortCol);
    if (typeof va === 'number' && typeof vb === 'number') return (va - vb) * sortDir;
    return String(va).localeCompare(String(vb)) * sortDir;
  });

  tbody.innerHTML = '';
  filtered.forEach((s, idx) => {
    const tr = document.createElement('tr');
    tr.className = 'task-row';
    columns.forEach(col => {
      const td = document.createElement('td');
      if (col.key === 'score') {
        td.className = 'score-cell';
        td.style.color = `var(--${scoreColor(s.score)})`;
        td.textContent = (s.score * 100).toFixed(1) + '%';
      } else if (col.key.startsWith('sec_')) {
        const v = (s.section_scores || {})[col.key.slice(4)];
        if (v != null) {
          td.className = 'score-cell';
          td.style.color = `var(--${scoreColor(v)})`;
          td.textContent = (v * 100).toFixed(1) + '%';
        } else { td.textContent = '—'; td.style.color = 'var(--text-dim)'; }
      } else if (col.key === 'error') {
        td.className = 'error-cell';
        td.textContent = s.error || '';
        td.title = s.error || '';
      } else if (TOKEN_KEYS.has(col.key)) {
        td.style.fontVariantNumeric = 'tabular-nums';
        td.style.textAlign = 'right';
        td.textContent = s[col.key] ? s[col.key].toLocaleString() : '—';
      } else {
        td.textContent = s[col.key] ?? '—';
      }
      tr.appendChild(td);
    });

    const detailTr = document.createElement('tr');
    detailTr.className = 'detail';
    const detailTd = document.createElement('td');
    detailTd.colSpan = columns.length;
    const uid = 'detail-' + idx;
    detailTd.innerHTML = buildDetail(s, uid);
    detailTr.appendChild(detailTd);

    tr.addEventListener('click', () => {
      detailTr.classList.toggle('open');
    });

    tbody.appendChild(tr);
    tbody.appendChild(detailTr);
  });

  theadRow.querySelectorAll('th').forEach((th, i) => {
    th.classList.remove('sorted-asc', 'sorted-desc');
    if (i === sortCol) th.classList.add(sortDir === 1 ? 'sorted-asc' : 'sorted-desc');
  });
}

function sortTable(col) {
  if (sortCol === col) sortDir *= -1;
  else { sortCol = col; sortDir = col === 0 ? 1 : -1; }
  renderTable();
}

function buildDetail(s, uid) {
  const verdicts = s.verdicts || [];
  const traj = s._trajectory || [];
  const hasQuery = !!s.query;
  const hasAnswer = !!s.answer;
  const hasTraj = traj.length > 0;
  const hasVerdicts = verdicts.length > 0;

  const tabs = [];
  if (hasVerdicts) tabs.push({ id: 'verdicts', label: `Verdicts (${verdicts.filter(v=>v.weight>0).length})` });
  if (hasTraj) {
    const toolCalls = traj.filter(t => t.type === 'tool_call').length;
    const msgs = traj.filter(t => t.type === 'message').length;
    tabs.push({ id: 'trajectory', label: `Trajectory (${toolCalls} calls, ${msgs} msgs)` });
  }
  if (hasAnswer) tabs.push({ id: 'answer', label: 'Answer' });
  if (hasQuery) tabs.push({ id: 'query', label: 'Query' });

  let h = '<div class="detail-inner">';

  // meta
  h += '<div class="meta-row">';
  h += `<div class="meta-item">Model: <span>${esc(s.underlying_model || s.model)}</span></div>`;
  h += `<div class="meta-item">Turns: <span>${s.num_turns || 0}</span></div>`;
  h += `<div class="meta-item">Judge: <span>${esc(s.judge_model || '—')}</span></div>`;
  h += `<div class="meta-item">Harness: <span>${esc(s.harness || '—')}</span></div>`;
  h += '</div>';

  // tabs
  if (tabs.length > 1) {
    h += '<div class="detail-tabs">';
    tabs.forEach((t, i) => {
      h += `<div class="detail-tab ${i===0?'active':''}" onclick="switchTab('${uid}','${t.id}',this)">${t.label}</div>`;
    });
    h += '</div>';
  }

  // verdicts panel
  if (hasVerdicts) {
    const met = verdicts.filter(v => v.verdict === 'MET' && v.weight > 0).length;
    const total = verdicts.filter(v => v.weight > 0).length;
    const negHit = verdicts.filter(v => v.verdict === 'MET' && v.weight < 0).length;
    h += `<div class="detail-panel ${tabs[0]?.id==='verdicts'?'active':''}" data-tab="verdicts" data-uid="${uid}">`;
    h += '<div class="detail-section">';
    h += `<h3>Verdicts — ${met}/${total} met` + (negHit ? `, ${negHit} penalty triggered` : '') + '</h3>';
    h += '<table class="verdict-table"><thead><tr>';
    h += '<th>Section</th><th>Requirement</th><th>Weight</th><th>Verdict</th><th>Reason</th>';
    h += '</tr></thead><tbody>';
    verdicts.forEach(v => {
      const vclass = v.verdict === 'MET' ? (v.weight < 0 ? 'verdict-unmet' : 'verdict-met') : 'verdict-unmet';
      const wclass = v.weight < 0 ? 'weight-negative' : 'weight-positive';
      const display = v.weight < 0 && v.verdict === 'MET' ? 'TRIGGERED' :
                      v.weight < 0 && v.verdict === 'UNMET' ? 'AVOIDED' : v.verdict;
      h += `<tr>
        <td style="white-space:nowrap">${esc(v.section_id || '')}</td>
        <td>${esc(v.requirement || '')}</td>
        <td class="${wclass}" style="text-align:right">${v.weight > 0 ? '+' : ''}${v.weight}</td>
        <td class="${vclass}">${display}</td>
        <td style="color:var(--text-dim)">${esc(v.reason || '')}</td>
      </tr>`;
    });
    h += '</tbody></table></div></div>';
  }

  // trajectory panel — group tool_call + tool_output by call_id
  if (hasTraj) {
    const isFirst = tabs[0]?.id === 'trajectory';
    h += `<div class="detail-panel ${isFirst?'active':''}" data-tab="trajectory" data-uid="${uid}">`;
    h += '<div class="detail-section"><h3>Agent Trajectory</h3>';
    h += '<div class="traj-timeline">';

    // Legacy format: separate tool_output items grouped by call_id
    const outputsByCallId = {};
    traj.forEach(t => {
      if (t.type === 'tool_output' && t.call_id) {
        if (!outputsByCallId[t.call_id]) outputsByCallId[t.call_id] = [];
        outputsByCallId[t.call_id].push(t);
      }
    });
    const renderedOutputIds = new Set();

    traj.forEach(t => {
      if (t.type === 'message') {
        const meta = [];
        if (t.model) meta.push(t.model);
        if (t.input_tokens) meta.push(`${t.input_tokens} in`);
        if (t.output_tokens) meta.push(`${t.output_tokens} out`);
        const metaStr = meta.length ? ` <span style="color:var(--text-dim);font-weight:normal;font-size:10px">(${esc(meta.join(', '))})</span>` : '';
        h += `<div class="traj-item msg">
          <div class="traj-label msg">Message${metaStr}</div>
          <div class="traj-content expandable" onclick="this.classList.toggle('expanded')">${esc(t.content || '')}</div>
        </div>`;
      } else if (t.type === 'tool_call') {
        // New format: output is inline on the tool_call item
        const inlineOutput = t.output || '';
        // Legacy format: output from separate tool_output items
        const legacyOutputs = t.call_id ? (outputsByCallId[t.call_id] || []) : [];
        legacyOutputs.forEach(o => renderedOutputIds.add(o));
        const outputText = inlineOutput || legacyOutputs.map(o => o.output).join('\n') || '';

        h += `<div class="traj-item tool-group">
          <div class="traj-label tool-call">Tool Call — <span class="traj-tool-name">${esc(t.name || '?')}</span></div>
          <div class="traj-args">${esc(t.arguments || '')}</div>`;
        if (outputText) {
          h += `<div class="traj-output-divider"></div>
          <div class="traj-label tool-output" style="color:var(--purple)">Output</div>
          <div class="traj-content expandable" onclick="this.classList.toggle('expanded')">${esc(outputText)}</div>`;
        }
        if (t.error) {
          h += `<div style="color:var(--red);margin-top:4px;font-size:11px">Error: ${esc(t.error)}</div>`;
        }
        h += '</div>';
      } else if (t.type === 'tool_output') {
        if (renderedOutputIds.has(t)) return;
        h += `<div class="traj-item tool-output">
          <div class="traj-label tool-output">Tool Output</div>
          <div class="traj-content expandable" onclick="this.classList.toggle('expanded')">${esc(t.output || '')}</div>
        </div>`;
      } else if (t.type === 'cli_result') {
        h += `<div class="traj-item cli-result">
          <div class="traj-label cli-result">CLI Result — ${esc(t.meta || '')}</div>
          <div class="traj-content expandable" onclick="this.classList.toggle('expanded')">${esc(t.stdout || '')}</div>
          ${t.error ? `<div style="color:var(--red);margin-top:4px">${esc(t.error)}</div>` : ''}
        </div>`;
      } else if (t.type === 'agent') {
        // Agent span — show as a header marker
      }
    });
    h += '</div></div></div>';
  }

  // answer panel
  if (hasAnswer) {
    const isFirst = tabs[0]?.id === 'answer';
    h += `<div class="detail-panel ${isFirst?'active':''}" data-tab="answer" data-uid="${uid}">`;
    h += '<div class="detail-section"><h3>Agent Answer</h3>';
    h += `<div class="text-block">${esc(s.answer)}</div></div></div>`;
  }

  // query panel
  if (hasQuery) {
    const isFirst = tabs[0]?.id === 'query';
    h += `<div class="detail-panel ${isFirst?'active':''}" data-tab="query" data-uid="${uid}">`;
    h += '<div class="detail-section"><h3>Task Query</h3>';
    h += `<div class="text-block">${esc(s.query)}</div></div></div>`;
  }

  h += '</div>';
  return h;
}

function switchTab(uid, tabId, el) {
  el.parentElement.querySelectorAll('.detail-tab').forEach(t => t.classList.remove('active'));
  el.classList.add('active');
  document.querySelectorAll(`.detail-panel[data-uid="${uid}"]`).forEach(p => {
    p.classList.toggle('active', p.dataset.tab === tabId);
  });
}

function esc(s) {
  const d = document.createElement('div');
  d.textContent = s;
  return d.innerHTML;
}

document.getElementById('search').addEventListener('input', renderTable);
document.getElementById('verdict-filter').addEventListener('change', renderTable);
renderTable();
</script>
</body>
</html>"""
