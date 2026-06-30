import SwiftUI

struct TitleBarView: View {
    @Environment(AppState.self) private var state

    var body: some View {
        ZStack {
            HStack {
                TrafficLights()
                Spacer()
            }
            Text("WebHarvest")
                .font(.system(size: 13, weight: .semibold))
                .foregroundStyle(Color.textPrimary)
        }
        .padding(.horizontal, 20)
        .frame(height: 52)
        .background(.backgroundCard)
        .overlay(alignment: .bottom) {
            Rectangle().fill(Color.borderSubtle).frame(height: 1)
        }
    }
}

struct TrafficLights: View {
    var body: some View {
        HStack(spacing: 8) {
            Circle().fill(Color(red: 1, green: 0.37, blue: 0.40)).frame(width: 12, height: 12)
            Circle().fill(Color(red: 1, green: 0.73, blue: 0.25)).frame(width: 12, height: 12)
            Circle().fill(Color(red: 0.31, green: 0.78, blue: 0.35)).frame(width: 12, height: 12)
        }
    }
}
