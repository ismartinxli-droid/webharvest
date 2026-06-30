import SwiftUI

struct URLFieldView: View {
    @Environment(AppState.self) private var state
    @FocusState private var focused: Bool

    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            Text("目标网址")
                .font(.system(size: 13, weight: .semibold))
                .foregroundStyle(Color.textPrimary)
            HStack(spacing: 12) {
                Image(systemName: "link")
                    .font(.system(size: 14))
                    .foregroundStyle(Color.textSecondary)
                    .frame(width: 18)
                TextField("https://example.com", text: bindURL())
                    .textFieldStyle(.plain)
                    .font(.system(size: 15))
                    .focused($focused)
                if focused {
                    Rectangle().fill(Color.brand).frame(width: 2, height: 20)
                }
            }
            .padding(.horizontal, 14)
            .frame(height: 48)
            .background(
                RoundedRectangle(cornerRadius: 10)
                    .fill(Color.backgroundInput)
                    .overlay(
                        RoundedRectangle(cornerRadius: 10)
                            .stroke(focused ? Color.brand : Color.borderDefault, lineWidth: focused ? 1.5 : 1)
                    )
            )
        }
    }

    private func bindURL() -> Binding<String> {
        Binding(get: { state.url }, set: { state.url = $0 })
    }
}
