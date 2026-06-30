# WebHarvest — 站点资源抓取 · 实施交付包

> 给写代码的 AI 用的实施说明。把设计稿拆成可执行的模块、文件、接口。

## 0. 项目定位

macOS 桌面工具:用户输入一个网址,工具爬取该域名下所有页面,按类型分类下载图片 / 视频 / PDF 到用户指定目录。

未来会扩展为多模块工具(批量重命名、资源整理等),所以本次主屏是 **Tab 1**,需要为 Tab 系统预留扩展能力。

## 1. 技术选型建议

| 层 | 选型 | 理由 |
|---|---|---|
| 桌面壳 | **SwiftUI** (macOS 14+,Deployment target 13.0) | 原生,体积小,符合"轻量化"诉求 |
| 爬虫核心 | **Python 3.11+**,库:`httpx`(异步)、`selectolax`(HTML 解析)、`tldextract`(同域判断) | Swift 写爬虫太累,Python 生态成熟 |
| 进程通信 | **子进程 + stdio JSON 协议** | Swift `Process` 启动 `python3 -m webharvest`,Python 端逐行 stdout JSON 推送进度 |
| 打包 | Swift 主程序打 DMG;Python 端用 `python-build-standalone` 嵌入二进制 | 用户不需要额外装 Python |
| 图标 | SF Symbols(免费)或自绘 | 设计稿里已用纯 SVG,直接对应 SF Symbol 名即可 |

## 2. 目录结构

```
WebHarvest/
├── SwiftApp/                          # Xcode 项目
│   ├── WebHarvest.xcodeproj
│   ├── Sources/
│   │   ├── App/
│   │   │   ├── WebHarvestApp.swift    # @main,定义 WindowGroup
│   │   │   └── AppState.swift         # @Observable 单例,持有全局状态
│   │   ├── Modules/
│   │   │   ├── ModuleTab.swift        # 枚举当前选中的模块
│   │   │   ├── ModuleTabBar.swift     # 顶部 Tab Bar 视图
│   │   │   ├── SiteCrawler/           # Tab 1:站点资源抓取
│   │   │   │   ├── SiteCrawlerView.swift
│   │   │   │   ├── HeroBlockView.swift
│   │   │   │   ├── InputCardView.swift
│   │   │   │   ├── URLFieldView.swift
│   │   │   │   ├── TypesChipsView.swift
│   │   │   │   ├── SavePathFieldView.swift
│   │   │   │   └── ActionRowView.swift
│   │   │   ├── BatchRename/           # Tab 2:占位(灰显)
│   │   │   │   └── BatchRenameView.swift  // 显示"即将上线"
│   │   │   ├── ResourceOrganize/      # Tab 3:占位(灰显)
│   │   │   │   └── ResourceOrganizeView.swift
│   │   │   └── Settings/              # Tab 4:占位
│   │   │       └── SettingsView.swift
│   │   ├── Components/                # 可复用基础组件
│   │   │   ├── PrimaryButton.swift    # 紫色主按钮
│   │   │   ├── SecondaryButton.swift  // 白色描边按钮
│   │   │   ├── ChipToggle.swift       // 勾选胶囊
│   │   │   └── PathPicker.swift       // 目录选择器
│   │   ├── Bridge/
│   │   │   ├── CrawlerProcess.swift   # 启动 Python 子进程,stdin/stdout JSON
│   │   │   └── CrawlerMessages.swift  // Swift 侧的消息类型定义
│   │   └── Resources/
│   │       └── Assets.xcassets        # Color set / Image set 占位
│   ├── Tests/
│   │   └── ...
│   └── Info.plist
│
├── PythonCore/                        # Python 爬虫(随主程序打包)
│   ├── pyproject.toml
│   ├── webharvest/
│   │   ├── __init__.py
│   │   ├── __main__.py                # python -m webharvest 入口
│   │   ├── cli.py                     # 解析 stdin JSON 命令,stdout JSON 事件
│   │   ├── crawler/
│   │   │   ├── __init__.py
│   │   │   ├── spider.py              # 异步爬虫主循环
│   │   │   ├── url_frontier.py        # BFS 队列 + 同域过滤
│   │   │   └── dedupe.py              # URL hash 去重
│   │   ├── extractors/
│   │   │   ├── __init__.py
│   │   │   ├── images.py
│   │   │   ├── videos.py
│   │   │   └── pdfs.py
│   │   ├── downloader/
│   │   │   ├── __init__.py
│   │   │   ├── fetcher.py             # httpx 异步下载
│   │   │   └── progress.py            # 进度回报
│   │   └── config.py
│   └── tests/
│
├── shared/
│   ├── protocol.md                    # Swift ↔ Python IPC 协议说明
│   └── design-tokens.json             # 设计 token 机器可读版
│
├── DESIGN_BRIEF.md                    # 设计说明(本目录)
├── DESIGN_TOKENS.json                 # 机器友好的色板/字号/间距
└── README.md
```

## 3. SwiftUI 视图与设计节点对应表

打开 `DESIGN_TOKENS.json` 看完整色板。每个 View 都对应设计稿里的一个 frame。

| 设计稿节点 ID | SwiftUI View | 关键参数 |
|---|---|---|
| `2:1` | `SiteCrawlerView` (root) | 960×680,`Spacer()` 上下撑满 |
| `2:2` | `TitleBarView` | `.frame(height: 52)`,白底 + 底部 1px hairline |
| `2:3` | `TrafficLights` | 3 个 12×12 圆点,SF Symbol `circle.fill` 红/黄/绿 |
| `2:7` | `Text("WebHarvest")` | Inter SemiBold 13,色 `#1A1A2E` |
| `2:77` | `ModuleTabBar` | 48 高,白底,`HStack(spacing: 4)` + 1px 底分割线 |
| `2:78` | `TabItem(label: "站点资源抓取", state: .active, icon: "arrow.down.to.line")` | 紫色胶囊 `#F2F2FE`,紫色文字 |
| `2:83` | `TabItem(label: "批量重命名", state: .disabled, icon: "arrow.triangle.2.circlepath", badge: "即将上线")` | 灰显,`.disabled(true)` |
| `2:88` | `TabItem(label: "资源整理", state: .disabled, icon: "square.grid.2x2", badge: "即将上线")` | 灰显 |
| `2:93` | `TabItem(label: "设置", state: .disabled, icon: "gearshape")` | 灰显 |
| `2:98` | `TabBarMeta` | 右对齐,Sparkle + 版本号 |
| `2:10` | `HeroBlockView` | `VStack(spacing: 8)`,下方 padding 20 |
| `2:12` | `BrandLogo` | 36×36 圆角 10,SVG 内嵌 |
| `2:17` | `Text("WebHarvest").font(.title2.bold())` | Inter Bold 20 |
| `2:18` | `Text("抓取整站资源,一步到位")` | Inter Bold 32,`#1A1A2E`,center |
| `2:19` | `Text("输入网址…")` | Inter Regular 14,`#6B6B8A`,center |
| `2:20` | `InputCardView` | 640 宽,白底,radius 16,双层阴影 |
| `2:23` | `URLFieldView` | 48 高,radius 10,`#F9FAFE` 底 |
| `2:31` | `ChipToggle(label: "图片", icon: "photo", state: .on)` | 紫色态 |
| `2:39` | `ChipToggle(label: "视频", icon: "video", state: .on)` | 紫色态 |
| `2:46` | `ChipToggle(label: "PDF", icon: "doc.richtext", state: .off)` | 灰态 |
| `2:55` | `PathDisplay(path: "~/Downloads/WebHarvest")` | flex 填充 |
| `2:59` | `SecondaryButton("更改")` | 描边按钮,触发 `NSOpenPanel` |
| `2:61` | `Divider()` | 1px 水平线,色 `#E7E7EA` |
| `2:69` | `StopButton` | 白色描边,运行中变红边 |
| `2:73` | `PrimaryButton("开始下载")` | 紫色填充,`#5046E5` |

## 4. 业务逻辑流程

### 4.1 用户在 SwiftUI 端做的事

```swift
@Observable
class AppState {
    var url: String = ""                       // URLFieldView 双向绑定
    var fileTypes: Set<FileType> = [.image, .video]
    var savePath: URL = URL(fileURLWithPath: NSString("~/Downloads/WebHarvest").expandingTildeInPath)
    var isRunning: Bool = false
    var progress: Progress = .idle
    
    var canStart: Bool { 
        !url.isEmpty && !fileTypes.isEmpty && !isRunning 
    }
}

enum FileType: String, CaseIterable, Codable {
    case image, video, pdf
    var icon: String { /* SF Symbol name */ }
    var displayName: String { /* 显示名 */ }
    var folderName: String { /* "images" / "videos" / "pdfs" */ }
    var extensions: Set<String> { /* 扩展名集合 */ }
}
```

### 4.2 点击"开始下载"时

```swift
func startDownload() {
    guard canStart else { return }
    isRunning = true
    progress = .crawling
    
    let config = CrawlConfig(
        url: url,
        types: fileTypes,
        savePath: savePath
    )
    crawlerProcess.start(config: config) { [weak self] event in
        Task { @MainActor in
            self?.handle(event: event)
        }
    }
}

func stopDownload() {
    crawlerProcess.stop()   // 发送 stop 命令,Python 端优雅退出当前文件
    isRunning = false
    progress = .idle
}
```

### 4.3 Python 端收到 `start` 命令后的工作

1. `urlparse(target).netloc` 拿到基准域名
2. 启动 BFS 队列,加入 target 自身
3. 异步抓取每个页面 → 解析 HTML → 提取 `<a href>` 中同域链接入队 + 提取 `<img>` / `<video>` / `Content-Type: application/pdf` 链接入资产队列
4. 资产去重(SHA-1 of URL)后,按类型分发到 `{savePath}/images/` / `videos/` / `pdfs/` 子目录
5. 实时 stdout JSON:
   ```json
   {"event": "progress.crawling", "pages_crawled": 42, "queue_size": 18}
   {"event": "asset.found", "type": "image", "url": "https://…/cat.jpg"}
   {"event": "asset.downloaded", "type": "image", "path": "~/Downloads/WebHarvest/images/cat.jpg", "size": 234567}
   {"event": "asset.failed", "type": "video", "url": "https://…/clip.mp4", "error": "timeout"}
   {"event": "done", "summary": {"pages": 42, "downloaded": 87, "failed": 2}}
   ```

## 5. IPC 协议(写在 `shared/protocol.md`)

### Swift → Python(每行一条 JSON,以 `\n` 结束)

```json
{"cmd": "start", "url": "https://example.com", "types": ["image","video"], "save_path": "/Users/foo/Downloads/WebHarvest"}
{"cmd": "stop"}
{"cmd": "ping"}
```

### Python → Swift(每行一条 JSON,以 `\n` 结束)

```json
{"event": "ready"}
{"event": "progress.crawling", "pages_crawled": 42}
{"event": "asset.downloaded", "type": "image", "path": "...", "size": 234567}
{"event": "asset.failed", "type": "video", "url": "...", "error": "..."}
{"event": "done", "summary": {"downloaded": 87, "failed": 2}}
{"event": "error", "message": "invalid url"}
```

## 6. 状态机

```
idle
  └─ 点击"开始下载" → validating
                         └─ URL 不合法 → idle (Toast: 网址格式不正确)
                         └─ 合法 → fetching(拉取首页)
                                     └─ 失败 → error
                                     └─ 成功 → crawling(广度优先爬取)
                                                  └─ 每下载一个文件 → downloading(实时进度)
                                                  └─ 点击"停止" → stopping(完成当前文件后停)
                                                  └─ 队列空 → completed
                                                              └─ 5s 后 → idle
```

## 7. 验收标准(M3 / 衡量做没做对)

- [ ] 启动 App,看到顶部 4 个 Tab,只有"站点资源抓取"可点击
- [ ] 输入 `https://example.com`,勾选"图片"和"视频",选好保存目录
- [ ] 点击"开始下载",按钮变灰,"停止"按钮变红
- [ ] 进度条(后续屏幕)/状态条(底部)实时更新
- [ ] 下载完成后,保存目录下出现 `images/` 和 `videos/` 两个子目录,文件已分类
- [ ] 跨页面链接被正确跟随(同域名判定)
- [ ] 外站链接不被下载
- [ ] 点击"停止"后,当前文件下载完即停,不会启动新文件
- [ ] 程序崩溃 / 网络异常时,SwiftUI 端 Toast 提示,不白屏

## 8. 设计 token 引用

具体色值、字号、圆角、阴影、间距 → 打开 `DESIGN_TOKENS.json`。SwiftUI 端在 `Assets.xcassets` 中按 token 名字建 Color set,Python 端不需要关心样式。

## 9. 后续路线(本次不做,留位)

- 进度详情屏幕(实时文件列表 + 暂停 / 继续 / 重试)
- 历史记录 + 收藏
- 设置(并发数、超时、UA、Cookie、代理)
- 批量重命名模块(Tab 2)
- 资源整理模块(Tab 3)

设计稿与本说明严格对齐,任何不一致以本说明为准。
