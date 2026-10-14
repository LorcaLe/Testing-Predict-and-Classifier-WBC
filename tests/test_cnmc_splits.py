import unittest

from scripts.build_cnmc_splits import decide, parse_identity, validate


def row(path, subject, split, sha, label='all'):
    return dict(path=path, subject_id=subject, source_image_id=subject+'_'+path,
                split=split, sha256=sha, label=label, original_split=split)


class SplitSafetyTests(unittest.TestCase):
    def test_healthy_ids_and_case(self):
        self.assertEqual(parse_identity('UID_h3_12_2_hem.bmp'), ('UID_H3', 'UID_H3_12', 'hem'))
        with self.assertRaises(ValueError):
            parse_identity('UID_H3_12_2_all.bmp')

    def test_transitive_subject_links_remove_entire_train_subject(self):
        rows = [row('a1', 'A', 'train', 'x'), row('b1', 'B', 'train', 'x'),
                row('b2', 'B', 'train', 'y'), row('c1', 'C', 'validation', 'y'),
                row('a2', 'A', 'train', 'unique')]
        decisions, subjects, _ = decide(rows)
        self.assertEqual(subjects, ['A', 'B'])
        self.assertEqual([r['path'] for r in decisions if r['decision']=='keep'], ['c1'])

    def test_conflicting_labels_quarantine_both(self):
        decisions, _, conflicts = decide([row('a', 'A', 'train', 'x'), row('b', 'B', 'train', 'x', 'hem')])
        self.assertEqual(conflicts, ['x'])
        self.assertTrue(all(r['decision']=='exclude' for r in decisions))

    def test_test_duplicates_preserved(self):
        rows = [row('a', '', 'test_final_unlabeled', 'x', ''), row('b', '', 'test_final_unlabeled', 'x', '')]
        decisions, _, _ = decide(rows)
        self.assertTrue(all(r['decision']=='keep' for r in decisions))

    def test_heldout_collision_stops(self):
        with self.assertRaises(ValueError):
            decide([row('a', 'A', 'validation', 'x'), row('b', 'B', 'test_preliminary', 'x')])

    def test_train_dedup_is_deterministic(self):
        rows = [row('b', 'A', 'train', 'x'), row('a', 'A', 'train', 'x')]
        first, _, _ = decide(rows)
        second, _, _ = decide(rows[::-1])
        self.assertEqual(first, second)
        self.assertEqual([r['path'] for r in first if r['decision']=='keep'], ['a'])

    def test_subject_overlap_stops(self):
        with self.assertRaises(ValueError):
            decide([row('a', 'A', 'train', 'x'), row('b', 'A', 'validation', 'y')])

    def test_validator_rejects_leakage(self):
        rows = [dict(row('a', 'A', 'train', 'x'), decision='keep'),
                dict(row('b', 'B', 'validation', 'x'), decision='keep')]
        with self.assertRaises(ValueError):
            validate(rows)


if __name__ == '__main__':
    unittest.main()
