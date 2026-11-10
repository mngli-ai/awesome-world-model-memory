# -*- coding: utf-8 -*-
"""从 arXiv 官方 comments/journal_ref 抽取强信号，作为智能体结论的交叉校验基线。"""
import json
import os
import re

import yaml

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCR = os.path.join(ROOT, "scripts")

VENUE_ALIASES = [
    (r"neurips|nips\b|neural information processing", "NeurIPS"),
    (r"\bicml\b|international conference on machine learning", "ICML"),
    (r"\biclr\b|learning representations", "ICLR"),
    (r"\bcvpr\b|computer vision and pattern recognition", "CVPR"),
    (r"\biccv\b|international conference on computer vision", "ICCV"),
    (r"\beccv\b|european conference on computer vision", "ECCV"),
    (r"\baccv\b|asian conference on computer vision", "ACCV"),
    (r"\bwacv\b|winter conference on applications", "WACV"),
    (r"\bacm mm\b|\bmm 20\d\d\b|acm international conference on multimedia", "ACM MM"),
    (r"\baaai\b", "AAAI"),
    (r"\bijcai\b", "IJCAI"),
    (r"\bsiggraph asia\b", "SIGGRAPH Asia"),
    (r"\bsiggraph\b", "SIGGRAPH"),
    (r"\b3dv\b|international conference on 3d vision", "3DV"),
    (r"\btpami\b|pattern analysis and machine intelligence", "TPAMI"),
    (r"\bijcv\b|international journal of computer vision", "IJCV"),
    (r"\bjmlr\b|journal of machine learning research", "JMLR"),
    (r"\btmlr\b|transactions on machine learning research", "TMLR"),
    (r"\bbmvc\b|british machine vision", "BMVC"),
    (r"\bcorl\b|conference on robot learning", "CoRL"),
    (r"\bicra\b", "ICRA"),
    (r"\brss\b|robotics: science and systems", "RSS"),
]


def find_venue(text):
    low = text.lower()
    for pat, name in VENUE_ALIASES:
        if re.search(pat, low):
            return name
    return ""


def find_year(text, fallback):
    ys = re.findall(r"\b(20\d\d)\b", text or "")
    if ys:
        return int(max(ys))
    return int(str(fallback)[:4]) if fallback else None


ACCEPT = re.compile(r"(accepted|accept|to appear|appear (?:at|in)|published (?:at|in|as)|camera[- ]ready|oral|spotlight)", re.I)
WORKSHOP = re.compile(r"workshop", re.I)
TECHREP = re.compile(r"(technical report|tech report|technical memo)", re.I)
PREPRINT = re.compile(r"\bpreprint\b", re.I)
UNDERREV = re.compile(r"(under review|submitted to|in submission)", re.I)


def judge(rec):
    """返回 (status, venue, year, track, conf, why)"""
    c = rec.get("comments") or ""
    jr = rec.get("journal_ref") or ""
    pub = rec.get("arxiv_published") or ""

    if jr:
        v = find_venue(jr) or jr.split(",")[0].strip()
        return "published", v, find_year(jr, pub), "journal", "high", "arXiv journal_ref 有值"
    if ACCEPT.search(c):
        v = find_venue(c)
        tr = "workshop" if WORKSHOP.search(c) else ("main" if v else "unknown")
        st = "published" if re.search(r"published", c, re.I) else "accepted"
        return st, v, find_year(c, pub), tr, "high" if v else "medium", "arXiv comments 含录用声明"
    if TECHREP.search(c):
        return "technical_report", "", find_year(c, pub), "unknown", "high", "arXiv comments 注明技术报告"
    if UNDERREV.search(c):
        return "submitted", "", find_year(c, pub), "unknown", "high", "arXiv comments 注明在投"
    if PREPRINT.search(c):
        return "preprint", "", find_year(c, pub), "unknown", "high", "arXiv comments 自称预印本"
    return "preprint", "", find_year(c, pub), "unknown", "low", "comments 无发表声明，按 arXiv 预印本处理"


def main():
    meta = json.load(open(os.path.join(SCR, "arxiv_meta_cache.json"), encoding="utf-8"))
    out = {}
    for a, m in meta.items():
        st, v, y, tr, cf, why = judge(m)
        out[a] = {"status": st, "venue": v, "year": y, "track": tr,
                  "confidence": cf, "basis": why}
    json.dump(out, open(os.path.join(SCR, "baseline.json"), "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)
    import collections
    print("基线判定 %d 条" % len(out))
    for k, n in collections.Counter(v["status"] for v in out.values()).most_common():
        print("  %-18s %d" % (k, n))
    print("--- 有明确会议名的 ---")
    for a, v in out.items():
        if v["venue"]:
            print("  ", a, v["venue"], v["year"], v["track"])


if __name__ == "__main__":
    main()
