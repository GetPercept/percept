import SwiftUI

@main
struct PerceptCompanionApp: App {
    @StateObject private var audioRelay = AudioRelayService()
    
    var body: some Scene {
        WindowGroup {
            CompanionView()
                .environmentObject(audioRelay)
                .onAppear {
                    WatchConnectivityManager.shared.activate()
                    audioRelay.start()
                }
        }
    }
}
