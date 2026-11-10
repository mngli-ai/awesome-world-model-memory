# -*- coding: utf-8 -*-
"""第三交叉源：OpenAlex 按标题检索，找非 arXiv 的会议/期刊版本。"""
import json
import os
import re
import time
import urllib.parse
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
UA = {"User-Agent": "wm-map-verify/1.0 (mailto:verify@example.com)"}
MAILTO = "verify@example.com"


def norm(s):
    return re.sub(r"[^a-z0-9]", "", (s or "").lower())


def jget(url, timeout=45):
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8"))


def query(title):
    q = urllib.parse.quote(title[:200])
    url = "https://api.openalex.org/works?search=%s&per-page=5&mailto=%s" % (q, MAILTO)
    try:
        d = jget(url)
    except Exception as ex:
        return {"error": str(ex)}
    out = []
    for w in d.get("results", []):
        src = ((w.get("primary_location") or {}).get("source") or {})
        out.append({
            "title": w.get("title") or "",
            "type": w.get("type") or "",
            "year": w.get("publication_year"),
            "source": src.get("display_name") or "",
            "source_type": src.get("type") or "",
            "doi": (w.get("doi") or "").replace("https://doi.org/", ""),
        })
    return {"hits": out}


def main():
    meta = json.load(open(os.path.join(ROOT, "scripts", "arxiv_meta_cache.json"), encoding="utf-8"))
    path = os.path.join(ROOT, "scripts", "openalex_cache.json")
    cache = json.load(open(path, encoding="utf-8")) if os.path.exists(path) else {}
    todo = [a for a in meta if a not in cache]
    print("OpenAlex 待查 %d/%d" % (len(todo), len(meta)))
    for k, a in enumerate(todo):
        cache[a] = query(meta[a]["title"])
        if (k + 1) % 25 == 0:
            print("  %d/%d" % (k + 1, len(todo)))
            json.dump(cache, open(path, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
        time.sleep(0.35)
    json.dump(cache, open(path, "w", encoding="utf-8"), ensure_ascii=False, indent=1)

    ok = err = mat = 0
    for a, v in cache.items():
        if v.get("error"):
            err += 1
            continue
        ok += 1
        t = norm(meta[a]["title"])
        for h in v.get("hits") or []:
            if norm(h["title"]) == t and h["source_type"] in ("conference", "journal"):
                mat += 1
                break
    print("完成: 成功 %d 失败 %d, 标题精确匹配且有会议/期刊源 %d" % (ok, err, mat))


if __name__ == "__main__":
    main()
