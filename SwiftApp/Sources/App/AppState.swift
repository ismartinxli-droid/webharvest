import AppKit
import Foundation
import Observation

@Observable
final class AppState {
    var selectedModule: Module = .siteCrawler
    var url: String = ""
    var fileTypes: Set<FileType> = [.image, .video]
    var savePath: URL = URL(fileURLWithPath: NSString("~/Downloads/WebHarvest").expandingTildeInPath)
    var progress: Progress = .idle
    var log: [LogEntry] = []
    var currentFile: String?
    var downloadedCount: Int = 0
    var failedCount: Int = 0
    var lastError: String?

    private let crawler = CrawlerProcess()

    var canStart: Bool {
        !url.isEmpty && !fileTypes.isEmpty && progress.phase != .running
    }

    init() {
        crawler.onEvent = { [weak self] event in
            guard let self else { return }
            Task { @MainActor in self.handle(event: event) }
        }
    }

    func start() {
        guard canStart else { return }
        guard let parsed = URL(string: url), let scheme = parsed.scheme,
              scheme == "http" || scheme == "https", parsed.host != nil else {
            lastError = "请输入以 http:// 或 https:// 开头的网址"
            return
        }
        lastError = nil
        downloadedCount = 0
        failedCount = 0
        log = []
        progress = .running

        try? FileManager.default.createDirectory(at: savePath, withIntermediateDirectories: true)
        let config = CrawlConfig(url: url, types: fileTypes, savePath: savePath)
        crawler.start(config: config)
    }

    func stop() {
        crawler.stop()
        progress = .idle
        currentFile = nil
    }

    func selectSavePath() {
        let panel = NSOpenPanel()
        panel.canChooseFiles = false
        panel.canChooseDirectories = true
        panel.allowsMultipleSelection = false
        panel.directoryURL = savePath.deletingLastPathComponent()
        if panel.runModal() == .OK, let url = panel.url {
            savePath = url
        }
    }

    private func handle(event: CrawlerEvent) {
        switch event {
        case .ready:
            log.append(.info("Python 子进程已就绪"))
        case .phase(let phase):
            progress = .runningPhase(phase)
        case .pagesCrawled(let n):
            log.append(.info("已扫描 \(n) 个页面"))
        case .assetQueued(let type, let url):
            log.append(.info("发现 \(type.label): \(url)"))
        case .assetDownloaded(let type, let path, let size):
            downloadedCount += 1
            currentFile = path.lastPathComponent
            log.append(.ok("已下载 \(type.label) → \(path.lastPathComponent) (\(Self.formatBytes(size)))"))
        case .assetFailed(let type, let url, let reason):
            failedCount += 1
            log.append(.err("\(type.label) 下载失败: \(url) — \(reason)"))
        case .done(let summary):
            progress = .done(downloaded: summary.downloaded, failed: summary.failed)
            currentFile = nil
            log.append(.ok("完成。共下载 \(summary.downloaded) 个,失败 \(summary.failed) 个"))
        case .error(let message):
            progress = .error(message)
            lastError = message
            log.append(.err(message))
        }
    }

    private static func formatBytes(_ n: Int) -> String {
        let units = ["B", "KB", "MB", "GB"]
        var v = Double(n)
        var i = 0
        while v >= 1024 && i < units.count - 1 { v /= 1024; i += 1 }
        return String(format: "%.1f %@", v, units[i])
    }
}

enum Progress: Equatable {
    case idle
    case running
    case runningPhase(String)
    case done(downloaded: Int, failed: Int)
    case error(String)

    var phase: Phase {
        switch self {
        case .idle, .done, .error: return .notRunning
        case .running, .runningPhase: return .running
        }
    }

    enum Phase { case running, notRunning }
}

enum LogEntry: Identifiable {
    case info(String), ok(String), err(String)
    let id = UUID()
    var icon: String { switch self { case .info: return "○"; case .ok: return "✓"; case .err: return "✕" } }
    var text: String {
        switch self { case .info(let s), .ok(let s), .err(let s): return s }
    }
    var color: String {
        switch self {
        case .info: return "secondary"
        case .ok: return "success"
        case .err: return "danger"
        }
    }
}
