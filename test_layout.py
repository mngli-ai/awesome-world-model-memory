import collections
import unittest

import build_map as m


def node(i, day, branch='', precision='day', month=10):
    return dict(id=str(i), title=str(i), date=f'2026-{month:02d}-{day:02d}',
                lane='A', branch=branch, precision=precision)


def build(nodes):
    return m.layout(nodes, ['A'], {})


class AdaptiveAxisTests(unittest.TestCase):
    def test_sparse_month_stays_one_column(self):
        data = build([node(1, 1), node(2, 30)])
        self.assertEqual(len(data['lanes'][0]['columns']), 1)
        self.assertEqual(len({n['x'] for n in data['nodes']}), 1)

    def test_dense_month_splits_and_branches_align(self):
        nodes = [node(i, d) for i, d in enumerate([1, 5, 12, 15, 23, 29])]
        nodes.append(node('other', 12, 'B'))
        data = build(nodes)
        self.assertEqual([c['label'] for c in data['lanes'][0]['columns']],
                         ['10月上旬', '10月中旬', '10月下旬'])
        by_id = {n['id']: n for n in data['nodes']}
        self.assertEqual(by_id['2']['x'], by_id['other']['x'])

    def test_dense_first_ten_days_refines_further(self):
        data = build([node(i, i + 1, month=11) for i in range(9)])
        self.assertGreater(len(data['lanes'][0]['columns']), 1)
        self.assertLessEqual(max(collections.Counter((n['branch'], n['x'])
                                 for n in data['nodes']).values()), 3)

    def test_same_day_overflow_uses_continuation(self):
        data = build([node(i, 2) for i in range(11)])
        self.assertEqual(len(data['lanes'][0]['columns']), 4)
        self.assertIn('续', data['lanes'][0]['columns'][1]['label'])

    def test_imprecise_dates_are_not_assigned_to_ten_day_period(self):
        nodes = [node(i, d) for i, d in enumerate([1, 5, 12, 15, 23, 29])]
        nodes += [node('month', 1, precision='month'), node('unknown', 1, precision='unknown')]
        data = build(nodes)
        labels = {c['x']: c['label'] for c in data['lanes'][0]['columns']}
        for n in data['nodes']:
            if n['id'] in ('month', 'unknown'):
                self.assertIn('未定日', labels[n['x']])

    def test_leap_day_and_empty_months(self):
        nodes = [node(i, 1, month=2) for i in range(4)]
        nodes.append(dict(node('leap', 1), date='2024-02-29'))
        data = build(nodes)
        self.assertTrue(any('2024' == y['label'] for y in data['lanes'][0]['years']))
        self.assertEqual(len(data['nodes']), 5)

    def test_real_dataset_preserved_and_no_overlap(self):
        nodes, order, colors = m.load('research-map.yaml')
        data = m.layout(nodes, order, colors)
        self.assertEqual({n['id'] for n in nodes}, {n['id'] for n in data['nodes']})
        counts = collections.Counter((n['lane'], n['branch'], n['x']) for n in data['nodes'])
        self.assertLessEqual(max(counts.values()), 3)
        for a in data['nodes']:
            for b in data['nodes']:
                if a['id'] >= b['id']:
                    continue
                self.assertFalse(abs(a['x'] - b['x']) < m.CARD_W and
                                 abs(a['y'] - b['y']) < m.CARD_H,
                                 (a['id'], b['id']))
        reordered = m.layout(list(reversed(nodes)), order, colors)
        # Preserve the source's presentation order, but layout coordinates must be stable.
        data['nodes'].sort(key=lambda n: n['id'])
        reordered['nodes'].sort(key=lambda n: n['id'])
        self.assertEqual(data, reordered)


if __name__ == '__main__':
    unittest.main()
