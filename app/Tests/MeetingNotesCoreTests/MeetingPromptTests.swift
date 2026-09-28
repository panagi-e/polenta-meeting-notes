import CoreGraphics
import Foundation
import Testing

@testable import MeetingNotesCore

/// Where the meeting pop-up sits, and whether it shows at all.
struct MeetingPromptTests {
    @Test("the pop-up sits in the top-right of the usable screen area")
    func test_top_right() {
        // A 1512x982 screen with a 33pt menu bar and no Dock at the bottom:
        // AppKit's origin is bottom-left, so the top edge is maxY.
        let visible = CGRect(x: 0, y: 0, width: 1512, height: 949)
        let origin = PromptPlacement.topRightOrigin(
            size: CGSize(width: 360, height: 130), visibleFrame: visible)
        #expect(origin == CGPoint(x: 1512 - 360 - 12, y: 949 - 130 - 12))
    }

    @Test("a second screen to the left places the pop-up on that screen")
    func test_offset_screen() {
        let visible = CGRect(x: -1920, y: 0, width: 1920, height: 1055)
        let origin = PromptPlacement.topRightOrigin(
            size: CGSize(width: 360, height: 130), visibleFrame: visible, margin: 16)
        #expect(origin == CGPoint(x: -1920 + 1920 - 360 - 16, y: 1055 - 130 - 16))
    }

    @Test("the pop-up is on unless it has been turned off")
    func test_preference_default() throws {
        let defaults = try #require(UserDefaults(suiteName: "MeetingPromptTests-\(UUID())"))
        #expect(MeetingPromptPreference.isEnabled(defaults))

        defaults.set(false, forKey: MeetingPromptPreference.enabledKey)
        #expect(!MeetingPromptPreference.isEnabled(defaults))

        defaults.set(true, forKey: MeetingPromptPreference.enabledKey)
        #expect(MeetingPromptPreference.isEnabled(defaults))
    }
}
