import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch, FancyArrowPatch
from pathlib import Path
out=Path("docs/images")
plt.rcParams.update({"font.family":"DejaVu Sans","font.size":10})
# Workflow diagram
fig, ax=plt.subplots(figsize=(12,4.6)); ax.set_xlim(0,12); ax.set_ylim(0,5); ax.axis("off")
steps=[
(0.25,2.05,1.75,1.15,"Devign","Hàm C/C++\nnhãn 0 / 1","#e8f1fb"),
(2.55,2.05,1.75,1.15,"Tiền xử lý","Chuẩn hóa, ánh xạ\ntrường dữ liệu","#e8f1fb"),
(4.85,2.05,1.75,1.15,"Tokenizer","Token đặc biệt,\ncắt/đệm độ dài","#e9f6ee"),
(7.15,2.05,1.75,1.15,"UniXcoder","Biểu diễn ngữ cảnh\ncho chuỗi mã","#fff3df"),
(9.45,2.05,2.1,1.15,"Phân loại & đánh giá","Xác suất, ngưỡng,\nmetrics","#fce9ec")]
for x,y,w,h,title,body,c in steps:
 ax.add_patch(FancyBboxPatch((x,y),w,h,boxstyle="round,pad=0.08,rounding_size=0.08",fc=c,ec="#38536b",lw=1.2))
 ax.text(x+w/2,y+h*.68,title,ha="center",va="center",weight="bold",fontsize=10)
 ax.text(x+w/2,y+h*.31,body,ha="center",va="center",fontsize=9)
for i in range(4):
 x1=steps[i][0]+steps[i][2]; x2=steps[i+1][0]
 ax.add_patch(FancyArrowPatch((x1+.05,2.62),(x2-.08,2.62),arrowstyle="-|>",mutation_scale=13,color="#38536b",lw=1.4))
ax.text(6,4.35,"Quy trình thực nghiệm phát hiện lỗ hổng ở mức hàm",ha="center",fontsize=14,weight="bold",color="#18344e")
ax.text(6,.82,"Validation: chọn checkpoint/ngưỡng    •    Test: đánh giá cuối cùng, không dùng để điều chỉnh",ha="center",fontsize=10,color="#40596f")
fig.tight_layout(); fig.savefig(out/"ch3_pipeline.png",dpi=180,bbox_inches="tight"); plt.close(fig)
# Model diagram
fig, ax=plt.subplots(figsize=(10,5.3)); ax.set_xlim(0,10); ax.set_ylim(0,6); ax.axis("off")
def box(x,y,w,h,title,sub,color):
 ax.add_patch(FancyBboxPatch((x,y),w,h,boxstyle="round,pad=0.08",fc=color,ec="#37566e",lw=1.3))
 ax.text(x+w/2,y+h*.67,title,ha="center",va="center",weight="bold",fontsize=10)
 ax.text(x+w/2,y+h*.30,sub,ha="center",va="center",fontsize=8.7)
box(.5,4.5,2.2,.9,"Hàm C/C++","Mã nguồn đầu vào","#e8f1fb")
box(.5,3.0,2.2,.9,"UniXcoder tokenizer","Token ID + mask","#e9f6ee")
box(3.7,3.0,2.5,.9,"Embedding","Token + vị trí","#fff3df")
box(3.7,1.55,2.5,.9,"Transformer encoder","Self-attention × nhiều lớp","#fff3df")
box(7.3,3.0,2.2,.9,"Vector biểu diễn","Đặc trưng của hàm","#e8f1fb")
box(7.3,1.55,2.2,.9,"Classification head","Logits → softmax","#fce9ec")
box(7.3,.18,2.2,.8,"Kết quả","P(safe), P(vulnerable)","#fce9ec")
for a,b in [((1.6,4.45),(1.6,3.95)),((2.75,3.45),(3.6,3.45)),((4.95,2.95),(4.95,2.5)),((6.25,2.0),(7.2,3.25)),((8.4,2.95),(8.4,2.5)),((8.4,1.45),(8.4,1.03))]:
 ax.add_patch(FancyArrowPatch(a,b,arrowstyle="-|>",mutation_scale=13,color="#37566e",lw=1.35))
ax.text(5,5.65,"Kiến trúc phân loại mã nguồn dựa trên UniXcoder",ha="center",fontsize=14,weight="bold",color="#18344e")
ax.text(5,.02,"Trong thực nghiệm này, toàn bộ encoder và đầu phân loại được fine-tune.",ha="center",fontsize=9,color="#40596f")
fig.tight_layout(); fig.savefig(out/"ch3_architecture.png",dpi=180,bbox_inches="tight"); plt.close(fig)
# Metric comparison
labels=["Accuracy","Precision","Recall","F1"]
sel=[.4667,.4623,.9880,.6299]; fixed=[.5395,.4986,.4151,.4530]
fig,ax=plt.subplots(figsize=(9,4.8)); x=range(len(labels)); w=.34
b1=ax.bar([i-w/2 for i in x],sel,w,label="Ngưỡng chọn trên validation (0,191)",color="#2878a5")
b2=ax.bar([i+w/2 for i in x],fixed,w,label="Ngưỡng 0,5",color="#e6953b")
ax.set_xticks(list(x),labels); ax.set_ylim(0,1.12); ax.set_ylabel("Giá trị"); ax.set_title("Chỉ số test theo hai ngưỡng phân loại",weight="bold",pad=14)
ax.grid(axis="y",alpha=.22); ax.legend(frameon=False,loc="upper left")
for bars in (b1,b2):
 for bar in bars:
  ax.text(bar.get_x()+bar.get_width()/2,bar.get_height()+.025,f"{bar.get_height():.3f}",ha="center",fontsize=8)
fig.tight_layout(); fig.savefig(out/"ch3_metrics.png",dpi=180,bbox_inches="tight"); plt.close(fig)
# Confusion matrices
import numpy as np
mats=[np.array([[35,1442],[15,1240]]),np.array([[953,524],[734,521]])]
titles=["Ngưỡng 0,191 (validation)","Ngưỡng 0,5"]
fig,axs=plt.subplots(1,2,figsize=(9,4.4))
for ax,m,title in zip(axs,mats,titles):
 im=ax.imshow(m,cmap="Blues")
 ax.set_title(title,weight="bold"); ax.set_xticks([0,1],["An toàn","Có lỗ hổng"]); ax.set_yticks([0,1],["An toàn","Có lỗ hổng"])
 ax.set_xlabel("Dự đoán"); ax.set_ylabel("Thực tế")
 for (i,j),v in np.ndenumerate(m):
  ax.text(j,i,f"{v:,}".replace(",", "."),ha="center",va="center",color="white" if v>800 else "#18344e",weight="bold")
fig.suptitle("Ma trận nhầm lẫn trên tập test",fontsize=13,weight="bold")
fig.tight_layout(); fig.savefig(out/"ch3_confusion.png",dpi=180,bbox_inches="tight"); plt.close(fig)
