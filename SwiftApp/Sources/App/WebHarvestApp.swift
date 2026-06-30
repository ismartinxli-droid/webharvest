import SwiftUI

@main
struct WebHarvestApp: App {
    @State private var state = AppState()

    var body: some Scene {
        WindowGroup("WebHarvest") {
            ContentView()
                .environment(state)
                .frame(width: 960, height: 680)
        }
        .windowStyle(.hiddenTitleBar)
        .windowResizability(.contentSize)
        .commands {
            CommandGroup(replacing: .newItem) {}
        }
    }
}
