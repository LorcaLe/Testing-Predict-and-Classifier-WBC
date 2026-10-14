"""Build reproducible C-NMC manifests without modifying source images.

Patient naming is documented in the local CNMC_readme.pdf. Subject identity itself
is not independently verified. Shared bytes connect subjects conservatively.
"""
import csv
import hashlib
import json
import re
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'outputs' / 'splits' / 'cnmc_v1'
DATA = ROOT / 'Data' / 'PKG - C-NMC 2019'
FIELDS = ['path', 'sha256', 'label', 'subject_id', 'source_image_id',
          'original_split', 'split', 'decision', 'reason', 'related_paths']
MAPPING = {'fold_0': 'train', 'fold_1': 'train', 'fold_2': 'validation',
           'test_preliminary': 'test_preliminary',
           'test_final_unlabeled': 'test_final_unlabeled'}


def parse_identity(name):
    match = re.fullmatch(r'UID_(H?\d+)_(\d+)_(\d+)_(all|hem)\.bmp', name, re.I)
    if not match:
        raise ValueError(f'Unrecognized C-NMC name: {name}')
    subject, image, cell, label = match.groups()
    subject, label = subject.upper(), label.lower()
    if subject.startswith('H') != (label == 'hem'):
        raise ValueError(f'Subject prefix disagrees with class: {name}')
    return 'UID_' + subject, f'UID_{subject}_{image}', label


def decide(rows):
    """Quarantine conflicts; preserve held-out partitions; exclude linked train subjects."""
    rows = [dict(r, decision='keep', reason='', related_paths='') for r in rows]
    groups, edges, heldout = defaultdict(list), defaultdict(set), set()
    subject_splits = defaultdict(set)
    for row in rows:
        groups[row['sha256']].append(row)
        sid = row['subject_id']
        if sid:
            subject_splits[sid].add(row['split'])
            if row['split'] != 'train':
                heldout.add(sid)
    if any(len(splits) > 1 for splits in subject_splits.values()):
        raise ValueError('Subject ID overlaps partitions before cleaning; review required')
    conflicts = []
    for sha, group in groups.items():
        if len({r['label'] for r in group if r['label']}) > 1:
            conflicts.append(sha)
            for row in group:
                row.update(decision='exclude', reason='conflicting_labels_quarantine')
        ids = {r['subject_id'] for r in group if r['subject_id']}
        for sid in ids:
            edges[sid].update(ids - {sid})
        # Anonymous final-test images still protect test from matching train subjects.
        if any(r['split'].startswith('test_') for r in group):
            heldout.update(ids)
    reached, queue = set(heldout), list(heldout)
    while queue:
        for sid in edges[queue.pop()]:
            if sid not in reached:
                reached.add(sid)
                queue.append(sid)
    excluded_subjects = sorted({r['subject_id'] for r in rows
                                if r['split'] == 'train' and r['subject_id'] in reached})
    for row in rows:
        if row['split'] == 'train' and row['subject_id'] in excluded_subjects and row['decision'] == 'keep':
            row.update(decision='exclude', reason='train_subject_linked_to_heldout_by_exact_duplicate')
    for sha, group in groups.items():
        if len(group) == 1:
            continue
        for row in group:
            row['related_paths'] = json.dumps(sorted(r['path'] for r in group if r['path'] != row['path']))
        remaining = [r for r in group if r['decision'] == 'keep']
        # A validation/test collision requires explicit review, not a silent test edit.
        if len({r['split'] for r in remaining}) > 1:
            raise ValueError(f'Held-out partitions share bytes: {sha}')
        if remaining and remaining[0]['split'] in ('train', 'validation'):
            for row in sorted(remaining, key=lambda r: r['path'])[1:]:
                row.update(decision='exclude', reason='duplicate_within_partition')
    if any(r['decision'] != 'keep' and r['split'].startswith('test_') for r in rows):
        raise ValueError('Test labels conflict: preserve original test and review manually')
    return sorted(rows, key=lambda r: r['path']), excluded_subjects, conflicts


def write_csv(path, rows):
    with path.open('w', newline='', encoding='utf-8-sig') as stream:
        writer = csv.DictWriter(stream, fieldnames=FIELDS)
        writer.writeheader()
        writer.writerows(rows)


def validate(rows):
    kept = [r for r in rows if r['decision'] == 'keep']
    for field in ('sha256', 'subject_id', 'source_image_id'):
        partitions = defaultdict(set)
        for row in kept:
            if row[field]:
                partitions[row[field]].add(row['split'])
        if any(len(splits) > 1 for splits in partitions.values()):
            raise ValueError(f'Cross-partition overlap remains: {field}')
    for split in ('train', 'validation'):
        selected = [r for r in kept if r['split'] == split]
        if len({r['sha256'] for r in selected}) != len(selected):
            raise ValueError(f'Duplicate remains within {split}')
        if {r['label'] for r in selected} != {'all', 'hem'}:
            raise ValueError(f'Missing class in {split}')


def main():
    manifest = ROOT / 'outputs' / 'audit' / 'manifest.csv'
    label_file = DATA / 'C-NMC_test_prelim_phase_data' / 'C-NMC_test_prelim_phase_data_labels.csv'
    with label_file.open(encoding='utf-8-sig', newline='') as stream:
        preliminary = {r['new_names']: r for r in csv.DictReader(stream)}
    with manifest.open(encoding='utf-8-sig', newline='') as stream:
        original = [r for r in csv.DictReader(stream) if r['dataset'] == DATA.name]
    rows = []
    for r in original:
        if r['error'] or not r['sha256']:
            raise ValueError(f'Unresolved input audit error: {r["path"]}')
        path = ROOT / r['path']
        with path.open('rb') as stream:
            current_hash = hashlib.file_digest(stream, 'sha256').hexdigest()
        if current_hash != r['sha256']:
            raise ValueError(f'Stale manifest: {r["path"]}')
        subject = source_image = ''
        if r['split'] != 'test_final_unlabeled':
            name = preliminary[path.name]['Patient_ID'] if r['split'] == 'test_preliminary' else path.name
            subject, source_image, label = parse_identity(name)
            if label != r['label']:
                raise ValueError(f'Filename and manifest labels disagree: {r["path"]}')
            if r['split'] == 'test_preliminary' and preliminary[path.name]['labels'] != {'all': '1', 'hem': '0'}[label]:
                raise ValueError(f'Preliminary numeric label disagrees: {path.name}')
        rows.append(dict(path=r['path'], sha256=r['sha256'], label=r['label'],
                         subject_id=subject, source_image_id=source_image,
                         original_split=r['split'], split=MAPPING[r['split']]))
    decisions, excluded_subjects, conflicts = decide(rows)
    validate(decisions)
    OUT.mkdir(parents=True, exist_ok=True)
    write_csv(OUT / 'decisions.csv', decisions)
    write_csv(OUT / 'excluded.csv', [r for r in decisions if r['decision'] == 'exclude'])
    for split in sorted(set(MAPPING.values())):
        write_csv(OUT / (split + '.csv'), [r for r in decisions if r['split'] == split and r['decision'] == 'keep'])
    kept = [r for r in decisions if r['decision'] == 'keep']
    groups = defaultdict(list)
    for row in rows:
        groups[row['sha256']].append(row)
    counts = {split: dict(Counter(r['label'] or 'unlabeled' for r in kept if r['split'] == split)) for split in sorted(set(MAPPING.values()))}
    summary = dict(status='exact_duplicate_clean_subject_conservative_v1',
                   input_rows=len(rows), retained_rows=len(kept), excluded_rows=len(rows)-len(kept),
                   excluded_train_subjects=excluded_subjects, conflicting_label_groups=len(conflicts),
                   counts=counts,
                   subjects={s: len({r['subject_id'] for r in kept if r['split'] == s and r['subject_id']}) for s in counts},
                   original_train_subjects=len({r['subject_id'] for r in rows if r['original_split'].startswith('fold_')}),
                   duplicate_groups=[dict(sha256=sha, paths=[r['path'] for r in group],
                                          subjects=sorted({r['subject_id'] for r in group if r['subject_id']}),
                                          labels=sorted({r['label'] for r in group if r['label']}))
                                     for sha, group in sorted(groups.items()) if len(group)>1],
                   exclusion_reasons=dict(Counter(r['reason'] for r in decisions if r['decision']=='exclude')),
                   checks={'source_sha256_reverified': True, 'cross_partition_sha256_overlap': 0,
                           'cross_partition_subject_id_overlap': 0, 'cross_partition_source_image_id_overlap': 0,
                           'train_validation_internal_exact_duplicates': 0, 'test_rows_preserved': True},
                   limitations=['Near-duplicates have not been checked.',
                                'Filename identity follows local README; physical subject identity is not independently verified.',
                                'Two exact duplicate groups within final test are preserved; final-test labels/subject IDs are unavailable.',
                                'This is a modified internal split, not an unchanged official benchmark split.'])
    (OUT / 'summary.json').write_text(json.dumps(summary, indent=2), encoding='utf-8')
    lock = {'policy': 'cnmc_v1', 'files': {}}
    artifacts = [manifest, label_file, DATA / 'CNMC_readme.pdf', Path(__file__), *sorted(OUT.glob('*.csv')), OUT / 'summary.json']
    for path in artifacts:
        lock['files'][path.relative_to(ROOT).as_posix()] = hashlib.sha256(path.read_bytes()).hexdigest()
    (OUT / 'checksums.json').write_text(json.dumps(lock, indent=2), encoding='utf-8')
    print(json.dumps({k: v for k, v in summary.items() if k != 'duplicate_groups'}, indent=2))


if __name__ == '__main__':
    main()
