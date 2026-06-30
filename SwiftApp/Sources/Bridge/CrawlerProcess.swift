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

    func start(config: CrawlConfig) {
        stop()

        // Surface early feedback immediately
        onEvent?(.phase("正在启动 Python 子进程..."))

        let proc = Process()
        proc.executableURL = Self.pythonURL()
        proc.arguments = ["-m", "webharvest"]

        // Set PYTHONPATH so embedded Python finds webharvest + deps
        // NB: do NOT set PYTHONHOME — PBS is self-contained and PYTHONHOME breaks its internal paths
        var env = ProcessInfo.processInfo.environment
        let bundlePath = Bundle.main.bundlePath
        let sitePackages = bundlePath
            .appending("/Contents/Resources/python/site-packages")
        let existing = env["PYTHONPATH"] ?? ""
        env["PYTHONPATH"] = "\(sitePackages):\(existing)"
        proc.environment = env

        let stdinPipe = Pipe()
        let stdoutPipe = Pipe()
        let stderrPipe = Pipe()
        proc.standardInput = stdinPipe
        proc.standardOutput = stdoutPipe
        proc.standardError = stderrPipe

        proc.terminationHandler = { [weak self] p in
            self?.log.info("Python exited with status \(p.terminationStatus)")
            if p.terminationStatus != 0 {
                // Capture stderr on crash
                if let stderr = self?.stderr {
                    let data = stderr.fileHandleForReading.readDataToEndOfFile()
                    if let msg = String(data: data, encoding: .utf8), !msg.isEmpty {
                        self?.log.error("python stderr: \(msg, privacy: .public)")
                        self?.onEvent?(.error("Python 崩溃: \(msg.prefix(200))"))
                    } else {
                        self?.onEvent?(.error("Python 子进程异常退出 (status=\(p.terminationStatus))"))
                    }
                }
            }
        }

        do {
            try proc.run()
            log.info("Python process launched at \(Self.pythonURL().path)")
        } catch {
            onEvent?(.error("启动 Python 失败: \(error.localizedDescription)"))
            return
        }

        self.process = proc
        self.stdin = stdinPipe
        self.stdout = stdoutPipe
        self.stderr = stderrPipe

        // Forward stderr lines as error events so the user can see Python tracebacks
        stderrPipe.fileHandleForReading.readabilityHandler = { [weak self] fh in
            let data = fh.availableData
            guard let s = String(data: data, encoding: .utf8), !s.isEmpty else { return }
            for line in s.split(separator: "\n") {
                let trimmed = line.trimmingCharacters(in: .whitespaces)
                if trimmed.isEmpty { continue }
                self?.log.error("python stderr: \(trimmed, privacy: .public)")
                // Surface to UI — but throttle by not flooding
                if trimmed.count < 300 {
                    self?.onEvent?(.error(trimmed))
                }
            }
        }

        readLoop(handle: stdoutPipe.fileHandleForReading)
        send(.start(config: config))
        log.info("Crawler started: \(config.url)")
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
            buffer.append(chunk)
            while let nl = buffer.firstIndex(of: 0x0A) {
                let line = buffer.prefix(upTo: nl)
                buffer = buffer.suffix(from: buffer.index(after: nl))
                if let event = Self.decode(Data(line)) {
                    self?.onEvent?(event)
                } else if let text = String(data: Data(line), encoding: .utf8) {
                    self?.log.info("unparsed stdout: \(text)")
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
        return URL(fileURLWithPath: bundlePath)
            .appending(path: "Contents/Resources/python/bin/python3.11")
    }
}
