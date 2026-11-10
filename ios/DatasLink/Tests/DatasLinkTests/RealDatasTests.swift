import XCTest

@testable import DatasLink

#if canImport(WebKit) && os(iOS)
import WebKit
#endif

/// Against a real Datas on this machine. Skipped unless the address and a fresh one-time
/// code are given in the environment (the build does: see .github/workflows/ios.yml):
///   DATAS_LINK_HOST, DATAS_LINK_PORT, DATAS_LINK_CODE  [DATAS_LINK_NAME]
/// In the iPhone simulator the same test also loads the computer's Datas in the app's own
/// kind of web view, through the door.
final class RealDatasTests: XCTestCase {
    private func env(_ key: String) -> String? {
        let value = ProcessInfo.processInfo.environment[key]
        return (value ?? "").isEmpty ? nil : value
    }

    func testPairOpenAndBeRefusedLikeAPhone() throws {
        guard let host = env("DATAS_LINK_HOST"), let port = Int(env("DATAS_LINK_PORT") ?? ""),
              let code = env("DATAS_LINK_CODE")
        else {
            throw XCTSkip("no real Datas to talk to (DATAS_LINK_HOST, DATAS_LINK_PORT, DATAS_LINK_CODE)")
        }
        // a wrong code is refused, and says so
        XCTAssertThrowsError(try LinkClient.pair(host: host, port: port, code: "AAAA-BBBB-CCCC", phoneName: "x"))

        let computer = try LinkClient.pair(host: host, port: port, code: code,
                                           phoneName: env("DATAS_LINK_NAME") ?? "iPhone test")
        XCTAssertEqual(computer.id.count, 64)
        XCTAssertEqual(computer.secret.count, 64)
        XCTAssertFalse(computer.name.isEmpty)

        let info = try LinkClient.info(computer)
        XCTAssertEqual(info["ok"] as? Bool, true)
        XCTAssertEqual(info["name"] as? String, computer.name)

        // the computer's Datas, through the door
        let door = try Door(computer: computer)
        defer { door.close() }
        XCTAssertGreaterThan(door.port, 0)
        let (status, body) = DoorCheck.request(port: door.port, path: "/api/status")
        XCTAssertEqual(status, 200, body)
        XCTAssertTrue(body.contains("\"remote\""), "the computer should know this is a phone: \(body.prefix(300))")
        let (scriptStatus, script) = DoorCheck.request(port: door.port, path: "/ui/app.js")
        XCTAssertEqual(scriptStatus, 200)
        XCTAssertTrue(script.contains("function renderShell"), "a whole file should come through")
        let (saved, savedBody) = DoorCheck.request(port: door.port, method: "POST", path: "/api/chats",
                                                   body: "{\"messages\":[{\"role\":\"user\",\"content\":\"hola\"}]}")
        XCTAssertEqual(saved, 200, savedBody)
        // what a phone may not do there
        XCTAssertEqual(DoorCheck.request(port: door.port, method: "POST", path: "/api/shutdown", body: "{}").0, 403)
        XCTAssertEqual(DoorCheck.request(port: door.port, path: "/api/things").0, 403)

        // a made-up secret is nobody; another certificate is not the linked computer
        let stranger = Computer(id: computer.id, name: "x", host: host, port: port,
                                secret: String(repeating: "00", count: 32))
        XCTAssertThrowsError(try LinkClient.info(stranger))
        let impostor = Computer(id: String(repeating: "ab", count: 32), name: "x", host: host, port: port,
                                secret: computer.secret)
        XCTAssertThrowsError(try LinkClient.info(impostor)) { error in
            XCTAssertTrue(((error as? LinkError)?.message ?? "").contains("not the computer that was linked"),
                          "\(error)")
        }
        // through the door the person then sees a plain page, not an error code
        let closed = try Door(computer: impostor)
        defer { closed.close() }
        let (sorryStatus, sorry) = DoorCheck.request(port: closed.port, path: "/")
        XCTAssertEqual(sorryStatus, 502)
        XCTAssertTrue(sorry.contains("Not connected"))

        #if canImport(WebKit) && os(iOS)
        try loadInTheAppsWebView(door.url)
        #endif
    }

    #if canImport(WebKit) && os(iOS)
    private final class Watcher: NSObject, WKNavigationDelegate {
        let finished: (String?) -> Void

        init(_ finished: @escaping (String?) -> Void) {
            self.finished = finished
        }

        func webView(_ webView: WKWebView, didFinish navigation: WKNavigation!) {
            finished(nil)
        }

        func webView(_ webView: WKWebView, didFail navigation: WKNavigation!, withError error: Error) {
            finished(error.localizedDescription)
        }

        func webView(_ webView: WKWebView, didFailProvisionalNavigation navigation: WKNavigation!, withError error: Error) {
            finished(error.localizedDescription)
        }
    }

    /// The app shows the computer's Datas in a WKWebView that asks the door. Do exactly that.
    private func loadInTheAppsWebView(_ url: URL) throws {
        let loaded = expectation(description: "the computer's Datas loads through the door")
        var seen = ""
        var failure: String?
        let web = WKWebView(frame: CGRect(x: 0, y: 0, width: 390, height: 800))
        let watcher = Watcher { problem in
            if let problem {
                failure = problem
                loaded.fulfill()
                return
            }
            // give the page's own scripts a moment to draw the window
            DispatchQueue.main.asyncAfter(deadline: .now() + 2) {
                web.evaluateJavaScript("document.title + '|' + (typeof renderShell) + '|' + document.querySelectorAll('#side .nav-item').length") { value, _ in
                    seen = (value as? String) ?? ""
                    loaded.fulfill()
                }
            }
        }
        web.navigationDelegate = watcher  // held weakly by the web view: keep it alive while waiting
        web.load(URLRequest(url: url))
        withExtendedLifetime(watcher) {
            wait(for: [loaded], timeout: 90)
        }
        XCTAssertNil(failure, "the web view could not load the door: \(failure ?? "")")
        let parts = seen.split(separator: "|").map(String.init)
        XCTAssertEqual(parts.first, "Datas", seen)
        XCTAssertEqual(parts.count > 1 ? parts[1] : "", "function", "the window's scripts did not run: \(seen)")
        XCTAssertGreaterThan(Int(parts.last ?? "0") ?? 0, 4, "the window did not draw its menu: \(seen)")
    }
    #endif
}
