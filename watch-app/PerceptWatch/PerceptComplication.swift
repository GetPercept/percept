import SwiftUI
import WidgetKit
import ClockKit

/// Watch face complication — tap to launch app and start recording
struct PerceptComplicationProvider: TimelineProvider {
    func placeholder(in context: Context) -> PerceptEntry {
        PerceptEntry(date: Date())
    }
    
    func getSnapshot(in context: Context, completion: @escaping (PerceptEntry) -> Void) {
        completion(PerceptEntry(date: Date()))
    }
    
    func getTimeline(in context: Context, completion: @escaping (Timeline<PerceptEntry>) -> Void) {
        let entry = PerceptEntry(date: Date())
        let timeline = Timeline(entries: [entry], policy: .never)
        completion(timeline)
    }
}

struct PerceptEntry: TimelineEntry {
    let date: Date
}

struct PerceptComplicationView: View {
    var body: some View {
        ZStack {
            Circle()
                .fill(Color.red.opacity(0.2))
            Image(systemName: "mic.fill")
                .font(.system(size: 16))
                .foregroundColor(.red)
        }
    }
}

/// WidgetKit-based complication for watchOS 9+
// NOTE: To use, add a Widget extension target in Xcode and register this widget.
// This is the complication view — tapping it launches the app.
//
// @main
// struct PerceptWidget: Widget {
//     let kind = "PerceptComplication"
//     var body: some WidgetConfiguration {
//         StaticConfiguration(kind: kind, provider: PerceptComplicationProvider()) { entry in
//             PerceptComplicationView()
//         }
//         .configurationDisplayName("Percept")
//         .description("Tap to talk to Jarvis")
//         .supportedFamilies([.accessoryCircular, .accessoryCorner])
//     }
// }
