import SwiftUI

struct TypesChipsView: View {
    @Environment(AppState.self) private var state

    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            Text("文件类型")
                .font(.system(size: 13, weight: .semibold))
                .foregroundStyle(Color.textPrimary)
            HStack(spacing: 10) {
                ForEach(FileType.allCases, id: \.self) { type in
                    ChipToggle(type: type, isOn: state.fileTypes.contains(type)) {
                        if state.fileTypes.contains(type) {
                            state.fileTypes.remove(type)
                        } else {
                            state.fileTypes.insert(type)
                        }
                    }
                }
                Spacer()
            }
        }
    }
}

struct ChipToggle: View {
    let type: FileType
    let isOn: Bool
    let action: () -> Void

    var body: some View {
        Button(action: action) {
            HStack(spacing: 8) {
                ZStack {
                    RoundedRectangle(cornerRadius: 5)
                        .fill(isOn ? Color.brand : Color.backgroundCard)
                        .frame(width: 18, height: 18)
                        .overlay(
                            RoundedRectangle(cornerRadius: 5)
                                .stroke(isOn ? Color.brand : Color.borderStrong, lineWidth: isOn ? 0 : 1.5)
                        )
                    if isOn {
                        Image(systemName: "checkmark")
                            .font(.system(size: 11, weight: .bold))
                            .foregroundStyle(.white)
                    }
                }
                Image(systemName: type.icon)
                    .font(.system(size: 13))
                    .foregroundStyle(isOn ? Color.brand : Color.textSecondary)
                Text(type.label)
                    .font(.system(size: 14, weight: isOn ? .semibold : .medium))
                    .foregroundStyle(isOn ? Color.brand : Color.textSecondary)
            }
            .padding(.horizontal, 14)
            .frame(height: 40)
            .background(
                RoundedRectangle(cornerRadius: 10)
                    .fill(isOn ? Color.tabActiveFill : .clear)
                    .overlay(
                        RoundedRectangle(cornerRadius: 10)
                            .stroke(isOn ? Color.brand.opacity(0.25) : Color.borderDefault, lineWidth: 1)
                    )
            )
        }
        .buttonStyle(.plain)
    }
}
