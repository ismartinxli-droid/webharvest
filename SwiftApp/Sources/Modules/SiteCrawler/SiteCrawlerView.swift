import SwiftUI

struct SiteCrawlerView: View {
    @Environment(AppState.self) private var state

    var body: some View {
        VStack(spacing: 20) {
            HeroBlockView()
            InputCardView()
            if !state.log.isEmpty {
                LogPanel()
            }
        }
        .padding(.horizontal, 48)
        .padding(.vertical, 20)
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
        .padding(.bottom, 12)
    }
}
