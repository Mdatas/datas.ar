import Foundation
import Network

/// A computer with Datas that announces itself on this Wi-Fi.
struct Found: Identifiable, Hashable {
    let id: String
    let name: String
    let endpoint: NWEndpoint
}

/// Listens for the announcement Datas makes on the home network when its link is on
/// ("_datas-link._tcp", the same one the Android app looks for). Its callbacks arrive on the
/// main thread.
final class Nearby: ObservableObject {
    @Published var found: [Found] = []
    private var browser: NWBrowser?

    func start() {
        guard browser == nil else { return }
        let browser = NWBrowser(for: .bonjour(type: "_datas-link._tcp", domain: nil), using: NWParameters())
        browser.browseResultsChangedHandler = { [weak self] results, _ in
            let list = results.compactMap { result -> Found? in
                if case let .service(name, _, _, _) = result.endpoint {
                    return Found(id: name, name: name, endpoint: result.endpoint)
                }
                return nil
            }.sorted { $0.name < $1.name }
            DispatchQueue.main.async {
                self?.found = list
            }
        }
        browser.start(queue: .main)
        self.browser = browser
    }

    func stop() {
        browser?.cancel()
        browser = nil
    }

    /// The address ("192.168.1.20:8424") behind an announcement, or nil.
    func address(of item: Found, done: @escaping (String?) -> Void) {
        let parameters = NWParameters.tcp
        if let ip = parameters.defaultProtocolStack.internetProtocol as? NWProtocolIP.Options {
            ip.version = .v4
        }
        let connection = NWConnection(to: item.endpoint, using: parameters)
        let once = Once(done)
        connection.stateUpdateHandler = { state in
            switch state {
            case .ready:
                var text: String?
                if case let .hostPort(host, port)? = connection.currentPath?.remoteEndpoint {
                    let name = "\(host)".split(separator: "%").first.map(String.init) ?? ""
                    text = name.isEmpty ? nil : "\(name):\(port.rawValue)"
                }
                connection.cancel()
                once.answer(text)
            case .failed, .waiting:
                connection.cancel()
                once.answer(nil)
            default:
                break
            }
        }
        connection.start(queue: .main)
        DispatchQueue.main.asyncAfter(deadline: .now() + 6) {
            connection.cancel()
            once.answer(nil)
        }
    }
}

/// Calls back one time only, whoever asks first.
private final class Once {
    private var done: ((String?) -> Void)?

    init(_ done: @escaping (String?) -> Void) {
        self.done = done
    }

    func answer(_ text: String?) {
        let call = done
        done = nil
        call?(text)
    }
}
