import SwiftUI

struct ActionRowView: View {
    @Environment(AppState.self) private var state

    var body: some View {
        HStack {
            HStack(spacing: 6) {
                Image(systemName: "lock")
                    .font(.system(size: 12))
                    .foregroundStyle(Color.textTertiary)
                Text("仅下载该域名下公开可访问的资源")
                    .font(.system(size: 12))
                    .foregroundStyle(Color.textTertiary)
            }
            Spacer()
            HStack(spacing: 10) {
                StopButton()
                StartButton()
            }
        }
    }
}

struct StopButton: View {
    @Environment(AppState.self) private var state
    var isRunning: Bool { state.progress.phase == .running }

    var body: some View {
        Button(action: state.stop) {
            HStack(spacing: 6) {
                RoundedRectangle(cornerRadius: 2).fill(isRunning ? Color.accentDanger : Color.textPrimary)
                    .frame(width: 10, height: 10)
                Text("停止")
                    .font(.system(size: 14, weight: .semibold))
                    .foregroundStyle(isRunning ? Color.accentDanger : Color.textPrimary)
            }
            .padding(.horizontal, 18)
            .frame(height: 44)
            .background(
                RoundedRectangle(cornerRadius: 10)
                    .fill(Color.backgroundCard)
                    .overlay(
                        RoundedRectangle(cornerRadius: 10)
                            .stroke(isRunning ? Color.accentDanger : Color.borderDefault, lineWidth: 1)
                    )
            )
        }
        .buttonStyle(.plain)
        .disabled(!isRunning)
    }
}

struct StartButton: View {
    @Environment(AppState.self) private var state
    var isRunning: Bool { state.progress.phase == .running }

    var body: some View {
        Button(action: state.start) {
            HStack(spacing: 8) {
                Image(systemName: "arrow.down.to.line")
                    .font(.system(size: 14, weight: .semibold))
                Text(isRunning ? "下载中…" : "开始下载")
                    .font(.system(size: 14, weight: .semibold))
            }
            .padding(.horizontal, 22)
            .frame(height: 44)
            .foregroundStyle(.white)
            .background(
                RoundedRectangle(cornerRadius: 10)
                    .fill(isRunning || !state.canStart ? Color.borderStrong : Color.brand)
                    .shadow(color: isRunning ? .clear : Color.brand.opacity(0.25), radius: 12, x: 0, y: 4)
            )
        }
        .buttonStyle(.plain)
        .disabled(!state.canStart)
    }
}
