import SwiftUI

@main
struct UniverseControlCenterApp: App {
    var body: some Scene {
        WindowGroup {
            ContentView()
        }
        #if os(macOS)
        .defaultSize(width: 1480, height: 960)
        #endif
    }
}
