import Foundation
import os.log

/// Bridge to the embedded Python subprocess. Communicates over stdin/stdout with newline-delimited JSON.
final class CrawlerProcess {
    private var process: Process?
    private var stdin: FileHandle?
    private var stdout: FileHandle?
    private let log = Logger(subsystem: "cn.webharvest.app", category: "CrawlerProcess")

    var onEvent: ((CrawlerEvent) -> Void)?

    func start(config: CrawlConfig) {
        stop()
        let proc = Process()
        proc.executableURL = Self.pythonURL()
        proc.arguments = ["-m", "webharvest"]

        let stdinPipe = Pipe()
        let stdoutPipe = Pipe()
        let stderrPipe = Pipe()
        proc.standardInput = stdinPipe
        proc.standardOutput = stdoutPipe
        proc.standardError = stderrPipe

        proc.terminationHandler = { [weak self] p in
            self?.log.info("Python exited with status \(p.terminationStatus)")
            if p.terminationReason != .exit {
                self?.onEvent?(.error("Python 子进程异常退出"))
            }
        }

        do {
            try proc.run()
        } catch {
            onEvent?(.error("启动 Python 失败: \(error.localizedDescription)"))
            return
        }

        self.process = proc
        self.stdin = stdinPipe.fileHandleForWriting
        self.stdout = stdoutPipe.fileHandleForReading

        readLoop(handle: stdoutPipe.fileHandleForReading)
        drainStderr(stderrPipe.fileHandleForReading)
        send(.start(config: config))
    }

    func stop() {
        send(.stop)
        process?.terminate()
        process = nil
        stdin = nil
        stdout = nil
    }

    // MARK: - Internal

    private enum Command: Codable {
        case start(config: CrawlConfig)
        case stop
        case ping
    }

    private func send(_ cmd: Command) {
        guard let stdin else { return }
        do {
            let data = try JSONEncoder().encode(cmd) + Data("\n".utf8)
            try stdin.write(contentsOf: data)
        } catch {
            log.error("send failed: \(error.localizedDescription)")
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
                }
            }
        }
    }

    private func drainStderr(_ handle: FileHandle) {
        handle.readabilityHandler = { [weak self] fh in
            let data = fh.availableData
            guard let s = String(data: data, encoding: .utf8), !s.isEmpty else { return }
            self?.log.error("python stderr: \(s, privacy: .public)")
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
            return .done((obj["downloaded"] as? Int ?? 0, obj["failed"] as? Int ?? 0))
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
        return URL(fileURLWithPath: bundlePath)
            .appending(path: "Contents/Resources/python/bin/python3")
    }
}
