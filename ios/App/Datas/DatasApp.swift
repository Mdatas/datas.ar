import SwiftUI

/// Datas for iPhone and iPad: link to your own computers and use their Datas from here.
/// It runs no AI on the phone; the computer does the thinking, over an encrypted link.
@main
struct DatasApp: App {
    @StateObject private var store = Store()

    var body: some Scene {
        WindowGroup {
            ComputersView()
                .environmentObject(store)
        }
    }
}
