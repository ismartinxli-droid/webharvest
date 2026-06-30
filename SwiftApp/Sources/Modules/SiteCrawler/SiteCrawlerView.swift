import SwiftUI

struct SiteCrawlerView: View {
    @Environment(AppState.self) private var state

    var body: some View {
        VStack(spacing: 16) {
            HeroBlockView()
            InputCardView()
            Spacer(minLength: 0)
            StatusBar()
        }
        .padding(.horizontal, 48)
        .padding(.top, 20)
        .padding(.bottom, 8)
        .frame(maxWidth: .infinity, maxHeight: .infinity)
    }
}

struct HeroBlockView: View {
    var body: some View {
        VStack(spacing: 8) {
            HStack(spacing: 10) {
                RoundedRectangle(cornerRadius: 10)
                    .fill(Color.brand)
                    .overlay(
                        Image(systemName: "arrow.down.to.line")
                            .font(.system(size: 16, weight: .bold))
                            .foregroundStyle(.white)
                    )
                    .frame(width: 36, height: 36)
                Text("WebHarvest")
                    .font(.system(size: 20, weight: .bold))
                    .foregroundStyle(Color.textPrimary)
            }
            Text("抓取整站资源,一步到位")
                .font(.system(size: 32, weight: .bold))
                .foregroundStyle(Color.textPrimary)
            Text("输入网址,选择文件类型,即可批量下载该域名下的所有图片、视频与 PDF。")
                .font(.system(size: 14))
                .foregroundStyle(Color.textSecondary)
                .multilineTextAlignment(.center)
        }
        .padding(.bottom, 8)
    }
}

/// Tiny bottom-of-window status strip. Shows live activity + counts.
struct StatusBar: View {
    @Environment(AppState.self) private var state

    var body: some View {
        HStack(spacing: 12) {
            Circle()
                .fill(dotColor)
                .frame(width: 6, height: 6)
            Text(state.statusMessage)
                .font(.system(size: 11, design: .monospaced))
                .foregroundStyle(Color.textTertiary)
                .lineLimit(1)
                .truncationMode(.middle)
            Spacer()
            if state.downloadedCount > 0 || state.failedCount > 0 {
                Text("已下载 \(state.downloadedCount)")
                    .font(.system(size: 11, design: .monospaced))
                    .foregroundStyle(Color.accentSuccess)
                if state.failedCount > 0 {
                    Text("· 失败 \(state.failedCount)")
                        .font(.system(size: 11, design: .monospaced))
                        .foregroundStyle(Color.accentDanger)
                }
            }
        }
        .frame(maxWidth: .infinity)
    }

    private var dotColor: Color {
        switch state.progress.phase {
        case .running: .accentSuccess
        case .notRunning: Color.borderStrong
        }
    }
}
