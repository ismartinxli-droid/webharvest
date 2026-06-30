# WebHarvest — macOS 桌面资源下载器 · 设计交付说明

> 一款基于 macOS 的轻量化桌面工具,根据用户输入的网址,自动爬取并按类型分类下载该域名下所有图片、视频与 PDF 文件。

---

## 1. 设计文件入口

- **设计文件链接**: https://ardot.tencent.com/file/698748626179724
- **设计文件名称**: WebHarvest - 站点资源下载器
- **主屏幕节点 ID**: `2:1` (App Window, 960 × 680)

## 2. 视觉语言

| 项 | 值 |
|---|---|
| 主色(品牌紫) | `#5046E5` |
| 文本主色 | `#1A1A2E` (近黑,非纯黑) |
| 文本次色 | `#6B6B8A` |
| 文本弱化 | `#9498AB` |
| 页面背景 | `#F9F9FB` (warm gray) |
| 卡片背景 | `#FFFFFF` |
| 描边(默认) | `#E7E7EA` / `#D8DCE8` |
| 输入框背景 | `#F9FAFE` |
| 品牌主色轻填充 | `#F2F2FE` |
| 卡片圆角 | 16px(主卡片) / 10px(输入) / 100px(状态 chip) |
| 阴影 | `0 1px 2px rgba(15,20,25,0.04)` + `0 4px 16px rgba(15,20,25,0.06)` |
| 字体 | Inter (Regular / Medium / SemiBold / Bold) |

参考风格:**Bento Attio Flat Modern + Notion Warm Inter**,浅色双层画布,12–16px 圆角,超轻阴影,三色信号面板(紫主色 + 绿进度 + 琥珀警示)。

## 3. 布局结构(自顶向下)

```
App Window (960 × 680, fill #F9F9FB)
├── Title Bar (52px, fill #FFFFFF, 1px hairline bottom)
│   ├── Traffic Lights(红 / 黄 / 绿,12px 圆点)
│   ├── App Title "WebHarvest"  (Inter SemiBold 13)
│   └── Right Spacer (占位以平衡中央标题)
│
├── Module Tab Bar (48px, fill #FFFFFF, 1px hairline bottom, space-between)
│   ├── Tab Group (gap 4, hug contents)
│   │   ├── Tab 站点资源抓取  ←  激活态(紫色填充 #F2F2FE + 紫色文字 + 紫色下载图标 + 绿色状态点)
│   │   ├── Tab 批量重命名    ←  灰显(浅灰图标 + 灰色文字 + "即将上线"小角标)
│   │   ├── Tab 资源整理      ←  灰显(浅灰图标 + 灰色文字 + "即将上线"小角标)
│   │   └── Tab 设置          ←  灰显(浅灰齿轮图标 + 灰色文字)
│   └── Tab Bar Meta (右侧信息)
│       ├── Sparkle Icon(14px,装饰)
│       └── Meta Text "v0.1 · 单模块预览"
│
└── Body (padding 20/48, vertical, gap 20)
    ├── Hero Block (560 × hug, gap 8, bottom-padding 32)
    │   ├── Brand Mark (logo icon 36px 圆角 + "WebHarvest" 20px Bold)
    │   ├── Hero Title  "抓取整站资源,一步到位"  (Inter Bold 32, center)
    │   └── Hero Subtitle  解释文本 (Inter Regular 14, #6B6B8A, center)
    │
    └── Input Card (640 × hug, white, radius 16, shadow, padding 28×32, gap 24)
        ├── URL Field
        │   ├── Label  "目标网址"  (13 SemiBold)
        │   └── URL Input (48px, radius 10, fill #F9FAFE, link icon + 占位文本 + 紫色光标)
        │
        ├── Types Field
        │   ├── Label  "文件类型"
        │   └── Chips Row (10px gap)
        │       ├── Image Chip  (紫色边框 + 紫色对勾 + 紫色文字 "图片")  ← 勾选
        │       ├── Video Chip  (紫色边框 + 紫色对勾 + 紫色文字 "视频")  ← 勾选
        │       └── PDF Chip    (灰色边框 + 空对勾 + 灰色文字 "PDF")    ← 未勾选
        │
        ├── Save Path Field
        │   ├── Label  "存储目录"
        │   └── Picker Row (8px gap)
        │       ├── Path Display (folder icon + "~/Downloads/WebHarvest", flex grow)
        │       └── Browse Button  "更改"
        │
        ├── Divider (1px 水平线)
        │
        └── Action Row (space-between)
            ├── Hint Block (lock icon + "仅下载该域名下公开可访问的资源")
            └── Button Group (10px gap)
                ├── Stop Button  (白底 + 黑边框 + 实心方块 icon + "停止")
                └── Start Button (紫色填充 + 投影 + 下载 icon + "开始下载")
```

## 4. 关键交互状态

| 状态 | 视觉 |
|---|---|
| URL Input 焦点 | 紫色描边 1.5px + 紫色 2px 闪烁光标 |
| Chip 勾选 | 紫色边框 + 紫色对勾 box + 紫色文字 + #F2F2FE 填充 |
| Chip 未勾选 | 灰色边框 + 空 box + 灰色文字 + #FFFFFF 填充 |
| Browse Button 悬停 | 边框由 `#D8DCE8` 加深为 `#5046E5` 30% |
| Start Button 默认 | 紫色填充 + 紫色 25% 软阴影 |
| Start Button 悬停 | 阴影半径 16→20 + 微微下沉 |
| Stop Button 悬停 | 描边由 `#D8DCE8` 加深为 `#1A1A2E` |
| 任务进行中 | Start 按钮变为禁用灰,Stop 按钮变红边框 + 红色文字 "停止" |

## 5. 节点索引速查

| ID | 名称 |
|---|---|
| `2:1` | App Window(主屏幕根) |
| `2:2` | Title Bar |
| `2:3` | Traffic Lights |
| `2:7` | App Title 文本 |
| `2:77` | **Module Tab Bar(新增)** |
| `2:78` | **Tab 站点资源抓取(激活态,新增)** |
| `2:82` | **Active Dot 状态点(新增)** |
| `2:83` | **Tab 批量重命名(灰显,新增)** |
| `2:87` | **Soon Badge 文本(新增)** |
| `2:88` | **Tab 资源整理(灰显,新增)** |
| `2:93` | **Tab 设置(灰显,新增)** |
| `2:98` | **Tab Bar Meta(右侧元信息,新增)** |
| `2:9` | Body |
| `2:10` | Hero Block |
| `2:12` | Logo Icon (SVG) |
| `2:17` | Brand Name 文本 |
| `2:18` | Hero Title 文本 |
| `2:19` | Hero Subtitle 文本 |
| `2:20` | Input Card |
| `2:23` | URL Input |
| `2:24` | Link Icon (SVG) |
| `2:26` | Input Placeholder 文本 |
| `2:27` | Caret(紫色光标) |
| `2:31` | Image Chip |
| `2:39` | Video Chip |
| `2:46` | PDF Chip |
| `2:55` | Path Display |
| `2:58` | Path Text |
| `2:59` | Browse Button |
| `2:61` | Divider |
| `2:69` | Stop Button |
| `2:73` | Start Button |

## 6. 给后续 AI 的开发建议

### 技术栈推荐
- **桌面壳**: Swift + SwiftUI(macOS 14+,原生体验)
- **爬虫核心**: Python 3.11+ `httpx`(异步) + `selectolax` 或 `lxml`(HTML 解析)
- **进程间通信**: XPC Service(Swift 主进程调用 Python 助手)或子进程 + stdin/stdout JSON
- **打包分发**: `py2app` 或 `PyInstaller` 单文件 DMG

### 拆分文件结构
```
WebHarvest/
├── App/
│   ├── WebHarvestApp.swift          # @main 入口,定义 WindowGroup
│   ├── Views/
│   │   ├── ContentView.swift        # 对应 2:1
│   │   ├── TitleBarView.swift       # 对应 2:2
│   │   ├── HeroBlockView.swift      # 对应 2:10
│   │   ├── InputCardView.swift      # 对应 2:20
│   │   ├── URLFieldView.swift       # 对应 2:21
│   │   ├── TypesChipsView.swift     # 对应 2:28
│   │   ├── SavePathFieldView.swift  # 对应 2:52
│   │   └── ActionRowView.swift      # 对应 2:62
│   ├── Models/
│   │   ├── DownloadTask.swift
│   │   ├── FileType.swift           # enum: image / video / pdf
│   │   └── AppState.swift           # @Observable,持有 URL/类型/目录/状态
│   └── Resources/
│       └── Colors.xcassets          # 按本文 §2 复制色板
├── Crawler/                          # Python 助手
│   ├── harvest.py                   # 主入口
│   ├── parsers/
│   │   ├── html_parser.py           # 从同一域名下提取链接
│   │   └── asset_extractor.py       # 按类型筛选资源 URL
│   ├── downloader.py                # 异步下载 + 进度回报
│   └── filters/
│       ├── same_domain.py
│       └── dedupe.py                # 用 URL hash 去重
└── bridge/
    └── ipc.py                       # JSON over stdin/stdout
```

### 关键交互逻辑
- **URL 校验**: 用户输入后,App 端用 URLComponents 做基础校验,只接受 http/https;失焦时即时提示。
- **范围控制**: 爬虫只跟随 `<a href>` 中 `urlparse(link).netloc == urlparse(target).netloc` 的链接,避免外链。
- **类型判断**:
  - 图片:扩展名 in `{jpg, jpeg, png, gif, webp, bmp, svg, tiff, avif}` 或 `<img>` `src`
  - 视频:扩展名 in `{mp4, mov, webm, mkv, avi, m4v}` 或 `<video>` `src` / `<source>`
  - PDF:扩展名 = `pdf` 或 `Content-Type: application/pdf`
- **目录结构**: 用户目录 / `images/`、`videos/`、`pdfs/` 三个子文件夹分别存放。
- **去重**: 用 URL 的 SHA-1 摘要做 set 去重。
- **进度回报**: Python 每下载完一个文件就 stdout 一行 JSON,Swift 端实时更新底部状态条(可在后续屏幕实现,本次设计稿为初始主屏)。
- **停止机制**: Swift 端点击"停止"时,向 Python 子进程发送 SIGINT,Python 端 `asyncio.Task` 捕获后停止新的下载,但当前文件下载完为止。

### 状态机建议
```
idle → validating → fetching → crawling → downloading ⇄ stopping → completed
                              ↓
                            error(failed URL 列表可点击重试)
```

### 后续可扩展屏幕(本次未做)
1. 下载进度屏幕(实时进度条、当前文件、已用流量)
2. 历史记录屏幕
3. 设置屏幕(并发数、超时、UA、cookie)
4. 错误重试面板
5. **批量重命名模块(占位 Tab 对应)**
6. **资源整理模块(占位 Tab 对应)**

---

设计稿以 Bento 风格构建,主屏幕聚焦"输入 → 确认"的核心动作。剩余屏幕建议沿用相同色板、阴影规范、圆角与字体梯度,以保持系统一致性。
