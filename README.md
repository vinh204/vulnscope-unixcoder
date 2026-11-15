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

Tải bộ CodeXGLUE Defect Detection (Devign) từ [kho chính thức Microsoft/CodeXGLUE](https://github.com/microsoft/CodeXGLUE/tree/main/Code-Code/Defect-detection), rồi đặt các tệp `train.jsonl`, `valid.jsonl` và `test.jsonl` vào `data/devign/`. Mỗi dòng là một đối tượng JSON có trường `func` (mã hàm), `target` (nhãn) và `idx` (chỉ mục). `target=1` là vulnerable theo nhãn bộ dữ liệu; `target=0` là non-vulnerable. Bộ split chính thức có 21.854 mẫu train, 2.732 validation và 2.732 test.

`code/prepare_devign.py` là bước chuyển đổi từ bản dữ liệu gốc dạng `function.json` cùng các file chỉ mục `train.txt`, `valid.txt` và `test.txt`; nó không giải nén hoặc tải dữ liệu thay bạn. Nếu dùng các JSONL đã được CodeXGLUE tiền xử lý, không cần chạy bước chuyển đổi này. Lưu lại nguồn tải, phiên bản/commit và checksum của dữ liệu trong hồ sơ nộp để người khác có thể xác định chính xác bản dữ liệu đã dùng.

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

`training.log` ghi tiến trình và thời gian; `training_history.json` lưu loss và các chỉ số của từng epoch; `run_summary.json` lưu thời gian chạy và epoch tốt nhất; `training_config.json` lưu cấu hình. Checkpoint chọn theo F1 được lưu ở `outputs/devign_ft_gpu_run1/checkpoint-best-f1/model.bin`. Lần chạy mới mặc định không lưu `checkpoint-last`; thêm `--save_last_checkpoint` nếu cần tiếp tục sau khi gián đoạn.

Nếu muốn có thể resume, thêm cờ sau vào lệnh huấn luyện:

```bash
--save_last_checkpoint
```

Sau đó có thể tiếp tục từ `outputs/devign_ft_gpu_run1/checkpoint-last` bằng `--resume_from_checkpoint`.

### Chạy xác nhận lại cấu hình `2e-5`

Để đối chiếu lần chạy trước, giữ cùng learning rate, seed, dữ liệu và chọn checkpoint theo F1 validation. Lưu vào thư mục mới để không ghi đè checkpoint cũ:

```bash
export PYTHONHASHSEED=42
python3 -u code/run.py \
  --do_train --do_eval \
  --train_data_file data/devign/train.jsonl \
  --eval_data_file data/devign/valid.jsonl \
  --output_dir outputs/devign_ft_lr2e5_repeat \
  --num_train_epochs 3 \
  --block_size 512 \
  --train_batch_size 4 \
  --eval_batch_size 8 \
  --gradient_accumulation_steps 4 \
  --learning_rate 2e-5 \
  --seed 42 \
  --validation_metric f1
```

So sánh F1 validation của từng epoch trong `outputs/devign_ft_lr2e5_repeat/training_history.json` với lần cũ (cao nhất 0,6132 ở epoch 2). Nếu cần chốt kết quả test của lần lặp, đánh giá checkpoint tốt nhất một lần:

```bash
python3 code/evaluate_trained_checkpoint.py \
  --checkpoint outputs/devign_ft_lr2e5_repeat/checkpoint-best-f1/model.bin \
  --validation-data data/devign/valid.jsonl \
  --test-data data/devign/test.jsonl \
  --output-dir results/devign_ft_lr2e5_repeat
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

Trong lần chạy hiện tại, checkpoint được chọn tại epoch 2 theo F1 validation của vòng huấn luyện (`0,6132`, ở ngưỡng mặc định `0,5`). Sau đó script đánh giá chọn thêm ngưỡng `0,2718` để tối đa F1 trên cùng validation; F1 validation tại ngưỡng này là `0,6571`. Ngưỡng được khóa trước khi chấm test. Vì cùng validation được dùng để chọn checkpoint và tối ưu ngưỡng, F1 validation sau tối ưu có thể lạc quan; chỉ số test là kết quả held-out chính.

Lệnh lưu metric, dự đoán và metadata SHA-256 của checkpoint. Không dùng tập test để chọn checkpoint hay ngưỡng.

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
