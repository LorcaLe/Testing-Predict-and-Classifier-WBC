"""Read-only dataset audit. Run from any directory; outputs stay under outputs/audit."""
import csv
import hashlib
import json
import re
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'outputs' / 'audit'
EXT = {'.jpg', '.jpeg', '.png', '.bmp', '.tif', '.tiff'}


def inspect(path):
    rel = path.relative_to(ROOT)
    parts = rel.parts
    dataset = parts[1]
    row = dict(path=rel.as_posix(), dataset=dataset, split='unassigned', label='',
               label_scope='', patient_id_candidate='', patient_id_verified=False,
               source_dataset='', sha256='', width='', height='', error='')
    if dataset == 'TXL-PBC_Dataset':
        row.update(split=path.parent.name, label='WBC/RBC/Platelets', label_scope='box')
    elif dataset.startswith('PKG - C-NMC'):
        if 'C-NMC_training_data' in parts:
            row.update(split=next(p for p in parts if p.startswith('fold_')),
                       label=path.parent.name, label_scope='cell')
        elif 'C-NMC_test_prelim_phase_data' in parts:
            row.update(split='test_preliminary', label_scope='cell')
        else:
            row.update(split='test_final_unlabeled', label_scope='cell')
        original = path.name
        if row['split'] == 'test_preliminary':
            entry = PRELIM.get(path.name)
            if entry:
                original = entry['Patient_ID']
                row['label'] = {'1': 'all', '0': 'hem'}.get(entry['labels'], '')
            else:
                row['error'] = 'missing preliminary label'
        match = re.fullmatch(r'UID_(H?\d+)_\d+_\d+_(all|hem)\.bmp', original, re.IGNORECASE)
        if match:
            row['patient_id_candidate'] = 'UID_' + match[1].upper()
    elif dataset.startswith('ALL_IDB'):
        row.update(split='external_test', label=path.stem.rsplit('_', 1)[-1],
                   label_scope='image_blast_presence' if dataset == 'ALL_IDB1' else 'cell')
    else:
        row.update(label=path.parent.name, label_scope='cell', split='extension_unassigned')
    try:
        with path.open('rb') as stream:
            row['sha256'] = hashlib.file_digest(stream, 'sha256').hexdigest()
        with Image.open(path) as img:
            img.load()
            row.update(width=img.width, height=img.height)
        if dataset == 'TXL-PBC_Dataset':
            label = path.parents[2] / 'labels' / path.parent.name / (path.stem + '.txt')
            lines = label.read_text().splitlines()
            for number, line in enumerate(lines, 1):
                cls, x, y, w, h = map(float, line.split())
                if cls not in (0, 1, 2) or not (0 <= x <= 1 and 0 <= y <= 1 and 0 < w <= 1 and 0 < h <= 1):
                    raise ValueError(f'invalid YOLO label at line {number}')
                if min(x-w/2, y-h/2) < -1e-5 or max(x+w/2, y+h/2) > 1+1e-5:
                    raise ValueError(f'box exceeds image at line {number}')
    except Exception as exc:
        row['error'] = (row['error'] + '; ' + str(exc)).strip('; ')
    return row


def write_csv(name, rows, fields):
    with (OUT / name).open('w', newline='', encoding='utf-8-sig') as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


if __name__ == '__main__':
    OUT.mkdir(parents=True, exist_ok=True)
    label_file = next((ROOT / 'Data' / 'PKG - C-NMC 2019').rglob('*.csv'))
    with label_file.open(encoding='utf-8-sig', newline='') as stream:
        PRELIM = {r['new_names']: r for r in csv.DictReader(stream)}
    paths, excluded = [], []
    for path in sorted((ROOT / 'Data').rglob('*')):
        if not path.is_file() or path.suffix.lower() not in EXT:
            continue
        rel = path.relative_to(ROOT)
        if '__MACOSX' in path.parts or path.name.startswith('._') or (rel.parts[1] == 'TXL-PBC_Dataset' and 'images' not in rel.parts):
            excluded.append({'path': rel.as_posix(), 'reason': 'metadata_or_non_dataset_image'})
        else:
            paths.append(path)
    rows = []
    with ThreadPoolExecutor(max_workers=8) as pool:
        for i, row in enumerate(pool.map(inspect, paths), 1):
            rows.append(row)
            if i % 5000 == 0:
                print(f'Inspected {i}/{len(paths)}', flush=True)
    write_csv('manifest.csv', rows, list(rows[0]))
    write_csv('excluded.csv', excluded, ['path', 'reason'])
    write_csv('errors.csv', [r for r in rows if r['error']], list(rows[0]))
    hashes, patients = defaultdict(list), defaultdict(set)
    for row in rows:
        if row['sha256']:
            hashes[row['sha256']].append(row)
        if row['patient_id_candidate']:
            patients[row['patient_id_candidate']].add(row['split'])
    duplicates = [dict(sha256=sha, paths=[r['path'] for r in group],
                       partitions=sorted({r['dataset'] + '/' + r['split'] for r in group}))
                  for sha, group in hashes.items() if len(group) > 1]
    overlap = {p: sorted(s) for p, s in patients.items() if len(s) > 1}
    summary = dict(total_images=len(rows), excluded=len(excluded),
                   datasets=dict(Counter(r['dataset'] for r in rows)),
                   partitions=dict(Counter(r['dataset'] + '/' + r['split'] for r in rows)),
                   errors=sum(bool(r['error']) for r in rows),
                   exact_duplicate_groups=len(duplicates),
                   candidate_patient_overlap=overlap,
                   limitations=['C-NMC naming follows the local README including H/h prefixes; physical subject identity is not independently verified.',
                                'SHA-256 detects exact file duplicates only; near-duplicate review remains pending.',
                                'Source metadata and dataset versions are not yet joined; no split is certified leakage-free.'])
    for name, data in [('summary.json', summary), ('duplicates.json', duplicates)]:
        (OUT / name).write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding='utf-8')
    print(json.dumps(summary, indent=2), flush=True)
