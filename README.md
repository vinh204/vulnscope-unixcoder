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

Ứng dụng ưu tiên checkpoint tại `outputs/checkpoint-best-f1/model.bin`. Nếu file
không tồn tại, ứng dụng tự tải artifact đã ghim phiên bản từ
[`vinh204/vulnscope-unixcoder-devign`](https://huggingface.co/vinh204/vulnscope-unixcoder-devign).

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

## Chạy bằng Docker

Checkpoint không được lưu trong Git repository. Khi chạy local, mount checkpoint vào container:

```powershell
docker build -t vulnscope-unixcoder .
docker run --rm -p 7860:7860 `
  -v "${PWD}/outputs/checkpoint-best-f1/model.bin:/app/models/model.bin:ro" `
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
APP_ENV=production
```

Nếu Model repository là private, thêm `HF_TOKEN` dưới dạng Space secret. Không commit token vào source code. Khi khởi động, container tải checkpoint từ Model repository và lưu trong Hugging Face cache.

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
- `code/metrics.py`: metric nhị phân an toàn khi lớp bị thiếu.
- `code/app.py`: ứng dụng Streamlit.
- `code/bootstrap.py`: chuẩn bị checkpoint và khởi động production server.

## Lưu ý khoa học

Attribution cho biết token ảnh hưởng đến dự đoán, không chứng minh token đó là nguyên nhân lỗ hổng. Khi báo cáo kết quả cần dùng split chống trùng lặp, nhiều random seed, baseline và ablation; không dùng chế độ minh họa làm số liệu thực nghiệm.
