# -*- coding: utf-8 -*-
"""批量抓 arXiv 官方元数据（title/comments/journal_ref/versions），供发表状态核实用。"""
import json
import os
import re
import sys
import time
import urllib.request
import xml.etree.ElementTree as ET

import yaml

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
NS = {"a": "http://www.w3.org/2005/Atom",
      "arxiv": "http://arxiv.org/schemas/atom"}


def fetch(ids):
    url = "http://export.arxiv.org/api/query?id_list=%s&max_results=%d" % (
        ",".join(ids), len(ids))
    req = urllib.request.Request(url, headers={"User-Agent": "wm-map-verify/1.0"})
    with urllib.request.urlopen(req, timeout=90) as r:
        return r.read()


def _txt(e, tag):
    """安全取子元素文本：Element 的真值判断按子节点数走，必须显式判 None。"""
    el = e.find(tag, NS)
    if el is None or el.text is None:
        return ""
    return " ".join(el.text.split())


def parse(raw):
    out = {}
    root = ET.fromstring(raw)
    for e in root.findall("a:entry", NS):
        eid = e.find("a:id", NS).text.strip()
        aid = re.sub(r"v\d+$", "", eid.rsplit("/abs/", 1)[-1])
        pc = e.find("arxiv:primary_category", NS)
        out[aid] = {
            "arxiv": aid,
            "title": _txt(e, "a:title"),
            "published": _txt(e, "a:published")[:10],
            "updated": _txt(e, "a:updated")[:10],
            "comments": _txt(e, "arxiv:comment"),
            "journal_ref": _txt(e, "arxiv:journal_ref"),
            "doi": _txt(e, "arxiv:doi"),
            "primary": pc.attrib.get("term", "") if pc is not None else "",
            "n_versions": sum(1 for l in e.findall("a:link", NS) if l.attrib.get("rel") == "alternate"),
        }
    return out


def main():
    nodes = yaml.safe_load(open(os.path.join(ROOT, "research-map.yaml"), encoding="utf-8"))["nodes"]
    ids = []
    for n in nodes:
        a = (n.get("arxiv") or "").strip()
        if a and re.match(r"^\d{4}\.\d{4,5}$", a) and a not in ids:
            ids.append(a)
    print("待抓取 arXiv 条目: %d" % len(ids))

    cache_path = os.path.join(ROOT, "scripts", "arxiv_meta_cache.json")
    meta = {}
    if os.path.exists(cache_path):
        meta = json.load(open(cache_path, encoding="utf-8"))
        print("已有缓存: %d" % len(meta))

    todo = [i for i in ids if i not in meta]
    B = 40
    for start in range(0, len(todo), B):
        chunk = todo[start:start + B]
        for attempt in range(3):
            try:
                got = parse(fetch(chunk))
                meta.update(got)
                print("  [%d/%d] 拿到 %d 条" % (min(start + B, len(todo)), len(todo), len(got)))
                break
            except Exception as ex:
                print("  重试 %d: %s" % (attempt + 1, ex))
                time.sleep(5)
        json.dump(meta, open(cache_path, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
        time.sleep(3)

    missing = [i for i in ids if i not in meta]
    print("完成. 缓存 %d 条, 缺失 %d 条: %s" % (len(meta), len(missing), missing[:10]))


if __name__ == "__main__":
    main()
