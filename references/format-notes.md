# DXF 格式与目标软件兼容要点

## 两档输出策略

| | 标注版 | 几何版（Fusion） |
|---|---|---|
| 版本 | AC1009 (R12) | AC1015 (R2000)，ezdxf 生成 |
| 编码 | GBK, `$DWGCODEPAGE=ANSI_936` | 纯 ASCII（全部字节 <128） |
| 实体 | LINE/ARC/CIRCLE/TEXT/SOLID | 仅 LINE/ARC/CIRCLE |
| 文字 | 中文注释/尺寸 | 无 |
| 用途 | AutoCAD 看图/打印 | Fusion 360 插入草图 |
| 文件名 | 中文可以 | **必须英文** |

## Fusion 360（插入 DXF → 草图）

已知限制（踩坑记录）：

- 不支持 TEXT、SOLID、HATCH、DIMENSION——**只要出现就整份导入失败**，报「无法插入此 DXF 文件」
- 中文文件名 / 非 ASCII 字节可能导致拒读
- 推荐 AutoCAD 2000/2007 ASCII DXF；ezdxf `new("R2000")` 的输出实测可导入
- `$INSUNITS=4`（mm）写入可减少单位误会；导入对话框仍建议手动选 mm
- 坐标必须 Z=0 平面几何
- 块引用（INSERT）慎用；本工具不生成块

## AutoCAD 中文环境

- 中文字型组合：`txt.shx` + bigfont `gbcbig.shx`（STYLE 的 3/4 组码）
- GBK 字库不含 ↧(U+21A7) 与 Ø(U+00D8)：深度写「深3」，直径写 φ
- R12 无 LWPOLYLINE（R2000+ 才有）——R12 多段线请拆成 LINE 段或 POLYLINE
- SOLID 三角形（箭头）：第 4 点 = 第 3 点，得到三角形；实心箭头 2.5×0.7mm

## 组码书写注意

- 每行一个组码/值；DXF 传统用 CRLF，写出后把 `\n` 归一成 `\r\n`
- 实体段统计写 `0/8/10/20/30/40/50/51` 等；数值 `%.4f` 去尾零
- 手工写 R12 时 TABLES 至少含 LTYPE(CONTINUOUS)、LAYER、STYLE、APPID
- R2000+ 需要 CLASSES/OBJECTS/BLOCK_RECORD——**不要手工拼，用 ezdxf**

## 校验清单（生成后必跑）

```bash
python scripts/dxf_kit.py inspect xxx.dxf
```

- `pure_ascii: True` 且 `fusion_safe: True` → 可给 Fusion
- `has_text/has_solid` 为 True → 只能给 AutoCAD
- 实体数量与设计表对得上（孔 = 圆数，外廓 = 线+弧数）
- `render` 出 PNG 目视核对孔位/外廓/两视图相对位置

## ezdxf 用法

```python
doc = ezdxf.new("R2000", setup=False)
doc.header["$INSUNITS"] = 4
doc.layers.add("HOLES", color=1)
msp = doc.modelspace()
msp.add_line((0, 0), (42, 0), dxfattribs={"layer": "OUTLINE"})
msp.add_arc((38, 2), 2, 270, 360, dxfattribs={"layer": "OUTLINE"})
msp.add_circle((3, 10), 1.5, dxfattribs={"layer": "HOLES"})
auditor = doc.audit()
assert not auditor.has_errors
doc.saveas("out.dxf", fmt="asc")
```

安装：`pip install ezdxf --target ./pylib`（离线/失败时用 `dxf_kit.write_geometry_dxf` 的手工 R12 回退）。
