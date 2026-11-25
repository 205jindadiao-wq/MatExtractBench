import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
from matplotlib.colors import LinearSegmentedColormap, Normalize
from matplotlib.cm import ScalarMappable

# =========================
# 1. 读取数据
# =========================
file_path = "gaitaikuang.xlsx"
df = pd.read_excel(file_path)
df.columns = df.columns.str.strip()

# =========================
# 2. 参数设置
# =========================
TOP_N_CATEGORY = 6          # 每个类别变量最多保留前6个高频类别
MIN_CATEGORY_COUNT = 3      # 类别至少出现3次才保留
MAX_VARS = 40               # 最多显示变量数
MIN_ABS_R = 0.08            # 只显示绝对相关系数 >= 0.08 的气泡
BUBBLE_SCALE = 180          # 气泡大小比例

# =========================
# 3. 指定变量类型
# =========================
numeric_cols = [
    "PCE(%)",
    "VOC(V)",
    "JSC(mA cm-2)",
    "FF(%)"
]

categorical_cols = [
    "catalyst",
    "buried interface passivation agent",
    "perovskite layer additives",
    "perovskite interface passivation agent"
]

numeric_cols = [c for c in numeric_cols if c in df.columns]
categorical_cols = [c for c in categorical_cols if c in df.columns]

# =========================
# 4. 数据预处理
# =========================
for col in numeric_cols:
    df[col] = pd.to_numeric(df[col], errors="coerce")

for col in categorical_cols:
    df[col] = df[col].astype(str).str.strip()
    df[col] = df[col].replace(
        ["nan", "NaN", "None", "NONE", "", "C^", "CA", "NA", "N/A", "null"],
        np.nan
    )

# =========================
# 5. one-hot 编码
# =========================
encoded_parts = []

if numeric_cols:
    encoded_parts.append(df[numeric_cols])

for col in categorical_cols:
    temp = df[col].copy()

    top_values = temp.value_counts(dropna=True).head(TOP_N_CATEGORY).index
    temp = temp.where(temp.isin(top_values), other=np.nan)

    dummies = pd.get_dummies(temp, prefix=col, prefix_sep=": ")
    dummies = dummies.loc[:, dummies.sum(axis=0) >= MIN_CATEGORY_COUNT]

    if dummies.shape[1] > 0:
        encoded_parts.append(dummies)

data_encoded = pd.concat(encoded_parts, axis=1)

# 删除无效列
data_encoded = data_encoded.dropna(axis=1, how="all")
data_encoded = data_encoded.loc[:, data_encoded.nunique(dropna=True) > 1]

# 缺失值填充
data_encoded = data_encoded.apply(lambda x: x.fillna(x.mean()), axis=0)

# =========================
# 6. 变量分组
# =========================
group_map = {}

for col in data_encoded.columns:
    if col in ["PCE(%)", "VOC(V)", "JSC(mA cm-2)", "FF(%)"]:
        group_map[col] = "Device performance"
    elif col.startswith("catalyst"):
        group_map[col] = "Perovskite material"
    elif col.startswith("buried interface passivation agent"):
        group_map[col] = "Buried interface"
    elif col.startswith("perovskite layer additives"):
        group_map[col] = "Layer additive"
    elif col.startswith("perovskite interface passivation agent"):
        group_map[col] = "Interface passivation"
    else:
        group_map[col] = "Other"

# 颜色参照你图片的风格
group_colors = {
    "Perovskite material": "#2CA02C",      # 绿色
    "Buried interface": "#6A3D9A",         # 紫色
    "Layer additive": "#FF8C00",           # 橙色
    "Interface passivation": "#E41A1C",    # 红色
    "Device performance": "#000000",       # 黑色
    "Other": "#888888"
}

group_order = [
    "Perovskite material",
    "Buried interface",
    "Layer additive",
    "Interface passivation",
    "Device performance",
    "Other"
]

# =========================
# 7. 控制变量数量
# =========================
must_keep = [c for c in numeric_cols if c in data_encoded.columns]
dummy_cols = [c for c in data_encoded.columns if c not in must_keep]

dummy_cols = sorted(dummy_cols, key=lambda c: data_encoded[c].sum(), reverse=True)

remain_num = max(0, MAX_VARS - len(must_keep))
selected_cols = dummy_cols[:remain_num] + must_keep

data_encoded = data_encoded[selected_cols]

ordered_cols = sorted(
    data_encoded.columns,
    key=lambda x: (group_order.index(group_map[x]), x)
)

data_encoded = data_encoded[ordered_cols]

# =========================
# 8. 计算相关矩阵
# =========================
corr = data_encoded.corr(method="spearman")

# =========================
# 9. 标签美化
# =========================
def clean_label(label):
    label = label.replace("PCE(%)", "PCE")
    label = label.replace("VOC(V)", "VOC")
    label = label.replace("JSC(mA cm-2)", "JSC")
    label = label.replace("FF(%)", "FF")

    label = label.replace("catalyst: ", "mat: ")
    label = label.replace("buried interface passivation agent: ", "buried: ")
    label = label.replace("perovskite layer additives: ", "additive: ")
    label = label.replace("perovskite interface passivation agent: ", "interface: ")

    if len(label) > 20:
        label = label[:19] + "…"

    return label

labels = [clean_label(c) for c in corr.columns]

# =========================
# 10. 绘图
# =========================
n = corr.shape[0]
print(f"Number of plotted variables: {n}")

fig, ax = plt.subplots(figsize=(11, 9), dpi=300)

# 颜色改为参考图风格：蓝-浅灰白-红
cmap = LinearSegmentedColormap.from_list(
    "blue_white_red",
    ["#2166AC", "#F7F7F7", "#B2182B"]
)

# 背景空心小圆
for i in range(n):
    for j in range(n):
        ax.scatter(
            j, i,
            s=10,
            facecolors="white",
            edgecolors="#E6E6E6",
            linewidths=0.25,
            zorder=1
        )

# 有效相关气泡
for i in range(n):
    for j in range(n):
        r = corr.iloc[i, j]

        if pd.isna(r):
            continue

        if abs(r) < MIN_ABS_R and i != j:
            continue

        bubble_size = (abs(r) ** 1.2) * BUBBLE_SCALE
        color = cmap((r + 1) / 2)

        ax.scatter(
            j, i,
            s=bubble_size,
            color=color,
            edgecolors="none",
            zorder=2
        )

# 坐标轴
ax.set_xticks(np.arange(n))
ax.set_yticks(np.arange(n))

ax.set_xticklabels(labels, rotation=90, fontsize=5)
ax.set_yticklabels(labels, fontsize=5)

ax.xaxis.tick_bottom()
ax.tick_params(axis="x", pad=1, length=0)
ax.tick_params(axis="y", pad=1, length=0)

ax.set_xlim(-0.5, n - 0.5)
ax.set_ylim(n - 0.5, -0.5)
ax.set_aspect("equal")

# 网格线
ax.set_xticks(np.arange(-0.5, n, 1), minor=True)
ax.set_yticks(np.arange(-0.5, n, 1), minor=True)
ax.grid(which="minor", color="#EEEEEE", linestyle="-", linewidth=0.35)
ax.tick_params(which="minor", bottom=False, left=False)

# 标签颜色
for tick, col in zip(ax.get_xticklabels(), corr.columns):
    tick.set_color(group_colors[group_map[col]])

for tick, col in zip(ax.get_yticklabels(), corr.columns):
    tick.set_color(group_colors[group_map[col]])

# 去掉边框
for spine in ax.spines.values():
    spine.set_visible(False)

# =========================
# 11. 分组分割线
# =========================
group_list = [group_map[c] for c in corr.columns]
boundaries = []

for idx in range(1, n):
    if group_list[idx] != group_list[idx - 1]:
        boundaries.append(idx)

for b in boundaries:
    ax.axhline(b - 0.5, color="#D0D0D0", linewidth=0.7)
    ax.axvline(b - 0.5, color="#D0D0D0", linewidth=0.7)

# =========================
# 12. 颜色条
# =========================
norm = Normalize(vmin=-1, vmax=1)
sm = ScalarMappable(norm=norm, cmap=cmap)
sm.set_array([])

cbar = plt.colorbar(sm, ax=ax, fraction=0.03, pad=0.02)
cbar.set_label("Correlation coefficient", fontsize=7)
cbar.ax.tick_params(labelsize=6)

# =========================
# 13. 标题与保存
# =========================

plt.savefig(
    "perovskite_correlation_bubble_matrix_full.png",
    dpi=600,
    bbox_inches="tight",
    pad_inches=0.05
)

plt.savefig(
    "perovskite_correlation_bubble_matrix_full.pdf",
    bbox_inches="tight",
    pad_inches=0.05
)

plt.show()