import SwiftUI

struct ContentView: View {
    var body: some View {
        VStack(spacing: 0) {
            TitleBarView()
            Divider().opacity(0)
            SiteCrawlerView()
        }
        .background(Color.backgroundPage)
    }
}