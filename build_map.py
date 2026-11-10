"""Research map: each lane (route) gets its own time axis."""

from __future__ import annotations

import json
import sys
from collections import defaultdict
from datetime import date, timedelta
from pathlib import Path

import yaml

LABEL_W = 214
PLOT_W = 2100
CARD_W = 248
CARD_H = 100
ROW_H = 116
LANE_PAD = 34
AXIS_H = 30
LANE_GAP = 22
TOP_PAD = 26

LANE_COLORS = ["#4a6cf7", "#0f9d76", "#c2740e", "#8b5cf6", "#d0326b", "#0e7c86", "#5b6472"]
BADGE = {"需训": "#d0326b", "免训": "#0f9d76", "推理期技巧": "#c2740e", "不适用": "#6b7280"}


def parse_day(v):
    if isinstance(v, date):
        return v
    return date.fromisoformat(str(v))


def _cites(v):
    """引用量：整数（yaml 里写成字符串也认），拿不到就是 None。"""
    if isinstance(v, bool) or v is None:
        return None
    if isinstance(v, (int, float)):
        return int(v)
    s = str(v).strip().replace(",", "").replace("_", "")
    return int(s) if s.lstrip("-").isdigit() else None


def _cpm(v):
    """引用速率（次/月）：保留 1 位小数，拿不到就是 None。"""
    if isinstance(v, bool) or v is None:
        return None
    try:
        x = float(str(v).strip())
    except (TypeError, ValueError):
        return None
    if x != x or x in (float("inf"), float("-inf")):
        return None
    return round(x, 3)


def _inherit(v):
    """图谱内被继承次数：非负整数，缺省 0。"""
    n = _cites(v)
    return max(0, n) if n is not None else 0


def month_start(d):
    return date(d.year, d.month, 1)


def month_end(d):
    if d.month == 12:
        return date(d.year, 12, 31)
    return date(d.year, d.month + 1, 1) - timedelta(days=1)


def next_month(d):
    return date(d.year + (d.month // 12), d.month % 12 + 1, 1)


def months(a, b):
    out, cur = [], month_start(a)
    while cur <= b:
        out.append(cur)
        cur = next_month(cur)
    return out


def load(path):
    doc = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    nodes = doc["nodes"]
    lanes = doc.get("lanes") or []
    order = [l["name"] for l in lanes]
    color = {l["name"]: l.get("color") for l in lanes}
    for n in nodes:
        if n["lane"] not in order:
            order.append(n["lane"])
    return nodes, order, color


MAX_STACK = 3


def time_columns(items):
    """泳道内共享列；仅将拥挤时段逐级细分，不给缺日论文伪造日序。"""
    by_month = defaultdict(list)
    for n in items:
        d = parse_day(n["date"])
        by_month[(d.year, d.month)].append(n)
    columns = []

    def emit(group, year, label):
        # 同一天或缺日条目仍可能拥挤，按分支独立分页，共享续列。
        branches = defaultdict(list)
        for n in group:
            branches[n.get("branch") or ""].append(n)
        pages = max((len(g) + MAX_STACK - 1) // MAX_STACK for g in branches.values())
        for page in range(pages):
            members = [n for g in branches.values()
                       for n in g[page * MAX_STACK:(page + 1) * MAX_STACK]]
            columns.append({"year": year, "label": label + (f" · 续{page + 1}" if page else ""),
                            "ids": [n["id"] for n in members]})

    def split(group, year, month, start, end, level, label):
        density = defaultdict(int)
        for n in group:
            density[n.get("branch") or ""] += 1
        if max(density.values()) <= MAX_STACK or level == 3:
            emit(group, year, label)
            return
        if level == 0:
            ranges = [(1, 10, f"{month}月上旬"), (11, 20, f"{month}月中旬"),
                      (21, end, f"{month}月下旬")]
        elif level == 1:
            mid = start + 4
            ranges = [(start, mid, f"{month}月{start}–{mid}日"),
                      (mid + 1, end, f"{month}月{mid + 1}–{end}日")]
        else:
            ranges = [(d, d, f"{month}月{d}日") for d in range(start, end + 1)]
        for lo, hi, text in ranges:
            subset = [n for n in group if lo <= parse_day(n["date"]).day <= hi]
            if subset:
                split(subset, year, month, lo, hi, level + 1, text)

    for (year, month), group in sorted(by_month.items()):
        precise = [n for n in group if (n.get("precision") or "day") == "day"]
        imprecise = [n for n in group if (n.get("precision") or "day") != "day"]
        density = defaultdict(int)
        for n in group:
            density[n.get("branch") or ""] += 1
        if max(density.values()) <= MAX_STACK:
            emit(group, year, f"{month}月")
        else:
            # 月精度放入单独列，避免将占位日期 01 误读为上旬。
            if imprecise:
                emit(imprecise, year, f"{month}月 · 未定日")
            if precise:
                split(precise, year, month, 1, month_end(date(year, month, 1)).day, 0, f"{month}月")
    return columns


def paper_signals(n, rules):
    """出版证据与项目匹配分开：不从原始 venue 文案推断已录用。"""
    record = rules.get("papers", {}).get(n["id"], {})
    venue = rules.get("venues", {}).get(record.get("name"), {})
    verified = (record.get("status") in ("accepted", "published")
                and record.get("track") in ("main", "journal")
                and str(record.get("source", "")).startswith("https://")
                and str(venue.get("source", "")).startswith("https://"))
    publication = dict(record, tier=venue.get("tier", 0) if verified else 0,
                       rank=venue.get("rank", ""), rank_source=venue.get("source", ""))
    status = record.get("status")
    evidence = str(record.get("source", "")).startswith("https://")
    if verified:
        label, caution = "已核实发表/录用", "出版经历已核实；仍需核查实验与结论是否适用。"
    elif evidence and record.get("track") == "workshop":
        label, caution = "Workshop", "Workshop 论文，不等同对应会议主会；结论与实验需另行核查。"
    elif evidence and status == "submitted":
        label, caution = "投稿中", "只有投稿声明，尚无录用证据；不作为已通过正式评审的依据。"
    elif evidence and status == "preprint":
        label, caution = "预印本", "已确认预印本身份，尚无已核实正式录用记录；优先复核实验与实现。"
    elif status == "product":
        label, caution = "工业产品", "商业产品发布，未经同行评审；引用时应注明为产品发布而非论文。"
    elif status == "project_page":
        label, caution = "项目页", "仅有项目主页或代码仓库，未见对应正式发表论文。"
    elif status == "unknown":
        label, caution = "状态不明", "公开渠道未能核实其发表状态，也未确认其未发表。"
    elif evidence and status == "technical_report":
        label, caution = "技术报告", "技术报告，尚无已核实主会/期刊录用；结果需独立验证。"
    elif evidence and status in ("accepted", "published"):
        label, caution = "录用·赛道待核", "已有录用声明，但具体赛道或等级尚未核实，不按主会晋档。"
    else:
        label, caution = "发表未核实", "本图谱尚未核实正式发表/录用状态；不代表一定未录用，也不代表论文质量低。"
    confidence = record.get("verification_confidence")
    if confidence == "medium":
        caution += " 核验置信度中等，部分依据来自第三方索引，引用前建议复查原始出版记录。"
    publication.update(label=label, caution=caution, verified=verified)
    concepts = set(n.get("concepts") or [])
    reasons = []
    if n["id"] == "solarrenderer":
        reasons.append("当前实验基座：SolarRenderer 结构条件自回归渲染。")
    if n["id"] in ("echo-infinity", "echo-forcing", "memrope"):
        reasons.append("当前记忆增强候选：与 Echo-Infinity 接入及位置编码检查直接相关。")
    if n.get("lane") == "位置时间寻址" and (
            n.get("branch") in ("锚 sink", "重排位置", "实体挂载") or
            concepts & {"旋转位置编码", "分块因果缓存", "记忆写入淘汰"}):
        reasons.append("AR 记忆主线：RoPE、历史寻址或持久缓存，可用于分析长视频回访与记忆失效。")
    if n.get("lane") == "几何位姿寻址" and n.get("branch") in ("位姿视锥", "显式几何库"):
        reasons.append("空间记忆主线：按位姿或显式几何取回历史视图，可对照相机回访与场景一致性记忆设计。")
    if n.get("lane") == "代码世界模型" and n.get("branch") == "神经渲染器" and (
            concepts & {"结构条件渲染", "分块因果缓存", "流式分块推理"}):
        reasons.append("渲染主线：结构 proxy 驱动的流式渲染，与当前 SolarRenderer 管线可对照。")
    # 多人一致性只看机制描述，不因参考文献或限制中出现“多人”就标高相关。
    mechanism = " ".join(str(n.get(k) or "") for k in ("title", "one_liner", "mechanism"))
    if any(t in mechanism.lower() for t in ("多人身份", "多角色一致", "多人一致", "multi-character consistency", "multi-person consistency")):
        reasons.append("角色主线：机制涉及多人或多角色身份一致性，可对照多人 proxy 实验。")
    # 正式构建采用人工审阅的项目精选，不再把宽泛规则命中的论文全亮。
    if "project_shortlist" in rules:
        shortlist = rules["project_shortlist"]
        for lane, picks in shortlist.items():
            if len(picks) > 5:
                raise ValueError(f"项目精选每个板块最多5篇：{lane}")
        picks = shortlist.get(n.get("lane"), {})
        reasons = [picks[n["id"]]] if n["id"] in picks else []
    return dict(publication=publication, project_relevance=reasons)


def layout(nodes, order, color, signals=None):
    """同一泳道共用一条紧凑时间轴：按日期排位次，不留空月；分支各占一行。"""
    by_lane = defaultdict(list)
    for n in nodes:
        by_lane[n["lane"]].append(n)

    lane_meta, node_out = [], []
    top = TOP_PAD
    STEP = CARD_W + 26
    width = LABEL_W + 900

    for li, lane in enumerate(order):
        items = by_lane.get(lane, [])
        if not items:
            continue

        by_date = sorted(items, key=lambda n: (parse_day(n["date"]), n["title"]))
        branches = []
        for n in by_date:
            b = n.get("branch") or ""
            if b not in branches:
                branches.append(b)

        columns = time_columns(by_date)
        col = {nid: i for i, c in enumerate(columns) for nid in c["ids"]}

        # 同列同分支最多三层；列由整条泳道共享。
        branch_slot = {}
        placed = {}
        rough = {}
        max_right = LABEL_W
        for n in by_date:
            k = col[n["id"]]
            bi = branches.index(n.get("branch") or "")
            rough.setdefault((bi, k), []).append(n)
        for (bi, k), group in rough.items():
            branch_slot[bi] = max(branch_slot.get(bi, 1), len(group))
            for g, n in enumerate(group):
                x = LABEL_W + k * STEP
                placed[n["id"]] = (x, g)

        # 分支纵向偏移：按每支实际摞的层数累加
        btop, acc = {}, 0
        for bi, b in enumerate(branches):
            btop[bi] = top + max(LANE_PAD, 62) + acc * (CARD_H + 14) + bi * 26
            acc += branch_slot.get(bi, 1)

        for n in by_date:
            x, g = placed[n["id"]]
            bi = branches.index(n.get("branch") or "")
            placed[n["id"]] = (x, btop[bi] + g * (CARD_H + 14))
            max_right = max(max_right, x + CARD_W)

        years, prev = [], None
        for i, c in enumerate(columns):
            c["x"] = LABEL_W + i * STEP
            if prev is None or c["year"] != prev:
                years.append({"x": c["x"] - 14, "label": str(c["year"])})
            prev = c["year"]

        plot_w = max(420, max_right - LABEL_W + 30)
        height = (max(placed[n["id"]][1] for n in items) + CARD_H + 30) - top
        width = max(width, LABEL_W + plot_w + 70)

        lane_meta.append({
            "name": lane,
            "color": color.get(lane) or LANE_COLORS[li % len(LANE_COLORS)],
            "top": top, "height": height, "plotW": plot_w,
            "count": len(items), "years": years, "columns": columns,
            "branches": [{"name": b, "y": btop[i], "count": sum(1 for n in by_date if (n.get("branch") or "") == b)}
                         for i, b in enumerate(branches)],
        })

        for n in items:
            x, y = placed[n["id"]]
            node_out.append({
                **paper_signals(n, signals or {}),
                "id": n["id"], "title": n["title"], "date": n["date"],
                "precision": n.get("precision") or "day",
                "lane": lane, "branch": n.get("branch") or "",
                "arxiv": n.get("arxiv") or "", "venue": n.get("venue") or "",
                "training": n.get("training") or "", "status": n.get("status") or "",
                "one_liner": n.get("one_liner") or "", "mechanism": n.get("mechanism") or "",
                "detail": n.get("detail") or None,
                "tags": n.get("tags") or [], "concepts": n.get("concepts") or [], "explain": n.get("explain") or "",
                "key_numbers": n.get("key_numbers") or [],
                "self_measured": n.get("self_measured") or [],
                "media": n.get("media") or [], "links": n.get("links") or [],
                "note": n.get("note") or "", "parent": n.get("parent"),
                "link_strength": n.get("link_strength") or "",
                "key": bool(n.get("key")),
                "citations": _cites(n.get("citations")),
                "cpm": _cpm(n.get("cpm")),
                "inherited": _inherit(n.get("inherited")), "inherited_chain": _inherit(n.get("inherited_chain")),
                "repro": (n.get("repro") or "").strip(),
                "x": round(x, 1), "y": y,
            })

        top += height + LANE_GAP

    pos = {n["id"]: n for n in node_out}
    for n in node_out:
        p = n.get("parent")
        if p and p in pos:
            src = pos[p]
            n["sx"] = src["x"] + CARD_W
            n["sy"] = src["y"] + CARD_H / 2
            n["cross"] = src["lane"] != n["lane"]
        else:
            n["sx"] = None

    return {
        "nodes": node_out, "lanes": lane_meta,
        "width": width, "height": top + 30,
        "labelW": LABEL_W, "plotW": PLOT_W,
        "card": {"w": CARD_W, "h": CARD_H},
        "badge": BADGE,
        "init": {"scale": 1.0, "tx": 8, "ty": 8},
    }


def validate(data, out_dir, prefix):
    missing = []
    for n in data["nodes"]:
        for m in n["media"]:
            p = (out_dir / (prefix + m)).resolve()
            if not p.exists():
                missing.append(f"{n['id']}: {prefix}{m}")
    return missing


HTML = r"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<title>__TITLE__</title>
<style>
  :root{
    --ink:#0F172A; --ink2:#334155; --muted:#64748B; --line:rgba(15,23,42,.08); --line2:rgba(15,23,42,.14);
    --bg:#F4F6FB; --card:#ffffff; --band-a:rgba(255,255,255,.72); --band-b:rgba(238,242,250,.72);
    --accent:#4F46E5; --accent-weak:rgba(79,70,229,.08);
    --ring:0 0 0 4px rgba(79,70,229,.14);
    --sh-sm:0 1px 2px rgba(15,23,42,.06),0 4px 12px rgba(15,23,42,.05);
    --sh-lg:0 24px 60px -12px rgba(15,23,42,.28);
    --ease:cubic-bezier(.22,.8,.3,1);
  }
  *{box-sizing:border-box}
  html,body{margin:0;height:100%;color:var(--ink);-webkit-font-smoothing:antialiased;
    font-family:"Inter","PingFang SC","HarmonyOS Sans SC","Noto Sans SC","Microsoft YaHei",system-ui,sans-serif;
    background:
      radial-gradient(1200px 600px at 8% -10%,rgba(99,102,241,.14),transparent 60%),
      radial-gradient(900px 500px at 100% 0%,rgba(14,165,233,.12),transparent 55%),
      var(--bg);}
  header{position:fixed;inset:0 0 auto 0;height:64px;display:flex;align-items:center;gap:14px;padding:0 22px;
    background:rgba(255,255,255,.72);backdrop-filter:saturate(180%) blur(18px);-webkit-backdrop-filter:saturate(180%) blur(18px);
    border-bottom:1px solid var(--line);z-index:20}
  header::before{content:"";width:10px;height:10px;border-radius:50%;flex:none;
    background:conic-gradient(from 200deg,#4F46E5,#0EA5E9,#10B981,#4F46E5);box-shadow:0 0 0 4px rgba(79,70,229,.12)}
  header h1{font-size:18px;margin:0;font-weight:700;letter-spacing:.02em;white-space:nowrap;
    background:linear-gradient(90deg,#0F172A 0%,#4338CA 100%);-webkit-background-clip:text;background-clip:text;color:transparent}
  #q{height:38px;width:300px;border:1px solid var(--line);border-radius:999px;padding:0 16px 0 38px;font-size:14px;
    background:rgba(255,255,255,.85) url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='16' height='16' fill='none' stroke='%2364748B' stroke-width='2' stroke-linecap='round'%3E%3Ccircle cx='7' cy='7' r='5'/%3E%3Cpath d='m11 11 3.5 3.5'/%3E%3C/svg%3E") no-repeat 14px 50%;
    color:var(--ink);outline:none;transition:.2s var(--ease)}
  #q:focus{border-color:var(--accent);box-shadow:var(--ring);width:340px}
  #play{height:38px;padding:0 18px;border:0;border-radius:999px;font-size:13.5px;font-weight:600;cursor:pointer;color:#fff;white-space:nowrap;
    background:linear-gradient(135deg,#4F46E5,#6366F1 55%,#0EA5E9);box-shadow:0 6px 16px -4px rgba(79,70,229,.55);transition:.2s var(--ease)}
  #play:hover{transform:translateY(-1px);box-shadow:0 10px 22px -4px rgba(79,70,229,.6)}
  #play:active{transform:none}
  .hint{font-size:12px;color:var(--muted);margin-left:auto;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;max-width:42vw}
  #stage{position:fixed;inset:64px 0 0 0;overflow:hidden;cursor:grab;
    background-image:radial-gradient(rgba(15,23,42,.10) 1px,transparent 1.2px);background-size:22px 22px}
  #stage.drag{cursor:grabbing}
  svg{width:100%;height:100%;display:block}
  .lane-box{stroke:rgba(15,23,42,.07);stroke-width:1;rx:18;ry:18}
  .lane-name{font-size:24px;font-weight:800;letter-spacing:.01em}
  .lane-count{font-size:13px;fill:var(--muted)}
  .branch{font-size:14px;fill:#475569;font-weight:500}
  .tick{stroke:rgba(15,23,42,.06);stroke-width:1}
  .tick.major{stroke:rgba(15,23,42,.12)}
  /* ---- 引用速率炫光：cpm 四档，越高越宽/越亮/呼吸越快；无数据不发光 ---- */
  .glow{pointer-events:none}
  .glow .halo,.glow .ring{fill:none;stroke-linejoin:round}
  .glow .halo{animation:gbreathe var(--gd) ease-in-out infinite}
  .glow .ring{animation:gring var(--gd) ease-in-out infinite}
  .glow.g1{--gd:5.6s}
  .glow.g1 .ring{stroke:#A9C1FF}
  .glow.g1 .halo{stroke:#A9C1FF;filter:drop-shadow(0 0 6px rgba(169,193,255,.90))}
  .glow.g2{--gd:4.4s}
  .glow.g2 .ring{stroke:#6C8CFF}
  .glow.g2 .halo{stroke:#6C8CFF;filter:drop-shadow(0 0 10px rgba(108,140,255,.95)) drop-shadow(0 0 19px rgba(108,140,255,.50))}
  .glow.g3{--gd:3.4s}
  .glow.g3 .ring{stroke:#8B5CF6}
  .glow.g3 .halo{stroke:#8B5CF6;filter:drop-shadow(0 0 13px rgba(139,92,246,.95)) drop-shadow(0 0 27px rgba(139,92,246,.58))}
  .glow.g4{--gd:2.4s}
  .glow.g4 .ring{stroke:#F0A500}
  .glow.g4 .halo{stroke:#F0A500;filter:drop-shadow(0 0 17px rgba(240,165,0,.98)) drop-shadow(0 0 36px rgba(240,165,0,.68))}
  @keyframes gbreathe{0%,100%{stroke-opacity:.30}50%{stroke-opacity:.92}}
  @keyframes gring{0%,100%{stroke-opacity:.55}50%{stroke-opacity:1}}
  .cpt{display:flex;flex-wrap:wrap;gap:6px;padding:2px 0 10px}
.cpt-chip{border:1px solid #0F766E33;background:#0F766E0F;color:#0F766E;font-size:12px;padding:4px 9px;border-radius:999px;cursor:pointer;font-family:inherit}
.cpt-chip:hover{background:#0F766E1F}
.cite-badge{font-size:10.5px;font-weight:700;letter-spacing:.02em;font-variant-numeric:tabular-nums;opacity:.92}
  .inherit-badge{font-size:10px;font-weight:700;letter-spacing:.01em;font-variant-numeric:tabular-nums}
  /* ---- 面板「影响力」小节 ---- */
  .imp{display:flex;flex-direction:column;gap:1px;border:1px solid var(--line);border-radius:12px;overflow:hidden;background:var(--line)}
  .imp-row{display:flex;gap:12px;align-items:baseline;padding:9px 12px;background:rgba(255,255,255,.92)}
  .imp-k{flex:none;width:96px;font-size:12px;font-weight:600;color:var(--muted)}
  .imp-v{font-size:13px;line-height:1.6;color:var(--ink2);font-variant-numeric:tabular-nums}
  .imp-v b{color:var(--ink);font-weight:700}
  .imp-v .u{color:var(--muted);font-weight:500;font-size:12px}
  .imp-note{margin-top:7px;font-size:11.5px;color:var(--muted);line-height:1.6}
  @media (prefers-reduced-motion:reduce){.glow .halo,.glow .ring{animation:none}}
  .year-sep{stroke:rgba(15,23,42,.22);stroke-width:1.2;stroke-dasharray:3 6;stroke-linecap:round}
  .project-mark{display:none;pointer-events:none}
  .card.project-related .project-mark{display:block}
  .card.project-muted{opacity:.30}
  .venue-badge{font-size:10px;font-weight:700;pointer-events:none}
  #project-toggle[aria-pressed="true"]{background:#0F766E;color:white;border-color:#0F766E}
  .time-label{font-size:14px;font-weight:650;fill:var(--muted)}
  .time-tick{stroke:rgba(100,116,139,.18);stroke-dasharray:3 7;pointer-events:none}
  .year-label{font-size:15px;font-weight:800;letter-spacing:.06em}
  .tick-label-old{font-size:13px;fill:#94A3B8}
  .tick-label.major{fill:#475569;font-weight:600}
  .axis-line{stroke:rgba(15,23,42,.10);stroke-width:1}
  .link{fill:none;stroke:#B6C0D4;stroke-width:1.6;stroke-linecap:round}
  .link.cross{stroke-dasharray:4 6;stroke:#CBD3E3;stroke-width:1.2}
  .card{cursor:pointer;transition:opacity .25s var(--ease)}
  .card>*{transition:transform .25s var(--ease)}
  .bg{fill:var(--card);stroke:rgba(15,23,42,.08);stroke-width:1;filter:url(#sh);transition:stroke .2s,stroke-width .2s}
  .card:hover .bg{stroke:var(--accent);stroke-width:1.6}
  .card.dim{opacity:.14}
  .card.active .bg{stroke:var(--ink);stroke-width:2}
  .t-title{font-size:19px;font-weight:650;fill:var(--ink);letter-spacing:.005em}
  .t-date{font-size:13px;fill:#94A3B8;font-variant-numeric:tabular-nums}
  .badge-t{font-size:11.5px;font-weight:700}
  .tag-t{font-size:10.5px;font-weight:600}
  #panel{position:fixed;top:64px;right:0;bottom:0;width:440px;max-width:100vw;
    background:rgba(255,255,255,.88);backdrop-filter:saturate(180%) blur(22px);-webkit-backdrop-filter:saturate(180%) blur(22px);
    border-left:1px solid var(--line);transform:translateX(104%);transition:transform .38s var(--ease);z-index:30;display:flex;flex-direction:column}
  #panel.open{transform:none;box-shadow:var(--sh-lg)}
  #phead{padding:22px 56px 16px 24px;border-bottom:1px solid var(--line);position:relative;
    background:linear-gradient(180deg,rgba(79,70,229,.06),transparent)}
  #phead .t{font-size:19px;font-weight:750;line-height:1.35;letter-spacing:.005em}
  #phead .m{font-size:12.5px;color:var(--muted);margin-top:8px}
  #pclose{position:absolute;top:16px;right:16px;border:0;background:rgba(15,23,42,.06);border-radius:50%;
    width:30px;height:30px;font-size:16px;cursor:pointer;color:#475569;transition:.2s}
  #pclose:hover{background:rgba(15,23,42,.12);transform:rotate(90deg)}
  .body{overflow:auto;padding:20px 24px 48px;scrollbar-width:thin}
  .lab{font-size:11.5px;font-weight:800;color:var(--accent);letter-spacing:.14em;margin:22px 0 9px;display:flex;align-items:center;gap:8px}
  .lab::after{content:"";flex:1;height:1px;background:var(--line)}
  .lab:first-child{margin-top:0}
  .xbtn{margin:2px 0 12px;padding:9px 16px;border:1px solid rgba(79,70,229,.35);background:var(--accent-weak);
    color:var(--accent);border-radius:999px;font-size:13.5px;font-weight:650;cursor:pointer;transition:.2s var(--ease)}
  .xbtn:hover{background:var(--accent);color:#fff;transform:translateY(-1px)}
  .explain{font-size:15px;line-height:1.95;color:var(--ink2);margin-bottom:14px;padding:16px 18px;border-radius:14px;
    background:linear-gradient(135deg,rgba(79,70,229,.07),rgba(14,165,233,.06));border:1px solid rgba(79,70,229,.14)}
  .body p{margin:0;font-size:13.5px;line-height:1.8;color:var(--ink2)}
  .body ul{margin:0;padding-left:18px}
  .body li{font-size:13px;line-height:1.9;color:var(--ink2)}
  .chips{display:flex;flex-wrap:wrap;gap:7px}
  .chip{font-size:12.5px;font-weight:500;background:rgba(79,70,229,.07);border:1px solid rgba(79,70,229,.16);color:#3730A3;border-radius:999px;padding:4px 11px}
  .chip.self{background:rgba(245,158,11,.10);border-color:rgba(245,158,11,.28);color:#92400E}
  video,img{width:100%;border-radius:12px;border:1px solid var(--line);margin:6px 0;background:#000;box-shadow:var(--sh-sm)}
  a{color:var(--accent);font-size:13px;word-break:break-all;text-decoration:none;border-bottom:1px solid rgba(79,70,229,.3)}
  a:hover{border-bottom-color:var(--accent)}
  #dock{position:fixed;right:18px;bottom:18px;display:flex;flex-direction:column;gap:2px;z-index:25;padding:5px;
    background:rgba(255,255,255,.8);backdrop-filter:blur(16px);-webkit-backdrop-filter:blur(16px);
    border:1px solid var(--line);border-radius:16px;box-shadow:var(--sh-sm)}
  #dock button{width:38px;height:38px;border:0;background:transparent;border-radius:11px;font-size:17px;cursor:pointer;color:var(--ink2);transition:.18s}
  #dock button:hover{background:var(--accent-weak);color:var(--accent)}
  #legend{position:fixed;left:16px;bottom:16px;background:rgba(255,255,255,.82);backdrop-filter:blur(16px);-webkit-backdrop-filter:blur(16px);
    border:1px solid var(--line);border-radius:16px;padding:11px 14px;font-size:12.5px;z-index:25;box-shadow:var(--sh-sm);max-width:240px}
  #legend .hd{display:flex;align-items:center;gap:8px;cursor:pointer;font-weight:700;color:var(--ink)}
  #legend .hd span{margin-left:auto;color:var(--muted);font-weight:400}
  #legend .row{display:flex;align-items:center;gap:9px;padding:4px 6px;margin:0 -6px;border-radius:8px;cursor:pointer;user-select:none;transition:.15s}
  #legend .row:hover{background:rgba(15,23,42,.04)}
  #legend .row.off{opacity:.32}
  #legend i{width:10px;height:10px;border-radius:50%;display:inline-block}
  #legend .n{margin-left:auto;color:var(--muted);font-size:11.5px;font-variant-numeric:tabular-nums}
  ::-webkit-scrollbar{width:8px}::-webkit-scrollbar-thumb{background:rgba(15,23,42,.15);border-radius:8px}
  @media(max-width:900px){.hint{display:none}#q{width:180px}#q:focus{width:200px}#panel{width:100vw}}
  #stage{touch-action:none}
  .card.faint{opacity:.34}
  .card.future{opacity:.05;pointer-events:none}
  .link{transition:opacity .2s,stroke .2s}
  .link.on{stroke:var(--accent);stroke-width:2.6}
  .link.faint{opacity:.1}
  .link-dot{fill:#B6C0D4}
  .lbg{fill:var(--card);stroke:rgba(15,23,42,.12);opacity:0;transition:opacity .18s;filter:url(#sh)}
  .stuck .lbg{opacity:.93}
  #qc{font-size:12.5px;color:var(--accent);font-weight:600;white-space:nowrap;min-width:0}
  #mini{position:fixed;right:74px;bottom:18px;z-index:25;padding:5px;background:rgba(255,255,255,.82);backdrop-filter:blur(16px);
    -webkit-backdrop-filter:blur(16px);border:1px solid var(--line);border-radius:14px;box-shadow:var(--sh-sm);cursor:pointer;line-height:0;
    transition:right .38s var(--ease)}
  #mini .vr{fill:rgba(79,70,229,.10);stroke:var(--accent);stroke-width:14}
  #toast{position:fixed;left:50%;bottom:26px;transform:translate(-50%,20px);opacity:0;z-index:40;pointer-events:none;
    padding:10px 20px;border-radius:999px;background:rgba(15,23,42,.88);color:#fff;font-size:14px;font-weight:600;transition:.3s var(--ease)}
  #toast.on{opacity:1;transform:translate(-50%,0)}
  #dock{transition:right .38s var(--ease)}
  body.panel-open #dock{right:458px} body.panel-open #mini{right:514px}
  @media(max-width:900px){#mini{display:none}body.panel-open #dock{right:18px}}
</style>
</head>
<body>
<header>
  <h1>__TITLE__</h1>
  <input id="q" placeholder="搜索标题 / 机制 / 一句话">
  <span id="qc"></span>
  <button id="play">按时间播放</button>
  <button id="project-toggle" aria-pressed="false" title="每个大板块最多5篇，按当前项目可借鉴的具体机制人工精选；青绿虚线不是学术评级，新增论文不会自动挤入名单">项目精选：关</button>
  <span class="hint">Ctrl+滚轮缩放 · 滚轮/拖拽平移 · 双击空白全览 · ←→ 切换论文 · / 搜索 · 连线为机制同构非引用</span>
</header>
<div id="stage">
  <svg id="svg"><defs>
    <filter id="sh" x="-30%" y="-30%" width="180%" height="180%">
      <feDropShadow dx="0" dy="1.5" stdDeviation="4" flood-color="#1e1b4b" flood-opacity="0.11"/>
    </filter>
  </defs><g id="vp"></g></svg>
</div>
<aside id="panel"><div id="phead"><div class="t"></div><div class="m"></div>
  <button id="pclose">×</button></div><div class="body" id="pbody"></div></aside>
<div id="dock">
  <button id="zin" title="放大">+</button>
  <button id="zout" title="缩小">−</button>
  <button id="zreset" title="回到起点">⌂</button>
  <button id="zfit" title="全览">⛶</button>
</div>
<div id="legend"></div>
<div id="mini" title="点击或拖动以导航"></div>
<div id="toast"></div>
<script>
window.BADGE = __BADGE__;
const DATA = __DATA__;
const svg = document.getElementById("svg"), vp = document.getElementById("vp"),
  stage = document.getElementById("stage"), panel = document.getElementById("panel");
let scale = 1, tx = 0, ty = 0, anim = 0;
const clamp = (v, a, b) => Math.min(b, Math.max(a, v)), cs = s => clamp(s, .12, 3);
const PANEL_W = () => panel.classList.contains("open") ? panel.offsetWidth : 0;
const byId = {}, cards = {}, links = {}, kids = {}, stickies = [];
DATA.nodes.forEach(n => {
  byId[n.id] = n;
  n.hay = [n.title, n.mechanism, n.one_liner, n.lane, n.branch, (n.tags||[]).join(" "), (n.concepts||[]).join(" "), n.explain].join(" ").toLowerCase();
});
DATA.nodes.forEach(n => { if(n.parent && byId[n.parent]) (kids[n.parent] = kids[n.parent] || []).push(n.id); });

function el(tag, attrs, parent){
  const n = document.createElementNS("http://www.w3.org/2000/svg", tag);
  for(const [k,v] of Object.entries(attrs || {})) if(v != null) n.setAttribute(k, v);
  (parent || vp).appendChild(n); return n;
}

/* ---------- 影响力光圈：按引用速率 cpm（次/月）分 4 档 ----------
 * 用速率而不是绝对引用数，是为了让 2026 年的新论文不至于全被压成 0：
 * 刚发两个月被引 3 次（1.5/月）比两年前被引 20 次（0.8/月）更热。
 * 四档阈值：0 < cpm < 0.15 / 0.15–0.40 / 0.40–1.00 / ≥ 1.00
 * cpm 缺失或 0 不发光。*/
const GLOW_TIERS = [
  {ring:2.0, pad:3.5, halo:7,  badge:"#5F79C4"},   // < 0.15 次/月
  {ring:3.0, pad:4.0, halo:10, badge:"#4A5FE0"},   // 0.15–0.40
  {ring:4.5, pad:4.5, halo:14, badge:"#7C3AED"},   // 0.40–1.00
  {ring:6.0, pad:5.0, halo:18, badge:"#B06500"},   // ≥ 1.00
];
const RATE_CUTS = [0.15, 0.40, 1.00];
function rateTier(cpm){
  if(cpm == null || !isFinite(cpm) || cpm <= 0) return 0;
  if(cpm < RATE_CUTS[0]) return 1;
  if(cpm < RATE_CUTS[1]) return 2;
  if(cpm < RATE_CUTS[2]) return 3;
  return 4;
}
function numText(c){ return c >= 1000 ? (c/1000).toFixed(c >= 10000 ? 0 : 1) + "k" : String(c); }
function rateText(v){ return (Math.round(v*10)/10).toFixed(1); }
/* 光晕沉到卡面之下：只在卡片外沿溢出，卡内毛玻璃/文字不被着色 */
function glowTier(n){ return Math.max(rateTier(n.cpm), n.publication?.tier || 0); }
function drawGlow(g, n){
  const w = DATA.card.w, h = DATA.card.h, t = glowTier(n);
  if(t){
    const T = GLOW_TIERS[t - 1], pad = T.pad + T.ring / 2;
    const gl = el("g", {class:"glow g" + t}, g);
    el("rect", {class:"halo", x:-pad, y:-pad, width:w + pad*2, height:h + pad*2,
      rx:16 + pad, "stroke-width":T.halo}, gl);
    el("rect", {class:"ring", x:-pad, y:-pad, width:w + pad*2, height:h + pad*2,
      rx:16 + pad, "stroke-width":T.ring}, gl);
    g.insertBefore(gl, g.firstChild);
  }
  if(n.publication?.tier){
    const badge = el("text", {class:"venue-badge", x:15, y:67, fill:"#7C3AED"}, g);
    badge.textContent = n.publication.name + " · " + n.publication.rank;
    el("title", {}, badge).textContent = "出版等级补充光效，不等同单篇质量；来源见详情";
  } else {
    const txt = n.publication?.label || "发表未核实";
    const bg = el("g", {class:"publication-warning"}, g);
    el("rect", {x:12,y:57,width:txt.length*10+14,height:17,rx:4,fill:"#FFF4DB",stroke:"#D69E36","stroke-width":.7}, bg);
    el("text", {x:19,y:69,fill:"#92400E","font-size":10,"font-weight":700}, bg).textContent = txt;
    el("title", {}, bg).textContent = n.publication?.caution || "出版状态尚未核实";
  }
  // 右下角：被引量 + 速率（速率缺失就只写被引）
  const parts = [];
  if(n.citations != null) parts.push("被引 " + numText(n.citations));
  if(n.cpm != null && n.cpm > 0) parts.push(rateText(n.cpm) + "/月");
  if(parts.length){
    const b = el("text", {class:"cite-badge", x:w - 11, y:h - 13, "text-anchor":"end",
      fill:t ? GLOW_TIERS[t - 1].badge : "#7C8698"}, g);
    b.textContent = parts.join(" · ");
  }
}
/* 图谱内被后继工作继承的次数：小胶囊，压在引用标记上方 */
function drawInherit(g, n){
  if(!n.inherited) return;
  const w = DATA.card.w, h = DATA.card.h, txt = "被继承 " + n.inherited;
  const pw = txt.length * 6 + 16, x = w - 11 - pw, y = h - 44;
  el("rect", {x, y, width:pw, height:16, rx:8, fill:"rgba(13,148,136,.12)",
    stroke:"rgba(13,148,136,.28)", "stroke-width":1}, g);
  el("text", {class:"inherit-badge", x:x + pw/2, y:y + 11.5, "text-anchor":"middle", fill:"#0F766E"}, g)
    .textContent = txt;
}

/* ---------- 相机 ---------- */
function apply(){
  const w = svg.clientWidth, h = svg.clientHeight, m = 120;
  tx = clamp(tx, m - DATA.width*scale, Math.max(24, (w - DATA.width*scale)/2)); ty = clamp(ty, m - DATA.height*scale, Math.max(14, (h - DATA.height*scale)/2));
  vp.setAttribute("transform", `translate(${tx},${ty}) scale(${scale})`);
  stick(); drawMini();
}
function flyTo(ns, ntx, nty, dur){
  cancelAnimationFrame(anim);
  const s0 = scale, x0 = tx, y0 = ty, t0 = performance.now(); dur = dur || 560;
  (function step(now){
    const k = Math.min(1, (now - t0)/dur), e = 1 - Math.pow(1 - k, 3);
    scale = s0 + (ns - s0)*e; tx = x0 + (ntx - x0)*e; ty = y0 + (nty - y0)*e; apply();
    if(k < 1) anim = requestAnimationFrame(step);
  })(t0);
}
function zoomAt(mx, my, ns){ ns = cs(ns); tx = mx - (mx - tx)*(ns/scale); ty = my - (my - ty)*(ns/scale); scale = ns; apply(); }
function zoomBtn(k){ cancelAnimationFrame(anim); const w = svg.clientWidth - PANEL_W(); zoomAt(w/2, svg.clientHeight/2, scale*k); }
function fitAll(){
  const w = svg.clientWidth, h = svg.clientHeight, s = Math.min((w-60)/DATA.width, (h-40)/DATA.height, 1.2);
  flyTo(s, Math.max(16, (w - DATA.width*s)/2), 14);
}
function resetView(now){ const i = DATA.init; now ? (scale = i.scale, tx = i.tx, ty = i.ty, apply()) : flyTo(i.scale, i.tx, i.ty); }
function focusNode(n){
  const w = svg.clientWidth - PANEL_W(), h = svg.clientHeight, ns = cs(Math.max(scale, .85));
  const cx = (DATA.labelW*ns + w)/2;   // 让出左侧固定标签列
  flyTo(ns, cx - (n.x + DATA.card.w/2)*ns, h/2 - (n.y + DATA.card.h/2)*ns);
}
function focusLane(l){
  const w = svg.clientWidth - PANEL_W(), h = svg.clientHeight;
  const s = cs(Math.min((w-50)/(DATA.labelW + l.plotW + 32), (h-40)/(l.height+20), 1));
  flyTo(s, 20 - 8*s, 20 - (l.top - 10)*s);
}

/* ---------- 吸附标签：随镜头滑进可视区 ---------- */
function mkSticky(parent, kind, lane, extra){
  const g = el("g", {class:"stk"}, parent);
  return {g, kind, lane, ...extra};
}
function finishSticky(s){
  const bb = s.g.getBBox(); s.bb = bb;
  el("rect", {class:"lbg", x:bb.x-9, y:bb.y-5, width:bb.width+18, height:bb.height+10, rx:10}, s.g);
  s.g.insertBefore(s.g.lastChild, s.g.firstChild);
  stickies.push(s);
}
function stick(){
  const L = -tx/scale, T = -ty/scale, px = 16/scale, py = 14/scale, laneX = {};
  for(const s of stickies){
    const l = s.lane, R = DATA.labelW + l.plotW + 32 - 10, B = l.top + l.height - 10, bb = s.bb;
    let dx = 0, dy = 0, anchor = L + px;
    if(s.kind === "year") anchor = Math.max(anchor, laneX[l.name] + DATA.labelW - 36);
    dx = clamp(anchor - bb.x, 0, Math.max(0, (s.right || R) - (bb.x + bb.width) ));
    if(s.kind !== "branch") dy = clamp(T + py - bb.y, 0, Math.max(0, B - (bb.y + bb.height)));
    if(s.kind === "lane") { laneX[l.name] = bb.x + dx; l.dy = dy; }
    if(s.kind === "year") dy = l.dy || 0;
    s.g.setAttribute("transform", `translate(${dx},${dy})`);
    s.g.classList.toggle("stuck", dx > 1 || dy > 1);
  }
}

/* ---------- 构建 ---------- */
function build(){
  const laneColor = {}; DATA.lanes.forEach(l => laneColor[l.name] = l.color);
  DATA.lanes.forEach((l, li) => {
    el("rect", {class:"lane-box", x:8, y:l.top-10, width:DATA.labelW + l.plotW + 24, height:l.height+8, rx:20,
      fill: li % 2 ? "var(--band-b)" : "var(--band-a)"});
    el("rect", {x:9, y:l.top-6, width:5, height:l.height-4, rx:2.5, fill:l.color, opacity:.9});
    l.years.forEach(y => el("line", {class:"year-sep", x1:y.x, y1:l.top-2, x2:y.x, y2:l.top+l.height-6}));
    l.branches.forEach(b => {
      const baseY = b.y + DATA.card.h + 16;
      el("line", {class:"axis-line", x1:DATA.labelW-14, y1:baseY, x2:DATA.labelW + l.plotW - 10, y2:baseY});
    });
  });
  DATA.nodes.forEach(n => {
    if(n.sx == null) return;
    const x1 = n.sx, y1 = n.sy, x2 = n.x, y2 = n.y + DATA.card.h/2, mid = (x1 + x2)/2;
    const path = el("path", {d:`M${x1},${y1} C${mid},${y1} ${mid},${y2} ${x2},${y2}`, class: n.cross ? "link cross" : "link"});
    const dot = el("circle", {cx:x1, cy:y1, r:2.6, class:"link-dot"});
    links[n.id] = {path, dot};
    links[n.id].show = v => { path.style.display = dot.style.display = v ? "" : "none"; };
  });
  DATA.nodes.forEach(n => {
    const g = el("g", {class:"card", "data-id":n.id, transform:`translate(${n.x},${n.y})`}); cards[n.id] = g;
    el("title", {}, g).textContent = n.one_liner || n.title;
    el("rect", {class:"bg", width:DATA.card.w, height:DATA.card.h, rx:16}, g);
    drawGlow(g, n);   // 引用速率 cpm 分档炫光 + 被引/速率标记（原手选 n.key 名单已废）
    drawInherit(g, n); // 图谱内被继承次数
    const focus = el("g", {class:"project-mark"}, g);
    el("rect", {x:-11,y:-11,width:DATA.card.w+22,height:DATA.card.h+22,rx:24,
      fill:"none",stroke:"#0D9488","stroke-width":3,"stroke-dasharray":"10 5"}, focus);
    el("title", {}, focus).textContent = (n.project_relevance || []).join(" ");
    el("rect", {class:"stripe", width:5, height:DATA.card.h-16, x:1.5, y:8, fill:laneColor[n.lane] || "#888", rx:2.5, opacity:.9}, g);
    const FREE = {"免训":"免训", "推理期技巧":"推理期"};
    const tagList = (FREE[n.training] ? [{t:FREE[n.training], free:true}] : []).concat((n.tags || []).map(t => ({t, free:false})));
    let xRight = DATA.card.w - 10;
    tagList.slice(0, 3).forEach(o => {
      const w = o.t.length*10.5 + 12; if(xRight - w < 12) return;
      el("rect", {x:xRight-w, y:9, width:w, height:17, rx:8, fill:o.free ? "#0E9F6E" : (laneColor[n.lane] || "#6b7280"), opacity:o.free ? 1 : .12}, g);
      el("text", {x:xRight-w+6, y:21.5, class:"tag-t", fill:o.free ? "#fff" : (laneColor[n.lane] || "#6b7280")}, g).textContent = o.t;
      xRight -= w + 5;
    });
    const t1 = el("text", {class:"t-title", x:15, y:50}, g); t1.textContent = n.title;
    while(t1.textContent.length > 4 && t1.getComputedTextLength() > DATA.card.w - 24) t1.textContent = t1.textContent.slice(0, -2) + "…";
    el("text", {class:"t-date", x:15, y:DATA.card.h-14}, g).textContent =
      n.date.slice(0, 7) + (n.precision === "month" || n.precision === "unknown" ? "" : "-" + n.date.slice(8, 10));
    g.addEventListener("click", ev => { ev.stopPropagation(); if(moved < 6) openPanel(n); });
    g.addEventListener("mouseenter", () => { hoverId = n.id; refresh(); });
    g.addEventListener("mouseleave", () => { hoverId = null; refresh(); });
  });
  // 标签层放最上面，吸附时才不会被卡片盖住
  const lab = el("g", {id:"labels"});
  DATA.lanes.forEach(l => {
    const s = mkSticky(lab, "lane", l);
    el("text", {class:"lane-name", x:26, y:l.top+16, fill:l.color}, s.g).textContent = l.name;
    el("text", {class:"lane-count", x:26, y:l.top+34}, s.g).textContent = l.count + " 篇";
    finishSticky(s);
    l.branches.forEach(b => { if(!b.name) return;
      const t = mkSticky(lab, "branch", l);
      el("circle", {cx:30, cy:b.y+30, r:3.4, fill:l.color, opacity:.75}, t.g);
      el("text", {class:"branch", x:40, y:b.y+34}, t.g).textContent = b.name;
      finishSticky(t);
    });
    l.columns.forEach(c => {
      el("line", {class:"time-tick", x1:c.x-13, y1:l.top+42, x2:c.x-13, y2:l.top+l.height-6}, lab);
      el("text", {class:"time-label", x:c.x+5, y:l.top+43}, lab).textContent = c.label;
    });
    l.years.forEach((y, i) => {
      const t = mkSticky(lab, "year", l, {right: (l.years[i+1] ? l.years[i+1].x : DATA.labelW + l.plotW + 22) - 8});
      el("text", {class:"year-label", x:y.x+6, y:l.top+16, fill:l.color}, t.g).textContent = y.label;
      finishSticky(t);
    });
  });
}

/* ---------- 状态：高亮脉络 / 搜索 / 图例 / 播放 ---------- */
let activeId = null, hoverId = null, q = "", reveal = null; const hidden = new Set();
function related(id){
  const s = new Set([id]); let c = id;
  while(byId[c] && byId[c].parent && byId[byId[c].parent]){ c = byId[c].parent; s.add(c); }
  const st = [id]; while(st.length){ (kids[st.pop()] || []).forEach(k => { s.add(k); st.push(k); }); }
  return s;
}
let projectMode = false;
const projectToggle = document.getElementById("project-toggle");
projectToggle.onclick = () => {
  projectMode = !projectMode;
  projectToggle.setAttribute("aria-pressed", String(projectMode));
  projectToggle.textContent = projectMode
    ? "项目精选：开 · " + DATA.nodes.filter(n => n.project_relevance?.length).length + " 篇"
    : "项目精选：关";
  refresh();
};
function refresh(){
  const f = reveal ? null : (hoverId || activeId), rel = f ? related(f) : null; let hit = 0;
  DATA.nodes.forEach(n => {
    const c = cards[n.id], hide = hidden.has(n.lane), match = !q || n.hay.includes(q);
    c.style.display = hide ? "none" : ""; if(match && !hide) hit++;
    c.classList.toggle("dim", !match);
    c.classList.toggle("faint", !!rel && !rel.has(n.id));
    c.classList.toggle("future", !!reveal && !reveal.has(n.id));
    c.classList.toggle("active", n.id === activeId);
    c.classList.toggle("project-related", projectMode && !!n.project_relevance?.length);
    c.classList.toggle("project-muted", projectMode && !n.project_relevance?.length && !rel?.has(n.id));
    const lk = links[n.id]; if(!lk) return;
    const p = byId[n.parent], gone = hide || hidden.has(p.lane) || (reveal && !(reveal.has(n.id) && reveal.has(p.id)));
    lk.show(!gone);
    const on = !!rel && rel.has(n.id) && rel.has(p.id);
    lk.path.classList.toggle("on", on);
    lk.path.classList.toggle("faint", (!!rel && !on) || (!!q && !(match && p.hay.includes(q))));
  });
  document.getElementById("qc").textContent = q ? hit + " 篇匹配" : "";
}
function setActive(n){
  activeId = n ? n.id : null; refresh();
  try{ history.replaceState(null, "", n ? "#" + n.id : location.pathname + location.search); }catch(e){}
}
function closePanel(){ panel.classList.remove("open"); document.body.classList.remove("panel-open"); setActive(null); }
/* ---------- 面板「影响力」：被引 / 速率 / 被继承 / 可复现 ---------- */
const REPRO = {
  code_weights: ["代码 + 权重", "全开，可直接复现"],
  code_only:    ["仅代码", "权重未放出"],
  paper_only:   ["仅论文", "未开源"],
  closed:       ["闭源", "无公开实现"],
};
const TIER_WORD = ["", "微微发光", "小热", "明显偏热", "最热一档"];
function addImpact(b, n){
  const t = rateTier(n.cpm), rows = [];
  rows.push(["被引", n.citations != null
    ? `<b>${n.citations}</b> 次 <span class="u">OpenAlex 口径</span>`
    : `<span class="u">暂未收录</span>`]);
  rows.push(["引用速率", (n.cpm != null && n.cpm > 0)
    ? `<b>${rateText(n.cpm)}</b> 次/月 <span class="u">≈ 每月新增被引，${TIER_WORD[t]}（第 ${t}/4 档）</span>`
    : (n.cpm === 0 ? `<b>0.0</b> 次/月 <span class="u">引用记录为零；出版等级可能另行提供光效</span>`
                   : `<span class="u">无数据（未统计速率）</span>`)]);
  rows.push(["图谱内被继承", n.inherited > 0
    ? `<b>${n.inherited}</b> 篇后续工作直接接在它上面${n.inherited_chain > 0 ? ` <span class="u">另有 ${n.inherited_chain} 篇经传递链继承</span>` : ""}`
    : `<span class="u">暂无</span>`]);
  const rp = REPRO[n.repro];
  if(rp) rows.push(["可复现性", `<b>${rp[0]}</b> <span class="u">${rp[1]}</span>`]);

  const lab = document.createElement("div"); lab.className = "lab"; lab.textContent = "影响力";
  const box = document.createElement("div"); box.className = "imp";
  rows.forEach(([k, v]) => {
    const r = document.createElement("div"); r.className = "imp-row";
    const a = document.createElement("span"); a.className = "imp-k"; a.textContent = k;
    const c = document.createElement("span"); c.className = "imp-v"; c.innerHTML = v;
    r.appendChild(a); r.appendChild(c); box.appendChild(r);
  });
  b.appendChild(lab); b.appendChild(box);
  const note = document.createElement("p"); note.className = "imp-note";
  note.textContent = "光效档位取引用速率与已核实出版等级的较高值，不叠加计分。CCF A 或 ICORE A* 主会/期刊提供第3档、CCF B第2档、CCF C第1档；第4档仍需引用信号。出版等级不是单篇质量保证，未核实、投稿中及Workshop不自动晋档。";
  b.appendChild(note);
  const pub = n.publication || {};
  const warning=document.createElement("div"); warning.className="p publication-caution";
  warning.textContent=pub.label+"："+pub.caution;
  if(!pub.verified){warning.style.cssText="padding:10px 12px;background:#FFF4DB;border-left:3px solid #D69E36;border-radius:6px;color:#92400E";}
  b.appendChild(warning);
  const heading = document.createElement("div"); heading.className = "lab"; heading.textContent = "出版证据与项目相关性"; b.appendChild(heading);
  const text = document.createElement("div"); text.className = "p";
  text.textContent = pub.tier ? `${pub.name} ${pub.year || ""} · ${pub.rank} · 出版补充第${pub.tier}/4档` : `出版等级未启用：${n.venue || "尚无已核实发表信息"}。原始venue文案不作为录用证明。`;
  b.appendChild(text);
  if(pub.evidence){
    const ev=document.createElement("div"); ev.className="p";
    ev.textContent="核验依据："+pub.evidence;
    b.appendChild(ev);
  }
  if(pub.verification_confidence){
    const cf=document.createElement("p"); cf.className="imp-note";
    cf.textContent="状态核验置信度："+({high:"高",medium:"中",low:"低"}[pub.verification_confidence] || pub.verification_confidence)+"。这是对状态证据的把握，不是论文质量评分。";
    b.appendChild(cf);
  }
  [["发表证据",pub.source],["等级依据",pub.rank_source]].forEach(([label,url]) => {
    if(!url?.startsWith("https://")) return;
    const a=document.createElement("a"); a.href=url; a.target="_blank"; a.rel="noopener noreferrer"; a.textContent=label+" ↗"; a.style.marginRight="16px"; b.appendChild(a);
  });
  const relevance = document.createElement("div"); relevance.className = "p";
  relevance.textContent = n.project_relevance?.length ? "规则匹配 · " + n.project_relevance.join(" ") : "暂未匹配当前项目的高相关规则，不表示该论文不重要。";
  b.appendChild(relevance);
}
function openPanel(n){
  setActive(n);
  panel.querySelector("#phead .t").textContent = n.title;
  const meta = [n.date, n.precision === "month" ? "日期只到月" : "", n.training, n.status, n.lane + " / " + (n.branch || "主支")]
    .filter(Boolean).join(" · ");
  panel.querySelector("#phead .m").textContent = meta;

  const b = document.getElementById("pbody");
  b.innerHTML = "";
  const add = (cls, text) => { const d = document.createElement("div"); d.className = cls; d.textContent = text; b.appendChild(d); };
  if(n.explain){
    const btn = document.createElement("button");
    btn.className = "xbtn";
    btn.textContent = "▶ 直白讲解";
    const box = document.createElement("div");
    box.className = "explain";
    box.textContent = n.explain;
    box.style.display = "none";
    btn.onclick = () => {
      const open = box.style.display !== "none";
      box.style.display = open ? "none" : "block";
      btn.textContent = open ? "▶ 直白讲解" : "▼ 收起讲解";
    };
    b.appendChild(btn);
    b.appendChild(box);
  }
  if((n.concepts||[]).length){
    add("lab", "做法概念");
    const cw = document.createElement("div"); cw.className = "cpt";
    n.concepts.forEach(c => {
      const chip = document.createElement("button");
      chip.className = "cpt-chip"; chip.textContent = c;
      chip.onclick = ev => { ev.stopPropagation(); closePanel(); const qi2 = document.getElementById("q"); qi2.value = c; qi2.dispatchEvent(new Event("input")); };
      cw.appendChild(chip);
    });
    b.appendChild(cw);
  }
  if(n.one_liner){ add("lab", "一句话"); add("p", n.one_liner); }
  addImpact(b, n);
  if(n.detail){ window.renderDetail(b, n.detail); }
  else if(n.mechanism){ add("lab", "机制"); add("p", n.mechanism); }
  if(n.key_numbers && n.key_numbers.length){
    add("lab", "关键数字");
    const c = document.createElement("div"); c.className = "chips";
    n.key_numbers.forEach(k => { const s = document.createElement("span"); s.className = "chip"; s.textContent = k; c.appendChild(s); });
    b.appendChild(c);
  }
  if(n.self_measured && n.self_measured.length){
    add("lab", "我们自测（非论文指标）");
    const c = document.createElement("div"); c.className = "chips";
    n.self_measured.forEach(k => { const s = document.createElement("span"); s.className = "chip self"; s.textContent = k; c.appendChild(s); });
    b.appendChild(c);
  }
  if(n.media && n.media.length){
    add("lab", "素材");
    n.media.forEach(m => {
      const src = DATA.prefix + m;
      if(/\.(mp4|webm|mov)$/i.test(m)){
        const v = document.createElement("video");
        v.src = src; v.controls = true; v.muted = true; v.playsInline = true; v.preload = "metadata";
        b.appendChild(v);
      } else {
        const img = document.createElement("img"); img.src = src; img.loading = "lazy";
        b.appendChild(img);
      }
    });
  }
  if(n.links && n.links.length){
    add("lab", "链接");
    n.links.forEach(u => { const a = document.createElement("a"); a.href = u; a.target = "_blank"; a.textContent = u; b.appendChild(a); b.appendChild(document.createElement("br")); });
  }
  if(n.note){ add("lab", "备注"); add("p", n.note); }
  panel.classList.add("open"); document.body.classList.add("panel-open"); focusNode(n); b.scrollTop = 0;
}

document.getElementById("pclose").onclick = closePanel;

/* ---------- 输入：拖拽 / 双指缩放 / 滚轮 ---------- */
const ptrs = new Map(); let moved = 0, pinch0 = null;
svg.addEventListener("pointerdown", ev => {
  if(ev.pointerType === "mouse" && ev.button !== 0) return;
  cancelAnimationFrame(anim); ptrs.set(ev.pointerId, {x:ev.clientX, y:ev.clientY});
  if(ptrs.size === 1) moved = 0;
  if(ptrs.size === 2){ const [a, b] = [...ptrs.values()]; pinch0 = {d:Math.hypot(a.x-b.x, a.y-b.y), s:scale}; }
  stage.classList.add("drag");
});
window.addEventListener("pointermove", ev => {
  const p = ptrs.get(ev.pointerId); if(!p) return;
  const dx = ev.clientX - p.x, dy = ev.clientY - p.y; p.x = ev.clientX; p.y = ev.clientY;
  if(ptrs.size === 1){ moved += Math.abs(dx) + Math.abs(dy); tx += dx; ty += dy; apply(); }
  else if(pinch0){
    const [a, b] = [...ptrs.values()], r = svg.getBoundingClientRect(); moved = 99;
    zoomAt((a.x+b.x)/2 - r.left, (a.y+b.y)/2 - r.top, pinch0.s * Math.hypot(a.x-b.x, a.y-b.y) / pinch0.d);
  }
});
const endPtr = ev => { ptrs.delete(ev.pointerId); if(ptrs.size < 2) pinch0 = null; if(!ptrs.size) stage.classList.remove("drag"); };
window.addEventListener("pointerup", endPtr); window.addEventListener("pointercancel", endPtr);
svg.addEventListener("click", ev => { if(!ev.target.closest(".card") && moved < 6 && panel.classList.contains("open")) closePanel(); });
svg.addEventListener("wheel", ev => {
  ev.preventDefault(); cancelAnimationFrame(anim);
  if(ev.ctrlKey || ev.metaKey){            // 触控板捏合 / Ctrl+滚轮 = 缩放
    const r = svg.getBoundingClientRect();
    zoomAt(ev.clientX - r.left, ev.clientY - r.top, scale * Math.exp(-ev.deltaY * (Math.abs(ev.deltaY) > 40 ? .0016 : .01)));
  } else {                                  // 普通滚轮 / 双指滑动 = 平移
    const sw = ev.shiftKey && !ev.deltaX; tx -= sw ? ev.deltaY : ev.deltaX; ty -= sw ? 0 : ev.deltaY; apply();
  }
}, {passive:false});
svg.addEventListener("dblclick", ev => { if(!ev.target.closest(".card")) fitAll(); });
zin.onclick = () => zoomBtn(1.25); zout.onclick = () => zoomBtn(1/1.25);
zreset.onclick = () => resetView(); zfit.onclick = fitAll;

/* ---------- 搜索 / 图例 / 键盘 ---------- */
const qi = document.getElementById("q");
qi.addEventListener("input", () => { q = qi.value.trim().toLowerCase(); refresh(); });
qi.addEventListener("keydown", ev => {
  if(ev.key === "Enter"){ const n = DATA.nodes.find(x => !hidden.has(x.lane) && (!q || x.hay.includes(q))); if(n) { setActive(n); focusNode(n); } }
  if(ev.key === "Escape"){ qi.value = ""; q = ""; refresh(); qi.blur(); }
});
const legend = document.getElementById("legend"), hd = document.createElement("div"), rows = document.createElement("div");
hd.className = "hd"; hd.innerHTML = "路线导航 <span>−</span>"; legend.append(hd, rows);
hd.onclick = () => { const c = rows.style.display === "none"; rows.style.display = c ? "" : "none"; hd.lastChild.textContent = c ? "−" : "+"; };
DATA.lanes.forEach(l => {
  const row = document.createElement("div"); row.className = "row"; row.title = "点名称飞到该路线；点圆点显示/隐藏";
  row.innerHTML = `<i style="background:${l.color}"></i><span>${l.name}</span><span class="n">${l.count}</span>`;
  row.querySelector("i").onclick = ev => { ev.stopPropagation();
    hidden.has(l.name) ? hidden.delete(l.name) : hidden.add(l.name); row.classList.toggle("off", hidden.has(l.name)); refresh(); };
  row.onclick = () => { hidden.delete(l.name); row.classList.remove("off"); refresh(); focusLane(l); };
  rows.appendChild(row);
});
const laneOrder = n => DATA.nodes.filter(x => x.lane === n.lane).sort((a, b) => a.date.localeCompare(b.date));
window.addEventListener("keydown", ev => {
  if(ev.target.tagName === "INPUT") return;
  if(ev.key === "/"){ ev.preventDefault(); qi.focus(); }
  else if(ev.key === "Escape"){ timer ? stopPlay() : closePanel(); }
  else if((ev.key === "ArrowRight" || ev.key === "ArrowLeft") && activeId){
    const l = laneOrder(byId[activeId]), i = l.findIndex(x => x.id === activeId) + (ev.key === "ArrowRight" ? 1 : -1);
    if(l[i]){ ev.preventDefault(); openPanel(l[i]); }
  }
});

/* ---------- 缩略导航 ---------- */
const mini = document.getElementById("mini"), MW = 150, MH = Math.round(MW * DATA.height / DATA.width);
const msvg = el("svg", {viewBox:`0 0 ${DATA.width} ${DATA.height}`, width:MW, height:MH}, mini);
DATA.lanes.forEach(l => el("rect", {x:8, y:l.top-10, width:DATA.labelW + l.plotW + 24, height:l.height+8, fill:l.color, opacity:.14, rx:30}, msvg));
DATA.nodes.forEach(n => el("rect", {x:n.x, y:n.y, width:DATA.card.w, height:DATA.card.h, fill:(DATA.lanes.find(l => l.name === n.lane) || {}).color, opacity:.8, rx:14}, msvg));
const vr = el("rect", {class:"vr", rx:10}, msvg);
function drawMini(){
  const w = svg.clientWidth, h = svg.clientHeight;
  vr.setAttribute("x", -tx/scale); vr.setAttribute("y", -ty/scale); vr.setAttribute("width", w/scale); vr.setAttribute("height", h/scale);
}
let mdrag = false;
const miniGo = ev => { const r = msvg.getBoundingClientRect(), w = svg.clientWidth - PANEL_W();
  tx = w/2 - (ev.clientX - r.left)/r.width*DATA.width*scale; ty = svg.clientHeight/2 - (ev.clientY - r.top)/r.height*DATA.height*scale; apply(); };
mini.addEventListener("pointerdown", ev => { cancelAnimationFrame(anim); mdrag = true; miniGo(ev); ev.stopPropagation(); });
window.addEventListener("pointermove", ev => { if(mdrag) miniGo(ev); });
window.addEventListener("pointerup", () => mdrag = false);

/* ---------- 按时间播放：镜头跟随、逐个亮起 ---------- */
let timer = null; const playBtn = document.getElementById("play"), toast = document.getElementById("toast");
function stopPlay(){ clearInterval(timer); timer = null; reveal = null; playBtn.textContent = "按时间播放"; toast.classList.remove("on"); refresh(); }
playBtn.onclick = () => {
  if(timer){ stopPlay(); return; }
  const order = DATA.nodes.filter(n => !hidden.has(n.lane)).sort((a, b) => a.date.localeCompare(b.date));
  closePanel(); reveal = new Set(); playBtn.textContent = "■ 停止"; let i = 0;
  const step = () => {
    if(i >= order.length){ const last = order[order.length-1]; stopPlay(); setActive(last); return; }
    const n = order[i++]; reveal.add(n.id); setActive(n); focusNode(n);
    toast.textContent = `${n.date.slice(0, 7)} · ${n.title}　${i}/${order.length}`; toast.classList.add("on");
  };
  step(); timer = setInterval(step, 1300);
};

build(); resetView(true); refresh();
const h0 = decodeURIComponent(location.hash.slice(1));
if(byId[h0]) setTimeout(() => openPanel(byId[h0]), 60);
</script>

</body>
</html>
"""


def main():
    if len(sys.argv) < 4:
        raise SystemExit("用法: build_map.py data.yaml out.html TITLE [media_prefix]")
    src, out, title = Path(sys.argv[1]), Path(sys.argv[2]), sys.argv[3]
    prefix = sys.argv[4] if len(sys.argv) > 4 else ""
    nodes, order, color = load(src)
    signal_file = src.parent / "paper-signals.yaml"
    signals = yaml.safe_load(signal_file.read_text(encoding="utf-8")) if signal_file.exists() else {}
    data = layout(nodes, order, color, signals)
    data["prefix"] = prefix
    missing = validate(data, out.parent, prefix)
    html = HTML.replace("__TITLE__", title)
    html = html.replace("__BADGE__", json.dumps(BADGE, ensure_ascii=False))
    _css, _js = [], []
    for _f in ("katex_inline.css", "panel_detail.css", "concept_timeline.css"):
        _p = src.parent / _f
        if _p.exists():
            _css.append(_p.read_text(encoding="utf-8"))
    for _f in ("katex.min.js", "panel_detail.js", "concept_timeline.js"):
        _p = src.parent / _f
        if _p.exists():
            _js.append(_p.read_text(encoding="utf-8"))
    if _css:
        html = html.replace("</head>", "<style>" + "\n".join(_css) + "</style>\n</head>", 1)
    if _js:
        html = html.replace("</body>", "<script>" + "\n".join(_js) + "</script>\n</body>", 1)
    html = html.replace("__DATA__", json.dumps(data, ensure_ascii=False))
    out.write_text(html, encoding="utf-8")
    print(f"wrote {out.name}  nodes={len(data['nodes'])} lanes={len(data['lanes'])} size={int(data['width'])}x{int(data['height'])}")
    if missing:
        print("缺素材：")
        for m in missing:
            print("  -", m)
    else:
        print("素材全部存在")


if __name__ == "__main__":
    main()
