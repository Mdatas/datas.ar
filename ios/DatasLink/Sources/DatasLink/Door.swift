import Foundation
import Network

/// A door on this phone (127.0.0.1, a free port): whatever the app's web view asks there is
/// carried, encrypted, to the linked computer's Datas. One encrypted connection per
/// connection of the web view. Nothing outside this phone can reach the door.
public final class Door {
    public let computer: Computer
    private let listener: NWListener
    private let queue = DispatchQueue(label: "ar.datas.link.door")

    public init(computer: Computer) throws {
        self.computer = computer
        let parameters = NWParameters.tcp
        parameters.requiredInterfaceType = .loopback  // this phone only
        parameters.allowLocalEndpointReuse = true
        do {
            listener = try NWListener(using: parameters, on: .any)
        } catch {
            throw LinkError("This phone could not open its side of the connection.")
        }
        let ready = DispatchSemaphore(value: 0)
        let opened = Box<Bool>()
        listener.stateUpdateHandler = { state in
            switch state {
            case .ready:
                if opened.setOnce(true) { ready.signal() }
            case .failed, .cancelled:
                if opened.setOnce(false) { ready.signal() }
            default:
                break
            }
        }
        listener.newConnectionHandler = { [weak self] local in
            self?.carry(local)
        }
        listener.start(queue: queue)
        if ready.wait(timeout: .now() + 5) == .timedOut || opened.value != true {
            listener.cancel()
            throw LinkError("This phone could not open its side of the connection.")
        }
    }

    public var port: Int {
        Int(listener.port?.rawValue ?? 0)
    }

    public var url: URL {
        URL(string: "http://127.0.0.1:\(port)/")!
    }

    public func close() {
        listener.cancel()
    }

    private func carry(_ local: NWConnection) {
        let computer = self.computer
        let queue = self.queue
        local.start(queue: queue)
        DispatchQueue.global(qos: .userInitiated).async {
            do {
                let remote = try LinkClient.open(computer, op: "window")
                Door.pump(from: local, to: remote.connection)
                Door.pump(from: remote.connection, to: local)
            } catch {
                let why = (error as? LinkError)?.message
                    ?? "Could not reach \(computer.name). Is Datas open on it, and is this phone on the same network?"
                Door.sorry(local, why, queue)
            }
        }
    }

    /// Copy what arrives on one side to the other, until either side ends.
    private static func pump(from: NWConnection, to: NWConnection) {
        from.receive(minimumIncompleteLength: 1, maximumLength: 65536) { data, _, isComplete, error in
            if let data, !data.isEmpty {
                to.send(content: data, completion: .contentProcessed { sendError in
                    if sendError != nil || isComplete || error != nil {
                        from.cancel()
                        to.cancel()
                    } else {
                        pump(from: from, to: to)
                    }
                })
            } else if isComplete || error != nil {
                from.cancel()
                to.cancel()
            } else {
                pump(from: from, to: to)
            }
        }
    }

    /// The person sees a plain page, not an error code.
    private static func sorry(_ local: NWConnection, _ why: String, _ queue: DispatchQueue) {
        let safe = why.replacingOccurrences(of: "&", with: "&amp;").replacingOccurrences(of: "<", with: "&lt;")
        let page = "<!doctype html><meta charset=\"utf-8\"><meta name=\"viewport\" content=\"width=device-width\">"
            + "<body style=\"font-family:-apple-system,sans-serif;padding:24px;line-height:1.5\">"
            + "<h2>Not connected</h2><p>" + safe + "</p></body>"
        let body = Data(page.utf8)
        let head = "HTTP/1.1 502 Bad Gateway\r\nContent-Type: text/html; charset=utf-8\r\nCache-Control: no-store\r\n"
            + "Connection: close\r\nContent-Length: \(body.count)\r\n\r\n"
        // read the request first: closing with unread bytes would cut the answer off
        local.receive(minimumIncompleteLength: 1, maximumLength: 65536) { _, _, _, _ in
            local.send(content: Data(head.utf8) + body, contentContext: .finalMessage, isComplete: true,
                       completion: .contentProcessed { _ in
                           queue.asyncAfter(deadline: .now() + 1) { local.cancel() }
                       })
        }
    }
}
