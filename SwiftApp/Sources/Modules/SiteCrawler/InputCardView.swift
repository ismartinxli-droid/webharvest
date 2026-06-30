import SwiftUI

struct InputCardView: View {
    @Environment(AppState.self) private var state

    var body: some View {
        VStack(alignment: .leading, spacing: 20) {
            URLFieldView()
            TypesChipsView()
            SavePathFieldView()
            Divider().background(Color.borderSubtle)
            ActionRowView()
        }
        .padding(24)
        .frame(width: 640)
        .background(
            RoundedRectangle(cornerRadius: 16)
                .fill(Color.backgroundCard)
                .shadow(color: .black.opacity(0.04), radius: 16, x: 0, y: 4)
                .shadow(color: .black.opacity(0.04), radius: 2, x: 0, y: 1)
        )
        .overlay(
            RoundedRectangle(cornerRadius: 16)
                .stroke(Color.borderSubtle, lineWidth: 1)
        )
    }
}
