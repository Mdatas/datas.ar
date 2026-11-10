import DatasLink
import Foundation
import SwiftUI

/// The computers this phone is linked to, and whether each one answers right now.
/// Everything here is changed on the main thread; the asking is done on a background one.
final class Store: ObservableObject {
    @Published var computers: [Computer] = []
    @Published var online: [String: Bool] = [:]

    init() {
        if let data = Keychain.read("computers"), let list = try? JSONDecoder().decode([Computer].self, from: data) {
            computers = list
        }
    }

    private func save() {
        if let data = try? JSONEncoder().encode(computers) {
            Keychain.write("computers", data)
        }
    }

    func add(_ computer: Computer) {
        computers.removeAll { $0.id == computer.id }
        computers.append(computer)
        save()
    }

    /// Forget a computer on this phone. (To turn this phone away for good, also press
    /// Unlink next to it on the computer's Devices screen.)
    func remove(_ computer: Computer) {
        computers.removeAll { $0.id == computer.id }
        online[computer.id] = nil
        save()
    }

    func refresh() {
        for computer in computers {
            DispatchQueue.global(qos: .utility).async {
                let answers = (try? LinkClient.info(computer)) != nil
                DispatchQueue.main.async {
                    self.online[computer.id] = answers
                }
            }
        }
    }
}
