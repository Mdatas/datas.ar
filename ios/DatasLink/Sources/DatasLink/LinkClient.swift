import Foundation
import Network
import Security

// The phone's side of the link between a person's own devices.
//
// Linking (once): the computer shows a one-time code. The phone invents a long random secret
// and proves, with the code, that the secret is its own; the computer proves it knows the code
// too. The code never travels, and both proofs include the fingerprint of the computer's
// certificate, so a device in between cannot swap in its own.
//
// Afterwards: TLS 1.3, accepting only that exact certificate, and the secret shown inside the
// encrypted connection. No account, no server in the middle.
//
// The same messages, in Python, are in tests/phone.py; in Java, in the Android app; the
// computer's side is datas/link/__init__.py. Everything here comes from Apple's own
// libraries (Network, CryptoKit, CommonCrypto).

/// Something to show the person: wrong code, computer not reachable, not linked any more.
public struct LinkError: Error, LocalizedError, Equatable, Sendable {
    public let message: String

    public init(_ message: String) {
        self.message = message
    }

    public var errorDescription: String? { message }
}

/// A value handed from a callback to the thread that waits for it.
final class Box<T> {
    private let lock = NSLock()
    private var stored: T?

    var value: T? {
        get {
            lock.lock()
            defer { lock.unlock() }
            return stored
        }
        set {
            lock.lock()
            stored = newValue
            lock.unlock()
        }
    }

    /// Keep the first value only. Returns whether this call was the first.
    func setOnce(_ new: T) -> Bool {
        lock.lock()
        defer { lock.unlock() }
        if stored != nil { return false }
        stored = new
        return true
    }
}

/// One encrypted connection to a computer (TLS 1.3). While linking, any certificate is
/// noted; afterwards only the remembered one passes. Its calls wait for their answer, so
/// they must not be made on the main thread.
public final class Channel {
    public let connection: NWConnection
    public internal(set) var lastReply: [String: Any] = [:]
    private let queue: DispatchQueue
    private let seen: Box<String>
    private let pin: String?

    public static let unreachable = "Could not reach that computer. Is Datas open on it, and is this phone on the same network?"

    /// The fingerprint (SHA-256, hex) of the certificate the other side showed.
    public var fingerprint: String? { seen.value }

    init(host: String, port: Int, pin: String?) throws {
        guard port > 0, port < 65536, let nwPort = NWEndpoint.Port(rawValue: UInt16(port)), !host.isEmpty else {
            throw LinkError("That address is not complete.")
        }
        let queue = DispatchQueue(label: "ar.datas.link.channel")
        let seen = Box<String>()
        let tls = NWProtocolTLS.Options()
        let options = tls.securityProtocolOptions
        sec_protocol_options_set_min_tls_protocol_version(options, .TLSv13)
        sec_protocol_options_set_verify_block(options, { _, trust, complete in
            let secTrust = sec_trust_copy_ref(trust).takeRetainedValue()
            guard let chain = SecTrustCopyCertificateChain(secTrust) as? [SecCertificate], let leaf = chain.first else {
                complete(false)
                return
            }
            let shown = Crypto.hex(Crypto.sha256(SecCertificateCopyData(leaf) as Data))
            seen.value = shown
            complete(pin == nil || pin == shown)
        }, queue)
        let tcp = NWProtocolTCP.Options()
        tcp.connectionTimeout = 12
        tcp.noDelay = true
        self.queue = queue
        self.seen = seen
        self.pin = pin
        self.connection = NWConnection(host: NWEndpoint.Host(host), port: nwPort, using: NWParameters(tls: tls, tcp: tcp))
    }

    func start(timeout: TimeInterval = 15) throws {
        let done = DispatchSemaphore(value: 0)
        let outcome = Box<Result<Bool, NWError>>()
        connection.stateUpdateHandler = { state in
            switch state {
            case .ready:
                if outcome.setOnce(.success(true)) { done.signal() }
            case .failed(let error), .waiting(let error):
                if outcome.setOnce(.failure(error)) { done.signal() }
            case .cancelled:
                if outcome.setOnce(.failure(.posix(.ECANCELED))) { done.signal() }
            default:
                break
            }
        }
        connection.start(queue: queue)
        if done.wait(timeout: .now() + timeout) == .timedOut {
            connection.cancel()
            throw LinkError(Channel.unreachable)
        }
        if case .failure(let error)? = outcome.value {
            connection.cancel()
            if let pin, let shown = seen.value, shown != pin {
                throw LinkError("The device at that address is not the computer that was linked.")
            }
            throw LinkError(Channel.unreachable + " (" + error.localizedDescription + ")")
        }
    }

    func send(_ data: Data, timeout: TimeInterval = 30) throws {
        let done = DispatchSemaphore(value: 0)
        let failure = Box<String>()
        connection.send(content: data, completion: .contentProcessed { error in
            if let error { failure.value = error.localizedDescription }
            done.signal()
        })
        if done.wait(timeout: .now() + timeout) == .timedOut {
            throw LinkError("The computer did not answer in time.")
        }
        if failure.value != nil {
            throw LinkError("The connection to the computer was lost.")
        }
    }

    func receive(exactly count: Int, timeout: TimeInterval = 30) throws -> Data {
        var buffer = Data()
        while buffer.count < count {
            let done = DispatchSemaphore(value: 0)
            let piece = Box<Data>()
            connection.receive(minimumIncompleteLength: 1, maximumLength: count - buffer.count) { data, _, _, _ in
                if let data, !data.isEmpty { piece.value = data }
                done.signal()
            }
            if done.wait(timeout: .now() + timeout) == .timedOut {
                throw LinkError("The computer did not answer in time.")
            }
            guard let got = piece.value else {
                throw LinkError("The connection to the computer was lost.")
            }
            buffer.append(got)
        }
        return buffer
    }

    /// One message: four bytes that say how long it is, then JSON.
    func sendFrame(_ object: [String: Any]) throws {
        let body = Wire.data(object)
        let n = UInt32(body.count)
        let head = Data([UInt8(n >> 24 & 0xff), UInt8(n >> 16 & 0xff), UInt8(n >> 8 & 0xff), UInt8(n & 0xff)])
        try send(head + body)
    }

    func receiveFrame() throws -> [String: Any] {
        let head = try receive(exactly: 4)
        let length = head.reduce(0) { $0 << 8 | Int($1) }
        guard length > 0, length <= 1 << 20 else {
            throw LinkError("The computer sent something unexpected.")
        }
        guard let object = Wire.object(try receive(exactly: length)) else {
            throw LinkError("The computer sent something unexpected.")
        }
        return object
    }

    public func close() {
        connection.cancel()
    }
}

public enum LinkClient {
    public static let proto = "datas-link-v1"
    public static let defaultPort = 8424
    public static let pbkdf2Rounds = 300_000
    public static let codeLength = 12

    /// The code as the person may have typed it ("abcd-efgh jklm") → "ABCDEFGHJKLM".
    public static func cleanCode(_ code: String) -> String {
        String(code.uppercased().filter { $0.isLetter || $0.isNumber })
    }

    /// The code, stretched: PBKDF2-HMAC-SHA256, salt = "datas-link-v1" + both random numbers.
    public static func derive(code: String, nonces: Data) throws -> Data {
        guard let key = Crypto.pbkdf2(password: cleanCode(code), salt: Data(proto.utf8) + nonces, rounds: pbkdf2Rounds) else {
            throw LinkError("This phone lacks a needed security function (PBKDF2).")
        }
        return key
    }

    public static func proof(key: Data, role: String, fpSelf: String, fpOther: String, n1: Data, n2: Data) -> Data {
        let message = [proto, role, fpSelf, fpOther, Crypto.hex(n1), Crypto.hex(n2)].joined(separator: "|")
        return Crypto.hmac(key: key, message: Data(message.utf8))
    }

    public static func json(_ object: [String: Any]) -> String {
        Wire.text(object)
    }

    private static func text(_ value: Any?) -> String? {
        guard let s = value as? String, !s.isEmpty else { return nil }
        return s
    }

    // ---- linking (once) -----------------------------------------------------------------

    public static func pair(host: String, port: Int, code: String, phoneName: String, os: String = "ios") throws -> Computer {
        let clean = cleanCode(code)
        guard clean.count == codeLength else {
            throw LinkError("The code has \(codeLength) letters and digits.")
        }
        let secret = Crypto.random(32)
        let me = Crypto.hex(Crypto.sha256(secret))
        let channel = try Channel(host: host, port: port, pin: nil)
        defer { channel.close() }
        try channel.start()
        guard let computer = channel.fingerprint else {
            throw LinkError("The computer did not identify itself.")
        }
        let nc = Crypto.random(16)
        try channel.sendFrame(["op": "pair", "app": true, "id": me, "name": phoneName, "os": os, "nonce": Crypto.hex(nc)])
        let first = try channel.receiveFrame()
        guard (first["ok"] as? Bool) == true else {
            throw LinkError(text(first["error"]) ?? "That computer is not showing a code right now.")
        }
        guard let ns = Crypto.unhex(text(first["nonce"]) ?? ""), !ns.isEmpty else {
            throw LinkError("The computer sent something unexpected. Is its Datas up to date?")
        }
        let key = try derive(code: clean, nonces: nc + ns)
        let mine = proof(key: key, role: "client", fpSelf: me, fpOther: computer, n1: nc, n2: ns)
        try channel.sendFrame(["proof": Crypto.hex(mine)])
        let second = try channel.receiveFrame()
        guard (second["ok"] as? Bool) == true else {
            throw LinkError(text(second["error"]) ?? "Wrong or expired code.")
        }
        let want = proof(key: key, role: "server", fpSelf: computer, fpOther: me, n1: ns, n2: nc)
        guard let theirs = Crypto.unhex(text(second["proof"]) ?? ""), Crypto.same(want, theirs) else {
            throw LinkError("The computer could not prove it knows the code. Nothing was linked.")
        }
        return Computer(id: computer, name: text(first["name"]) ?? host, host: host, port: port, secret: Crypto.hex(secret))
    }

    // ---- after linking ------------------------------------------------------------------

    /// Connect to a linked computer and make one request. For "window" the connection that
    /// comes back then carries plain web traffic to that computer's Datas.
    public static func open(_ computer: Computer, op: String) throws -> Channel {
        let channel = try Channel(host: computer.host, port: computer.port, pin: computer.id)
        do {
            try channel.start()
            try channel.sendFrame(["op": op, "auth": computer.secret])
            let reply = try channel.receiveFrame()
            guard (reply["ok"] as? Bool) == true else {
                throw LinkError(text(reply["error"]) ?? "The computer refused.")
            }
            channel.lastReply = reply
            return channel
        } catch {
            channel.close()
            throw error
        }
    }

    /// How the computer is: name, version, whether an AI is ready.
    public static func info(_ computer: Computer) throws -> [String: Any] {
        let channel = try open(computer, op: "info")
        channel.close()
        return channel.lastReply
    }
}
