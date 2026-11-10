import Foundation

/// A linked computer, as the phone remembers it.
public struct Computer: Codable, Equatable, Identifiable, Sendable {
    /// Fingerprint (SHA-256, hex) of the computer's certificate. Only this certificate is accepted.
    public var id: String
    public var name: String
    public var host: String
    public var port: Int
    /// This phone's secret for that computer (hex). It never leaves the encrypted connection.
    public var secret: String

    public init(id: String, name: String, host: String, port: Int, secret: String) {
        self.id = id
        self.name = name
        self.host = host
        self.port = port
        self.secret = secret
    }

    public func at(host: String, port: Int) -> Computer {
        Computer(id: id, name: name, host: host, port: port, secret: secret)
    }

    public func json() -> String {
        Wire.text(["id": id, "name": name, "host": host, "port": port, "secret": secret])
    }

    public static func from(json text: String) -> Computer? {
        guard let m = Wire.object(Data(text.utf8)),
              let id = m["id"] as? String, let host = m["host"] as? String,
              let secret = m["secret"] as? String
        else { return nil }
        let port = (m["port"] as? NSNumber)?.intValue ?? LinkClient.defaultPort
        return Computer(id: id, name: (m["name"] as? String) ?? host, host: host, port: port, secret: secret)
    }
}

/// JSON in and out, in the compact form the computer sends and expects.
enum Wire {
    static func data(_ object: [String: Any]) -> Data {
        (try? JSONSerialization.data(withJSONObject: object, options: [.sortedKeys, .withoutEscapingSlashes])) ?? Data("{}".utf8)
    }

    static func text(_ object: [String: Any]) -> String {
        String(decoding: data(object), as: UTF8.self)
    }

    static func object(_ data: Data) -> [String: Any]? {
        (try? JSONSerialization.jsonObject(with: data)) as? [String: Any]
    }
}
