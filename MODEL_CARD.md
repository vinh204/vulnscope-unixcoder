---
license: mit
library_name: transformers
pipeline_tag: text-classification
tags:
  - code
  - vulnerability-detection
  - unixcoder
  - devign
---

# VulnScope UniXcoder — Devign checkpoint

Checkpoint dùng cho demo VulnScope, phân loại hàm C/C++ thành `safe` hoặc
`vulnerable`. Encoder nền là `microsoft/unixcoder-base`.

## Phạm vi

- Đầu vào: một hàm C/C++.
- Đầu ra: xác suất nhị phân `safe`/`vulnerable`.
- Dataset thử nghiệm: Devign.
- Cấu hình demo hiện tại: encoder đóng băng, 3 epoch, 2.000 mẫu huấn luyện,
  block size 128.

## Giới hạn

Đây là checkpoint phục vụ demo đồ án, chưa phải mô hình kiểm thử bảo mật cho
production. Kết quả chỉ nên dùng để sàng lọc và không thay thế code review,
static analysis hoặc kiểm thử chuyên sâu. Mô hình có thể bỏ sót lỗ hổng, cảnh
báo sai, và không quan sát được phần code bị cắt quá giới hạn token.

## Ứng dụng

Source code và hướng dẫn chạy:
https://github.com/vinh204/vulnscope-unixcoder
