"""Generate figures from the completed model comparison artifacts."""

import json
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np


root = Path(__file__).resolve().parents[1]
out = root / "docs" / "images"
rows = json.loads((root / "results" / "model_comparison.json").read_text(encoding="utf-8"))
selected = [row for row in rows if row["operating_point"] == "threshold selected on validation"]
plt.rcParams.update({"font.family": "DejaVu Sans", "font.size": 10})

labels = ["Accuracy", "Precision", "Recall", "F1", "ROC-AUC", "PR-AUC"]
keys = ["accuracy", "precision", "recall", "f1", "roc_auc", "pr_auc"]
fig, ax = plt.subplots(figsize=(11, 5.2))
x = np.arange(len(labels))
width = 0.35
colors = ["#2878a5", "#e6953b"]
for offset, row, color in zip([-width / 2, width / 2], selected, colors):
    values = [row[key] for key in keys]
    bars = ax.bar(x + offset, values, width, label=row["model"], color=color)
    for bar in bars:
        ax.text(bar.get_x() + bar.get_width() / 2, bar.get_height() + 0.015,
                f"{bar.get_height():.3f}", ha="center", fontsize=8)
ax.set_xticks(x, labels)
ax.set_ylim(0, 1.08)
ax.set_ylabel("Giá trị")
ax.set_title("So sánh UniXcoder và baseline trên tập test", weight="bold", pad=14)
ax.grid(axis="y", alpha=0.22)
ax.legend(frameon=False, loc="upper left")
fig.tight_layout()
fig.savefig(out / "ch3_metrics.png", dpi=180, bbox_inches="tight")
plt.close(fig)

fig, axes = plt.subplots(1, 2, figsize=(10.5, 4.7))
for ax, row in zip(axes, selected):
    matrix = np.asarray(row["confusion_matrix"])
    ax.imshow(matrix, cmap="Blues")
    ax.set_title(f'{row["model"]}\nNgưỡng {row["threshold"]:.4f}', weight="bold")
    ax.set_xticks([0, 1], ["An toàn", "Có khả năng lỗi"])
    ax.set_yticks([0, 1], ["An toàn", "Có khả năng lỗi"])
    ax.set_xlabel("Dự đoán")
    ax.set_ylabel("Thực tế")
    for (i, j), value in np.ndenumerate(matrix):
        ax.text(j, i, f"{value:,}".replace(",", "."), ha="center", va="center",
                color="white" if value > 800 else "#18344e", weight="bold")
fig.suptitle("Ma trận nhầm lẫn trên tập test", fontsize=13, weight="bold")
fig.tight_layout()
fig.savefig(out / "ch3_confusion.png", dpi=180, bbox_inches="tight")
plt.close(fig)
