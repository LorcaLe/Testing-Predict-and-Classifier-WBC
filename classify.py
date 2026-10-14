"""Research inference on a single cell crop; see docs/MODEL_CARD.md."""
import argparse
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent


def classify(image, weights):
    import numpy as np
    import torch
    from PIL import Image, ImageOps
    from torchvision.models import efficientnet_b0
    checkpoint = torch.load(weights,map_location='cpu',weights_only=True)
    if checkpoint['architecture'] != 'efficientnet_b0' or checkpoint['label_map'] != {'hem':0,'all':1}:
        raise ValueError('Unsupported architecture or label mapping.')
    preprocessing = checkpoint['preprocessing']
    if preprocessing['resize'] != 'preserve_aspect_ratio' or preprocessing['padding'] != 'black':
        raise ValueError('Unsupported preprocessing.')
    model = efficientnet_b0(weights=None)
    model.classifier[1] = torch.nn.Linear(model.classifier[1].in_features,1)
    model.load_state_dict(checkpoint['model_state_dict'],strict=True)
    model.eval()
    size = preprocessing['image_size']
    with Image.open(image) as source:
        resized = ImageOps.contain(source.convert('RGB'),(size,size),Image.Resampling.LANCZOS)
        canvas = Image.new('RGB',(size,size),(0,0,0))
        canvas.paste(resized,((size-resized.width)//2,(size-resized.height)//2))
    tensor = torch.from_numpy(np.asarray(canvas,dtype=np.float32)/255).permute(2,0,1)
    mean = torch.tensor(preprocessing['mean'])[:,None,None]
    std = torch.tensor(preprocessing['std'])[:,None,None]
    with torch.inference_mode():
        probability = torch.sigmoid(model(((tensor-mean)/std).unsqueeze(0))).item()
    threshold = checkpoint['threshold']
    return {'schema_version':'1.0','task':'cell_classification_research',
            'image':Path(image).name,'model':Path(weights).name,
            'score_all':probability,'threshold':threshold,
            'label':'all' if probability >= threshold else 'hem',
            'preprocessing_parity_verified':False,
            'note':'Single-logit sigmoid interpretation; original training code and interpolation parity remain unverified.'}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--image',type=Path,required=True,help='Single-cell crop, not a whole smear.')
    parser.add_argument('--weights',type=Path,default=ROOT/'models/classifier_best.pt')
    parser.add_argument('--output',type=Path,default=Path('outputs/classification.json'))
    args = parser.parse_args()
    result = classify(args.image,args.weights)
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(result,indent=2),encoding='utf-8')
    print(f'Saved {args.output}')
