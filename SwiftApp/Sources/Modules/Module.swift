import SwiftUI

enum Module: String, CaseIterable, Hashable {
    case siteCrawler
    case batchRename
    case organize
    case settings

    var label: String {
        switch self {
        case .siteCrawler: "站点资源抓取"
        case .batchRename: "批量重命名"
        case .organize: "资源整理"
        case .settings: "设置"
        }
    }

    var icon: String {
        switch self {
        case .siteCrawler: "arrow.down.to.line"
        case .batchRename: "arrow.triangle.2.circlepath"
        case .organize: "square.grid.2x2"
        case .settings: "gearshape"
        }
    }

    var isEnabled: Bool {
        self == .siteCrawler
    }
}
