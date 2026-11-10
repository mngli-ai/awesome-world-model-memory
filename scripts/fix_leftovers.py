# -*- coding: utf-8 -*-
"""修正上一轮遗留：补齐来源 URL，按 arXiv 原始证据纠正误判。"""
import os

import yaml

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
P = os.path.join(ROOT, "paper-signals.yaml")

# id: (status, name, year, track, source, evidence)
FIX = {
    "gen3c": ("accepted", "CVPR", 2025, "main", "https://arxiv.org/abs/2503.03751",
              "arXiv comments 明确写 To appear in CVPR 2025。"),
    "videophy": ("preprint", None, None, None, "https://arxiv.org/abs/2406.03520",
                 "arXiv 有正式论文（2406.03520），comments 仅注页数，无任何会议或期刊录用声明，按预印本处理。"),
    "worldsimbench": ("preprint", None, None, None, "https://arxiv.org/abs/2410.18072",
                      "arXiv 有正式论文（2410.18072），comments 为空，未见录用声明，按预印本处理。"),
    "cosmos": ("preprint", None, None, None, "https://arxiv.org/abs/2501.03575",
               "对应论文为 Cosmos World Foundation Model Platform for Physical AI（arXiv 2501.03575），属平台技术报告，comments 无录用声明，按预印本处理。"),
    "physcodebench": ("preprint", None, None, None, "https://arxiv.org/abs/2604.23580",
                      "项目页给出 arXiv 2604.23580，comments 为空，页面未声明任何会议或期刊录用，按预印本处理。"),
    "streamrender-h3": ("project_page", None, 2026, None,
                        "https://nvlabs.github.io/Sana/Sol-Engine/StreamRender-H3/",
                        "NVIDIA Research 研究项目页，页面 BibTeX 标为 Project page，无独立论文；所属 Sol-Engine 工作见 arXiv 2606.23743，亦无录用声明。"),
    "streaming-code-wm": ("project_page", None, 2026, None,
                          "https://github.com/TingtingLiao/streaming-code-world-model",
                          "社区流式实现仓库，README 以 @misc 引用自身，无对应正式论文。"),
    "genie3": ("product", None, 2025, None,
               "https://deepmind.google/discover/blog/genie-3-a-new-frontier-for-world-models/",
               "DeepMind 官方博客发布，原文写明 limited research preview，页面无 arXiv 论文也无会议期刊名称，BibTeX 仅指向该博客本身。"),
    "marble": ("product", None, 2025, None, "https://marble.worldlabs.ai/",
               "World Labs 商业产品页面，无对应论文与录用记录。"),
    "sora2-veo31": ("product", None, 2025, None, "https://openai.com/index/sora-2/",
                    "OpenAI Sora 2 与 Google Veo 3.1 均为商业产品发布页，非同行评审论文。"),
    "memactive": ("unknown", None, None, None, "",
                  "图谱内部标注为 MIPG 2026，无公开链接，公开索引与搜索引擎均未找到对应论文，该标注未经外部核实故不采信。"),
}


def main():
    d = yaml.safe_load(open(P, encoding="utf-8"))
    papers = d["papers"]
    for nid, (st, name, year, track, src, ev) in FIX.items():
        if nid not in papers:
            print("跳过（不存在）:", nid)
            continue
        e = {"status": st}
        if name:
            e["name"] = name
        if year:
            e["year"] = int(year)
        if track:
            e["track"] = track
        e["source"] = src
        e["evidence"] = ev
        papers[nid] = e
        print("修正", nid, "->", st, src or "(无公开来源)")

    with open(P, "w", encoding="utf-8") as f:
        yaml.dump(d, f, allow_unicode=True, sort_keys=False,
                  default_flow_style=False, width=200)
    print("已写回", P)


if __name__ == "__main__":
    main()
