# 6 ảnh máu hiển vi để thử detect/crop

Nguồn: [TXL-PBC, lugan113](https://github.com/lugan113/TXL-PBC_Dataset).
README của nguồn công bố dataset theo MIT; bản giấy phép được giữ nguyên trong `LICENSE.txt`.
Trích dẫn: Gan, L., Li, X. & Wang, X. A Curated and Re-annotated Peripheral Blood Cell Dataset Integrating Four Public Resources. Scientific Data 12, 1694 (2025). https://doi.org/10.1038/s41597-025-05980-z

Ảnh và nhãn được sao chép nguyên nội dung từ split **val** của bản dữ liệu local; chỉ đổi tên thành `sample_01` đến `sample_06` để dễ chạy. Chọn 6 vị trí cách đều trong danh sách tên ảnh có ít nhất một nhãn WBC, không chọn theo kết quả dự đoán của model.

- `images/`: ảnh PNG thật.
- `labels/`: nhãn YOLO gốc; mỗi dòng `class_id x_center y_center width height`, tọa độ chuẩn hóa 0–1. Lớp `0=WBC`, `1=RBC`, `2=Platelet`.
- `manifest.json`: ánh xạ tên gốc, split, kích thước, checksum và số tế bào theo nhãn gốc.

Bộ này chỉ để demo tính năng. Vì lấy từ validation đã dùng trong quá trình train, không dùng kết quả ở đây để báo cáo độ chính xác test độc lập. Nhãn là nhãn tế bào, không có nhãn bệnh ALL/HEM. Số WBC model phát hiện có thể khác số WBC trong nhãn gốc.

Từ gốc repository, chạy:

```powershell
.\.venv\Scripts\python.exe predict.py --image examples/blood_cells/images/sample_01.png --annotated outputs/demo/detected.png --crop-dir outputs/demo/wbc_crops --output outputs/demo/detection.json
```

Hoặc chạy cả 6 ảnh:

```powershell
.\.venv\Scripts\python.exe scripts/demo_detect_crop.py
```

Kết quả từng ảnh trong `outputs/demo/sample_01/`, ..., `sample_06/`; xem `detected.png`, `detection.json` và `wbc_crops/`. Bảng số lượng dự đoán/nhãn gốc được lưu ở `outputs/demo/summary.json`, chỉ để đối chiếu demo, không phải metric đánh giá.
