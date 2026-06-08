#!/usr/bin/env python3
"""
pinbead-local: 图片 → 拼豆图纸 (本地版, 0 API 调用)

pipeline:
  load spec + image → 中心正方形裁剪 → LANCZOS 缩放到 grid_w×grid_h →
  每格 → Lab → CIEDE2000 找 Mard 221 最近色 →
  背景检测 (连图边的色块 = 背景, 标 None 不拼) →
  写 grid.json + bom.csv + 渲染 pattern.png (带坐标轴、网格、每格色号)

usage:
  # 用 spec.json
  python convert.py --spec spec.json --image photo.jpg --out-dir out/

  # 纯命令行
  python convert.py photo.jpg --grid 100x100 --out-dir out/

  # 不裁背景（用纯色填充）
  python convert.py photo.jpg --grid 100x100 --bg-mode solid --bg-color "#FFFFFF"
"""

from __future__ import annotations

import argparse
import csv
import json
from collections import Counter
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFont
from scipy.ndimage import label as cc_label
from skimage import color as skcolor


PALETTE_PATH = Path(__file__).parent.parent / "palettes" / "mard_221.csv"


def load_palette(path: Path) -> list[dict]:
    rows = []
    with path.open("r", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            rows.append({
                "code": row["code"],
                "hex": row["hex"],
                "rgb": np.array([int(row["r"]), int(row["g"]), int(row["b"])], dtype=np.uint8),
                "name_zh": row.get("name_zh", ""),
                "name_en": row.get("name_en", ""),
            })
    return rows


def center_crop_square(img: Image.Image) -> Image.Image:
    w, h = img.size
    s = min(w, h)
    return img.crop(((w - s) // 2, (h - s) // 2, (w + s) // 2, (h + s) // 2))


def downsample(img: Image.Image, gw: int, gh: int) -> np.ndarray:
    """LANCZOS 缩到 gw×gh, 返回 (gh, gw, 3) uint8 数组"""
    return np.array(img.resize((gw, gh), Image.LANCZOS).convert("RGB"))


def snap_to_palette_ciede2000(grid_rgb: np.ndarray, palette: list[dict],
                              forbid: list[str] | None = None) -> tuple[np.ndarray, np.ndarray]:
    """
    grid_rgb: (gh, gw, 3) uint8
    返回 (codes_idx: (gh, gw) int 数组, pal_lab: (P, 3) float 数组)
    """
    p_use = [p for p in palette if not forbid or p["code"] not in forbid]
    pal_rgb = np.stack([p["rgb"] for p in p_use]).astype(np.float64) / 255.0
    pal_lab = skcolor.rgb2lab(pal_rgb.reshape(1, -1, 3)).reshape(-1, 3)

    h, w = grid_rgb.shape[:2]
    flat = grid_rgb.reshape(-1, 3).astype(np.float64) / 255.0
    flat_lab = skcolor.rgb2lab(flat.reshape(1, h * w, 3)).reshape(h * w, 3)

    # 广播到 (N, P, 3) 再算 ΔE，比 for-loop 快 50x
    q = flat_lab[:, None, :]      # (N, 1, 3)
    p = pal_lab[None, :, :]      # (1, P, 3)
    q_b = np.broadcast_to(q, (q.shape[0], p.shape[1], 3))
    p_b = np.broadcast_to(p, (q.shape[0], p.shape[1], 3))
    de = skcolor.deltaE_ciede2000(q_b, p_b)  # (N, P)
    idx = np.argmin(de, axis=1)
    return idx.reshape(h, w), pal_lab


def detect_background(mask_bg_code: np.ndarray) -> np.ndarray:
    """
    mask_bg_code: (h, w) bool, True 表示可能是背景 (e.g. 颜色 = 纯白)
    返回 (h, w) bool, True = 确认为背景
    规则: 连通到图边的 True 区域 = 背景, 内部孤岛 = 主体保留
    """
    structure = np.ones((3, 3), dtype=np.uint8)
    labeled, n = cc_label(mask_bg_code, structure=structure)
    bg = np.zeros_like(mask_bg_code, dtype=bool)
    for i in range(1, n + 1):
        region = (labeled == i)
        if region[0, :].any() or region[-1, :].any() or region[:, 0].any() or region[:, -1].any():
            bg |= region
    return bg


def render_pattern(grid_codes: list[list[str | None]], palette: list[dict],
                   cell_px: int = 22) -> Image.Image:
    pal_lookup = {p["code"]: p["hex"] for p in palette}
    h = len(grid_codes)
    w = len(grid_codes[0])

    AXIS = 28
    canvas_w = w * cell_px + AXIS
    canvas_h = h * cell_px + AXIS
    img = Image.new("RGB", (canvas_w, canvas_h), "#f0f0f0")
    draw = ImageDraw.Draw(img)
    draw.rectangle([AXIS, 0, canvas_w, canvas_h], fill="white")

    # 找中文字体（macOS 自带，失败回退默认）
    font_path = None
    for p in [
        "/System/Library/Fonts/PingFang.ttc",
        "/System/Library/Fonts/STHeiti Medium.ttc",
        "/System/Library/Fonts/Hiragino Sans GB.ttc",
    ]:
        if Path(p).exists():
            font_path = p
            break
    num_font = ImageFont.truetype(font_path, 10) if font_path else ImageFont.load_default()
    code_font = ImageFont.truetype(font_path, max(6, cell_px // 3)) if font_path else ImageFont.load_default()

    # 填色
    for r in range(h):
        for c in range(w):
            code = grid_codes[r][c]
            x, y = AXIS + c * cell_px, r * cell_px
            if code is None:
                draw.rectangle([x, y, x + cell_px, y + cell_px], fill="#e8e8e8")
            else:
                draw.rectangle([x, y, x + cell_px, y + cell_px], fill=pal_lookup.get(code, "#888"))

    # 细格线
    for i in range(w + 1):
        x = AXIS + i * cell_px
        draw.line([(x, 0), (x, h * cell_px)], fill="#00000018", width=1)
    for i in range(h + 1):
        y = i * cell_px
        draw.line([(AXIS, y), (canvas_w, y)], fill="#00000018", width=1)

    # 每 10 格粗线
    for i in range(0, w + 1, 10):
        x = AXIS + i * cell_px
        draw.line([(x, 0), (x, h * cell_px)], fill="#00000066", width=2)
    for i in range(0, h + 1, 10):
        y = i * cell_px
        draw.line([(AXIS, y), (canvas_w, y)], fill="#00000066", width=2)

    # 外框
    draw.rectangle([AXIS, 0, canvas_w - 1, h * cell_px - 1], outline="#000000aa", width=2)

    # 坐标
    for i in range(0, w + 1, 5):
        s = str(i)
        bbox = draw.textbbox((0, 0), s, font=num_font)
        tw = bbox[2] - bbox[0]
        draw.text((AXIS + i * cell_px - tw // 2, h * cell_px + 7), s, fill="#444", font=num_font)
    for i in range(0, h + 1, 5):
        s = str(i)
        bbox = draw.textbbox((0, 0), s, font=num_font)
        tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
        draw.text((AXIS - tw - 6, i * cell_px - th // 2), s, fill="#444", font=num_font)

    # 每格色号（带白色描边）
    for r in range(h):
        for c in range(w):
            code = grid_codes[r][c]
            if code is None:
                continue
            bbox = draw.textbbox((0, 0), code, font=code_font)
            tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
            x = AXIS + c * cell_px + (cell_px - tw) // 2
            y = r * cell_px + (cell_px - th) // 2 - 1
            for dx, dy in [(-1, 0), (1, 0), (0, -1), (0, 1)]:
                draw.text((x + dx, y + dy), code, fill="white", font=code_font)
            draw.text((x, y), code, fill="black", font=code_font)

    return img


def main():
    ap = argparse.ArgumentParser(description="图片 → Mard 221 拼豆图纸 (本地)")
    ap.add_argument("image", nargs="?", help="输入图片 (jpg/png/webp)")
    ap.add_argument("--spec", help="spec.json 路径 (覆盖 CLI 默认值)")
    ap.add_argument("--grid", default="100x100", help="目标网格 WxH, 默认 100x100")
    ap.add_argument("--bg-mode", default="auto", choices=["auto", "solid", "keep"],
                    help="auto=自动识别背景留空, solid=按 --bg-color 填, keep=原图所有格都拼")
    ap.add_argument("--bg-color", default="#FFFFFF", help="bg-mode=solid 时用这个色")
    ap.add_argument("--max-colors", type=int, default=0, help="限制颜色种数, 0=不限 (CIEDE2000 聚类到 top-K)")
    ap.add_argument("--forbid", default="", help="禁用色号, 逗号分隔 (e.g. H7,F5)")
    ap.add_argument("--cell-px", type=int, default=22, help="图纸每格像素")
    ap.add_argument("--crop", choices=["auto", "square", "none"], default="auto",
                    help="auto=非方形时中心裁方, square=总是裁, none=不裁")
    ap.add_argument("--palette", default=str(PALETTE_PATH))
    ap.add_argument("--out-dir", required=True, help="输出目录")
    ap.add_argument("--name", default="pattern", help="输出文件名前缀")
    args = ap.parse_args()

    gw, gh = map(int, args.grid.lower().split("x"))

    # 加载 spec (如果给了)
    spec = {}
    if args.spec:
        with open(args.spec) as f:
            spec = json.load(f)
        # spec 的 grid 覆盖 CLI（如果 spec 显式给了）
        if "grid_w" in spec and "grid_h" in spec:
            gw, gh = spec["grid_w"], spec["grid_h"]

    img = Image.open(args.image)
    if args.crop == "auto" and img.size[0] != img.size[1]:
        img = center_crop_square(img)
        crop_msg = f"中心裁方到 {img.size[0]}×{img.size[1]}"
    elif args.crop == "square":
        img = center_crop_square(img)
        crop_msg = f"中心裁方到 {img.size[0]}×{img.size[1]}"
    else:
        crop_msg = f"保持原比例 {img.size[0]}×{img.size[1]}"

    # 缩放到目标网格
    grid_rgb = downsample(img.convert("RGB"), gw, gh)

    # 加载色板
    palette = load_palette(Path(args.palette))
    forbid = [s.strip() for s in args.forbid.split(",") if s.strip()]
    if spec.get("forbid_colors"):
        forbid = list(set(forbid + spec["forbid_colors"]))

    # CIEDE2000 量化
    idx_grid, _ = snap_to_palette_ciede2000(grid_rgb, palette, forbid=forbid)
    codes_grid = [[palette[int(idx_grid[r, c])]["code"] for c in range(gw)] for r in range(gh)]

    # max_colors 二次聚类（用色板色互相 snap，不增加新色）
    bg_count = 0
    if args.bg_mode == "auto":
        # 找最接近纯白的色板色作为 bg 候选
        bg_target = np.array([255, 255, 255], dtype=np.float64).reshape(1, 1, 3) / 255.0
        bg_lab = skcolor.rgb2lab(bg_target.reshape(1, 1, 3)).reshape(1, 3)
        pal_rgb = np.stack([p["rgb"] for p in palette]).astype(np.float64) / 255.0
        pal_lab = skcolor.rgb2lab(pal_rgb.reshape(1, -1, 3)).reshape(-1, 3)
        dE_to_white = skcolor.deltaE_ciede2000(pal_lab, bg_lab).flatten()
        # 多个白色候选
        white_codes = {palette[i]["code"] for i in range(len(palette)) if dE_to_white[i] < 5}
        white_codes.update({palette[i]["code"] for i in range(len(palette)) if palette[i]["code"] in {"H1", "H2", "H18"}})
        mask_bg = np.isin(idx_grid, [i for i, p in enumerate(palette) if p["code"] in white_codes])
        bg_mask = detect_background(mask_bg)
        for r in range(gh):
            for c in range(gw):
                if bg_mask[r, c]:
                    codes_grid[r][c] = None
        bg_count = int(bg_mask.sum())
    elif args.bg_mode == "solid":
        # 用指定纯色 + 主体判别（连图边 = 背景）
        target = Image.new("RGB", (1, 1), args.bg_color).getpixel((0, 0))
        target_arr = np.array(target, dtype=np.uint8)
        target_lab = skcolor.rgb2lab(target_arr.reshape(1, 1, 3).astype(np.float64) / 255.0).reshape(1, 3)
        pal_lab = skcolor.rgb2lab(np.stack([p["rgb"] for p in palette]).astype(np.float64).reshape(1, -1, 3) / 255.0).reshape(-1, 3)
        dE = skcolor.deltaE_ciede2000(pal_lab, target_lab).flatten()
        bg_idx = int(np.argmin(dE))
        # 用原图边缘像素判断哪些是背景
        edge = np.concatenate([grid_rgb[0, :], grid_rgb[-1, :], grid_rgb[:, 0], grid_rgb[:, -1]], axis=0)
        # 简单：直接把"颜色 = bg_idx 色的格"且周围大范围都是这个色的标 None
        is_bg_color = (idx_grid == bg_idx)
        bg_mask = detect_background(is_bg_color)
        for r in range(gh):
            for c in range(gw):
                if bg_mask[r, c]:
                    codes_grid[r][c] = None
        bg_count = int(bg_mask.sum())

    # max_colors 限制（不在 top-K 的色 → snap 到 top-K 之一）
    max_k = args.max_colors or spec.get("max_colors", 0)
    if max_k > 0:
        flat = [c for row in codes_grid for c in row if c is not None]
        counter = Counter(flat)
        top = {code for code, _ in counter.most_common(max_k)}
        top_palette = [p for p in palette if p["code"] in top]
        top_lab = skcolor.rgb2lab(np.stack([p["rgb"] for p in top_palette]).astype(np.float64).reshape(1, -1, 3) / 255.0).reshape(-1, 3)
        for r in range(gh):
            for c in range(gw):
                code = codes_grid[r][c]
                if code is None or code in top:
                    continue
                orig_p = next(p for p in palette if p["code"] == code)
                orig_lab = skcolor.rgb2lab(orig_p["rgb"].astype(np.float64).reshape(1, 1, 3) / 255.0).reshape(1, 3)
                dE = skcolor.deltaE_ciede2000(top_lab, orig_lab)
                codes_grid[r][c] = top_palette[int(np.argmin(dE))]["code"]

    # 写 grid.json
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    flat = [c for row in codes_grid for c in row if c is not None]
    counter = Counter(flat)
    bead_count = sum(counter.values())
    bom_rows = sorted(counter.items(), key=lambda x: -x[1])

    grid_json = {
        "spec_id": spec.get("spec_id", args.name),
        "palette_id": "mard_221",
        "size": [gw, gh],
        "bead_count": bead_count,
        "bg_cells": bg_count,
        "cells": codes_grid,
        "bom": [
            {"code": code, "count": cnt,
             "hex": next(p["hex"] for p in palette if p["code"] == code),
             "name_zh": next(p["name_zh"] for p in palette if p["code"] == code)}
            for code, cnt in bom_rows
        ],
    }
    (out_dir / f"{args.name}_grid.json").write_text(json.dumps(grid_json, ensure_ascii=False, indent=2))

    # 写 bom.csv
    with (out_dir / f"{args.name}_bom.csv").open("w", newline="", encoding="utf-8") as f:
        w_csv = csv.writer(f)
        w_csv.writerow(["code", "hex", "name_zh", "name_en", "count"])
        for code, cnt in bom_rows:
            p = next(x for x in palette if x["code"] == code)
            w_csv.writerow([p["code"], p["hex"], p["name_zh"], p["name_en"], cnt])

    # 渲染 pattern.png
    pattern = render_pattern(codes_grid, palette, cell_px=args.cell_px)
    pattern.save(out_dir / f"{args.name}_pattern.png", optimize=True)

    n_colors = len(counter)

    # 写 stats.txt (人类可读总览: 全部色号 + 颗数 + 占比 + 条形图)
    max_cnt = bom_rows[0][1] if bom_rows else 0
    bar_w = 24
    stats_lines = [
        f"拼豆统计 - {args.name}",
        f"输入: {Path(args.image).name}",
        f"网格: {gw}×{gh} = {gw*gh} 格 | 豆 {bead_count} 颗 | 背景留空 {bg_count} 格",
        f"色数: {n_colors} 种 (Mard 221)",
        "",
        f"{'色号':<5} {'名称':<10} {'颗数':>5} {'占比':>6}  条形图",
        "-" * 64,
    ]
    for code, cnt in bom_rows:
        p = next(x for x in palette if x["code"] == code)
        pct = cnt / bead_count * 100 if bead_count else 0
        bar_len = int(round(cnt / max_cnt * bar_w)) if max_cnt else 0
        bar = "█" * bar_len
        stats_lines.append(
            f"{code:<5} {p['name_zh']:<10} {cnt:>5} {pct:>5.1f}%  {bar}"
        )
    stats_lines.append("-" * 64)
    stats_lines.append(f"{'合计':<5} {'':<10} {bead_count:>5} {'100.0%':>6}")
    (out_dir / f"{args.name}_stats.txt").write_text("\n".join(stats_lines) + "\n", encoding="utf-8")

    print(f"[pinbead-local] 输入: {Path(args.image).name} ({crop_msg})")
    print(f"[pinbead-local] 网格: {gw}×{gh} = {gw*gh} 格 ({bead_count} 颗豆, {bg_count} 背景留空)")
    print(f"[pinbead-local] 颜色: {n_colors} 种 (Mard 221)")
    print(f"[pinbead-local] 输出:")
    print(f"   - {out_dir / (args.name + '_pattern.png')}")
    print(f"   - {out_dir / (args.name + '_grid.json')}")
    print(f"   - {out_dir / (args.name + '_bom.csv')}")
    print(f"   - {out_dir / (args.name + '_stats.txt')}")
    if n_colors:
        print(f"[pinbead-local] TOP 5: {', '.join(f'{c}×{n}' for c, n in bom_rows[:5])}")


if __name__ == "__main__":
    main()
