import SwiftUI

struct ContentView: View {
    @Environment(AppState.self) private var state

    var body: some View {
        VStack(spacing: 0) {
            TitleBarView()
            ModuleTabBarView()
            Divider().opacity(0)
            ModuleRouterView()
        }
        .background(Color.backgroundPage)
    }
}

struct ModuleRouterView: View {
    @Environment(AppState.self) private var state

    var body: some View {
        switch state.selectedModule {
        case .siteCrawler: SiteCrawlerView()
        case .batchRename: PlaceholderView(title: "批量重命名", subtitle: "将在后续版本上线")
        case .organize: PlaceholderView(title: "资源整理", subtitle: "将在后续版本上线")
        case .settings: PlaceholderView(title: "设置", subtitle: "将在后续版本上线")
        }
    }
}

extension AppState {
    @MainActor
    var selectedModuleBinding: Binding<Module> {
        Binding(get: { self.selectedModule }, set: { self.selectedModule = $0 })
    }
}

struct PlaceholderView: View {
    let title: String
    let subtitle: String
    var body: some View {
        VStack(spacing: 8) {
            Image(systemName: "wrench.and.screwdriver")
                .font(.system(size: 40))
                .foregroundStyle(.secondary)
            Text(title).font(.title2.bold())
            Text(subtitle).font(.callout).foregroundStyle(.secondary)
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity)
    }
}
