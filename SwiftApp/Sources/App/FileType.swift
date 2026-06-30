import Foundation

enum FileType: String, CaseIterable, Codable, Hashable, Identifiable {
    case image, video, pdf, font

    var id: String { rawValue }

    var label: String {
        switch self {
        case .image: "图片"
        case .video: "视频"
        case .pdf: "PDF"
        case .font: "字体"
        }
    }

    var icon: String {
        switch self {
        case .image: "photo"
        case .video: "video"
        case .pdf: "doc.richtext"
        case .font: "textformat"
        }
    }

    var folderName: String {
        switch self {
        case .image: "images"
        case .video: "videos"
        case .pdf: "pdfs"
        case .font: "fonts"
        }
    }

    var extensions: Set<String> {
        switch self {
        case .image: ["jpg", "jpeg", "png", "gif", "webp", "bmp", "svg", "tiff", "avif", "heic"]
        case .video: ["mp4", "mov", "webm", "mkv", "avi", "m4v", "flv"]
        case .pdf: ["pdf"]
        case .font: ["ttf", "otf", "woff", "woff2", "eot"]
        }
    }
}
