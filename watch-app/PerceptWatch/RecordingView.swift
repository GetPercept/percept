import SwiftUI
import WatchKit

/// Main Watch UI: single button with two modes
/// - Quick tap: toggle recording on/off
/// - Long hold: walkie-talkie (record while holding, send on release)
struct RecordingView: View {
    #if targetEnvironment(simulator)
    @StateObject private var recorder = MockAudioRecorder()
    #else
    @StateObject private var recorder = AudioRecorder()
    #endif
    
    @State private var showSent = false
    @State private var isLongPressing = false
    @State private var pressStart: Date?
    @State private var isWalkieMode = false  // true when long press detected
    
    private let longPressThreshold: TimeInterval = 0.4  // seconds to trigger walkie mode
    
    var body: some View {
        VStack(spacing: 8) {
            Text("Percept")
                .font(.headline)
                .foregroundColor(.white.opacity(0.7))
            
            #if targetEnvironment(simulator)
            Text("SIMULATOR")
                .font(.caption2)
                .foregroundColor(.yellow.opacity(0.6))
            #endif
            
            WaveformView(audioLevel: recorder.audioLevel, isRecording: recorder.isRecording)
                .opacity(recorder.isRecording ? 1 : 0.3)
                .frame(height: 25)
            
            // Single button — tap or hold
            ZStack {
                Circle()
                    .fill(recorder.isRecording ? Color.red : Color.blue)
                    .frame(width: 85, height: 85)
                
                if recorder.isRecording {
                    Circle()
                        .stroke(Color.red.opacity(0.4), lineWidth: 4)
                        .frame(width: 85, height: 85)
                        .scaleEffect(1.3)
                        .opacity(0)
                        .animation(
                            .easeOut(duration: 1.2).repeatForever(autoreverses: false),
                            value: recorder.isRecording
                        )
                }
                
                VStack(spacing: 2) {
                    Image(systemName: recorder.isRecording ? "stop.fill" : "mic.fill")
                        .font(.system(size: 28))
                        .foregroundColor(.white)
                }
            }
            .scaleEffect(isLongPressing ? 0.92 : 1.0)
            .animation(.easeInOut(duration: 0.1), value: isLongPressing)
            .gesture(
                DragGesture(minimumDistance: 0)
                    .onChanged { _ in
                        guard !isLongPressing else { return }
                        isLongPressing = true
                        pressStart = Date()
                        
                        // After threshold, start walkie-talkie mode
                        DispatchQueue.main.asyncAfter(deadline: .now() + longPressThreshold) {
                            guard isLongPressing, let start = pressStart,
                                  Date().timeIntervalSince(start) >= longPressThreshold else { return }
                            isWalkieMode = true
                            if !recorder.isRecording {
                                recorder.startRecording()
                            }
                        }
                    }
                    .onEnded { _ in
                        let wasLongPress = isWalkieMode
                        let pressDuration = pressStart.map { Date().timeIntervalSince($0) } ?? 0
                        
                        isLongPressing = false
                        pressStart = nil
                        
                        if wasLongPress {
                            // Walkie-talkie: release = stop & send
                            isWalkieMode = false
                            stopAndSend()
                        } else if pressDuration < longPressThreshold {
                            // Quick tap: toggle
                            if recorder.isRecording {
                                stopAndSend()
                            } else {
                                showSent = false
                                recorder.startRecording()
                            }
                        }
                    }
            )
            
            if showSent {
                Text("✓ Sent to Jarvis")
                    .font(.caption2)
                    .foregroundColor(.green)
            } else if recorder.isRecording {
                Text(isWalkieMode ? "Release to send" : "Tap to stop")
                    .font(.caption2)
                    .foregroundColor(.white.opacity(0.5))
            } else {
                Text("Tap or hold")
                    .font(.caption2)
                    .foregroundColor(.white.opacity(0.5))
            }
        }
        .animation(.easeInOut(duration: 0.2), value: recorder.isRecording)
        .animation(.easeInOut(duration: 0.3), value: showSent)
        #if !targetEnvironment(simulator)
        .onAppear {
            WatchConnectivityManager.shared.activate()
        }
        #endif
    }
    
    private func stopAndSend() {
        recorder.stopRecording()
        showSent = true
        DispatchQueue.main.asyncAfter(deadline: .now() + 2) {
            showSent = false
        }
    }
}

#Preview {
    RecordingView()
}
