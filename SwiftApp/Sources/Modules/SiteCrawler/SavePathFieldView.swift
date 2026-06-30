import SwiftUI

struct SavePathFieldView: View {
    @Environment(AppState.self) private var state

    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            Text("存储目录")
                .font(.system(size: 13, weight: .semibold))
                .foregroundStyle(Color.textPrimary)
            HStack(spacing: 8) {
                HStack(spacing: 12) {
                    Image(systemName: "folder")
                        .font(.system(size: 14))
                        .foregroundStyle(Color.textSecondary)
                        .frame(width: 18)
                    Text(state.savePath.path)
                        .font(.system(size: 14, weight: .medium))
                        .foregroundStyle(Color.textPrimary)
                        .lineLimit(1)
                        .truncationMode(.middle)
                    Spacer()
                }
                .padding(.horizontal, 14)
                .frame(height: 48)
                .background(
                    RoundedRectangle(cornerRadius: 10)
                        .fill(Color.backgroundInput)
                        .overlay(
                            RoundedRectangle(cornerRadius: 10)
                                .stroke(Color.borderDefault, lineWidth: 1)
                        )
                )

                Button("更改", action: state.selectSavePath)
                    .font(.system(size: 13, weight: .semibold))
                    .foregroundStyle(Color.textPrimary)
                    .frame(width: 80, height: 48)
                    .background(
                        RoundedRectangle(cornerRadius: 10)
                            .fill(Color.backgroundInput)
                            .overlay(
                                RoundedRectangle(cornerRadius: 10)
                                    .stroke(Color.borderDefault, lineWidth: 1)
                            )
                    )
                    .buttonStyle(.plain)
            }
        }
    }
}
