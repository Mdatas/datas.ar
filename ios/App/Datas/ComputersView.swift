import DatasLink
import SwiftUI

/// The first screen: the computers this phone is linked to.
struct ComputersView: View {
    @EnvironmentObject private var store: Store
    @Environment(\.scenePhase) private var phase
    @State private var linking = false
    @State private var opened: Computer?

    var body: some View {
        NavigationView {
            List {
                Section {
                    if store.computers.isEmpty {
                        VStack(alignment: .leading, spacing: 8) {
                            Text(T("No computer is linked yet."))
                                .font(.headline)
                            Text(T("On your computer open Datas → Devices → Show a code. Then tap “Link a computer” here and type the address and the code it shows."))
                                .foregroundColor(.secondary)
                        }
                        .padding(.vertical, 6)
                    }
                    ForEach(store.computers) { computer in
                        Button {
                            opened = computer
                        } label: {
                            row(computer)
                        }
                    }
                    .onDelete { offsets in
                        for computer in offsets.map({ store.computers[$0] }) {
                            store.remove(computer)
                        }
                    }
                } header: {
                    Text(T("My computers"))
                } footer: {
                    Text(T("The computer does the thinking: this phone shows its Datas over an encrypted link. Nothing is stored on the phone except how to reach your computers."))
                }
                Section {
                    Button {
                        linking = true
                    } label: {
                        Label(T("Link a computer"), systemImage: "plus.circle.fill")
                            .font(.headline)
                    }
                }
            }
            .navigationTitle("Datas")
            .refreshable {
                store.refresh()
            }
        }
        .navigationViewStyle(.stack)
        .sheet(isPresented: $linking) {
            LinkView()
                .environmentObject(store)
        }
        .fullScreenCover(item: $opened) { computer in
            WindowScreen(computer: computer) {
                opened = nil
                store.refresh()
            }
        }
        .onAppear {
            store.refresh()
        }
        .onChange(of: phase) { now in
            if now == .active { store.refresh() }
        }
    }

    private func row(_ computer: Computer) -> some View {
        HStack(spacing: 12) {
            Image(systemName: "desktopcomputer")
                .font(.title2)
                .foregroundColor(.accentColor)
                .frame(width: 34)
            VStack(alignment: .leading, spacing: 2) {
                Text(computer.name)
                    .font(.headline)
                    .foregroundColor(.primary)
                Text(status(computer))
                    .font(.subheadline)
                    .foregroundColor(.secondary)
            }
            Spacer()
            Image(systemName: "chevron.right")
                .font(.footnote.weight(.semibold))
                .foregroundColor(.secondary)
        }
        .padding(.vertical, 4)
    }

    private func status(_ computer: Computer) -> String {
        switch store.online[computer.id] {
        case .some(true): return T("Ready")
        case .some(false): return T("Not reachable right now")
        case .none: return T("Checking…")
        }
    }
}
