---
name: drawing-to-dxf
description: 把机械尺寸图（照片/截图/标注数据）测量并生成 DXF：带尺寸标注的参考版 + Fusion 360 可插入的纯几何 ASCII 版。Use when 用户要"生成DXF"、"转成DXF"、"出CAD图"、"把图纸画成DXF"、"给我DXF文件"，或 Fusion 360 报"无法插入此DXF文件"/"插入DXF失败"，或发来机械/安装接口/外形尺寸图并要 CAD、支架、加工文件时。不用于海报插画图片生成，不用于分析已有 DXF 内部结构（除非在修导入错误）。
---

# 尺寸图生成 DXF

从图纸（照片或截图）提取几何，输出两份 DXF：

1. **标注版** —— 含尺寸、孔注释、标题的完整图纸（AutoCAD 看图用）
2. **几何版** —— 仅 LINE/ARC/CIRCLE 的纯 ASCII 文件（Fusion 360「插入 DXF」用）

## 重要规则（必须遵守）

1. **Fusion 360 兼容**：几何版禁止 TEXT / SOLID / HATCH / DIMENSION 实体，只允许 LINE、ARC、CIRCLE（LWPOLYLINE 慎用）。文件名必须纯 ASCII。这是 Fusion 报「无法插入此 DXF 文件」的头号原因。
2. **标注版编码**：GBK 写出，`$DWGCODEPAGE=ANSI_936`，字型 `txt.shx` + `gbcbig.shx`。中文注释用「深3」表示深度——GBK 没有 ↧ 符号；直径符号用 φ（GBK 有），不要用 Ø。
3. **尺寸链必须自洽**：标注数值是权威。实测像素有误差时，用标注值反推特征位置（例：M3 孔 x=3 与 23.7 得中列 x=26.7；M2 孔 x=4.5 与 22 得中列 x=26.5——允许 0.2mm 级台阶）。
4. **交叉验证**：同一尺寸在俯视/侧视/主视图都要验算比例尺；照片有屏幕摩尔纹幽灵线，优先用清晰截图定拓扑、高清照片定数值。
5. **校验闭环**：生成后必须 `inspect`（实体统计 + fusion_safe 检查）并渲染预览核对，再交付。
6. **交付命名**：几何版用英文文件名（如 `camera_mount_interface_fusion.dxf`）；标注版可用中文名。两版都在交付时说明用途差异。

## 工作流

### Step 1 — 明确需求

问清（或从上下文推断）：

- 输出什么视图？（安装接口 / 完整三视图 / 仅外轮廓）
- 要标注版、几何版，还是两版都要？（默认两版都要）
- 目标软件？（Fusion 360 → 只给几何版也可用；AutoCAD → 标注版）

### Step 2 — 测量图纸

详细方法见 `references/image-measurement.md`。要点：

1. 用 Pillow + numpy 检测长直线（投影法）和圆（环拟合），得到像素坐标。
2. 用**已标注尺寸**标定比例尺（px/mm），两个方向都要验算。
3. 把每个特征的坐标换算成 mm，画在约定坐标系里（安装面接缝中心为原点，y 向上）。
4. 记下不确定项（圆角半径、未标注孔的 Y 位置等），按图纸意图取整（如 R2、居中）。

### Step 3 — 生成标注版

用 `scripts/dxf_kit.py` 的 `AnnotatedDXF`：

```python
from dxf_kit import AnnotatedDXF
d = AnnotatedDXF()
d.line("OUTLINE", 0, 14.5, 42, 14.5)          # 轮廓
d.circle("HOLES", 3, 10, 1.5)                 # M3 孔 Ø3 (螺纹大径)
d.centermark("HOLES", 3, 10, 1.5)
d.dim_h(0, 42, 21.5, "42", (14.5, 12.5))      # 尺寸: 见证线起点可为元组(圆角切点/孔边)
d.dim_v(-10, 10, -16.5, "20", 1.5)            # 竖直尺寸: xfeat 用孔边(中心∓半径)
d.leader(30.5, -14, 27, -6.9, "4-M2 深3", 31, -15.2)
d.text("TEXT", -21, 30.5, 4.5, "安装接口图")
d.save("out.dxf")                             # GBK R12
```

约定：

- 螺纹孔按**螺纹大径**画（M2→Ø2，M3→Ø3），注释写「N-Mx 深y」
- 非安装特征（螺钉、接口、凹板）画在 `REF` 灰层；凹板/避让区画在 `PANEL` 层
- 窄尺寸（<6mm）自动箭头外置、文字放右外侧——已内置于 `dim_h`
- 顶部链式尺寸 y=17.6，总长 y=21.5，避免文字与尺寸线打架

### Step 4 — 生成几何版（Fusion）

同一批几何，只取轮廓/孔/参考的线弧圆，去掉全部文字与标注：

```python
from dxf_kit import write_geometry_dxf, rounded_rect_lines
lines, arcs, circles = [], [], []
rounded_rect_lines("OUTLINE", -11.675, -14.5, 42, 14.5, 2, (lines, arcs))
circles.append(("HOLES", 3, 10, 1.5))
path, mode = write_geometry_dxf("camera_mount_interface_fusion.dxf", lines, arcs, circles)
```

优先安装 ezdxf（`pip install ezdxf --target ./pylib`）以产出 R2000 完整结构；没有网络时自动回退手工 R12 几何版。

### Step 5 — 校验与交付

```bash
python scripts/dxf_kit.py inspect camera_mount_interface_fusion.dxf
# 期望: fusion_safe: True, has_text: False, has_solid: False
python scripts/dxf_kit.py render camera_mount_interface_fusion.dxf preview.png
```

渲染出的 PNG 必须目视核对（孔位、外廓、比例）；标注版同样 render 一张。然后用 present_files 交付两个 DXF + 预览图，附一句 Fusion 操作指引：**草图 → 插入 → 插入 DXF，单位选 mm**。

## 常见输出模板（安装接口类）

坐标系：主安装面，原点=前段/机身接缝 × 孔阵中心，y 向上。孔位置全部来自尺寸链反推，不要瞎猜。

| 要素 | 图层 | 说明 |
|------|------|------|
| 外轮廓 + 接缝 | OUTLINE | 圆角矩形拼接，台阶处画接缝线 |
| 螺纹孔 + 中心线 | HOLES | 按大径画圆 |
| 凹板/开孔避让区 | PANEL | 多段线闭合 |
| 螺钉/接口/LED | REF | 参考轮廓 |
| 尺寸与注释 | DIM / TEXT | 仅标注版 |

## Troubleshooting

| 现象 | 原因 | 处理 |
|------|------|------|
| Fusion「无法插入此 DXF 文件」 | 含 TEXT/SOLID/HATCH；或中文文件名/GBK | 只输出 LINE/ARC/CIRCLE；文件名 ASCII；跑 `inspect` 确认 `fusion_safe: True` |
| AutoCAD 中文乱码 | 编码/字型不配 | GBK + ANSI_936 + txt.shx/gbcbig.shx，勿用 UTF-8 与 ↧、Ø |
| 尺寸线穿字 | 文字落在线上 | 窄尺寸走 `dim_h` 自动外置；链式尺寸分层错开 y |
| 实测比例不一致 | 照片畸变/摩尔纹 | 用已标数值定比例；俯/侧视图交叉验算 |
| ezdxf 审计报错 | 实体属性缺失 | 只用 `write_geometry_dxf` 的 API，不要手工拼实体 |
| 导入 Fusion 单位不对 | 忽略 $INSUNITS | 插入对话框手动选 mm |
