# VulnScope — UniXcoder Vulnerability Detection

Demo đồ án phát hiện lỗ hổng ở mức hàm C/C++ bằng UniXcoder. Hệ thống hỗ trợ dự đoán nhị phân, giải thích bằng token occlusion, so sánh trước/sau bản vá và dashboard kết quả thực nghiệm.

**Demo trực tiếp:** [vulnscope-unixcoder.streamlit.app](https://vulnscope-unixcoder.streamlit.app/)

## Cấu trúc dự án

```text
code/       mã ứng dụng, huấn luyện, suy luận và đánh giá
data/       bộ dữ liệu Devign dùng cho thí nghiệm
outputs/    checkpoint và cấu hình huấn luyện
results/    metric và dự đoán cần cho demo
tests/      kiểm thử tự động
```

`.venv/`, dữ liệu, checkpoint và tài liệu báo cáo được giữ cục bộ, không đưa vào repository. Các kết quả được giữ trong Git chỉ gồm artifact cần để chạy dashboard.

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

Ứng dụng ưu tiên checkpoint full fine-tuning tại
`outputs/devign_full_ft_cpu/checkpoint-best-f1/model.bin`. Nếu file không tồn tại,
ứng dụng tự tải checkpoint demo công khai đã ghim phiên bản từ
[`vinh204/vulnscope-unixcoder-devign`](https://huggingface.co/vinh204/vulnscope-unixcoder-devign).
Checkpoint full fine-tuning dùng block size 512 và ngưỡng cảnh báo 0,3277; checkpoint demo
công khai dùng block size 128 và ngưỡng 0,191. Giao diện chọn mặc định tương ứng với checkpoint
đang được nạp.

Checkpoint full fine-tuning có dung lượng lớn và không được đưa vào Git. Khi chạy local, cần giữ
checkpoint tại đường dẫn trên. Bản deploy chưa được cập nhật tự động lên checkpoint này; nếu không
cấu hình checkpoint riêng, ứng dụng dùng artifact demo công khai.

Để phát triển giao diện mà không tải mô hình, đặt `APP_ENV=development` và bật
**chế độ minh họa**. Chế độ này chỉ kiểm tra giao diện bằng quy tắc đơn giản,
được ghi nhãn rõ ràng và không được dùng làm kết quả báo cáo.

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

Checkpoint tốt nhất của lần chạy được lưu tại
`outputs/devign_full_ft_cpu/checkpoint-best-f1/model.bin`. Checkpoint này được tạo bằng full
fine-tuning trên 21.854 mẫu, 3 epoch, block size 512 và chạy CPU.

## Đánh giá và tạo dashboard

```powershell
python code/evaluate_trained_checkpoint.py `
  --checkpoint outputs/devign_full_ft_cpu/checkpoint-best-f1/model.bin `
  --validation-data data/devign/valid.jsonl `
  --test-data data/devign/test.jsonl `
  --output-dir results/devign_full_ft_cpu_final
```

Script chọn ngưỡng F1 trên validation, khóa ngưỡng rồi đánh giá test một lần. Kết quả hiện có:
F1 test 0,6643, Recall 0,8932, ROC-AUC 0,6946 và PR-AUC 0,6692. Metric và dự đoán được lưu
trong `results/devign_full_ft_cpu_final/`.

## Baseline và kiểm tra lỗi

```powershell
python code/compare_baselines.py --output-dir results/devign_baseline
python code/analyze_results.py
```

Baseline TF-IDF + Logistic Regression đạt F1 test 0,6663. `analyze_results.py` sinh bảng so sánh,
kiểm tra hash trùng giữa split và phân tích false positive/false negative. Hai mô hình có đánh đổi
khác nhau; kết quả hiện tại chưa chứng minh UniXcoder có F1 cao hơn baseline. Không dùng các kết quả
này để tuyên bố khả năng tổng quát hóa sang dự án chưa thấy vì Devign có trùng hàm và dùng chung dự án
giữa các split.


## Kiểm thử

```powershell
python -m unittest discover -s tests -v
python -m compileall code
```

## Chạy bằng Docker

Checkpoint không được lưu trong Git repository. Khi chạy local, mount checkpoint vào container:

```powershell
docker build -t vulnscope-unixcoder .
docker run --rm -p 7860:7860 `
  -v "${PWD}/outputs/devign_full_ft_cpu/checkpoint-best-f1/model.bin:/app/models/model.bin:ro" `
  vulnscope-unixcoder
```

Mở `http://localhost:7860`. Container chạy bằng user không có quyền root và có health check tại `/_stcore/health`.

## Deploy Hugging Face Space

1. Tạo một **Model repository** và tải `model.bin` lên đó.
2. Tạo một **Docker Space** từ repository này.
3. Cấu hình các biến môi trường:

```text
CHECKPOINT_REPO_ID=vinh204/<ten-model-repo>
CHECKPOINT_FILENAME=model.bin
CHECKPOINT_REVISION=<commit-hash-hoac-tag>
MODEL_NAME=microsoft/unixcoder-base
MODEL_PROFILE=full_finetuned
APP_ENV=production
```

Chỉ đặt `MODEL_PROFILE=full_finetuned` sau khi đã tải checkpoint full fine-tuning mới lên Model repository. Nếu Model repository là private, thêm `HF_TOKEN` dưới dạng Space secret. Không commit token vào source code. Khi khởi động, container tải checkpoint từ Model repository và lưu trong Hugging Face cache.

Lưu ý: Hugging Face hiện yêu cầu gói PRO để tạo Docker/Gradio Space mới. Có thể
deploy miễn phí bằng **Streamlit Community Cloud** với các giá trị:

```text
Repository: vinh204/vulnscope-unixcoder
Branch: main
Main file path: code/app.py
App URL: vulnscope-unixcoder
```

Ứng dụng tự tải checkpoint công khai nên không cần khai báo secret trên
Streamlit Community Cloud.

## CI

GitHub Actions tự động chạy unit test, kiểm tra cú pháp Python và build Docker image cho mỗi push hoặc pull request vào `main`.

## Cấu trúc chính

- `code/run.py`: fine-tuning và đánh giá trong từng epoch.
- `code/inference.py`: nạp checkpoint, dự đoán và token occlusion.
- `code/evaluate.py`: đánh giá test set, xuất artifact cho dashboard.
- `code/evaluate_trained_checkpoint.py`: chọn ngưỡng validation rồi đánh giá test.
- `code/compare_baselines.py`: huấn luyện TF-IDF + Logistic Regression và audit split.
- `code/analyze_results.py`: tạo so sánh mô hình, độ nhạy duplicate và phân tích lỗi.
- `code/metrics.py`: metric nhị phân an toàn khi lớp bị thiếu.
- `code/app.py`: ứng dụng Streamlit.
- `code/bootstrap.py`: chuẩn bị checkpoint và khởi động production server.

## Lưu ý khoa học

Attribution cho biết token ảnh hưởng đến dự đoán, không chứng minh token đó là nguyên nhân lỗ hổng. Khi báo cáo kết quả cần dùng split chống trùng lặp, nhiều random seed, baseline và ablation; không dùng chế độ minh họa làm số liệu thực nghiệm.
