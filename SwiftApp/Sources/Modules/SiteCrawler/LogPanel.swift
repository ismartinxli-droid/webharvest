import SwiftUI

struct LogPanel: View {
    @Environment(AppState.self) private var state

    var body: some View {
        VStack(alignment: .leading, spacing: 6) {
            HStack {
                Text("实时日志").font(.system(size: 12, weight: .semibold)).foregroundStyle(Color.textSecondary)
                Spacer()
                if let cur = state.currentFile {
                    Text(cur).font(.system(size: 12)).foregroundStyle(Color.textTertiary)
                }
            }
            ScrollViewReader { proxy in
                ScrollView {
                    LazyVStack(alignment: .leading, spacing: 4) {
                        ForEach(state.log) { entry in
                            HStack(alignment: .top, spacing: 8) {
                                Text(entry.icon)
                                    .font(.system(size: 11, design: .monospaced))
                                    .foregroundStyle(color(entry.color))
                                Text(entry.text)
                                    .font(.system(size: 12, design: .monospaced))
                                    .foregroundStyle(Color.textPrimary)
                            }
                            .id(entry.id)
                        }
                    }
                    .padding(12)
                }
                .frame(height: 120)
                .background(
                    RoundedRectangle(cornerRadius: 10)
                        .fill(Color.backgroundInput)
                        .overlay(
                            RoundedRectangle(cornerRadius: 10)
                                .stroke(Color.borderSubtle, lineWidth: 1)
                        )
                )
                .onChange(of: state.log.count) {
                    if let last = state.log.last {
                        withAnimation { proxy.scrollTo(last.id, anchor: .bottom) }
                    }
                }
            }
        }
        .frame(width: 640)
    }

    private func color(_ name: String) -> Color {
        switch name {
        case "success": .accentSuccess
        case "danger": .accentDanger
        default: Color.textTertiary
        }
    }
}
