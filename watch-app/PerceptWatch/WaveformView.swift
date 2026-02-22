import SwiftUI

/// Animated waveform visualization shown during recording
struct WaveformView: View {
    let audioLevel: Float
    let isRecording: Bool
    
    @State private var phase: Double = 0
    
    private let barCount = 7
    
    var body: some View {
        HStack(spacing: 3) {
            ForEach(0..<barCount, id: \.self) { i in
                RoundedRectangle(cornerRadius: 2)
                    .fill(Color.red.opacity(isRecording ? 0.9 : 0.3))
                    .frame(width: 4, height: barHeight(for: i))
                    .animation(
                        .easeInOut(duration: 0.15)
                            .delay(Double(i) * 0.03),
                        value: audioLevel
                    )
            }
        }
        .frame(height: 30)
        .onAppear {
            withAnimation(.linear(duration: 2).repeatForever(autoreverses: false)) {
                phase = .pi * 2
            }
        }
    }
    
    private func barHeight(for index: Int) -> CGFloat {
        guard isRecording else { return 4 }
        let normalized = CGFloat(audioLevel)
        let position = Double(index) / Double(barCount - 1)
        let wave = (sin(position * .pi * 2 + phase) + 1) / 2
        let height = 4 + normalized * 26 * wave
        return max(4, height)
    }
}
