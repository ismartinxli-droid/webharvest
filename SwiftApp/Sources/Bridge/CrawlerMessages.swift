import Foundation

struct CrawlConfig: Codable {
    let url: String
    let types: Set<FileType>
    let savePath: URL
}

struct CrawlSummary {
    let downloaded: Int
    let failed: Int
}

enum CrawlerEvent {
    case ready
    case phase(String)
    case pagesCrawled(Int)
    case assetQueued(FileType, String)
    case assetDownloaded(FileType, URL, Int)
    case assetFailed(FileType, String, String)
    case done(CrawlSummary)
    case error(String)
}
