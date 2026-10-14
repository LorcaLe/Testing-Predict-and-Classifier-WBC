# Dữ liệu nghiên cứu

Toàn bộ dataset gốc không nằm trong bộ GitHub. Có kèm 6 mẫu validation TXL-PBC với nhãn và giấy phép tại `examples/blood_cells/` để test detect/crop ngay; xem README ở đó để biết nguồn và cách chạy. Lấy phần dữ liệu đầy đủ từ nguồn của dự án và giữ tài liệu nguồn/điều kiện sử dụng đi kèm.

Detector cần:

```text
Data/TXL-PBC_Dataset/TXL-PBC/
  images/train/
  images/val/
  labels/train/
  labels/val/
```

Sửa `configs/txl_pbc.yaml` với `path` tuyệt đối trỏ đến thư mục TXL-PBC. Nhãn YOLO: 0 WBC, 1 RBC, 2 Platelet.

Code audit và chia C-NMC được giữ nguyên từ dự án. Chúng tìm dữ liệu ở `Data/` tương đối với gốc repo và tạo kết quả trong `outputs/`:

```powershell
python scripts/audit_data.py
python scripts/build_cnmc_splits.py
python -m unittest discover -s tests -v
```

`build_cnmc_splits.py` cần cấu trúc nguồn `Data/PKG - C-NMC 2019/` như dự án gốc. Đây là logic chia dữ liệu để nghiên cứu; việc kiểm tra SHA-256/subject ID không tự chứng minh đã loại hết ảnh gần trùng.
Các manifest và checkpoint classifier cần được đối chiếu với code train gốc trước khi khẳng định classifier đã train trên đúng split này.

`examples/synthetic.png` được tạo bằng hình học đơn giản, không thuộc dataset và chỉ dùng kiểm tra chương trình chạy. Không đưa ảnh dataset/ảnh bệnh nhân vào examples khi chưa rõ quyền chia sẻ.
