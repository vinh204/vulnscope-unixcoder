"""VulnScope Streamlit demo for UniXcoder vulnerability detection."""

from __future__ import annotations

import json
import os
import re
from difflib import unified_diff
from pathlib import Path
from time import perf_counter

import pandas as pd
import streamlit as st

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CHECKPOINT = Path(os.getenv(
    "CHECKPOINT_PATH", ROOT / "outputs" / "checkpoint-best-f1" / "model.bin"
))
DEFAULT_METADATA = DEFAULT_CHECKPOINT.with_name("metadata.json")
MODEL_NAME = os.getenv("MODEL_NAME", "microsoft/unixcoder-base")
CHECKPOINT_REPO_ID = os.getenv(
    "CHECKPOINT_REPO_ID", "vinh204/vulnscope-unixcoder-devign"
)
CHECKPOINT_FILENAME = os.getenv("CHECKPOINT_FILENAME", "model.bin")
CHECKPOINT_REVISION = os.getenv(
    "CHECKPOINT_REVISION", "e8c7be3e075f261b8dee20196795b634e3d36f2a"
)
APP_ENV = os.getenv("APP_ENV", "production").lower()
EXAMPLES = {
    "Buffer overflow": '''void copy_input(const char *input) {
    char buffer[16];
    strcpy(buffer, input);
}''',
    "Use-after-free": '''void process(char *data) {
    free(data);
    printf("%s", data);
}''',
    "Phiên bản an toàn": '''void copy_input(const char *input) {
    char buffer[16];
    snprintf(buffer, sizeof(buffer), "%s", input);
}''',
}
SAFE_PATCH = '''void copy_input(const char *input) {
    char buffer[16];
    snprintf(buffer, sizeof(buffer), "%s", input);
}'''


def illustrative_prediction(code: str):
    """Transparent UI-only fallback; never reported as an experiment result."""
    started = perf_counter()
    risky = {
        "strcpy": 0.55, "strcat": 0.35, "gets": 0.60, "sprintf": 0.32,
        "free": 0.10, "printf": 0.04, "memcpy": 0.12,
    }
    protective = {"snprintf": -0.30, "sizeof": -0.12, "strlen": -0.08, "nullptr": -0.04}
    score = 0.18 + sum(value for token, value in risky.items() if token in code)
    score += sum(value for token, value in protective.items() if token in code)
    if re.search(r"free\s*\((\w+)\).*\b\1\b", code, re.DOTALL):
        score += 0.35
    score = max(0.02, min(0.98, score))
    return {"label": int(score >= 0.5), "vulnerable_probability": score,
            "safe_probability": 1 - score, "elapsed_ms": (perf_counter() - started) * 1000,
            "token_count": len(re.findall(r"\w+|[^\w\s]", code)), "truncated": False}


@st.cache_resource(show_spinner="Đang nạp UniXcoder...")
def load_predictor(checkpoint: str, block_size: int, model_name: str):
    # Import lazily so the UI-only demo starts quickly without loading PyTorch.
    from inference import UniXcoderPredictor
    return UniXcoderPredictor(
        checkpoint=checkpoint, block_size=block_size, model_name=model_name
    )


@st.cache_resource(show_spinner="Đang tải checkpoint VulnScope...")
def resolve_checkpoint(configured_path: str) -> str:
    """Use a local checkpoint or fetch the pinned public artifact."""
    local_path = Path(configured_path)
    if local_path.is_file():
        return str(local_path)

    from huggingface_hub import hf_hub_download

    return hf_hub_download(
        repo_id=CHECKPOINT_REPO_ID,
        filename=CHECKPOINT_FILENAME,
        revision=CHECKPOINT_REVISION,
        token=os.getenv("HF_TOKEN"),
    )


def get_prediction(code, checkpoint, block_size, demo_mode):
    if demo_mode:
        return illustrative_prediction(code), None
    predictor = load_predictor(checkpoint, block_size, MODEL_NAME)
    return predictor.predict(code).to_dict(), predictor


def show_result(result, threshold):
    probability = float(result["vulnerable_probability"])
    predicted = probability >= threshold
    if predicted:
        st.error(f"⚠️ Nguy cơ lỗ hổng — {probability:.1%}")
    else:
        st.success(f"✅ Chưa phát hiện nguy cơ cao — {probability:.1%}")
    st.text(f"Xác suất: {probability:.1%} | Token: {int(result['token_count'])} | "
            f"Thời gian: {float(result['elapsed_ms']):.1f} ms")
    if result["truncated"]:
        st.warning("Đầu vào đã bị cắt; kết quả có thể bỏ sót phần code quan trọng.")


def analyzer_page(checkpoint, block_size, threshold, demo_mode):
    st.header("Phân tích mã nguồn")
    example = st.selectbox("Ví dụ", list(EXAMPLES))
    uploaded = st.file_uploader("Hoặc tải file C/C++", type=["c", "cc", "cpp", "h", "hpp"])
    initial = uploaded.getvalue().decode("utf-8", errors="replace") if uploaded else EXAMPLES[example]
    code = st.text_area("Mã nguồn", initial, height=280)
    if st.button("Phân tích", type="primary", use_container_width=True):
        result = None
        predictor = None
        try:
            with st.spinner("Đang phân tích..."):
                result, predictor = get_prediction(code, checkpoint, block_size, demo_mode)
        except Exception as exc:
            st.error(f"Không thể chạy mô hình: {type(exc).__name__}: {exc}")

        # Rendering is intentionally outside the inference try/except. This
        # prevents UI errors from being misreported as model prediction errors.
        if result is not None:
            show_result(result, threshold)
            if predictor is not None:
                st.session_state["explain_code"] = code
                st.session_state["explain_checkpoint"] = checkpoint
                st.session_state["explain_block_size"] = block_size
                st.info("Dự đoán đã hoàn tất. Bấm bên dưới nếu cần tính giải thích token (sẽ chậm hơn).")
            else:
                st.info("Chế độ minh họa không tạo giải thích mô hình. Hãy chọn checkpoint thật để bảo vệ.")

    can_explain = (not demo_mode and st.session_state.get("explain_code") == code and
                   st.session_state.get("explain_checkpoint") == checkpoint and
                   st.session_state.get("explain_block_size") == block_size)
    if can_explain and st.button("Giải thích token", use_container_width=True):
        try:
            predictor = load_predictor(checkpoint, block_size, MODEL_NAME)
            with st.spinner("Đang che lần lượt từng token để kiểm chứng..."):
                explanation = predictor.explain(code)
            # Force primitive values; this avoids dataframe parsers interpreting token text.
            frame = pd.DataFrame([{
                "Token": str(item["token"]).replace("\n", "\\n"),
                "Vị trí": int(item["position"]),
                "Attribution": float(item["attribution"]),
            } for item in explanation[:15]])
            st.subheader("Token ảnh hưởng mạnh")
            st.table(frame)
            st.caption("Attribution dương làm tăng dự đoán lỗ hổng; được đo bằng cách che từng token.")
        except Exception as exc:
            st.warning(
                "Dự đoán vẫn hợp lệ nhưng chưa tạo được giải thích token. "
                f"Chi tiết: {type(exc).__name__}: {exc}"
            )


def comparison_page(checkpoint, block_size, threshold, demo_mode):
    st.header("So sánh trước và sau bản vá")
    left, right = st.columns(2)
    before = left.text_area("Trước bản vá", EXAMPLES["Buffer overflow"], height=260)
    after = right.text_area("Sau bản vá", SAFE_PATCH, height=260)
    if st.button("So sánh", type="primary", use_container_width=True):
        try:
            before_result, _ = get_prediction(before, checkpoint, block_size, demo_mode)
            after_result, _ = get_prediction(after, checkpoint, block_size, demo_mode)
            p_before, p_after = before_result["vulnerable_probability"], after_result["vulnerable_probability"]
            c1, c2, c3 = st.columns(3)
            c1.metric("Trước vá", f"{p_before:.1%}")
            c2.metric("Sau vá", f"{p_after:.1%}")
            c3.metric("Thay đổi", f"{p_after - p_before:+.1%}")
            diff = "\n".join(unified_diff(before.splitlines(), after.splitlines(),
                                          fromfile="before.c", tofile="after.c", lineterm=""))
            st.code(diff or "Không có thay đổi", language="diff")
        except Exception as exc:
            st.error(str(exc))


def dashboard_page():
    st.header("Dashboard thực nghiệm")
    metrics_path = ROOT / "results" / "metrics.json"
    predictions_path = ROOT / "results" / "predictions.csv"
    if not metrics_path.exists():
        st.warning("Chưa có kết quả thật. Chạy evaluate.py để tạo results/metrics.json và predictions.csv.")
        st.code(
            "python code/evaluate.py --data data/devign/test.txt "
            "--checkpoint outputs/checkpoint-best-f1/model.bin "
            "--block-size 128 --threshold 0.44 --head 500"
        )
        return
    metrics = json.loads(metrics_path.read_text(encoding="utf-8"))
    sample_count = None
    if predictions_path.exists():
        frame = pd.read_csv(predictions_path)
        sample_count = len(frame)
    scope = f" trên {sample_count:,} mẫu test" if sample_count is not None else ""
    st.caption(
        f"Checkpoint demo CPU{scope}: encoder đóng băng, huấn luyện 3 epoch trên 2.000 mẫu. "
        "Đây không phải kết quả fine-tune toàn bộ Devign."
    )
    cols = st.columns(6)
    for column, key in zip(cols, ["accuracy", "precision", "recall", "f1", "roc_auc", "pr_auc"]):
        value = metrics.get(key)
        column.metric(key.upper().replace("_", "-"), "N/A" if value is None else f"{value:.3f}")
    matrix = metrics.get("confusion_matrix", [[0, 0], [0, 0]])
    st.subheader("Confusion matrix")
    st.dataframe(pd.DataFrame(matrix, index=["Thật: An toàn", "Thật: Có lỗ hổng"],
                              columns=["Đoán: An toàn", "Đoán: Có lỗ hổng"]), use_container_width=True)
    if predictions_path.exists():
        st.subheader("Dự đoán chi tiết")
        st.dataframe(frame, use_container_width=True, hide_index=True)


def main():
    st.set_page_config(page_title="VulnScope", page_icon="🛡️", layout="wide")
    st.title("🛡️ VulnScope")
    st.caption("Phát hiện và giải thích lỗ hổng C/C++ bằng UniXcoder")
    checkpoint_error = None
    try:
        checkpoint = resolve_checkpoint(str(DEFAULT_CHECKPOINT))
    except Exception as exc:
        checkpoint = str(DEFAULT_CHECKPOINT)
        checkpoint_error = f"{type(exc).__name__}: {exc}"
    with st.sidebar:
        page = st.radio("Chức năng", ["Phân tích", "So sánh bản vá", "Dashboard"])
        if APP_ENV == "production":
            st.caption(f"Model: {MODEL_NAME}")
        else:
            checkpoint = st.text_input("Checkpoint", checkpoint)
        block_size = st.select_slider("Block size", [128, 256, 512], value=128)
        threshold = st.slider("Ngưỡng cảnh báo", 0.05, 0.95, 0.44, 0.01)
        checkpoint_exists = Path(checkpoint).is_file()
        if APP_ENV == "production":
            demo_mode = False
            if not checkpoint_exists:
                st.error("Không thể tải checkpoint mô hình.")
                if checkpoint_error:
                    st.caption(checkpoint_error)
        else:
            demo_mode = st.toggle("Chế độ minh họa", value=not checkpoint_exists)
        if demo_mode:
            st.warning("Kết quả đang dùng quy tắc minh họa, không phải UniXcoder và không được dùng trong báo cáo.")
        elif Path(checkpoint).resolve() == DEFAULT_CHECKPOINT.resolve():
            st.info("Checkpoint CPU demo: 2.000 mẫu huấn luyện, encoder đóng băng, 3 epoch, block size 128.")
    if page == "Phân tích":
        analyzer_page(checkpoint, block_size, threshold, demo_mode)
    elif page == "So sánh bản vá":
        comparison_page(checkpoint, block_size, threshold, demo_mode)
    else:
        dashboard_page()


if __name__ == "__main__":
    main()
