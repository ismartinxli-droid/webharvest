import Foundation
import os.log

/// Bridge to the embedded Python subprocess. Communicates over stdin/stdout with newline-delimited JSON.
final class CrawlerProcess {
    private var process: Process?
    private var stdin: Pipe?
    private var stdout: Pipe?
    private var stderr: Pipe?
    private let log = Logger(subsystem: "cn.webharvest.app", category: "CrawlerProcess")
    private let queue = DispatchQueue(label: "crawler.bridge")

    var onEvent: ((CrawlerEvent) -> Void)?

    /// Write diagnostics to ~/Desktop/WebHarvest.log for troubleshooting
    private static let diagURL = URL(fileURLWithPath: "~/Desktop/WebHarvest.log").standardizedFileURL
    private static let diagEnabled: Bool = {
        ProcessInfo.processInfo.environment["WEBHARVEST_DIAG"] == "1"
    }()

    private static func diag(_ msg: String) {
        guard diagEnabled else { return }
        let line = "[\(Date().ISO8601Format())] \(msg)\n"
        guard let data = line.data(using: .utf8) else { return }
        if FileManager.default.fileExists(atPath: diagURL.path) {
            if var existing = try? Data(contentsOf: diagURL) {
                existing.append(data)
                try? existing.write(to: diagURL)
            }
        } else {
            try? data.write(to: diagURL)
        }
    }

    func start(config: CrawlConfig) {
        stop()

        Self.diag("=== start() called ===")
        Self.diag("url=\(config.url) types=\(config.types.map(\.rawValue)) path=\(config.savePath.path)")

        onEvent?(.phase("正在启动 Python 子进程..."))

        let pythonURL = Self.pythonURL()
        Self.diag("python path: \(pythonURL.path)")
        Self.diag("python exists: \(FileManager.default.fileExists(atPath: pythonURL.path))")

        let proc = Process()
        proc.executableURL = pythonURL
        proc.arguments = ["-m", "webharvest"]

        // Set PYTHONPATH so embedded Python finds webharvest + deps
        var env = ProcessInfo.processInfo.environment
        let bundlePath = Bundle.main.bundlePath
        let sitePackages = bundlePath
            .appending("/Contents/Resources/python/site-packages")
        let existing = env["PYTHONPATH"] ?? ""
        env["PYTHONPATH"] = "\(sitePackages):\(existing)"
        proc.environment = env

        Self.diag("PYTHONPATH=\(sitePackages)")
        Self.diag("webharvest dir exists: \(FileManager.default.fileExists(atPath: sitePackages + "/webharvest"))")

        let stdinPipe = Pipe()
        let stdoutPipe = Pipe()
        let stderrPipe = Pipe()
        proc.standardInput = stdinPipe
        proc.standardOutput = stdoutPipe
        proc.standardError = stderrPipe

        proc.terminationHandler = { [weak self] p in
            let status = p.terminationStatus
            Self.diag("Python exited: status=\(status)")
            self?.log.info("Python exited with status \(status)")
            if status != 0 {
                if let stderr = self?.stderr {
                    let data = stderr.fileHandleForReading.readDataToEndOfFile()
                    if let msg = String(data: data, encoding: .utf8), !msg.isEmpty {
                        Self.diag("Python stderr: \(msg)")
                        self?.log.error("python stderr: \(msg, privacy: .public)")
                        self?.onEvent?(.error("Python 崩溃: \(msg.prefix(200))"))
                    } else {
                        Self.diag("Python exit with no stderr")
                        self?.onEvent?(.error("Python 子进程异常退出 (status=\(status))"))
                    }
                }
            }
        }

        do {
            try proc.run()
            Self.diag("Python launched OK")
            log.info("Python process launched at \(Self.pythonURL().path)")
        } catch {
            Self.diag("proc.run() failed: \(error.localizedDescription)")
            onEvent?(.error("启动 Python 失败: \(error.localizedDescription)"))
            return
        }

        self.process = proc
        self.stdin = stdinPipe
        self.stdout = stdoutPipe
        self.stderr = stderrPipe

        // Forward stderr lines as error events
        stderrPipe.fileHandleForReading.readabilityHandler = { [weak self] fh in
            let data = fh.availableData
            guard let s = String(data: data, encoding: .utf8), !s.isEmpty else { return }
            for line in s.split(separator: "\n") {
                let trimmed = line.trimmingCharacters(in: .whitespaces)
                if trimmed.isEmpty { continue }
                Self.diag("stderr: \(trimmed)")
                self?.log.error("python stderr: \(trimmed, privacy: .public)")
                if trimmed.count < 300 {
                    self?.onEvent?(.error(trimmed))
                }
            }
        }

        readLoop(handle: stdoutPipe.fileHandleForReading)
        send(.start(config: config))
        log.info("Crawler started: \(config.url)")
        Self.diag("send start command")
    }

    func stop() {
        if let proc = process, proc.isRunning {
            send(.stop)
        }
        process?.terminate()
        process = nil
        stdin = nil
        stdout = nil
        stderr = nil
        Self.diag("stop() called")
    }

    // MARK: - Internal

    private enum Command {
        case start(config: CrawlConfig)
        case stop
        case ping

        func encode() throws -> Data {
            let dict: [String: Any]
            switch self {
            case .start(let config):
                dict = [
                    "cmd": "start",
                    "url": config.url,
                    "types": config.types.map { $0.rawValue },
                    "save_path": config.savePath.path,
                    "max_depth": config.maxDepth
                ]
            case .stop:
                dict = ["cmd": "stop"]
            case .ping:
                dict = ["cmd": "ping"]
            }
            return try JSONSerialization.data(withJSONObject: dict, options: [])
        }
    }

    private func send(_ cmd: Command) {
        guard let stdin = stdin else {
            log.error("send called but stdin is nil")
            return
        }
        do {
            let json = try cmd.encode()
            var payload = json
            payload.append(0x0A)
            guard let text = String(data: json, encoding: .utf8) else {
                log.error("Failed to convert JSON to string")
                return
            }
            log.info("→ stdin: \(text)")
            queue.async {
                do {
                    try stdin.fileHandleForWriting.write(contentsOf: payload)
                } catch {
                    Self.diag("stdin write error: \(error.localizedDescription)")
                    self.log.error("stdin write failed: \(error.localizedDescription)")
                    self.onEvent?(.error("stdin 写入失败"))
                }
            }
        } catch {
            log.error("JSON encode failed: \(error.localizedDescription)")
            onEvent?(.error("JSON 编码失败"))
        }
    }

    private func readLoop(handle: FileHandle) {
        var buffer = Data()
        handle.readabilityHandler = { [weak self] fh in
            let chunk = fh.availableData
            if chunk.isEmpty { return }
            Self.diag("stdout raw: \(chunk.count) bytes")
            buffer.append(chunk)
            while let nl = buffer.firstIndex(of: 0x0A) {
                let line = buffer.prefix(upTo: nl)
                buffer = buffer.suffix(from: buffer.index(after: nl))
                let lineData = Data(line)
                if let text = String(data: lineData, encoding: .utf8) {
                    Self.diag("stdout line: \(text.prefix(200))")
                }
                if let event = Self.decode(lineData) {
                    Self.diag("parsed event: \(event)")
                    self?.onEvent?(event)
                } else if let text = String(data: lineData, encoding: .utf8) {
                    self?.log.info("unparsed stdout: \(text)")
                    Self.diag("unparsed: \(text.prefix(200))")
                }
            }
        }
    }

    private static func decode(_ data: Data) -> CrawlerEvent? {
        guard let obj = try? JSONSerialization.jsonObject(with: data) as? [String: Any],
              let kind = obj["event"] as? String else { return nil }
        switch kind {
        case "ready":
            return .ready
        case "phase":
            return .phase(obj["name"] as? String ?? "")
        case "pages.crawled":
            return .pagesCrawled(obj["count"] as? Int ?? 0)
        case "asset.queued":
            guard let t = obj["type"] as? String, let u = obj["url"] as? String,
                  let ft = FileType(rawValue: t) else { return nil }
            return .assetQueued(ft, u)
        case "asset.downloaded":
            guard let t = obj["type"] as? String, let p = obj["path"] as? String,
                  let s = obj["size"] as? Int, let ft = FileType(rawValue: t) else { return nil }
            return .assetDownloaded(ft, URL(fileURLWithPath: p), s)
        case "asset.failed":
            guard let t = obj["type"] as? String, let u = obj["url"] as? String,
                  let e = obj["error"] as? String, let ft = FileType(rawValue: t) else { return nil }
            return .assetFailed(ft, u, e)
        case "done":
            return .done(CrawlSummary(downloaded: obj["downloaded"] as? Int ?? 0, failed: obj["failed"] as? Int ?? 0))
        case "error":
            return .error(obj["message"] as? String ?? "unknown")
        default:
            return nil
        }
    }

    private static func pythonURL() -> URL {
        if let envPath = ProcessInfo.processInfo.environment["WEBHARVEST_PYTHON"] {
            return URL(fileURLWithPath: envPath)
        }
        let bundlePath = Bundle.main.bundlePath
        // PBS ships python3.11, not python3
        let path = bundlePath + "/Contents/Resources/python/bin/python3.11"
        return URL(fileURLWithPath: path)
    }
}
