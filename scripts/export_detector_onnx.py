"""Optional export; install ONNX export dependencies separately."""
import argparse
from pathlib import Path
from ultralytics import YOLO

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--weights',type=Path,default=Path(__file__).resolve().parents[1]/'models/detector_best.pt')
    args = parser.parse_args()
    if not args.weights.is_file():
        raise FileNotFoundError(args.weights)
    YOLO(str(args.weights)).export(format='onnx',imgsz=640,batch=1,
        dynamic=False,simplify=False,nms=False,device='cpu')
