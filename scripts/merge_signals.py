# -*- coding: utf-8 -*-
"""合并四个并行核实结果，修正口径偏差，写回 paper-signals.yaml。"""
import glob
import json
import os
import shutil

import yaml

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCR = os.path.join(ROOT, "scripts")

# 新增会议/期刊的分级依据（CCF 2022 推荐国际学术会议和期刊目录）
AI = "https://www.ccf.org.cn/Academic_Evaluation/AI/"
CG = "https://www.ccf.org.cn/Academic_Evaluation/CGAndMT/"
NEW_VENUES = {
    "AAAI": {"tier": 3, "rank": "CCF A", "source": AI},
    "SIGGRAPH": {"tier": 3, "rank": "CCF A", "source": CG},
    "WACV": {"tier": 2, "rank": "ICORE2026 A", "source": "https://portal.core.edu.au/conf-ranks/?search=WACV&by=all&source=all&sort=atitle&page=1"},
}

CONF_VENUES = {"NeurIPS", "ICML", "ICLR", "CVPR", "ICCV", "ECCV", "ACCV",
               "WACV", "ACM MM", "AAAI", "IJCAI", "SIGGRAPH", "SIGGRAPH Asia",
               "3DV", "BMVC", "CoRL", "ICRA", "RSS"}

# 手工修正：会议在 arXiv 首发之前已举行，第三方索引的会议归属不成立
YEAR_CONFLICT = {
    "longlive": "LongLive arXiv 首发 2025-09，而 ICLR 2025 已于 2025-04 举行，第三方索引的 ICLR 2025 归属在时间上不成立，按预印本处理。",
    "moc": "MoC arXiv 首发 2025-08，而 ICLR 2025 已于 2025-04 举行，第三方索引的 ICLR 2025 归属在时间上不成立，按预印本处理。",
    "zo3t": "Zo3t arXiv 首发 2025-09，而 AAAI 2025 已于 2025-02 举行，第三方索引的 AAAI 2025 归属在时间上不成立，按预印本处理。",
}


def main():
    sig_path = os.path.join(ROOT, "paper-signals.yaml")
    cur = yaml.safe_load(open(sig_path, encoding="utf-8"))

    recs = {}
    for f in sorted(glob.glob(os.path.join(SCR, "verify_out_[1-4].json"))):
        for r in json.load(open(f, encoding="utf-8")):
            recs[r["id"]] = r
    print("合并 %d 条核实结果" % len(recs))

    fixed = []
    for nid, r in recs.items():
        venue = (r.get("venue") or "").strip()
        track = r.get("track") or "unknown"
        status = r.get("status") or "unknown"

        # 规则 1：会议论文集的 journal_ref 不应把 track 记成 journal
        if track == "journal" and venue in CONF_VENUES:
            track = "main"
            fixed.append((nid, "track journal→main（会议论文集）"))
        # 规则 2：审稿中不涉及具体发表载体
        if status == "submitted" and track == "journal":
            track = "unknown"
            venue = ""
            fixed.append((nid, "submitted 状态清空 track/venue"))
        # 规则 3：comments 明确 Published at 的应为 published
        if status == "accepted" and "published at" in (r.get("evidence") or "").lower():
            status = "published"
            fixed.append((nid, "accepted→published（comments 写 Published at）"))

        if nid in YEAR_CONFLICT:
            status, venue, track = "preprint", "", "unknown"
            r["evidence"] = YEAR_CONFLICT[nid]
            r["confidence"] = "low"
            r["year"] = None
            fixed.append((nid, "降为 preprint（会议年份早于 arXiv 首发）"))

        r["status"], r["venue"], r["track"] = status, venue, track

    # 写入 papers
    papers = cur["papers"]
    added = 0
    for nid in sorted(recs):
        if nid in papers:
            continue
        r = recs[nid]
        entry = {"status": r["status"]}
        if r.get("venue") and r["status"] in ("accepted", "published"):
            entry["name"] = r["venue"]
        if r.get("year"):
            entry["year"] = int(r["year"])
        if r["status"] in ("accepted", "published"):
            entry["track"] = r["track"]
        entry["source"] = r["source"]
        entry["evidence"] = r["evidence"]
        if r.get("confidence"):
            entry["verification_confidence"] = r["confidence"]
        papers[nid] = entry
        added += 1

    # venues 补全
    for name, meta in NEW_VENUES.items():
        if name not in cur["venues"]:
            cur["venues"][name] = meta
            print("新增 venue: %s (tier %d, %s)" % (name, meta["tier"], meta["rank"]))

    shutil.copy(sig_path, sig_path + ".bak-20261110")
    with open(sig_path, "w", encoding="utf-8") as f:
        yaml.dump(cur, f, allow_unicode=True, sort_keys=False,
                  default_flow_style=False, width=200)

    print("新增 %d 条论文记录，共 %d 条" % (added, len(papers)))
    print("口径修正 %d 处：" % len(fixed))
    for nid, why in fixed:
        print("  %-22s %s" % (nid, why))

    import collections
    print("\n最终状态分布：")
    for k, v in collections.Counter(x["status"] for x in papers.values()).most_common():
        print("  %-18s %d" % (k, v))


if __name__ == "__main__":
    main()
