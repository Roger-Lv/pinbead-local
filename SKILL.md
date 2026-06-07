---
name: pinbead-local
description: 拼豆图纸本地生成器。把图片转换为 Mard 221 标准色卡的拼豆图纸。0 API 调用，全部本地处理（图像缩放 + CIEDE2000 颜色匹配 + PIL 渲染）。当用户说"拼豆"、"perler"、"hama"、"像素图转拼豆"、"帮我做拼豆图纸"、"把图片转成豆子图"时触发。
---

# pinbead-local

把图片转成 Mard 221 色拼豆图纸的**本地**工具。**0 API 调用**，跑完只需要 PIL/numpy/scipy/skimage。

## 工作流

1. 读 `spec.json`（可选）+ 加载图片
2. 默认中心正方形裁剪（非方形图）
3. LANCZOS 缩放到 `grid_w × grid_h`
4. 每格 RGB → Lab → CIEDE2000 找 Mard 221 最近色（逐像素 snap）
5. 背景检测（连图边的色块 = 背景，标 None 不拼）
6. 输出 `pattern.png`（带坐标轴/网格/色号）+ `grid.json` + `bom.csv`

## 调用

```bash
python3 scripts/convert.py <图片> --grid 100x100 --out-dir <输出目录>
```

可选参数：

| 参数 | 默认 | 说明 |
|------|------|------|
| `--grid WxH` | 100x100 | 目标网格 |
| `--bg-mode` | auto | auto / solid / keep |
| `--bg-color` | #FFFFFF | solid 模式用 |
| `--max-colors` | 0 | 0=不限，N=聚类到 N 色 |
| `--forbid` | - | 禁用色号，逗号分隔 |
| `--cell-px` | 22 | 图纸每格像素 |
| `--crop` | auto | auto / square / none |
| `--palette` | 内置 mard_221.csv | 色板路径 |
| `--name` | pattern | 输出文件名前缀 |
| `--spec` | - | spec.json 路径，覆盖 CLI 默认 |

## 输出

| 文件 | 用途 |
|------|------|
| `<name>_pattern.png` | 主图（带坐标轴、网格、每格色号） |
| `<name>_grid.json` | 完整网格数据 `{size, cells, bom, bead_count, bg_cells}` |
| `<name>_bom.csv` | 采购清单 `code,hex,name_zh,name_en,count` |

## spec.json 格式（可选）

```json
{
  "spec_id": "my_run",
  "grid_w": 100,
  "grid_h": 100,
  "max_colors": 0,
  "forbid_colors": ["H7"],
  "preserve_features": []
}
```

> `spec.json` 的 `grid_w/h` 显式给的话会覆盖 `--grid`。

## 背景处理

- **auto**（默认）：原图边缘连通的纯白色块 = 背景，留空不拼。内部白窟窿（如人物皮肤中的高光）会被强制 snap 到最近色板色。
- **solid**：把 `--bg-color` 指定的色识别为背景。
- **keep**：所有格都拼，不识别背景。

## 色板

内置 `palettes/mard_221.csv`（Mard 标准 221 色）。换色板就改 `--palette`。

## 跟其他工具的对比

- **vs pindou-skill**：pindou-skill 要调 gpt-image API 重绘像素图再提取，本工具跳过重绘直接量化原图。0 token 消耗。
- **vs pinbead-blueprint**（已废弃）：那个是 HTML 浏览器工具，本地是 CLI。

## 依赖

```
pip3 install pillow numpy scipy scikit-image
```

（macOS 自带 python3 + 上面这几个就够。）

## 触发场景

- 用户给张图说"做成拼豆"
- "把 cc&sky.jpg 转成 100x100 拼豆图"
- "我用 Mard 色卡做拼豆，需要个本地工具"
- "免 API 的拼豆转换器"
