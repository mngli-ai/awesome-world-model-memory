import unittest
from pathlib import Path
import build_map as m


class SignalTests(unittest.TestCase):
    def test_unverified_venue_never_promotes(self):
        n = dict(id='x', venue='CVPR 2026', citations=0)
        self.assertEqual(m.paper_signals(n, {})['publication']['tier'], 0)

    def test_verified_main_and_workshop_differ(self):
        rules = {'venues': {'CVPR': {'tier': 3, 'rank': 'CCF A', 'source': 'https://www.ccf.org.cn/Academic_Evaluation/AI/'}},
                 'papers': {'x': {'name': 'CVPR', 'status': 'published', 'track': 'main', 'source': 'https://openaccess.thecvf.com/x'}}}
        n = dict(id='x', venue='CVPR 2025')
        self.assertEqual(m.paper_signals(n, rules)['publication']['tier'], 3)
        rules['papers']['x']['track'] = 'workshop'
        self.assertEqual(m.paper_signals(n, rules)['publication']['tier'], 0)
        rules['papers']['x']['track'] = 'main'
        rules['papers']['x']['status'] = 'submitted'
        self.assertEqual(m.paper_signals(n, rules)['publication']['tier'], 0)

    def test_missing_evidence_never_promotes(self):
        rules = {'venues': {'CVPR': {'tier': 3}}, 'papers': {'x': {'name':'CVPR', 'status':'accepted', 'track':'main'}}}
        self.assertEqual(m.paper_signals(dict(id='x'), rules)['publication']['tier'], 0)

    def test_relevance_is_mechanism_based_not_quality(self):
        n = dict(id='future-paper', lane='位置时间寻址', branch='重排位置', concepts=['旋转位置编码'])
        reasons = m.paper_signals(n, {})['project_relevance']
        self.assertTrue(reasons)
        self.assertTrue(any('RoPE' in r for r in reasons))
        self.assertEqual(m.paper_signals(dict(id='benchmark', lane='评测基准'), {})['project_relevance'], [])
        self.assertTrue(m.paper_signals(dict(id='solarrenderer'), {})['project_relevance'])

    def test_publication_caution_labels(self):
        self.assertEqual(m.paper_signals(dict(id='x', arxiv='2611.12345'), {})['publication']['label'], '发表未核实')
        for status, label in [('preprint', '预印本'), ('submitted', '投稿中'), ('technical_report', '技术报告')]:
            rules = {'papers': {'x': {'status': status, 'source': 'https://arxiv.org/abs/x'}}}
            self.assertEqual(m.paper_signals(dict(id='x'), rules)['publication']['label'], label)
        rules = {'papers': {'x': {'status': 'accepted', 'track': 'workshop', 'source': 'https://example.org/paper'}}}
        self.assertEqual(m.paper_signals(dict(id='x'), rules)['publication']['label'], 'Workshop')
        rules['papers']['x']['track'] = 'unknown'
        self.assertEqual(m.paper_signals(dict(id='x'), rules)['publication']['label'], '录用·赛道待核')

    def test_full_verification_coverage(self):
        import yaml
        rules = yaml.safe_load(Path('paper-signals.yaml').read_text(encoding='utf-8'))
        nodes, _, _ = m.load(Path('research-map.yaml'))
        self.assertEqual({n['id'] for n in nodes}, set(rules['papers']))
        self.assertTrue(all(p.get('evidence') for p in rules['papers'].values()))
        self.assertEqual(rules['venues']['WACV']['rank'], 'ICORE2026 A')
        self.assertEqual(rules['papers']['gameverse']['track'], 'unknown')

    def test_real_data_exposes_metadata(self):
        nodes, order, colors = m.load(Path('research-map.yaml'))
        data = m.layout(nodes, order, colors)
        self.assertTrue(all('publication' in n and 'project_relevance' in n for n in data['nodes']))
        self.assertTrue(any(n['project_relevance'] for n in data['nodes']))


if __name__ == '__main__':
    unittest.main()
