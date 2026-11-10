import Foundation
import Security

/// The phone's own safe (the Keychain). What is kept there — how to reach your computers —
/// stays on this device only: it is not copied to iCloud or to another phone.
enum Keychain {
    static let service = "ar.datas.app"

    static func read(_ account: String) -> Data? {
        let query: [String: Any] = [
            kSecClass as String: kSecClassGenericPassword,
            kSecAttrService as String: service,
            kSecAttrAccount as String: account,
            kSecReturnData as String: true,
            kSecMatchLimit as String: kSecMatchLimitOne,
        ]
        var found: CFTypeRef?
        guard SecItemCopyMatching(query as CFDictionary, &found) == errSecSuccess else { return nil }
        return found as? Data
    }

    @discardableResult
    static func write(_ account: String, _ data: Data) -> Bool {
        let item: [String: Any] = [
            kSecClass as String: kSecClassGenericPassword,
            kSecAttrService as String: service,
            kSecAttrAccount as String: account,
        ]
        SecItemDelete(item as CFDictionary)
        var new = item
        new[kSecValueData as String] = data
        new[kSecAttrAccessible as String] = kSecAttrAccessibleAfterFirstUnlockThisDeviceOnly
        return SecItemAdd(new as CFDictionary, nil) == errSecSuccess
    }
}
