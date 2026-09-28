// Detection rules for section 2.2, app side. The backend's AC tests cover
// the same rules; these keep the Swift mirror honest.

import Foundation
import Testing
@testable import MeetingNotesCore

struct MeetingDetectionTests {
    @Test("a meeting is due from just before its start until the grace runs out")
    func test_due_window() {
        let start = Date(timeIntervalSince1970: 10_000)
        #expect(MeetingDetection.isDue(start: start, now: start.addingTimeInterval(-60)))
        #expect(MeetingDetection.isDue(start: start, now: start))
        #expect(MeetingDetection.isDue(start: start, now: start.addingTimeInterval(500)))
        #expect(!MeetingDetection.isDue(start: start, now: start.addingTimeInterval(-3_000)), "not due yet")
        #expect(!MeetingDetection.isDue(start: start, now: start.addingTimeInterval(3_000)), "long started")
    }

    @Test("an event is happening now from just before its start to just after its end")
    func test_happening_now() {
        let start = Date(timeIntervalSince1970: 10_000)
        let end = start.addingTimeInterval(3600)
        #expect(MeetingDetection.isHappeningNow(start: start, end: end, now: start.addingTimeInterval(600)))
        #expect(MeetingDetection.isHappeningNow(start: start, end: end, now: start.addingTimeInterval(-120)))
        #expect(MeetingDetection.isHappeningNow(start: start, end: end, now: end.addingTimeInterval(120)))
        #expect(!MeetingDetection.isHappeningNow(start: start, end: end, now: start.addingTimeInterval(-3600)))
        #expect(!MeetingDetection.isHappeningNow(start: start, end: end, now: end.addingTimeInterval(3600)))
    }

    @Test("call apps are recognised by bundle identifier, helpers included")
    func test_call_app_names() {
        // New Teams captures the microphone in a helper process.
        #expect(MeetingDetection.callAppName(forBundleID: "com.microsoft.teams2.modulehost") == "Microsoft Teams")
        #expect(MeetingDetection.callAppName(forBundleID: "com.microsoft.teams2") == "Microsoft Teams")
        #expect(MeetingDetection.callAppName(forBundleID: "com.microsoft.teams") == "Microsoft Teams")
        #expect(MeetingDetection.callAppName(forBundleID: "us.zoom.xos") == "Zoom")
        #expect(MeetingDetection.callAppName(forBundleID: "com.google.Chrome.helper") == "Google Chrome")
        #expect(MeetingDetection.callAppName(forBundleID: "com.apple.WebKit.GPU") == "Safari")

        // What holds the microphone all day on a real machine is not a call.
        #expect(MeetingDetection.callAppName(forBundleID: "com.amazon.workspaces") == nil)
        #expect(MeetingDetection.callAppName(forBundleID: "com.granola.app.helper") == nil)
        #expect(MeetingDetection.callAppName(forBundleID: "co.uk.designturbine.meetingnotes") == nil)

        // A prefix only matches at a component boundary.
        #expect(MeetingDetection.callAppName(forBundleID: "us.zoom.xosfake") == nil)
    }

    @Test("a call prompt fires when a call app starts using the microphone")
    func test_call_prompt_trigger() {
        // The machine this was built for: WorkSpaces and Granola hold the
        // microphone all day, and Teams runs all day. None of that is a call.
        let idle = MeetingDetection.callAppsCapturing(bundleIDs: [
            "com.amazon.workspaces", "com.granola.app.helper",
        ])
        #expect(idle.isEmpty)
        #expect(MeetingDetection.callPromptTrigger(capturing: idle, previouslyCapturing: []) == nil)

        // Joining a Teams call: Teams itself starts capturing. The old
        // device-level check could never see this, because the microphone
        // device was already busy.
        let inCall = MeetingDetection.callAppsCapturing(bundleIDs: [
            "com.amazon.workspaces", "com.granola.app.helper", "com.microsoft.teams2.modulehost",
        ])
        #expect(MeetingDetection.callPromptTrigger(
            capturing: inCall, previouslyCapturing: idle) == "Microsoft Teams")

        // Still in the call on the next look: already offered, no repeat.
        #expect(MeetingDetection.callPromptTrigger(capturing: inCall, previouslyCapturing: inCall) == nil)

        // The call ends, then the next one prompts again.
        #expect(MeetingDetection.callPromptTrigger(capturing: idle, previouslyCapturing: inCall) == nil)
        #expect(MeetingDetection.callPromptTrigger(
            capturing: inCall, previouslyCapturing: idle) == "Microsoft Teams")
    }

    @Test("a web call in a browser prompts too")
    func test_browser_call() {
        let meet = MeetingDetection.callAppsCapturing(bundleIDs: ["com.google.Chrome.helper"])
        #expect(MeetingDetection.callPromptTrigger(capturing: meet, previouslyCapturing: []) == "Google Chrome")
    }

    @Test("two apps starting together give a stable choice")
    func test_stable_choice() {
        let both: Set<String> = ["Zoom", "Microsoft Teams"]
        #expect(MeetingDetection.callPromptTrigger(capturing: both, previouslyCapturing: []) == "Microsoft Teams")
    }
}
