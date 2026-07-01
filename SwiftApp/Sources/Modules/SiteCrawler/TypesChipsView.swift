import SwiftUI

struct TypesChipsView: View {
    @Environment(AppState.self) private var state

    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            Text("文件类型")
                .font(.system(size: 13, weight: .semibold))
                .foregroundStyle(Color.textPrimary)

            HStack(spacing: 10) {
                ForEach(FileType.allCases) { ft in
                    TypeChip(ft: ft)
                }
            }

            HStack(spacing: 10) {
                Text("抓取深度")
                    .font(.system(size: 13, weight: .semibold))
                    .foregroundStyle(Color.textPrimary)
                Spacer()
                HStack(spacing: 0) {
                    ForEach(1...3, id: \.self) { depth in
                        DepthButton(depth: depth)
                    }
                }
                Text("级")
                    .font(.system(size: 13))
                    .foregroundStyle(Color.textSecondary)
            }
            Text("1=当前页 · 2=包含子页面 · 3=包含子页面的子页面")
                .font(.system(size: 11))
                .foregroundStyle(Color.textSecondary)
        }
    }
}

struct TypeChip: View {
    @Environment(AppState.self) private var state
    let ft: FileType
    var isSelected: Bool { state.fileTypes.contains(ft) }

    var body: some View {
        Button(action: {
            if isSelected { state.fileTypes.remove(ft) }
            else { state.fileTypes.insert(ft) }
        }) {
            HStack(spacing: 8) {
                ZStack {
                    RoundedRectangle(cornerRadius: 5)
                        .fill(isSelected ? Color.brand : Color.backgroundInput)
                        .overlay(
                            RoundedRectangle(cornerRadius: 5)
                                .stroke(isSelected ? Color.brand : Color.borderDefault, lineWidth: 1)
                        )
                    if isSelected {
                        Image(systemName: "checkmark")
                            .font(.system(size: 11, weight: .bold))
                            .foregroundStyle(.white)
                    }
                }
                .frame(width: 18, height: 18)

                Image(systemName: ft.icon)
                    .font(.system(size: 16))
                    .foregroundStyle(isSelected ? Color.brand : Color.textTertiary)

                Text(ft.label)
                    .font(.system(size: 14, weight: isSelected ? .semibold : .medium))
                    .foregroundStyle(isSelected ? Color.brand : Color.textSecondary)
            }
            .padding(.horizontal, 14)
            .frame(height: 40)
            .background(
                RoundedRectangle(cornerRadius: 10)
                    .fill(isSelected ? Color.brand.opacity(0.06) : Color.backgroundInput)
                    .overlay(
                        RoundedRectangle(cornerRadius: 10)
                            .stroke(isSelected ? Color.brand.opacity(0.25) : Color.borderDefault, lineWidth: 1)
                    )
            )
        }
        .buttonStyle(.plain)
    }
}

struct DepthButton: View {
    @Environment(AppState.self) private var state
    let depth: Int
    var isSelected: Bool { state.maxDepth == depth }

    var body: some View {
        Button(action: { state.maxDepth = depth }) {
            Text("\(depth)")
                .font(.system(size: 13, weight: isSelected ? .bold : .medium))
                .foregroundStyle(isSelected ? .white : Color.textSecondary)
                .frame(width: 28, height: 28)
                .background(
                    Rectangle()
                        .fill(isSelected ? Color.brand : Color.clear)
                )
        }
        .buttonStyle(.plain)
    }
}
