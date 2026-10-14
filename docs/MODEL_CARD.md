# Thông tin model và giới hạn

## Detector

- File: `models/detector_best.pt`, nguồn `txl_pbc_t4_local/weights/best.pt`.
- YOLOv8n, ảnh inference 640, class ID phải kiểm tra từ model; bản này WBC/RBC/Platelet.
- `reports/detector/results.csv` ghi 20 epoch. Ở epoch 20: precision 0.97461, recall 0.94218, mAP50 0.98541, mAP50-95 0.84956.
- Các con số trên lấy từ log validation của lần train, không phải đánh giá mới trên test độc lập. Không tự đồng nhất dòng cuối CSV với một kết quả đánh giá checkpoint mới chạy.
- Chưa xác minh độc lập near-duplicate hoặc phân tách nguồn của TXL-PBC trong bộ bàn giao này.

## Classifier

- File: `models/classifier_best.pt`, nguồn `cnmc_head_epochs_2_to_5_.../best.pt`, metadata epoch 5.
- Architecture `efficientnet_b0`; state dict có `classifier.1.weight` shape `[1,1280]`.
- Label map `hem=0`, `all=1`; threshold 0.5 trong checkpoint.
- Metadata: ảnh 224, giữ tỉ lệ, pad đen, mean `[0.485,0.456,0.406]`, std `[0.229,0.224,0.225]`.
- `classify.py` dùng sigmoid cho đầu ra một logit. Đây là cách diễn giải để chạy thử; cần code train gốc để xác nhận loss/output semantics. Interpolation chưa được checkpoint ghi; LANCZOS được chọn theo notebook Day2, chưa xác minh parity với train classifier.
- Số liệu lưu trong checkpoint: sensitivity 0.93122, specificity 0.44271; TP 2288, FN 169, FP 608, TN 483. Specificity thấp cho thấy nhiều mẫu HEM bị gán ALL ở threshold hiện tại.
- Chưa hiệu chỉnh xác suất, chưa chọn threshold mới, chưa đánh giá lại test, chưa xác nhận performance trên crop detector từ TXL-PBC. Score không phải xác suất bệnh của bệnh nhân.

