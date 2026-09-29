# -*- coding: utf-8 -*-
"""dxf_kit: 机械图纸 DXF 生成工具库.

两种输出:
  1. AnnotatedDXF   —— 带尺寸/文字的标注版 (ASCII DXF R12, GBK, AutoCAD 友好)
  2. write_geometry_dxf —— 纯几何版 (仅 LINE/ARC/CIRCLE, 纯 ASCII, R2000, Fusion 360 可插入)

附带: inspect() 回读校验, render() 预览渲染.

CLI:
  python dxf_kit.py inspect <file.dxf>
  python dxf_kit.py render  <file.dxf> <out.png>
"""
import math, os, sys
from collections import Counter


def fmt(v):
    s = "%.4f" % float(v)
    s = s.rstrip("0").rstrip(".")
    return s if s not in ("-0", "") else "0"


# ============================ 标注版 (R12 / GBK) ============================
class AnnotatedDXF:
    AL, AH = 2.5, 0.7          # 箭头长/半宽 (mm)

    def __init__(self):
        self.e = []
        self.xmin = self.ymin = 1e9
        self.xmax = self.ymax = -1e9

    def _b(self, x, y):
        self.xmin = min(self.xmin, x); self.xmax = max(self.xmax, x)
        self.ymin = min(self.ymin, y); self.ymax = max(self.ymax, y)

    def _p(self, *pairs):
        for c, v in pairs:
            self.e.append("%3d\n%s" % (c, v))

    def line(self, layer, x1, y1, x2, y2):
        self._b(x1, y1); self._b(x2, y2)
        self._p((0, "LINE"), (8, layer), (10, fmt(x1)), (20, fmt(y1)), (30, "0.0"),
                (11, fmt(x2)), (21, fmt(y2)), (31, "0.0"))

    def circle(self, layer, cx, cy, r):
        self._b(cx - r, cy - r); self._b(cx + r, cy + r)
        self._p((0, "CIRCLE"), (8, layer), (10, fmt(cx)), (20, fmt(cy)), (30, "0.0"), (40, fmt(r)))

    def arc(self, layer, cx, cy, r, a1, a2):
        for a in (a1, a2):
            t = math.radians(a)
            self._b(cx + r * math.cos(t), cy + r * math.sin(t))
        self._p((0, "ARC"), (8, layer), (10, fmt(cx)), (20, fmt(cy)), (30, "0.0"),
                (40, fmt(r)), (50, fmt(a1)), (51, fmt(a2)))

    def poly_lines(self, layer, pts):
        n = len(pts)
        for i in range(n):
            x1, y1 = pts[i]; x2, y2 = pts[(i + 1) % n]
            self.line(layer, x1, y1, x2, y2)

    def solid_tri(self, layer, tip, tail1, tail2):
        """实心三角 (箭头). DXF 约定: 第4点=第3点 得到三角形."""
        for x, y in (tip, tail1, tail2):
            self._b(x, y)
        self._p((0, "SOLID"), (8, layer),
                (10, fmt(tip[0])), (20, fmt(tip[1])), (30, "0.0"),
                (11, fmt(tail1[0])), (21, fmt(tail1[1])), (31, "0.0"),
                (12, fmt(tail2[0])), (22, fmt(tail2[1])), (32, "0.0"),
                (13, fmt(tail2[0])), (23, fmt(tail2[1])), (33, "0.0"))

    def text(self, layer, x, y, h, s, rot=0.0):
        self._b(x, y)
        self._p((0, "TEXT"), (8, layer), (10, fmt(x)), (20, fmt(y)), (30, "0.0"),
                (40, fmt(h)), (1, s), (50, fmt(rot)), (7, "STANDARD"))

    @staticmethod
    def tw(s, h):
        """文本宽度估算: 汉字=1.0h, 其余=0.62h (txt.shx 近似)."""
        return sum(1.0 if ord(ch) > 0x2E80 else 0.62 for ch in s) * h

    def _arrow(self, layer, tip, ux, uy):
        px, py = -uy, ux
        self.solid_tri(layer, tip,
                       (tip[0] - ux * self.AL + px * self.AH, tip[1] - uy * self.AL + py * self.AH),
                       (tip[0] - ux * self.AL - px * self.AH, tip[1] - uy * self.AL - py * self.AH))

    def dim_h(self, x1, x2, ydim, label, yfeat):
        """水平尺寸. yfeat: 见证线起点, 可为标量或 (y1, y2) 元组 (孔边/圆角切点)."""
        f1, f2 = yfeat if isinstance(yfeat, tuple) else (yfeat, yfeat)
        s1 = 1.0 if ydim > f1 else -1.0
        s2 = 1.0 if ydim > f2 else -1.0
        self.line("DIM", x1, f1 + 0.6 * s1, x1, ydim + 2.2 * s1)
        self.line("DIM", x2, f2 + 0.6 * s2, x2, ydim + 2.2 * s2)
        L = x2 - x1
        w = self.tw(label, 2.5)
        ty = ydim + 0.9 if s1 > 0 else ydim - 3.4
        if L >= 2 * self.AL + 1.0:
            self.line("DIM", x1, ydim, x2, ydim)
            self._arrow("DIM", (x1, ydim), -1, 0)
            self._arrow("DIM", (x2, ydim), 1, 0)
            tx = (x1 + x2) / 2 - w / 2
        else:
            self.line("DIM", x1 - self.AL - 1.2, ydim, x2 + self.AL + 1.2, ydim)
            self._arrow("DIM", (x1, ydim), 1, 0)
            self._arrow("DIM", (x2, ydim), -1, 0)
            tx = x2 + 0.6          # 窄尺寸: 文字放右外侧, 箭头外置
        self.text("TEXT", tx, ty, 2.5, label)

    def dim_v(self, y1, y2, xdim, label, xfeat):
        sgn = 1.0 if xdim > xfeat else -1.0
        self.line("DIM", xfeat + 0.6 * sgn, y1, xdim + 2.2 * sgn, y1)
        self.line("DIM", xfeat + 0.6 * sgn, y2, xdim + 2.2 * sgn, y2)
        L = y2 - y1
        w = self.tw(label, 2.5)
        tx = xdim - 3.4 if sgn < 0 else xdim + 0.9
        if L >= 2 * self.AL + 1.0:
            self.line("DIM", xdim, y1, xdim, y2)
            self._arrow("DIM", (xdim, y1), 0, -1)
            self._arrow("DIM", (xdim, y2), 0, 1)
        else:
            self.line("DIM", xdim, y1 - self.AL - 1.2, xdim, y2 + self.AL + 1.2)
            self._arrow("DIM", (xdim, y1), 0, 1)
            self._arrow("DIM", (xdim, y2), 0, -1)
        self.text("TEXT", tx, (y1 + y2) / 2 - w / 2, 2.5, label, rot=90)

    def centermark(self, layer, cx, cy, r):
        self.line(layer, cx - r - 1.2, cy, cx + r + 1.2, cy)
        self.line(layer, cx, cy - r - 1.2, cx, cy + r + 1.2)

    def leader(self, x0, y0, x1, y1, label, tx, ty, h=3.0):
        self.line("TEXT", x0, y0, x1, y1)
        d = math.hypot(x1 - x0, y1 - y0) or 1.0
        self._arrow("TEXT", (x1, y1), (x1 - x0) / d, (y1 - y0) / d)
        self.text("TEXT", tx, ty, h, label)

    def save(self, path, layers=None):
        layers = layers or [("0", 7), ("OUTLINE", 7), ("HOLES", 1), ("PANEL", 4),
                            ("REF", 8), ("DIM", 3), ("TEXT", 2)]
        L = []
        A = L.append
        A("0\nSECTION"); A("2\nHEADER")
        A("9\n$ACADVER\n1\nAC1009")
        A("9\n$DWGCODEPAGE\n3\nANSI_936")
        A("9\n$INSBASE\n10\n0\n20\n0\n30\n0")
        A("9\n$EXTMIN\n10\n%s\n20\n%s\n30\n0" % (fmt(self.xmin - 5), fmt(self.ymin - 5)))
        A("9\n$EXTMAX\n10\n%s\n20\n%s\n30\n0" % (fmt(self.xmax + 5), fmt(self.ymax + 5)))
        A("9\n$LIMMIN\n10\n%s\n20\n%s" % (fmt(self.xmin - 5), fmt(self.ymin - 5)))
        A("9\n$LIMMAX\n10\n%s\n20\n%s" % (fmt(self.xmax + 5), fmt(self.ymax + 5)))
        A("9\n$LTSCALE\n40\n1.0")
        A("9\n$TEXTSIZE\n40\n2.5")
        A("9\n$CLAYER\n8\nOUTLINE")
        A("0\nENDSEC")
        A("0\nSECTION"); A("2\nTABLES")
        A("0\nTABLE\n2\nLTYPE\n70\n1")
        A("0\nLTYPE\n2\nCONTINUOUS\n70\n0\n3\nSolid line\n72\n65\n73\n0\n40\n0.0")
        A("0\nENDTAB")
        A("0\nTABLE\n2\nLAYER\n70\n%d" % len(layers))
        for name, col in layers:
            A("0\nLAYER\n2\n%s\n70\n0\n62\n%d\n6\nCONTINUOUS" % (name, col))
        A("0\nENDTAB")
        A("0\nTABLE\n2\nSTYLE\n70\n1")
        # txt.shx + gbcbig.shx = 中文 AutoCAD 标准组合
        A("0\nSTYLE\n2\nSTANDARD\n70\n0\n40\n0.0\n41\n1.0\n50\n0.0\n71\n0\n42\n2.5\n3\ntxt.shx\n4\ngbcbig.shx")
        A("0\nENDTAB")
        A("0\nTABLE\n2\nAPPID\n70\n1")
        A("0\nAPPID\n2\nACAD\n70\n0\n1001\nACAD")
        A("0\nENDTAB")
        A("0\nENDSEC")
        A("0\nSECTION"); A("2\nBLOCKS"); A("0\nENDSEC")
        A("0\nSECTION"); A("2\nENTITIES")
        L.extend(self.e)
        A("0\nENDSEC"); A("0\nEOF")
        data = "\r\n".join(x.replace("\n", "\r\n") for x in L) + "\r\n"
        with open(path, "wb") as f:
            f.write(data.encode("gbk", errors="replace"))
        return path


# ============================ 几何版 (Fusion 360) ============================
def write_geometry_dxf(path, lines, arcs, circles, layers=None):
    """Fusion 360 兼容纯几何 DXF.

    lines:   [(layer, x1, y1, x2, y2), ...]
    arcs:    [(layer, cx, cy, r, start_deg, end_deg), ...]   # 逆时针, 度
    circles: [(layer, cx, cy, r), ...]
    仅 LINE/ARC/CIRCLE; 文件纯 ASCII; 单位 mm.

    优先 ezdxf(R2000, 结构完整); 无 ezdxf 时回退手工 R12 几何版.
    """
    layers = layers or [("OUTLINE", 7), ("HOLES", 1), ("PANEL", 4), ("REF", 8)]
    try:
        import ezdxf  # type: ignore
        doc = ezdxf.new("R2000", setup=False)
        doc.header["$INSUNITS"] = 4
        doc.header["$MEASUREMENT"] = 1
        for name, color in layers:
            doc.layers.add(name, color=color)
        msp = doc.modelspace()
        for ly, x1, y1, x2, y2 in lines:
            msp.add_line((x1, y1), (x2, y2), dxfattribs={"layer": ly})
        for ly, cx, cy, r, a1, a2 in arcs:
            msp.add_arc((cx, cy), r, a1, a2, dxfattribs={"layer": ly})
        for ly, cx, cy, r in circles:
            msp.add_circle((cx, cy), r, dxfattribs={"layer": ly})
        auditor = doc.audit()
        if auditor.has_errors:
            raise RuntimeError("ezdxf audit errors: %s" % auditor.errors[:3])
        doc.saveas(path, fmt="asc")
        return path, "ezdxf/R2000"
    except ImportError:
        pass
    # 回退: 手工 R12, 仅几何
    d = AnnotatedDXF()
    for ly, x1, y1, x2, y2 in lines:
        d.line(ly, x1, y1, x2, y2)
    for ly, cx, cy, r, a1, a2 in arcs:
        d.arc(ly, cx, cy, r, a1, a2)
    for ly, cx, cy, r in circles:
        d.circle(ly, cx, cy, r)
    d.save(path, layers=[(n, c) for n, c in layers])
    return path, "manual/R12"


def rounded_rect_lines(layer, x0, y0, x1, y1, r, collect):
    """圆角矩形 -> 线段/圆弧列表 (写入 collect 供 write_geometry_dxf 用)."""
    lines, arcs = collect
    lines.append((layer, x0 + r, y1, x1 - r, y1))
    arcs.append((layer, x1 - r, y1 - r, r, 0, 90))
    lines.append((layer, x1, y1 - r, x1, y0 + r))
    arcs.append((layer, x1 - r, y0 + r, r, 270, 360))
    lines.append((layer, x1 - r, y0, x0 + r, y0))
    arcs.append((layer, x0 + r, y0 + r, r, 180, 270))
    lines.append((layer, x0, y0 + r, x0, y1 - r))
    arcs.append((layer, x0 + r, y1 - r, r, 90, 180))


# ============================ 校验 / 渲染 ============================
def inspect(path):
    """回读 DXF: 实体统计、纯 ASCII、几何版检查(无 TEXT/SOLID)."""
    raw = open(path, "rb").read()
    ascii_ok = all(b < 128 for b in raw)
    text = raw.decode("gbk", errors="replace")
    lines = text.splitlines()
    pairs = [(lines[i].strip(), lines[i + 1]) for i in range(0, len(lines) - 1, 2)]
    types = Counter()
    in_ent = False
    for c, v in pairs:
        if c == "2" and v == "ENTITIES":
            in_ent = True
        elif in_ent and c == "0":
            if v == "ENDSEC":
                break
            types[v] += 1
    report = {
        "bytes": len(raw),
        "pure_ascii": ascii_ok,
        "entities": dict(types),
        "has_text": types.get("TEXT", 0) > 0,
        "has_solid": types.get("SOLID", 0) > 0,
        "fusion_safe": ascii_ok and not types.get("TEXT") and not types.get("SOLID")
                       and not types.get("HATCH") and not types.get("DIMENSION"),
    }
    return report


def render(dxf_path, png_path, px_per_mm=11, pad=8):
    """粗渲染预览 (校验用). 尽量用 ezdxf 读, 否则内部解析 LINE/ARC/CIRCLE/TEXT/SOLID."""
    from PIL import Image, ImageDraw, ImageFont
    try:
        import ezdxf  # type: ignore
        doc = ezdxf.readfile(dxf_path)
        ents = []
        for e in doc.modelspace():
            t = e.dxftype()
            if t == "LINE":
                a, b = e.dxf.start, e.dxf.end
                ents.append(("L", e.dxf.layer, (a.x, a.y, b.x, b.y)))
            elif t == "CIRCLE":
                c = e.dxf.center
                ents.append(("C", e.dxf.layer, (c.x, c.y, e.dxf.radius)))
            elif t == "ARC":
                c = e.dxf.center
                ents.append(("A", e.dxf.layer,
                             (c.x, c.y, e.dxf.radius,
                              math.radians(e.dxf.start_angle), math.radians(e.dxf.end_angle))))
        mode = "ezdxf"
    except Exception:
        raw = open(dxf_path, "rb").read().decode("gbk", errors="replace")
        lines = raw.splitlines()
        pairs = [(lines[i].strip(), lines[i + 1]) for i in range(0, len(lines) - 1, 2)]
        ents, cur, in_ent = [], None, False
        for c, v in pairs:
            if c == "2" and v == "ENTITIES":
                in_ent = True
            elif in_ent and c == "0":
                if v == "ENDSEC":
                    break
                cur = {"t": v, "d": {}}
                ents.append(cur)
            elif in_ent and cur is not None:
                cur["d"].setdefault(c, v)
        out = []
        for e in ents:
            d = e["d"]; t = e["t"]; ly = d.get("8", "0")
            if t == "LINE":
                out.append(("L", ly, (float(d["10"]), float(d["20"]),
                                      float(d["11"]), float(d["21"]))))
            elif t == "CIRCLE":
                out.append(("C", ly, (float(d["10"]), float(d["20"]), float(d["40"]))))
            elif t == "ARC":
                out.append(("A", ly, (float(d["10"]), float(d["20"]), float(d["40"]),
                                      math.radians(float(d["50"])), math.radians(float(d["51"])))))
        ents = out
        mode = "internal"
    if not ents:
        raise RuntimeError("no geometry entities found in %s" % dxf_path)
    xs = ys = []
    xs, ys = [], []
    for _, _, d in ents:
        if len(d) == 4:
            xs += [d[0], d[2]]; ys += [d[1], d[3]]
        else:
            xs += [d[0] - d[2], d[0] + d[2]]; ys += [d[1] - d[2], d[1] + d[2]]
    x0, x1 = min(xs) - pad, max(xs) + pad
    y0, y1 = min(ys) - pad, max(ys) + pad
    W = int((x1 - x0) * px_per_mm); H = int((y1 - y0) * px_per_mm)
    im = Image.new("RGB", (W, H), "white")
    dr = ImageDraw.Draw(im)
    col = {"OUTLINE": (0, 0, 0), "HOLES": (200, 0, 0), "PANEL": (0, 140, 160),
           "REF": (150, 150, 150), "DIM": (0, 150, 0), "TEXT": (30, 30, 30), "0": (0, 0, 0)}

    def T(x, y):
        return ((x - x0) * px_per_mm, (y1 - y) * px_per_mm)

    for typ, ly, d in ents:
        cc = col.get(ly, (0, 0, 0))
        if typ == "L":
            dr.line([T(d[0], d[1]), T(d[2], d[3])], fill=cc, width=1)
        elif typ == "C":
            dr.ellipse([T(d[0] - d[2], d[1] + d[2]), T(d[0] + d[2], d[1] - d[2])],
                       outline=cc, width=1)
        else:
            cx, cy, r, a1, a2 = d
            if a2 <= a1:
                a2 += 2 * math.pi
            pts = [T(cx + r * math.cos(a1 + (a2 - a1) * k / 32),
                     cy + r * math.sin(a1 + (a2 - a1) * k / 32)) for k in range(33)]
            dr.line(pts, fill=cc, width=1)
    im.save(png_path)
    return im.size, mode


if __name__ == "__main__":
    if len(sys.argv) < 3:
        print(__doc__)
        sys.exit(1)
    cmd = sys.argv[1]
    if cmd == "inspect":
        r = inspect(sys.argv[2])
        for k, v in r.items():
            print("%s: %s" % (k, v))
    elif cmd == "render":
        size, mode = render(sys.argv[2], sys.argv[3])
        print("rendered", sys.argv[3], size, "via", mode)
    else:
        print("unknown command:", cmd)
        sys.exit(1)
