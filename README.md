# Leukocyte AI — bộ bàn giao nghiên cứu và tích hợp .NET

Bộ này chứa model và code để test tính năng.
Checkpoint được lấy từ ba ZIP Google Drive của LorcaLe - được copy từ GG Colab

## Trạng thái

- **Detector:** YOLOv8n, 3 lớp `0=WBC`, `1=RBC`, `2=Platelet`; run TXL-PBC có 20 epoch.
- **Classifier:** EfficientNet-B0, đầu ra 1 logit, checkpoint epoch 5; `hem=0`, `all=1`.
- Detector đã có lệnh dự đoán ảnh hoàn chỉnh và JSON bounding box.
- Classifier có script chạy thử trên **ảnh crop một tế bào**.
- Chưa triển khai HTTP API, chưa xác nhận độ chính xác pipeline detector → classifier, chưa xác nhận parity ONNX/C#.
- Không phải hệ thống chẩn đoán đã được kiểm chứng. Xem `docs/MODEL_CARD.md` để biết kết quả và giới hạn thực nghiệm.

## Cài đặt và chạy

Chạy các lệnh từ thư mục chứa README này. Môi trường kiểm tra: Python 3.12, CPU.

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe predict.py --image "D:\images\smear.png" --output outputs/detection.json
.\.venv\Scripts\python.exe classify.py --image "D:\images\single_cell.png" --output outputs/classification.json
```

`requirements.txt` ghi phiên bản đã có trong môi trường local. Chưa kiểm tra cài mới từ registry trên máy khác; `reports/environment.json` ghi môi trường đối chiếu.
Inference không cần dataset train. Hai checkpoint đã có trong `models/`.
Đã chạy thử hai CLI trên ảnh tổng hợp; detector chạy thêm trên một ảnh validation thật (15 box, kiểm tra tọa độ hợp lệ); 8 test chia split đều qua. Chi tiết: `reports/verification.json`. Đây là kiểm tra chạy chương trình, không thay thế đánh giá độ chính xác.
`examples/synthetic.png` là ảnh nhân tạo chỉ để kiểm tra luồng chạy, không để đánh giá model:

```powershell
.\.venv\Scripts\python.exe predict.py --image examples/synthetic.png
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

## Test detect và crop ảnh bạch cầu — chạy file nào?

**Chạy `predict.py`** để phát hiện tế bào và cắt riêng từng bạch cầu WBC. Không cần chạy notebook hoặc train lại. File `models/detector_best.pt` được nạp tự động.

Đã kèm **6 ảnh máu hiển vi thật** trong `examples/blood_cells/images/`, nhãn YOLO gốc, manifest và giấy phép MIT. Đây là mẫu từ validation TXL-PBC để thử tính năng, không phải tập test độc lập. Xem `examples/blood_cells/README.md` để biết nguồn.

Sau khi cài môi trường ở trên, có thể test ngay bằng lệnh sau, không cần tải thêm dataset:

```powershell
.\.venv\Scripts\python.exe predict.py --image examples/blood_cells/images/sample_01.png --output outputs/detection.json --annotated outputs/detected.png --crop-dir outputs/wbc_crops
```

Hoặc chạy **cả 6 ảnh** với một lệnh:

```powershell
.\.venv\Scripts\python.exe scripts/demo_detect_crop.py
```

Mở `outputs/demo/sample_01/detected.png` để xem detect và `outputs/demo/sample_01/wbc_crops/` để xem crop. Tương tự cho `sample_02` đến `sample_06`; `outputs/demo/summary.json` tổng hợp số tế bào theo nhãn gốc và số dự đoán.

Các lệnh dưới đây dùng ảnh riêng: thay `D:\images\smear.png` bằng đường dẫn PNG/JPG của bạn. Chạy lệnh từ thư mục chứa README này.

### 1. Chỉ test detect

```powershell
.\.venv\Scripts\python.exe predict.py --image "D:\images\smear.png" --output outputs/detection.json --annotated outputs/detected.png
```

Mở `outputs/detected.png` để xem khung, nhãn và confidence của WBC, RBC, Platelet. `outputs/detection.json` chứa nhãn, confidence và tọa độ từng box trên ảnh gốc, dùng để tham khảo khi làm backend.

### 2. Test detect và crop riêng từng bạch cầu

```powershell
.\.venv\Scripts\python.exe predict.py --image "D:\images\smear.png" --output outputs/detection.json --annotated outputs/detected.png --crop-dir outputs/wbc_crops
```

Kết quả:

- `outputs/detected.png`: ảnh có khung và nhãn của cả 3 loại tế bào.
- `outputs/detection.json`: kết quả detect; trường `wbc_crops` ghi đường dẫn từng ảnh crop, box crop và chỉ số detection tương ứng.
- `outputs/wbc_crops/<tên_ảnh>_<mã_lần_chạy>/wbc_000.png`, `wbc_001.png`, ...: mỗi file là một **WBC (class 0)**. Không crop RBC/Platelet.

Terminal in ra số ảnh crop và thư mục vừa tạo. Mỗi lần chạy tạo thư mục con mới để không lẫn ảnh cũ. Crop giữ độ phân giải vùng ảnh gốc, làm tròn box ra ngoài và giới hạn trong biên ảnh; chưa resize 224×224. Nếu không phát hiện WBC, `wbc_crops` là danh sách rỗng và không có ảnh crop — không phải lỗi chương trình.

Mặc định confidence `0.25`, IoU NMS `0.7`, CPU. Có thể thêm `--confidence 0.4` để lọc chặt hơn; dùng `--device 0` nếu đã cài PyTorch CUDA và có GPU phù hợp. Ảnh `examples/synthetic.png` chỉ kiểm tra luồng chạy, không dùng để kỳ vọng có WBC thật.

### 3. Nếu muốn thử classifier trên ảnh đã crop

**Chạy `classify.py`**, thay đường dẫn bên dưới bằng một file crop thực tế được ghi trong `wbc_crops`:

```powershell
.\.venv\Scripts\python.exe classify.py --image "outputs/wbc_crops/<thư_mục_vừa_tạo>/wbc_000.png" --output outputs/classification.json
```

Script tự chuẩn bị ảnh 224×224 và nạp `models/classifier_best.pt`. Đây là bước thử nghiên cứu riêng; preprocessing với code train gốc và độ chính xác trên crop detector chưa được xác nhận. Xem `docs/MODEL_CARD.md`.

Nếu muốn đọc cách làm trong Colab, xem `notebooks/Day2.ipynb` (detect, crop WBC, chuẩn bị tensor); `notebooks/Day1.ipynb` dùng train detector.

## Cấu trúc

| Đường dẫn | Nội dung |
|---|---|
| `models/detector_best.pt` | Checkpoint YOLO từ run T4 trên Drive |
| `models/classifier_best.pt` | Checkpoint C-NMC tốt nhất được lưu, epoch 5 |
| `models/model_info.json` | Nguồn file, SHA-256, metadata và số liệu gốc |
| `predict.py` | Detect, vẽ khung, crop WBC và xuất JSON |
| `classify.py` | Thử phân loại một ảnh crop tế bào, xuất JSON |
| `notebooks/` | Day1 train YOLO và Day2 inference/crop, đã bỏ output |
| `configs/` | Cấu hình dữ liệu và kế hoạch baseline ban đầu |
| `scripts/` | Audit dữ liệu, chia split, train detector và export ONNX |
| `tests/` | Test logic chia dữ liệu C-NMC |
| `reports/` | Log và biểu đồ chọn lọc; summary pilot C-NMC |
| `docs/DOTNET_INTEGRATION.md` | Giao tiếp đề xuất với backend .NET |
| `docs/DATA.md` | Bố trí dữ liệu khi tái lập nghiên cứu |

Notebook giữ nguyên đường dẫn Colab để truy nguyên; chỉnh đường dẫn Drive khi chạy lại. `configs/baseline_plan.json` là **kế hoạch cũ**, không đại diện cho mọi tham số của checkpoint đã train. Tham số run detector thực tế ở `reports/detector/args.yaml`.

## Train lại detector / export

Sửa `path` trong `configs/txl_pbc.yaml` thành đường dẫn tuyệt đối đến TXL-PBC trên máy chạy.

```powershell
python scripts/train_detector.py --data configs/txl_pbc.yaml --device cpu
python scripts/export_detector_onnx.py
```

Train cần dữ liệu gốc và có thể tải pretrained `yolov8n.pt`. Export ONNX là tùy chọn, cần phụ thuộc export phù hợp với Ultralytics; chưa chạy export trong lần bàn giao này. Không cần export để chạy Python inference.
