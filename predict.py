"""Run the packaged detector on one local image and write a JSON response."""
import argparse
import hashlib
import json
import math
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent


def predict(image, weights, confidence=0.25, iou=0.7, device='cpu', crop_dir=None, annotated=None):
    from PIL import Image
    from ultralytics import YOLO
    image, weights = Path(image), Path(weights)
    if not image.is_file() or not weights.is_file():
        raise FileNotFoundError('Image and weights must be existing local files.')
    if not 0 <= confidence <= 1 or not 0 <= iou <= 1:
        raise ValueError('Confidence and IoU must be between 0 and 1.')
    model = YOLO(str(weights))
    result = model.predict(source=str(image), imgsz=640, conf=confidence,
                           iou=iou, device=device, verbose=False)[0]
    detections = []
    for box in result.boxes:
        class_id = int(box.cls.item())
        detections.append({'class_id':class_id, 'label':result.names[class_id],
                           'confidence':float(box.conf.item()),
                           'box_xyxy':[float(v) for v in box.xyxy[0].tolist()]})
    height, width = result.orig_shape
    response = {'schema_version':'1.0', 'task':'cell_detection',
            'model':weights.name, 'model_sha256':hashlib.sha256(weights.read_bytes()).hexdigest(),
            'image':{'filename':image.name,'width':width,'height':height},
            'settings':{'image_size':640,'confidence':confidence,'iou':iou},
            'detections':detections}
    if annotated is not None:
        annotated = Path(annotated)
        annotated.parent.mkdir(parents=True,exist_ok=True)
        Image.fromarray(result.plot()[..., ::-1]).save(annotated)
        response['annotated_image'] = str(annotated)
    if crop_dir is not None:
        if result.names.get(0) != 'WBC':
            raise ValueError('Crop requires class 0 to be WBC.')
        crop_dir = Path(crop_dir)
        crop_dir.mkdir(parents=True,exist_ok=True)
        # Separate runs prevent stale crops being mistaken for new detections.
        run_dir = Path(tempfile.mkdtemp(prefix=image.stem + '_',dir=crop_dir))
        original = Image.fromarray(result.orig_img[..., ::-1])
        crops = []
        for index, detection in enumerate(detections):
            if detection['class_id'] != 0:
                continue
            left, top, right, bottom = detection['box_xyxy']
            box = (max(0,math.floor(left)),max(0,math.floor(top)),
                   min(width,math.ceil(right)),min(height,math.ceil(bottom)))
            if box[2] <= box[0] or box[3] <= box[1]:
                continue
            path = run_dir / f'wbc_{len(crops):03d}.png'
            original.crop(box).save(path)
            crops.append({'detection_index':index,'file':str(path),
                          'crop_box_xyxy':list(box)})
        response['wbc_crop_dir'] = str(run_dir)
        response['wbc_crops'] = crops
    return response


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--image',type=Path,required=True)
    parser.add_argument('--weights',type=Path,default=ROOT/'models/detector_best.pt')
    parser.add_argument('--output',type=Path,default=Path('outputs/prediction.json'))
    parser.add_argument('--confidence',type=float,default=0.25)
    parser.add_argument('--iou',type=float,default=0.7)
    parser.add_argument('--device',default='cpu')
    parser.add_argument('--crop-dir',type=Path,help='Save original-resolution WBC crops in a new subfolder.')
    parser.add_argument('--annotated',type=Path,help='Save an image with detection boxes and labels.')
    args = parser.parse_args()
    response = predict(args.image,args.weights,args.confidence,args.iou,args.device,
                       crop_dir=args.crop_dir,annotated=args.annotated)
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(response,indent=2),encoding='utf-8')
    print(f'Saved {args.output}')
    if args.crop_dir is not None:
        print(f"Saved {len(response['wbc_crops'])} WBC crops in {response['wbc_crop_dir']}")


if __name__ == '__main__':
    main()
