# -*- coding: utf-8 -*-
"""把每篇论文的多源证据打包成切片文件，供并行智能体核实。"""
import json
import os
import re

import yaml

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCR = os.path.join(ROOT, "scripts")


def norm(s):
    return re.sub(r"[^a-z0-9]", "", (s or "").lower())


def main():
    nodes = yaml.safe_load(open(os.path.join(ROOT, "research-map.yaml"), encoding="utf-8"))["nodes"]
    meta = json.load(open(os.path.join(SCR, "arxiv_meta_cache.json"), encoding="utf-8"))
    cross = json.load(open(os.path.join(SCR, "cross_source_cache.json"), encoding="utf-8"))
    oa_path = os.path.join(SCR, "openalex_cache.json")
    oa = json.load(open(oa_path, encoding="utf-8")) if os.path.exists(oa_path) else {}
    signals = yaml.safe_load(open(os.path.join(ROOT, "paper-signals.yaml"), encoding="utf-8"))["papers"]

    # 已有核实记录的跳过
    skip = set(signals.keys())
    items = []
    for n in nodes:
        if n["id"] in skip:
            continue
        a = (n.get("arxiv") or "").strip()
        rec = {
            "id": n["id"],
            "graph_title": n.get("title"),
            "graph_venue_raw": n.get("venue") or "",
            "graph_date": n.get("date"),
            "arxiv": a if a in meta else "",
        }
        if a in meta:
            m = meta[a]
            rec.update({
                "arxiv_title": m["title"],
                "arxiv_published": m["published"],
                "arxiv_updated": m["updated"],
                "comments": m["comments"],
                "journal_ref": m["journal_ref"],
                "doi": m["doi"],
                "primary_category": m["primary"],
            })
            s2 = cross.get("s2", {}).get(a) or {}
            if s2:
                pv = s2.get("publicationVenue") or {}
                rec["s2_venue"] = (s2.get("venue") or "")
                rec["s2_venue_name"] = pv.get("name") or ""
                rec["s2_year"] = s2.get("year")
                rec["s2_types"] = s2.get("publicationTypes") or []
            o = oa.get(a) or {}
            if o.get("hits"):
                t = norm(m["title"])
                exact = [h for h in o["hits"] if norm(h["title"]) == t]
                if exact:
                    rec["openalex"] = [{k: h[k] for k in ("type", "year", "source", "source_type", "doi")}
                                       for h in exact[:2]]
        items.append(rec)

    print("待核实条目: %d" % len(items))
    # 按 arxiv 是否有元数据稳定排序后切片
    items.sort(key=lambda x: (x["arxiv"] == "", x["id"]))
    N = 4
    size = (len(items) + N - 1) // N
    for i in range(N):
        chunk = items[i * size:(i + 1) * size]
        p = os.path.join(SCR, "verify_shard_%d.json" % (i + 1))
        json.dump(chunk, open(p, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
        n_meta = sum(1 for c in chunk if c["arxiv"])
        print("  %s: %d 条 (其中 %d 条有 arXiv 元数据)" % (os.path.basename(p), len(chunk), n_meta))


if __name__ == "__main__":
    main()
