# WebHarvest

轻量化的 macOS 桌面工具(Apple Silicon only),按用户输入的网址抓取该域名下所有页面的图片、视频与 PDF,自动按类型分类下载到指定目录。

## 项目结构

```
.
├── Package.swift              SwiftPM 入口(替代 xcodeproj)
├── .github/workflows/         CI / Release 工作流
│   ├── ci.yml                 每次 push 跑测试 + build
│   └── release.yml            push tag 自动打 .dmg
├── SwiftApp/                  SwiftUI 源码
│   ├── Sources/               13 个 .swift 文件,每个 ≤ 200 行
│   └── Resources/Info.plist
├── PythonCore/                Python 异步爬虫
│   ├── webharvest/
│   │   ├── protocol.py        JSON 行协议
│   │   ├── cli.py             stdio 命令分发
│   │   ├── crawler/           BFS 爬虫 + URL 队列
│   │   ├── downloader/        流式下载 + 文件名清洗
│   │   └── config.py          扩展名 / 文件夹映射
│   ├── tests/                 smoke test(已通过)
│   └── pyproject.toml
├── build/                     本地构建脚本
│   ├── dev.sh                 开发循环(venv + tests + swift build + run)
│   └── release.sh             一键打 .dmg
├── DESIGN_BRIEF.md            设计说明(给人看)
├── DESIGN_TOKENS.json         设计数据(给 AI)
├── IMPLEMENTATION_BRIEF.md    实施 spec
├── TECH_DECISIONS.md          技术决策
├── BUILD.md                   详细构建说明
└── README.md                  (this file)
```

## 快速开始

### 路径 1:用 GitHub Actions 拿 .dmg(推荐,本机啥都不用装)

```bash
# 在 GitHub 上创建一个空仓库(网页操作,10 秒)
# 然后:

git init
git add . && git commit -m "v0.1.0"
git remote add origin git@github.com:YOUR_NAME/webharvest.git
git push -u origin main
git tag v0.1.0 && git push origin v0.1.0

# 5-8 分钟后,打开 github.com/YOUR_NAME/webharvest/actions
# 下载 "WebHarvest-arm64-dmg" artifact → 双击挂载 → 拖入 Applications
```

### 路径 2:本机构建(需要 ~700MB Command Line Tools)

```bash
xcode-select --install              # 一次性
brew install create-dmg              # 一次性
./build/release.sh                   # → dist/WebHarvest-0.1.0-arm64.dmg
```

### 路径 3:开发循环(改代码 → 跑)

```bash
./build/dev.sh
# 1. 创建 venv
# 2. 跑 smoke tests
# 3. swift build
# 4. 启动 app
```

### 路径 4:只跑 Python 端(没 Mac 也能验证)

```bash
cd PythonCore
python3 -m venv .venv && source .venv/bin/activate
pip install -e .
pytest tests/ -v
# 1 passed in ~1s
```

## 架构

```
┌────────────────────────────────────┐
│ SwiftUI 主程序 (Apple Silicon)     │
│  - AppState (@Observable)          │
│  - Views: TitleBar / TabBar / Card │
│  - CrawlerProcess: Process + stdio │
└────────────────┬───────────────────┘
                 │ stdin/stdout JSON 行协议
                 ↓
┌────────────────────────────────────┐
│ Python 子进程 (嵌入 arm64 PBS)     │
│  - webharvest.cli  分发命令        │
│  - crawler.spider  BFS + selectolax│
│  - downloader      流式下载        │
└────────────────────────────────────┘
```

## 技术决策

- **Apple Silicon 独占**:不兼容 Intel,体积减半
- **macOS 14+**:`@Observable` 宏需要 Swift 5.9
- **SwiftUI + AppKit**(仅 NSOpenPanel):不引第三方依赖
- **httpx + selectolax + tldextract**:轻量异步 HTTP + 快速 HTML 解析
- **python-build-standalone**:嵌入 Python 运行时,用户无需装 Python
- **JSON 行协议**:零依赖、易调试
- **SwiftPM** 替代 xcodeproj:命令行就能编,CI 友好

详细见 [TECH_DECISIONS.md](./TECH_DECISIONS.md) / [BUILD.md](./BUILD.md)。

## 状态

- [x] 设计稿(可编辑 Ardot)
- [x] 设计交付(4 份文档)
- [x] SwiftUI 完整骨架(13 文件)
- [x] Python 爬虫核心 + smoke test 通过 ✅
- [x] **SwiftPM 化**(无需 Xcode 工程)
- [x] **GitHub Actions 自动化**(.dmg 远程构建)
- [x] **本地一键打 .dmg**(`./build/release.sh`)
- [x] **零摩擦自用部署**(`xattr -cr` 替代 codesign,无 Gatekeeper 提示,无需 Apple 开发者账号)
- [ ] 在真 Mac 上跑(目前未在 Apple Silicon 设备上跑过)
- [ ] **如要分发出去:** Developer ID 签名 + 公证($99/年 Apple Developer 账号,**自用不需要**)
