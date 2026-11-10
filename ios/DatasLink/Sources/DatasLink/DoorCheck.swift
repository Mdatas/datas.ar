import Foundation
import Network

/// One plain web request to a door on this device, read to the end. The app's web view does
/// its own asking; this is for checks and tests ("does the computer's Datas answer?").
public enum DoorCheck {
    private final class Bytes {
        var data = Data()
    }

    /// Returns the status code (0 when nothing came back) and the body as text.
    public static func request(port: Int, method: String = "GET", path: String, body: String? = nil,
                               timeout: TimeInterval = 90) -> (Int, String) {
        guard port > 0, port < 65536, let nwPort = NWEndpoint.Port(rawValue: UInt16(port)) else { return (0, "") }
        let connection = NWConnection(host: "127.0.0.1", port: nwPort, using: .tcp)
        let queue = DispatchQueue(label: "ar.datas.link.doorcheck")
        let done = DispatchSemaphore(value: 0)
        let received = Bytes()
        let payload = Data((body ?? "").utf8)
        var head = "\(method) \(path) HTTP/1.1\r\nHost: 127.0.0.1\r\nConnection: close\r\n"
        if body != nil {
            head += "Content-Type: application/json\r\nContent-Length: \(payload.count)\r\n"
        }
        let request = Data((head + "\r\n").utf8) + payload

        func read() {
            connection.receive(minimumIncompleteLength: 1, maximumLength: 65536) { data, _, isComplete, error in
                if let data { received.data.append(data) }
                if isComplete || error != nil {
                    done.signal()
                } else {
                    read()
                }
            }
        }
        connection.stateUpdateHandler = { state in
            switch state {
            case .ready:
                connection.send(content: request, completion: .contentProcessed { _ in })
                read()
            case .failed, .waiting:
                done.signal()
            default:
                break
            }
        }
        connection.start(queue: queue)
        _ = done.wait(timeout: .now() + timeout)
        connection.cancel()
        let raw = queue.sync { received.data }
        return parse(raw)
    }

    /// Splits an HTTP/1.1 answer into its status code and its body (chunks joined).
    static func parse(_ raw: Data) -> (Int, String) {
        guard let split = raw.range(of: Data("\r\n\r\n".utf8)) else { return (0, "") }
        let head = String(decoding: raw[raw.startIndex..<split.lowerBound], as: UTF8.self)
        var content = Data(raw[split.upperBound...])
        let status = Int(head.split(separator: " ").dropFirst().first ?? "0") ?? 0
        if head.lowercased().contains("transfer-encoding: chunked") {
            var out = Data()
            var rest = content
            while let lineEnd = rest.range(of: Data("\r\n".utf8)) {
                let sizeText = String(decoding: rest[rest.startIndex..<lineEnd.lowerBound], as: UTF8.self)
                let digits = sizeText.split(separator: ";").first.map(String.init) ?? "0"
                let size = Int(digits.trimmingCharacters(in: .whitespaces), radix: 16) ?? 0
                if size == 0 { break }
                let start = lineEnd.upperBound
                guard rest.endIndex - start >= size else { break }
                out.append(rest[start..<(start + size)])
                let next = start + size + 2
                if next > rest.endIndex { break }
                rest = Data(rest[next...])
            }
            content = out
        }
        return (status, String(decoding: content, as: UTF8.self))
    }
}
