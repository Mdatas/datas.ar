import DatasLink
import SwiftUI
import UIKit

/// Link a computer: its address and the one-time code it shows.
struct LinkView: View {
    @EnvironmentObject private var store: Store
    @Environment(\.dismiss) private var dismiss
    @StateObject private var nearby = Nearby()
    @State private var address = ""
    @State private var code = ""
    @State private var busy = false
    @State private var problem: String?

    var body: some View {
        NavigationView {
            Form {
                Section {
                    TextField(T("Address, for example 192.168.1.20:8424"), text: $address)
                        .keyboardType(.numbersAndPunctuation)
                        .textInputAutocapitalization(.never)
                        .disableAutocorrection(true)
                    TextField(T("The 12 letters and digits"), text: $code)
                        .textInputAutocapitalization(.characters)
                        .disableAutocorrection(true)
                        .font(.system(.title3, design: .monospaced))
                } footer: {
                    Text(T("On your computer: Datas → Devices → Show a code. It shows an address and a code that works once, for ten minutes."))
                }
                Section {
                    if nearby.found.isEmpty {
                        Text(T("Looking for computers with Datas on this Wi-Fi…"))
                            .foregroundColor(.secondary)
                    }
                    ForEach(nearby.found) { item in
                        Button {
                            pick(item)
                        } label: {
                            Label(item.name, systemImage: "desktopcomputer")
                        }
                    }
                } header: {
                    Text(T("Seen on this network"))
                }
                if let problem {
                    Section {
                        Text(problem)
                            .foregroundColor(.red)
                    }
                }
                Section {
                    Button {
                        link()
                    } label: {
                        HStack {
                            Spacer()
                            if busy {
                                ProgressView()
                            } else {
                                Text(T("Link")).font(.headline)
                            }
                            Spacer()
                        }
                    }
                    .disabled(busy || address.trimmingCharacters(in: .whitespaces).isEmpty || LinkClient.cleanCode(code).count != LinkClient.codeLength)
                }
            }
            .navigationTitle(T("Link a computer"))
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .cancellationAction) {
                    Button(T("Cancel")) { dismiss() }
                }
            }
        }
        .navigationViewStyle(.stack)
        .onAppear { nearby.start() }
        .onDisappear { nearby.stop() }
    }

    private func pick(_ item: Found) {
        nearby.address(of: item) { text in
            if let text {
                address = text
                problem = nil
            } else {
                problem = T("Could not find the address of that computer. Type it as the computer shows it.")
            }
        }
    }

    private func link() {
        let (host, port) = LinkView.split(address)
        guard !host.isEmpty else {
            problem = T("Type the address the computer shows.")
            return
        }
        busy = true
        problem = nil
        let typed = code
        let name = UIDevice.current.name
        DispatchQueue.global(qos: .userInitiated).async {
            do {
                let computer = try LinkClient.pair(host: host, port: port, code: typed, phoneName: name, os: "ios")
                DispatchQueue.main.async {
                    store.add(computer)
                    store.refresh()
                    busy = false
                    dismiss()
                }
            } catch {
                let message = (error as? LinkError)?.message ?? error.localizedDescription
                DispatchQueue.main.async {
                    problem = Words.problem(message)
                    busy = false
                }
            }
        }
    }

    /// "192.168.1.20:8424" → ("192.168.1.20", 8424); without a port, the usual one.
    static func split(_ text: String) -> (String, Int) {
        let clean = text.trimmingCharacters(in: .whitespacesAndNewlines)
        if let colon = clean.lastIndex(of: ":"), clean.filter({ $0 == ":" }).count == 1,
           let port = Int(clean[clean.index(after: colon)...]), port > 0, port < 65536 {
            return (String(clean[..<colon]), port)
        }
        return (clean, LinkClient.defaultPort)
    }
}
