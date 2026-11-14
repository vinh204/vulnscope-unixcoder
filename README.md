# VulnScope – Phát hiện lỗ hổng mã nguồn bằng UniXcoder

Đồ án xây dựng ứng dụng hỗ trợ phân loại hàm C/C++ có dấu hiệu lỗ hổng bằng UniXcoder. Ứng dụng phân tích mã, so sánh hai phiên bản và hiển thị kết quả đánh giá.

## Cài đặt

Yêu cầu Python 3.10 trở lên.

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

## Dữ liệu

Đặt các tệp Devign trong `data/devign/`: `train.jsonl`, `valid.jsonl` và `test.jsonl`. Mỗi dòng là một đối tượng JSON có trường `func` (mã hàm), `target` (nhãn) và `idx` (chỉ mục). `target=1` là vulnerable theo nhãn bộ dữ liệu; `target=0` là non-vulnerable.

## Huấn luyện

Lần fine-tune GPU được ghi nhận dùng UniXcoder base, toàn bộ 21.854 mẫu train mỗi epoch, 3 epoch, seed 42 và RTX 3090 24 GB. Tổng thời gian chạy, gồm bước đánh giá, là **27 phút 23 giây**. F1 validation cao nhất là **0,6132 tại epoch 2**; epoch 3 đạt 0,5824. Checkpoint tốt nhất và log đã tải về nằm tại `outputs/devign_ft_gpu_run1/`.

Lệnh đã chạy trên máy Ubuntu có GPU:

```bash
export PYTHONHASHSEED=42
python3 -u code/run.py \
  --do_train --do_eval \
  --train_data_file data/devign/train.jsonl \
  --eval_data_file data/devign/valid.jsonl \
  --output_dir outputs/devign_ft_gpu_run1 \
  --num_train_epochs 3 \
  --block_size 512 \
  --train_batch_size 4 \
  --eval_batch_size 8 \
  --gradient_accumulation_steps 4 \
  --learning_rate 2e-5 \
  --seed 42 \
  --validation_metric f1
```

`training.log` ghi tiến trình và thời gian; `training_history.json` lưu loss và các chỉ số của từng epoch; `run_summary.json` lưu thời gian chạy và epoch tốt nhất; `training_config.json` lưu cấu hình. Checkpoint chọn theo F1 được lưu ở `outputs/devign_ft_gpu_run1/checkpoint-best-f1/model.bin`. Trạng thái có thể resume nằm ở `checkpoint-last/`.

Để tiếp tục huấn luyện sau khi bị dừng, giữ nguyên tham số và thêm:

```bash
--resume_from_checkpoint outputs/devign_ft_gpu_run1/checkpoint-last
```

## Đánh giá trên test

Sau khi chọn checkpoint theo validation, đánh giá tập test một lần:

```powershell
python code/evaluate_trained_checkpoint.py `
  --checkpoint outputs/devign_ft_gpu_run1/checkpoint-best-f1/model.bin `
  --validation-data data/devign/valid.jsonl `
  --test-data data/devign/test.jsonl `
  --output-dir results/devign_ft_gpu_run1
```

Lệnh chọn ngưỡng trên validation trước khi chấm test, rồi lưu metric, dự đoán và metadata SHA-256 của checkpoint. Không dùng tập test để chọn cấu hình.

## Chạy ứng dụng

```powershell
streamlit run code/app.py
```

Ứng dụng mặc định dùng checkpoint mới tại `outputs/devign_ft_gpu_run1/checkpoint-best-f1/model.bin`. Có thể đổi đường dẫn bằng biến môi trường `CHECKPOINT_PATH`. Nếu chưa có checkpoint cục bộ, ứng dụng dùng checkpoint demo công khai được cấu hình trong mã nguồn. Kết quả chế độ minh họa không dùng làm kết quả thực nghiệm.

## Baseline và phân tích

```powershell
python code/compare_baselines.py --output-dir results/devign_baseline
python code/analyze_results.py
```

`analyze_results.py` so sánh baseline TF-IDF với kết quả fine-tune GPU mới trong `results/devign_ft_gpu_run1/`. Hãy chạy bước đánh giá checkpoint trước khi tạo so sánh. Kết quả fine-tune CPU cũ đã được dọn khỏi dự án.

## Cấu trúc chính

```text
code/       ứng dụng, huấn luyện, suy luận và đánh giá
data/       dữ liệu Devign (tải riêng, không lưu trong Git)
outputs/    checkpoint và log fine-tune (không lưu trong Git)
results/    metric và dự đoán
tests/      kiểm thử tự động
```

Checkpoint lớn, môi trường ảo và dữ liệu tải về không được lưu trong Git. Không commit token hoặc thông tin bí mật.

## Giới hạn

Đánh giá định lượng hiện tại dùng Devign, chủ yếu gồm hàm C. Giao diện nhận một số phần mở rộng C/C++, nhưng mô hình chưa được đánh giá trên mọi ngôn ngữ. Dự đoán chỉ hỗ trợ sàng lọc; nó không xác nhận mã an toàn, CWE hay khả năng khai thác.
