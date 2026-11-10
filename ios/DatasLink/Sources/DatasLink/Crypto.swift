import CommonCrypto
import CryptoKit
import Foundation

/// The few pieces of arithmetic the link needs, all from Apple's own libraries.
public enum Crypto {
    public static func sha256(_ data: Data) -> Data {
        Data(SHA256.hash(data: data))
    }

    public static func hmac(key: Data, message: Data) -> Data {
        Data(HMAC<SHA256>.authenticationCode(for: message, using: SymmetricKey(data: key)))
    }

    /// PBKDF2-HMAC-SHA256: the one-time code, stretched so that guessing it is slow.
    public static func pbkdf2(password: String, salt: Data, rounds: Int, length: Int = 32) -> Data? {
        let pass = Array(password.utf8).map { Int8(bitPattern: $0) }
        let saltBytes = [UInt8](salt)
        var out = [UInt8](repeating: 0, count: length)
        let status = CCKeyDerivationPBKDF(
            CCPBKDFAlgorithm(kCCPBKDF2),
            pass, pass.count,
            saltBytes, saltBytes.count,
            CCPseudoRandomAlgorithm(kCCPRFHmacAlgSHA256),
            UInt32(rounds),
            &out, length
        )
        return status == Int32(kCCSuccess) ? Data(out) : nil
    }

    public static func random(_ count: Int) -> Data {
        var bytes = [UInt8](repeating: 0, count: count)
        if SecRandomCopyBytes(kSecRandomDefault, count, &bytes) != errSecSuccess {
            var generator = SystemRandomNumberGenerator()
            for k in 0..<count { bytes[k] = UInt8.random(in: 0...255, using: &generator) }
        }
        return Data(bytes)
    }

    public static func hex(_ data: Data) -> String {
        data.map { String(format: "%02x", $0) }.joined()
    }

    public static func unhex(_ text: String) -> Data? {
        let chars = Array(text.utf8)
        guard chars.count % 2 == 0 else { return nil }
        var out = Data(capacity: chars.count / 2)
        func value(_ c: UInt8) -> UInt8? {
            switch c {
            case 48...57: return c - 48
            case 97...102: return c - 87
            case 65...70: return c - 55
            default: return nil
            }
        }
        var k = 0
        while k < chars.count {
            guard let hi = value(chars[k]), let lo = value(chars[k + 1]) else { return nil }
            out.append(hi << 4 | lo)
            k += 2
        }
        return out
    }

    /// Compare without stopping at the first different byte.
    public static func same(_ a: Data, _ b: Data) -> Bool {
        guard a.count == b.count else { return false }
        var diff: UInt8 = 0
        for (x, y) in zip(a, b) { diff |= x ^ y }
        return diff == 0
    }
}
