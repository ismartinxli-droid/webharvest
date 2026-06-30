import SwiftUI

struct TitleBarView: View {
    @Environment(AppState.self) private var state

    var body: some View {
        ZStack {
            HStack {
                Spacer()
            }
            Text("WebHarvest")
                .font(.system(size: 13, weight: .semibold))
                .foregroundStyle(Color.textPrimary)
        }
        .padding(.horizontal, 20)
        .frame(height: 52)
        .background(Color.backgroundCard)
        .overlay(alignment: .bottom) {
            Rectangle().fill(Color.borderSubtle).frame(height: 1)
        }
    }
}
