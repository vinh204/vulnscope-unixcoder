# VulnScope — UniXcoder Vulnerability Detection

Demo đồ án phát hiện lỗ hổng ở mức hàm C/C++ bằng UniXcoder. Hệ thống hỗ trợ dự đoán nhị phân, giải thích bằng token occlusion, so sánh trước/sau bản vá và dashboard kết quả thực nghiệm.

## Cài đặt

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

## Chạy demo

```powershell
streamlit run code/app.py
```

Mặc định ứng dụng tìm checkpoint tại `outputs/checkpoint-best-f1/model.bin`. Khi chưa có checkpoint, ứng dụng bật **chế độ minh họa**. Chế độ này chỉ kiểm tra giao diện bằng quy tắc đơn giản, được ghi nhãn rõ ràng và không được dùng làm kết quả báo cáo.

## Dữ liệu Devign

Dataset chính thức đã được đặt trong `data/devign/`. Pipeline đọc được cả JSON array và JSONL. Mỗi mẫu Devign có dạng:

```json
{
  "idx": 1,
  "func": "void f(char *s) { char b[8]; strcpy(b, s); }",
  "target": 1
}
```

`target=1` là vulnerable, `target=0` là safe. Các split chính thức gồm 21.854 mẫu train, 2.732 mẫu validation và 2.732 mẫu test.

Nếu cần tạo lại split sau khi tải `function.json` và ba file chỉ mục:

```powershell
python code/prepare_devign.py --data-dir data/devign
```

## Huấn luyện

```powershell
python code/run.py `
  --do_train --do_eval `
  --train_data_file data/devign/train.jsonl `
  --eval_data_file data/devign/valid.jsonl `
  --output_dir outputs `
  --validation_metric f1
```

Checkpoint tốt nhất được lưu theo metric, ví dụ `outputs/checkpoint-best-f1/model.bin`.

## Đánh giá và tạo dashboard

```powershell
python code/evaluate.py `
  --data data/devign/test.jsonl `
  --checkpoint outputs/checkpoint-best-f1/model.bin
```

Lệnh tạo `results/metrics.json` và `results/predictions.csv`; trang Dashboard chỉ hiển thị các kết quả thật này, không tự tạo số liệu mẫu.

## Kiểm thử

```powershell
python -m unittest discover -s tests -v
python -m compileall code
```

## Cấu trúc chính

- `code/run.py`: fine-tuning và đánh giá trong từng epoch.
- `code/inference.py`: nạp checkpoint, dự đoán và token occlusion.
- `code/evaluate.py`: đánh giá test set, xuất artifact cho dashboard.
- `code/metrics.py`: metric nhị phân an toàn khi lớp bị thiếu.
- `code/app.py`: ứng dụng Streamlit.

## Lưu ý khoa học

Attribution cho biết token ảnh hưởng đến dự đoán, không chứng minh token đó là nguyên nhân lỗ hổng. Khi báo cáo kết quả cần dùng split chống trùng lặp, nhiều random seed, baseline và ablation; không dùng chế độ minh họa làm số liệu thực nghiệm.
