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

LOGO_SVG = """
<svg viewBox="0 0 72 72" role="img" aria-label="VulnScope logo" xmlns="http://www.w3.org/2000/svg">
  <defs>
    <linearGradient id="vs-gradient" x1="8" y1="8" x2="64" y2="64" gradientUnits="userSpaceOnUse">
      <stop stop-color="#34D399"/><stop offset="1" stop-color="#3B82F6"/>
    </linearGradient>
  </defs>
  <rect x="5" y="5" width="62" height="62" rx="18" fill="#0F1F28" stroke="url(#vs-gradient)" stroke-width="3"/>
  <path d="M27 24 17 35l10 11M41 24l10 11-10 11M38 19 31 51" fill="none" stroke="url(#vs-gradient)" stroke-width="4.5" stroke-linecap="round" stroke-linejoin="round"/>
  <circle cx="51" cy="50" r="8" fill="#0F1F28" stroke="#6EE7B7" stroke-width="3"/>
  <path d="m57 56 7 7" stroke="#6EE7B7" stroke-width="4" stroke-linecap="round"/>
</svg>
"""


def inject_styles():
    st.markdown("""
    <style>
    .block-container {
        padding-top: 2.75rem;
        padding-bottom: 9rem;
        max-width: 1280px;
    }
    [data-testid="stAppViewContainer"] {scroll-padding-top: 4rem;}
    [data-testid="stSidebar"] {border-right: 1px solid rgba(148,163,184,.18);}
    [data-testid="stMetric"] {
        background: rgba(30,41,59,.55); border: 1px solid rgba(148,163,184,.18);
        padding: 1rem; border-radius: 14px;
    }
    .vs-hero {
        padding: 1.45rem 1.6rem; border-radius: 18px; margin-bottom: 1.4rem;
        background: linear-gradient(120deg, rgba(16,185,129,.16), rgba(59,130,246,.10));
        border: 1px solid rgba(52,211,153,.24);
    }
    .vs-title {font-size: 2.15rem; font-weight: 750; margin: 0; letter-spacing: -.03em;}
    .vs-subtitle {color: #aab3c2; margin: .35rem 0 0;}
    .vs-brand {display: flex; align-items: center; gap: .9rem;}
    .vs-logo {width: 62px; height: 62px; flex: 0 0 62px;}
    .vs-sidebar-brand {display: flex; align-items: center; gap: .65rem; margin-bottom: 1rem;}
    .vs-sidebar-logo {width: 38px; height: 38px; flex: 0 0 38px;}
    .vs-sidebar-name {font-size: 1.45rem; font-weight: 720; letter-spacing: -.02em;}
    .vs-result {
        padding: 1rem 1.2rem; border-radius: 14px; margin: .8rem 0 1rem;
        border-left: 5px solid var(--accent); background: rgba(30,41,59,.48);
    }
    .vs-result h3 {margin: 0 0 .25rem; color: var(--accent);}
    .vs-result p {margin: 0; color: #aab3c2;}
    .vs-note {
        padding: .8rem 1rem; border-radius: 12px; color: #aab3c2;
        background: rgba(30,41,59,.4); border: 1px solid rgba(148,163,184,.14);
    }
    @media (max-width: 768px) {
        .block-container {padding-top: 3.5rem; padding-bottom: 10rem;}
        .vs-hero {padding: 1.1rem;}
        .vs-title {font-size: 1.75rem;}
    }
    </style>
    """, unsafe_allow_html=True)


def hero():
    st.markdown(f"""
    <div class="vs-hero">
      <div class="vs-brand">
        <div class="vs-logo">{LOGO_SVG}</div>
        <div class="vs-title">VulnScope</div>
      </div>
      <div class="vs-subtitle">Phát hiện, so sánh và giải thích rủi ro bảo mật trong hàm C/C++ bằng UniXcoder.</div>
    </div>
    """, unsafe_allow_html=True)


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
    confidence = probability if predicted else 1 - probability
    accent = "#fb7185" if predicted else "#34d399"
    title = "Có dấu hiệu lỗ hổng" if predicted else "Chưa phát hiện nguy cơ cao"
    detail = (
        f"Xác suất vulnerable {probability:.1%}, so với ngưỡng cảnh báo {threshold:.0%}."
    )
    st.markdown(
        f'<div class="vs-result" style="--accent:{accent}"><h3>{"⚠️" if predicted else "✅"} '
        f'{title}</h3><p>{detail}</p></div>', unsafe_allow_html=True,
    )
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Xác suất lỗ hổng", f"{probability:.1%}")
    c2.metric("Độ tin cậy", f"{confidence:.1%}")
    c3.metric("Token phân tích", f"{int(result['token_count']):,}")
    c4.metric("Độ trễ", f"{float(result['elapsed_ms']):.0f} ms")
    if result["truncated"]:
        st.warning("Đầu vào đã bị cắt; kết quả có thể bỏ sót phần code quan trọng.")


def analyzer_page(checkpoint, block_size, threshold, demo_mode):
    st.subheader("Phân tích mã nguồn")
    st.caption("Dán một hàm C/C++ hoặc chọn ví dụ để mô hình ước lượng rủi ro.")
    left, right = st.columns([1, 1])
    example = left.selectbox("Mẫu kiểm thử", list(EXAMPLES))
    uploaded = right.file_uploader("Tải file C/C++", type=["c", "cc", "cpp", "h", "hpp"])
    initial = uploaded.getvalue().decode("utf-8", errors="replace") if uploaded else EXAMPLES[example]
    code = st.text_area("Mã nguồn", initial, height=250, placeholder="Dán một hàm C/C++ tại đây...")
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
            st.session_state["last_analysis"] = {
                "code": code, "result": result, "threshold": threshold,
            }
            if predictor is not None:
                st.session_state["explain_code"] = code
                st.session_state["explain_checkpoint"] = checkpoint
                st.session_state["explain_block_size"] = block_size
            else:
                st.info("Chế độ minh họa không tạo giải thích mô hình. Hãy chọn checkpoint thật để bảo vệ.")

    analysis = st.session_state.get("last_analysis")
    if analysis and analysis.get("code") == code:
        st.divider()
        st.subheader("Kết quả phân tích")
        show_result(analysis["result"], analysis["threshold"])
        st.download_button(
            "Tải kết quả JSON",
            json.dumps(analysis["result"], ensure_ascii=False, indent=2),
            file_name="vulnscope-result.json", mime="application/json",
        )

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
    st.subheader("So sánh trước và sau bản vá")
    st.caption("Đo mức thay đổi rủi ro sau khi áp dụng bản vá, dùng cùng một checkpoint và ngưỡng.")
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
            if p_after < p_before:
                st.success(f"✅ Bản vá làm giảm rủi ro dự đoán {(p_before - p_after):.1%}.")
            else:
                st.warning("⚠️ Bản vá chưa làm giảm rủi ro dự đoán; cần tiếp tục kiểm tra.")
            diff = "\n".join(unified_diff(before.splitlines(), after.splitlines(),
                                          fromfile="before.c", tofile="after.c", lineterm=""))
            st.code(diff or "Không có thay đổi", language="diff")
        except Exception as exc:
            st.error(str(exc))


def dashboard_page():
    st.subheader("Dashboard thực nghiệm")
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
    sample_count = metrics.get("sample_count")
    if predictions_path.exists():
        frame = pd.read_csv(predictions_path)
        sample_count = len(frame)
    scope = f" trên {sample_count:,} mẫu test" if sample_count is not None else ""
    st.info(
        f"Baseline checkpoint{scope}: encoder đóng băng, huấn luyện 3 epoch trên 2.000 mẫu. "
        "Các số liệu được đọc từ artifact đánh giá thật và chưa phải kết quả cuối của đồ án."
    )
    cols = st.columns(6)
    for column, key in zip(cols, ["accuracy", "precision", "recall", "f1", "roc_auc", "pr_auc"]):
        value = metrics.get(key)
        column.metric(key.upper().replace("_", "-"), "N/A" if value is None else f"{value:.3f}")
    matrix = metrics.get("confusion_matrix", [[0, 0], [0, 0]])
    left, right = st.columns([1, 1])
    left.subheader("Confusion matrix")
    left.dataframe(pd.DataFrame(matrix, index=["Thật: An toàn", "Thật: Có lỗ hổng"],
                                columns=["Đoán: An toàn", "Đoán: Có lỗ hổng"]), use_container_width=True)
    right.subheader("Phân bố kết quả")
    right.bar_chart(pd.DataFrame({
        "Số mẫu": [matrix[0][0], matrix[0][1], matrix[1][0], matrix[1][1]]
    }, index=["True negative", "False positive", "False negative", "True positive"]))
    if predictions_path.exists():
        st.subheader("Dự đoán chi tiết")
        st.dataframe(frame, use_container_width=True, hide_index=True)


def main():
    st.set_page_config(page_title="VulnScope", page_icon="🔎", layout="wide")
    inject_styles()
    checkpoint_error = None
    try:
        checkpoint = resolve_checkpoint(str(DEFAULT_CHECKPOINT))
    except Exception as exc:
        checkpoint = str(DEFAULT_CHECKPOINT)
        checkpoint_error = f"{type(exc).__name__}: {exc}"
    with st.sidebar:
        st.markdown(
            f'<div class="vs-sidebar-brand"><div class="vs-sidebar-logo">{LOGO_SVG}</div>'
            '<div class="vs-sidebar-name">VulnScope</div></div>',
            unsafe_allow_html=True,
        )
        page = st.radio("Chức năng", ["Phân tích", "So sánh bản vá", "Dashboard"])
        if APP_ENV == "production":
            st.success("● Model sẵn sàng" if Path(checkpoint).is_file() else "Model chưa sẵn sàng")
            st.caption(f"`{MODEL_NAME}`")
        else:
            checkpoint = st.text_input("Checkpoint", checkpoint)
        with st.expander("Cấu hình nâng cao"):
            block_size = st.select_slider(
                "Độ dài đầu vào (token)", [128, 256, 512], value=128,
                help="Đầu vào dài hơn giới hạn sẽ bị cắt. Checkpoint demo được huấn luyện với 128 token.",
            )
            threshold = st.slider(
                "Ngưỡng cảnh báo", 0.05, 0.95, 0.44, 0.01,
                help="Được chọn trên validation set; xác suất từ ngưỡng này trở lên được cảnh báo.",
            )
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
        st.divider()
        st.caption("Công cụ hỗ trợ sàng lọc, không thay thế kiểm thử bảo mật chuyên sâu.")
    hero()
    if page == "Phân tích":
        analyzer_page(checkpoint, block_size, threshold, demo_mode)
    elif page == "So sánh bản vá":
        comparison_page(checkpoint, block_size, threshold, demo_mode)
    else:
        dashboard_page()


if __name__ == "__main__":
    main()
