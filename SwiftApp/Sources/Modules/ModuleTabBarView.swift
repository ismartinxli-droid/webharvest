import SwiftUI

struct ModuleTabBarView: View {
    @Environment(AppState.self) private var state

    var body: some View {
        HStack {
            HStack(spacing: 4) {
                ForEach(Module.allCases, id: \.self) { module in
                    TabPill(module: module, isActive: state.selectedModule == module) {
                        if module.isEnabled {
                            state.selectedModule = module
                        }
                    }
                }
            }
            Spacer()
            HStack(spacing: 8) {
                Image(systemName: "sparkles").font(.system(size: 11)).foregroundStyle(.tertiary)
                Text("v0.1 · 单模块预览").font(.caption2).foregroundStyle(.tertiary)
            }
        }
        .padding(.horizontal, 24)
        .frame(height: 48)
        .background(Color.backgroundCard)
        .overlay(alignment: .bottom) {
            Rectangle().fill(Color.borderSubtle).frame(height: 1)
        }
    }
}

struct TabPill: View {
    let module: Module
    let isActive: Bool
    let action: () -> Void

    var body: some View {
        Button(action: action) {
            HStack(spacing: 6) {
                Image(systemName: module.icon)
                    .font(.system(size: 12, weight: .semibold))
                Text(module.label)
                    .font(.system(size: 13, weight: isActive ? .semibold : .medium))
                if !module.isEnabled {
                    Text("即将上线")
                        .font(.system(size: 10, weight: .medium))
                        .foregroundStyle(.tertiary)
                }
                if isActive {
                    Circle().fill(Color.accentSuccess).frame(width: 6, height: 6)
                }
            }
            .padding(.horizontal, 14)
            .padding(.vertical, 8)
            .background(
                RoundedRectangle(cornerRadius: 8)
                    .fill(isActive ? Color.tabActiveFill : .clear)
            )
            .foregroundStyle(isActive ? Color.textActive : (module.isEnabled ? Color.textPrimary : Color.textDisabled))
        }
        .buttonStyle(.plain)
        .disabled(!module.isEnabled)
        .help(module.isEnabled ? module.label : "即将上线")
    }
}
