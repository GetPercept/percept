#!/bin/bash
# Generate Xcode project for Percept Watch
# Requires: Xcode 15+, xcodegen (brew install xcodegen)
#
# Usage: ./setup-xcode.sh

set -e

if ! command -v xcodegen &>/dev/null; then
    echo "Installing xcodegen..."
    brew install xcodegen
fi

echo "Generating Xcode project..."
xcodegen generate

echo ""
echo "✅ PerceptWatch.xcodeproj generated!"
echo ""
echo "Next steps:"
echo "  1. open PerceptWatch.xcodeproj"
echo "  2. Select your Apple Developer team in Signing & Capabilities"
echo "  3. Set App Group: group.com.percept.watch on both targets"
echo "  4. Build & run on paired Apple Watch"
