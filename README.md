# VulnScope - Phát hiện lỗ hổng mã nguồn bằng UniXcoder

Đồ án xây dựng ứng dụng hỗ trợ phân loại hàm C/C++ có dấu hiệu lỗ hổng bằng UniXcoder. Ứng dụng có các chức năng phân tích mã, so sánh hai phiên bản và xem kết quả đánh giá.

## Cài đặt

Yêu cầu Python 3.10 trở lên.

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

## Dữ liệu

Đặt các tệp Devign trong `data/devign/`:

- `train.jsonl`
- `valid.jsonl`
- `test.jsonl`

Mỗi dòng là một đối tượng JSON có trường `func` (mã hàm), `target` (nhãn) và `idx` (chỉ mục). `target=1` là vulnerable theo nhãn bộ dữ liệu; `target=0` là non-vulnerable theo nhãn bộ dữ liệu.

## Chạy ứng dụng cục bộ

```powershell
streamlit run code/app.py
```

Ứng dụng sử dụng checkpoint cục bộ nếu có tại `outputs/devign_full_ft_cpu/checkpoint-best-f1/model.bin`; nếu không, ứng dụng tải checkpoint demo công khai đã cấu hình trong mã nguồn. Để phát triển giao diện mà không tải mô hình, bật chế độ minh họa trong cấu hình ứng dụng. Kết quả chế độ minh họa không dùng làm kết quả thực nghiệm.

## Huấn luyện

```powershell
$env:PYTHONHASHSEED = "42"
python code/run.py `
  --do_train --do_eval `
  --train_data_file data/devign/train.jsonl `
  --eval_data_file data/devign/valid.jsonl `
  --output_dir outputs/devign_full_ft_cpu `
  --num_train_epochs 3 `
  --block_size 512 `
  --train_batch_size 4 `
  --eval_batch_size 8 `
  --gradient_accumulation_steps 4 `
  --learning_rate 2e-5 `
  --seed 42 `
  --validation_metric f1
```

Checkpoint tốt nhất được lưu trong `outputs/devign_full_ft_cpu/checkpoint-best-f1/`.

## Đánh giá checkpoint

```powershell
python code/evaluate_trained_checkpoint.py `
  --checkpoint outputs/devign_full_ft_cpu/checkpoint-best-f1/model.bin `
  --validation-data data/devign/valid.jsonl `
  --test-data data/devign/test.jsonl `
  --output-dir results/devign_full_ft_cpu_final
```

Ngưỡng phân loại được chọn trên validation trước khi đánh giá test. Kết quả được lưu trong `results/devign_full_ft_cpu_final/`.

## Baseline và phân tích

```powershell
python code/compare_baselines.py --output-dir results/devign_baseline
python code/analyze_results.py
```

Trong lần chạy đã báo cáo, UniXcoder đạt F1 0,6643 và baseline TF-IDF + Logistic Regression đạt F1 0,6663 trên test. Kết quả hiện tại chưa cho thấy UniXcoder có F1 cao hơn baseline.

## Cấu trúc chính

```text
code/       mã ứng dụng, huấn luyện, suy luận và đánh giá
data/       dữ liệu Devign
outputs/    checkpoint và cấu hình huấn luyện
results/    metric và dự đoán
tests/      kiểm thử tự động
```

Checkpoint lớn, môi trường ảo và tài liệu báo cáo không được lưu trong Git. Không commit token hoặc thông tin bí mật vào repository.

## Giới hạn

Đánh giá định lượng hiện tại sử dụng Devign, chủ yếu gồm hàm C. Giao diện nhận một số phần mở rộng C/C++, nhưng điều đó không đồng nghĩa mô hình đã được đánh giá trên mọi ngôn ngữ. Kết quả dự đoán chỉ hỗ trợ sàng lọc, không xác nhận mã an toàn, CWE hay khả năng khai thác.
