import DatasLink
import SwiftUI
import UIKit
import WebKit

/// A linked computer's Datas, shown on the phone. The web view asks a door on this phone
/// (127.0.0.1); the door carries everything, encrypted, to the computer.
struct WindowScreen: View {
    let computer: Computer
    let close: () -> Void
    @Environment(\.scenePhase) private var phase
    @State private var door: Door?
    @State private var problem: String?

    var body: some View {
        VStack(spacing: 0) {
            HStack(spacing: 6) {
                Button {
                    door?.close()
                    close()
                } label: {
                    Label(T("My computers"), systemImage: "chevron.left")
                        .font(.body.weight(.semibold))
                }
                Spacer()
                Image(systemName: "lock.fill")
                    .font(.footnote)
                    .foregroundColor(.secondary)
                Text(computer.name)
                    .font(.subheadline)
                    .foregroundColor(.secondary)
                    .lineLimit(1)
            }
            .padding(.horizontal, 14)
            .padding(.vertical, 9)
            Divider()
            if let door {
                WebWindow(url: door.url)
            } else if let problem {
                VStack(spacing: 16) {
                    Spacer()
                    Text(problem)
                        .multilineTextAlignment(.center)
                    Button(T("Try again")) { open() }
                        .buttonStyle(.borderedProminent)
                    Spacer()
                }
                .padding(24)
            } else {
                Spacer()
                ProgressView(T("Connecting…"))
                Spacer()
            }
        }
        .onAppear { open() }
        .onChange(of: phase) { now in
            if now == .active { check() }
        }
    }

    private func open() {
        problem = nil
        let computer = self.computer
        DispatchQueue.global(qos: .userInitiated).async {
            do {
                let new = try Door(computer: computer)
                DispatchQueue.main.async { door = new }
            } catch {
                let message = (error as? LinkError)?.message ?? error.localizedDescription
                DispatchQueue.main.async { problem = Words.problem(message) }
            }
        }
    }

    /// Back from another app: the system may have closed the door meanwhile. If it no
    /// longer answers, open a new one (the page then loads again).
    private func check() {
        guard let current = door else { return }
        DispatchQueue.global(qos: .userInitiated).async {
            let (status, _) = DoorCheck.request(port: current.port, path: "/api/status", timeout: 5)
            if status == 0 {
                current.close()
                DispatchQueue.main.async {
                    door = nil
                    open()
                }
            }
        }
    }
}

/// The web view itself. It keeps nothing on the phone (no cookies, no cache on disk), and a
/// link that leads outside the computer's Datas opens in the phone's own browser.
struct WebWindow: UIViewRepresentable {
    let url: URL

    func makeCoordinator() -> Coordinator {
        Coordinator()
    }

    func makeUIView(context: Context) -> WKWebView {
        let configuration = WKWebViewConfiguration()
        configuration.websiteDataStore = .nonPersistent()
        configuration.allowsInlineMediaPlayback = true
        let web = WKWebView(frame: .zero, configuration: configuration)
        web.navigationDelegate = context.coordinator
        web.uiDelegate = context.coordinator
        web.scrollView.keyboardDismissMode = .interactive
        web.load(URLRequest(url: url))
        return web
    }

    func updateUIView(_ web: WKWebView, context: Context) {
        if web.url?.port != url.port {
            web.load(URLRequest(url: url))
        }
    }

    final class Coordinator: NSObject, WKNavigationDelegate, WKUIDelegate {
        private func isOurs(_ target: URL) -> Bool {
            target.host == "127.0.0.1" || ["about", "blob", "data"].contains(target.scheme ?? "")
        }

        private func outside(_ target: URL) {
            if target.scheme == "http" || target.scheme == "https" {
                UIApplication.shared.open(target)
            }
        }

        func webView(_ webView: WKWebView, decidePolicyFor navigationAction: WKNavigationAction,
                     decisionHandler: @escaping (WKNavigationActionPolicy) -> Void) {
            guard let target = navigationAction.request.url else {
                decisionHandler(.cancel)
                return
            }
            if isOurs(target) {
                decisionHandler(.allow)
            } else {
                outside(target)
                decisionHandler(.cancel)
            }
        }

        // a link that asks for a new window
        func webView(_ webView: WKWebView, createWebViewWith configuration: WKWebViewConfiguration,
                     for navigationAction: WKNavigationAction, windowFeatures: WKWindowFeatures) -> WKWebView? {
            if let target = navigationAction.request.url {
                if isOurs(target) {
                    webView.load(navigationAction.request)
                } else {
                    outside(target)
                }
            }
            return nil
        }

        // the page's own questions (the agent's window asks before risky switches)
        func webView(_ webView: WKWebView, runJavaScriptAlertPanelWithMessage message: String,
                     initiatedByFrame frame: WKFrameInfo, completionHandler: @escaping () -> Void) {
            let alert = UIAlertController(title: nil, message: message, preferredStyle: .alert)
            alert.addAction(UIAlertAction(title: T("OK"), style: .default) { _ in completionHandler() })
            show(alert, from: webView) { completionHandler() }
        }

        func webView(_ webView: WKWebView, runJavaScriptConfirmPanelWithMessage message: String,
                     initiatedByFrame frame: WKFrameInfo, completionHandler: @escaping (Bool) -> Void) {
            let alert = UIAlertController(title: nil, message: message, preferredStyle: .alert)
            alert.addAction(UIAlertAction(title: T("Cancel"), style: .cancel) { _ in completionHandler(false) })
            alert.addAction(UIAlertAction(title: T("OK"), style: .default) { _ in completionHandler(true) })
            show(alert, from: webView) { completionHandler(false) }
        }

        private func show(_ alert: UIAlertController, from webView: WKWebView, otherwise: () -> Void) {
            var top = webView.window?.rootViewController
            while let next = top?.presentedViewController {
                top = next
            }
            if let top {
                top.present(alert, animated: true)
            } else {
                otherwise()
            }
        }
    }
}
