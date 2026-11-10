# -*- coding: utf-8 -*-
"""第三方交叉源核实：Semantic Scholar + DBLP。不看作者自述，只看已索引的出版记录。"""
import json
import os
import re
import time
import urllib.parse
import urllib.request

import yaml

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
UA = {"User-Agent": "wm-map-verify/1.0 (research metadata check)"}


def jget(url, data=None, timeout=60):
    req = urllib.request.Request(url, data=data, headers=UA)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8"))


def s2_batch(ids):
    """按 arXiv id 批量查 S2（一次最多 500）。"""
    url = ("https://api.semanticscholar.org/graph/v1/paper/batch"
           "?fields=title,venue,year,publicationVenue,externalIds,publicationTypes,journal")
    body = json.dumps({"ids": ["ARXIV:%s" % i for i in ids]}).encode()
    return jget(url, data=body, timeout=120)


def dblp(title):
    q = urllib.parse.quote(re.sub(r"[^\w\s-]", " ", title)[:180])
    url = "https://dblp.org/search/publ/api?q=%s&format=json&h=5" % q
    try:
        d = jget(url, timeout=40)
    except Exception as ex:
        return {"error": str(ex)}
    hits = d.get("result", {}).get("hits", {}).get("hit", []) or []
    out = []
    for h in hits:
        i = h.get("info", {})
        out.append({"title": i.get("title", ""), "venue": i.get("venue", ""),
                    "year": i.get("year", ""), "type": i.get("type", ""),
                    "key": i.get("key", ""), "doi": i.get("doi", "")})
    return {"hits": out}


def main():
    nodes = yaml.safe_load(open(os.path.join(ROOT, "research-map.yaml"), encoding="utf-8"))["nodes"]
    meta = json.load(open(os.path.join(ROOT, "scripts", "arxiv_meta_cache.json"), encoding="utf-8"))
    cache_path = os.path.join(ROOT, "scripts", "cross_source_cache.json")
    cache = json.load(open(cache_path, encoding="utf-8")) if os.path.exists(cache_path) else {}

    by_arxiv = {n["arxiv"].strip(): n for n in nodes if (n.get("arxiv") or "").strip() in meta}

    # 1) Semantic Scholar
    if "s2" not in cache:
        ids = list(meta.keys())
        try:
            res = s2_batch(ids)
            cache["s2"] = {i: r for i, r in zip(ids, res)}
            print("S2 返回 %d 条" % sum(1 for v in res if v))
        except Exception as ex:
            print("S2 失败: %s" % ex)
            cache["s2"] = {}
        json.dump(cache, open(cache_path, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    else:
        print("S2 命中缓存 %d 条" % len(cache["s2"]))

    # 2) DBLP 按标题（只对需要判断的查，避免无谓请求）
    cache.setdefault("dblp", {})
    todo = [a for a in meta if a not in cache["dblp"]]
    print("DBLP 待查 %d 条" % len(todo))
    for k, a in enumerate(todo):
        t = meta[a]["title"]
        cache["dblp"][a] = dblp(t)
        if (k + 1) % 20 == 0:
            print("  DBLP %d/%d" % (k + 1, len(todo)))
            json.dump(cache, open(cache_path, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
        time.sleep(1.2)
    json.dump(cache, open(cache_path, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print("完成. S2=%d DBLP=%d" % (len(cache["s2"]), len(cache["dblp"])))


if __name__ == "__main__":
    main()
