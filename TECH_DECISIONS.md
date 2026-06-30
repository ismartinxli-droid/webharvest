# 技术决策记录(Tech Decisions)

> 写代码前先拍板,避免边写边返工。

## 1. 平台策略

| 决策 | 值 | 理由 |
|---|---|---|
| 最低 macOS 版本 | **14.0 (Sonoma)** | `@Observable`、新 `NavigationSplitView`、Swift 5.9+ 宏 |
| CPU 架构 | **arm64 only**(Apple Silicon) | 用户明确不需要 Intel 兼容;省 50% 体积、零兼容代码 |
| 通用二进制 | **NO** | 不打 `lipo --create`;只出 `arm64-apple-macos14.0` |
| 最低 Swift 工具链 | Swift 5.9 / Xcode 15+ | `@Observable` 需要 Swift 5.9 编译器 |

## 2. 打包与分发

| 决策 | 值 | 理由 |
|---|---|---|
| 目标格式 | **`.app` Bundle → `.dmg`** | 用户要求 |
| Bundle ID | `cn.webharvest.app` | 反向域名,占位待定 |
| 签名 | **ad-hoc**(self-use 已足够;分发时再升级到 Developer ID) | 用户明确只自用,无需公证 / Apple Developer 账号 |
| Python 运行时 | **python-build-standalone**(嵌入 Bundle) | 用户无需装 Python;不污染系统环境 |
| Python 架构 | **arm64-apple-darwin** | 与主程序一致 |
| Python 入口调用方式 | 直接执行嵌入二进制 + 子进程 stdio | 比写 `.command` shim 简单 |

## 3. 进程架构

```
WebHarvest.app/
├── Contents/
│   ├── MacOS/WebHarvest                  # SwiftUI 主程序 (Mach-O arm64)
│   ├── Resources/
│   │   ├── python/
│   │   │   └── python-arm64              # 嵌入的 Python 3.11 解释器
│   │   ├── site-packages/                # httpx / selectolax / tldextract
│   │   └── webharvest/                   # Python 包源码
│   │       ├── __init__.py
│   │       ├── __main__.py
│   │       ├── cli.py
│   │       ├── crawler/
│   │       ├── extractors/
│   │       └── downloader/
│   ├── Info.plist
│   └── PkgInfo
```

**IPC**:`Swift` 用 `Process` 启动 `Contents/Resources/python/python-arm64 -m webharvest`,stdin/stdout JSON 行协议,一行一事件。

## 4. 关键库选型

| 库 | 版本 | 用途 |
|---|---|---|
| **SwiftUI** | 系统 | UI |
| **Combine** | 系统 | 事件流到 UI 绑定(`@Observable` 已够用,不强制用 Combine) |
| **AppKit**(NSOpenPanel) | 系统 | 目录选择器 |
| **Python 3.11** | pbs 20231002 | 嵌入 |
| **httpx** | ≥0.25 | 异步 HTTP 客户端 |
| **selectolax** | ≥0.3.7 | HTML 解析(比 BeautifulSoup 快 10×,依赖少) |
| **tldextract** | ≥5.1 | 同域 / 跨域判定 |
| **任何持久化库** | 无 | v0.1 不写历史记录,不引依赖 |

**禁止使用的库**:
- `requests` — 同步阻塞,换 httpx
- `BeautifulSoup` — 重,换 selectolax
- `scrapy` — 太重,v0.1 写一个 BFS 即可
- `PyInstaller` — 嵌入 PBS 即可,不需要
- 任何同步文件 IO 库 — 全部 `aiofiles` 或 `asyncio.to_thread`

## 5. 简约风格执行准则

写代码时遵守:

1. **每个文件 ≤ 200 行**;超了就拆
2. **不写 typealias / protocol 抽象层**直到有第二个实现
3. **不写单元测试**针对 v0.1,只写一个 `tests/smoke.py` 端到端验证
4. **不写 CLI 标志**,Swift 端传 JSON dict 给 Python
5. **不写 backward-compat 代码**,`@available(macOS 14.0, *)` 直接用
6. **不写 docstring** 给私有函数,只给 public API 写
7. **不用 force unwrap(`!`)**,除非是 xib/asset 路径常量
8. **不用 `try!`**,全部显式处理错误
9. **不写 README** 给 Python 子模块,只写一份根 README
10. **不引第三方 Swift 库**;SwiftUI + Foundation + AppKit 已够

## 6. 暂不做(明确砍掉)

- ❌ 历史记录
- ❌ 设置面板
- ❌ 多语言(中英切换)
- ❌ 暗色模式
- ❌ 自动更新
- ❌ Crash 上报
- ❌ 通知中心进度通知
- ❌ 拖拽 URL 到 Dock 图标
- ❌ 快捷键
- ❌ iCloud 同步

## 7. 未来需要时再加

- 多模块(Tab 2/3/4)真实功能
- 重试失败的下载
- 进度详情屏幕
- 命令行模式(直接 `webharvest <url>`)
