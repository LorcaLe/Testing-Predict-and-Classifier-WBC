"""Portable YOLO training entry point; the original run is in reports/detector."""
import argparse
from pathlib import Path
from ultralytics import YOLO

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--data',type=Path,required=True,help='Dataset YAML with an absolute dataset path.')
    parser.add_argument('--device',default='cpu')
    parser.add_argument('--epochs',type=int,default=20)
    parser.add_argument('--batch',type=int,default=16)
    args = parser.parse_args()
    YOLO('yolov8n.pt').train(data=str(args.data.resolve()),epochs=args.epochs,
        imgsz=640,batch=args.batch,device=args.device,workers=2,seed=0,
        patience=100,project='runs',name='txl_pbc_retrain')
