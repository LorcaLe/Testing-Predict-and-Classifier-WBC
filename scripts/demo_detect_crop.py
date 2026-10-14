"""Run detection and WBC cropping on the six bundled real sample images."""
import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from predict import predict


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output-dir',type=Path,default=ROOT/'outputs/demo')
    parser.add_argument('--device',default='cpu')
    args = parser.parse_args()
    samples = ROOT/'examples/blood_cells'
    manifest = json.loads((samples/'manifest.json').read_text(encoding='utf-8'))
    summaries = []
    for item in manifest:
        out = args.output_dir / item['sample']
        result = predict(samples/item['image'], ROOT/'models/detector_best.pt',
                         device=args.device,crop_dir=out/'wbc_crops',annotated=out/'detected.png')
        (out/'detection.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
        summaries.append({'sample':item['sample'],
                          'ground_truth_counts':item['ground_truth_counts'],
                          'predicted_counts':{name:sum(d['label']==name for d in result['detections'])
                                              for name in ['WBC','RBC','Platelet']},
                          'wbc_crops_saved':len(result['wbc_crops'])})
        print(f"{item['sample']}: {len(result['wbc_crops'])} WBC crops -> {out}")
    (args.output_dir/'summary.json').write_text(json.dumps(summaries,indent=2),encoding='utf-8')


if __name__ == '__main__':
    main()
