import Foundation
import CoreMotion
import WatchKit

/// Detects wrist raise gesture to auto-trigger recording
/// Uses CMMotionManager to detect when watch face is oriented toward mouth
final class RaiseToSpeakDetector: ObservableObject, @unchecked Sendable {
    @Published var isRaised = false
    
    private let motionManager = CMMotionManager()
    private var isMonitoring = false
    
    var onRaiseDetected: (() -> Void)?
    var onLowerDetected: (() -> Void)?
    
    func startMonitoring() {
        guard motionManager.isDeviceMotionAvailable, !isMonitoring else { return }
        isMonitoring = true
        
        motionManager.deviceMotionUpdateInterval = 0.1
        motionManager.startDeviceMotionUpdates(to: .main) { [weak self] motion, _ in
            guard let motion, let self else { return }
            
            // Detect "talking into watch" pose:
            // - Watch face roughly vertical (gravity.z near 0)
            // - Wrist raised (gravity.x negative = face pointing up-ish)
            // - Tilted toward face (pitch in speaking range)
            let pitch = motion.attitude.pitch // radians
            let gravZ = motion.gravity.z
            
            let isInSpeakingPose = pitch > 0.5 && pitch < 1.3 && abs(gravZ) < 0.5
            
            if isInSpeakingPose && !self.isRaised {
                self.isRaised = true
                self.onRaiseDetected?()
            } else if !isInSpeakingPose && self.isRaised {
                self.isRaised = false
                self.onLowerDetected?()
            }
        }
    }
    
    func stopMonitoring() {
        motionManager.stopDeviceMotionUpdates()
        isMonitoring = false
        isRaised = false
    }
}
