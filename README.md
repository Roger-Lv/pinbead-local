# pinbead-local 🧩

把任意图片转成 **Mard 221 标准色卡**拼豆图纸的本地 CLI 工具。

**零 API、零云端、零费用** —— 一张图从输入到图纸，全程在你电脑上跑完。

> 适合：把照片/插画/手绘图转成可以照着摆豆的网格图纸 + 采购清单。

---

## ✨ 特性

- 🎨 **Mard 221 标准色卡**：221 色，足够覆盖绝大多数照片/插画
- 🔬 **CIEDE2000 颜色匹配**：业界标准的感知色差算法，比 RGB 欧几里得距离准得多
- 🖼️ **自动背景识别**：连图边的纯白块自动判定为背景，留空不拼（省钱！）
- 📐 **可调网格尺寸**：`--grid 100x100` / `60x60` / 任意 `WxH`
- 🚫 **可禁用色号**：手头缺什么色就 ban 掉什么色
- 📊 **采购清单自动出**：`bom.csv` 直接给色号 + 数量，去淘宝照着下单
- 🚀 **CLI 优先**：一行命令搞定，可批量、可脚本化

---

## 📦 安装

依赖只有 4 个常见库：

```bash
pip3 install pillow numpy scipy scikit-image
```

> macOS 自带的 Python 3.9 + 这 4 个就够用。

---

## 🚀 快速开始

```bash
# 最简用法：100x100 图纸 + 自动背景识别
python3 scripts/convert.py photo.jpg --grid 100x100 --out-dir ./out/

# 60x60 小板（适合先打样）
python3 scripts/convert.py photo.jpg --grid 60x60 --out-dir ./out/

# 限制只用 24 种颜色（颜色少 = 好买 = 好拼）
python3 scripts/convert.py photo.jpg --grid 80x80 --max-colors 24 --out-dir ./out/
```

输出 3 个文件：

| 文件 | 用途 |
|------|------|
| `pattern.png` | 主图（带坐标轴、网格、每格色号），可直接打印或手机对照摆豆 |
| `grid.json` | 完整网格数据（尺寸、每格色号、BOM） |
| `bom.csv` | 采购清单，色号 + 颜色名 + 颗数 |

---

## 📖 完整参数

| 参数 | 默认 | 说明 |
|------|------|------|
| `--grid WxH` | `100x100` | 目标网格（决定图纸格数） |
| `--bg-mode` | `auto` | `auto` 自动识别背景 / `solid` 用指定色当背景 / `keep` 全部都拼 |
| `--bg-color` | `#FFFFFF` | `bg-mode=solid` 时用这个色当背景 |
| `--max-colors` | `0` | 0 = 不限（最多用全 221 色），N = 聚类到 N 色 |
| `--forbid` | - | 禁用色号，逗号分隔（e.g. `H7,F5`） |
| `--cell-px` | `22` | 图纸每格画多大像素（A4 打印建议 30-40） |
| `--crop` | `auto` | `auto` 非方形自动中心裁方 / `square` 总是裁 / `none` 不裁 |
| `--palette` | 内置 `mard_221.csv` | 色板 CSV 路径 |
| `--name` | `pattern` | 输出文件名前缀 |
| `--spec` | - | `spec.json` 路径，覆盖 CLI 默认值 |

### 用 `spec.json` 保存常用配置

```json
{
  "spec_id": "my_portrait",
  "grid_w": 100,
  "grid_h": 100,
  "max_colors": 0,
  "forbid_colors": []
}
```

```bash
python3 scripts/convert.py photo.jpg --spec my_spec.json --out-dir ./out/
```

---

## 🎯 背景处理详解

工具的"背景留空"逻辑很重要 —— 留空就不消耗豆子、能省一大笔钱。

| 模式 | 行为 | 适用场景 |
|------|------|---------|
| `auto`（默认） | 连通到图边的纯白块 = 背景，留空；图片内部的纯白高光（眼睛反光等）强制 snap 到最近色 | 大部分图 |
| `solid` | 把 `--bg-color` 指定的纯色识别为背景（连通到图边的） | 背景不是白色的图 |
| `keep` | 所有格都拼，不识别背景 | 想要满版图纸 |

> 算法：先找原图边缘的颜色 → 如果它们对应 Mard 221 中的"白"色（H1/H2/H18 等）→ 找这些色块的连通区域 → 连通到图边的 = 背景。

---

## 🆚 跟同类工具的对比

| 工具 | 调用 | 流程 | 适合谁 |
|------|------|------|--------|
| **pinbead-local**（本工具）| 0 API | 直接量化原图 | 想要快速、免费、可重现 |
| [pindou-skill](https://github.com/) | 调 gpt-image API | AI 重绘像素图 → 提取 | 想要"卡通化/扁平化"二次创作 |
| 在线网站（如 PerlerPatterns） | 上传云端 | 不透明算法 | 不在意隐私的尝鲜用户 |

**什么时候选本工具？**
- 你手头图片本身已经是想要的风格（照片/插画/像素画），不需要 AI 重画
- 你不想为每次转换付 API 钱
- 你希望处理过程可重现、可调参
- 你有隐私顾虑，不想把照片传云端

---

## 🛠️ 工作流

```
输入 photo.jpg
   ↓
[1] 读 spec.json（可选）+ 加载图片
   ↓
[2] 中心正方形裁剪（auto 模式，非方形图）
   ↓
[3] LANCZOS 缩放到 grid_w × grid_h
   ↓
[4] 每格 RGB → Lab → CIEDE2000 找 Mard 221 最近色
   ↓
[5] 背景检测：连通到图边的"白块" = 背景（标 None）
   ↓
[6] max_colors 二次聚类（如果指定了 N）
   ↓
[7] 渲染 pattern.png + 写 grid.json + 写 bom.csv
```

---

## 📊 性能

- 100×100 图纸：~0.5 秒（macOS M1）
- 200×200 图纸：~1.5 秒
- 主要瓶颈是 CIEDE2000 计算（用 skimage，已向量化）
- 100×100 = 10000 格 × 221 色 = 220 万次 ΔE 距离

---

## 🤝 作为 Claude Skill 使用

本工具同时是一个 [Claude Code](https://docs.claude.com/en/docs/claude-code) skill —— 装在 `~/.claude/skills/pinbead-local/` 后，对 Claude 说：

- "帮我把这张图做成拼豆"
- "把 photo.jpg 转成 60x60 拼豆图"
- "我要做拼豆图纸"
- "用 Mard 色卡"

Claude 就会自动调用本工具。

---

## 📜 License

MIT
