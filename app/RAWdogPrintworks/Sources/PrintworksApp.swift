import SwiftUI
import PrintworksCore

@main
struct PrintworksApp: App {
    var body: some Scene {
        WindowGroup {
            Text("RAWdog Printworks")
                .frame(minWidth: 900, minHeight: 600)
                .background(Theme.windowBase)
                .preferredColorScheme(.dark)
        }
    }
}
