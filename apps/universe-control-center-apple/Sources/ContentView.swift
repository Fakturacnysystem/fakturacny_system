import SwiftUI

struct ContentView: View {
    @Environment(\.openURL) private var openURL
    @StateObject private var session = UniverseSession()
    @State private var showingSettings = false

    var body: some View {
        ZStack {
            LinearGradient(
                colors: [
                    Color(red: 0.03, green: 0.08, blue: 0.14),
                    Color(red: 0.02, green: 0.13, blue: 0.19),
                    Color(red: 0.03, green: 0.05, blue: 0.09)
                ],
                startPoint: .topLeading,
                endPoint: .bottomTrailing
            )
            .ignoresSafeArea()

            VStack(spacing: 0) {
                header
                Divider().overlay(.white.opacity(0.08))
                if let url = session.commandCenterURL {
                    UniverseWebView(url: url, token: session.token)
                        .id(session.webViewIdentity)
                } else {
                    ContentUnavailableView(
                        "Invalid gateway URL",
                        systemImage: "exclamationmark.triangle",
                        description: Text("Set a valid Universe gateway URL in Settings.")
                    )
                    .frame(maxWidth: .infinity, maxHeight: .infinity)
                }
            }
            .padding(12)
        }
        .task {
            session.bootstrap()
        }
        .sheet(isPresented: $showingSettings) {
            SettingsView(session: session)
        }
    }

    private var header: some View {
        VStack(alignment: .leading, spacing: 16) {
            HStack(alignment: .top, spacing: 14) {
                VStack(alignment: .leading, spacing: 6) {
                    Text("Universe Control Center")
                        .font(.system(size: 30, weight: .bold, design: .rounded))
                    Text("Native shell for macOS and iPhone")
                        .font(.subheadline)
                        .foregroundStyle(.secondary)
                    Text(session.missionHeadline)
                        .font(.headline)
                    Text(session.missionDetail)
                        .font(.footnote)
                        .foregroundStyle(.secondary)
                        .lineLimit(2)
                }
                Spacer()
                VStack(alignment: .trailing, spacing: 10) {
                    statusPill(title: session.connectionBadge, value: session.gatewayHealth, tint: session.statusAccent)
                    Text("Last update \(session.lastUpdatedLabel)")
                        .font(.caption)
                        .foregroundStyle(.secondary)
                }
            }

            ScrollView(.horizontal, showsIndicators: false) {
                HStack(spacing: 12) {
                    summaryCard(title: "Mode", value: session.mode, note: session.targetMode)
                    summaryCard(title: "Provider", value: session.provider, note: session.role)
                    summaryCard(title: "Symbol", value: session.symbol, note: session.runtimeMode)
                    summaryCard(title: "Run", value: session.runID, note: session.runDirectory)
                    summaryCard(title: "Gate", value: session.gateStatus, note: session.readinessStage)
                }
                .padding(.vertical, 2)
            }

            HStack(spacing: 10) {
                Button {
                    Task { await session.refreshNow() }
                } label: {
                    Label("Refresh", systemImage: "arrow.clockwise")
                }
                .buttonStyle(.borderedProminent)
                .tint(.cyan)

                Button {
                    if session.token.isEmpty {
                        Task { await session.signIn() }
                    } else {
                        session.reconnectShell()
                    }
                } label: {
                    Label(session.token.isEmpty ? "Sign In" : "Reconnect", systemImage: session.token.isEmpty ? "person.crop.circle.badge.checkmark" : "bolt.horizontal.circle")
                }
                .buttonStyle(.bordered)

                Button {
                    showingSettings = true
                } label: {
                    Label("Settings", systemImage: "slider.horizontal.3")
                }
                .buttonStyle(.bordered)

                if let gatewayURL = session.gatewayLinkURL {
                    Button {
                        openURL(gatewayURL)
                    } label: {
                        Label("Gateway", systemImage: "link")
                    }
                    .buttonStyle(.bordered)
                }

                if let grafanaURL = session.grafanaLinkURL {
                    Button {
                        openURL(grafanaURL)
                    } label: {
                        Label("Grafana", systemImage: "waveform.path.ecg")
                    }
                    .buttonStyle(.bordered)
                }
            }
            .labelStyle(.titleAndIcon)

            Text(session.statusMessage)
                .font(.footnote)
                .foregroundStyle(.secondary)
        }
        .padding(20)
        .background(
            RoundedRectangle(cornerRadius: 28, style: .continuous)
                .fill(.ultraThinMaterial)
                .overlay(
                    RoundedRectangle(cornerRadius: 28, style: .continuous)
                        .stroke(.white.opacity(0.08), lineWidth: 1)
                )
        )
        .padding(.bottom, 10)
    }

    private func statusPill(title: String, value: String, tint: Color) -> some View {
        HStack(spacing: 8) {
            Circle()
                .fill(tint)
                .frame(width: 10, height: 10)
            VStack(alignment: .leading, spacing: 2) {
                Text(title.uppercased())
                    .font(.caption2)
                    .foregroundStyle(.secondary)
                Text(value)
                    .font(.headline)
                    .lineLimit(1)
            }
        }
        .padding(.horizontal, 14)
        .padding(.vertical, 10)
        .background(
            Capsule(style: .continuous)
                .fill(Color.white.opacity(0.06))
                .overlay(Capsule(style: .continuous).stroke(Color.white.opacity(0.08), lineWidth: 1))
        )
    }

    private func summaryCard(title: String, value: String, note: String) -> some View {
        VStack(alignment: .leading, spacing: 6) {
            Text(title.uppercased())
                .font(.caption2)
                .foregroundStyle(.secondary)
            Text(value)
                .font(.headline)
                .lineLimit(1)
            Text(note)
                .font(.caption)
                .foregroundStyle(.secondary)
                .lineLimit(1)
        }
        .frame(minWidth: 150, alignment: .leading)
        .padding(.horizontal, 14)
        .padding(.vertical, 12)
        .background(
            RoundedRectangle(cornerRadius: 18, style: .continuous)
                .fill(Color.white.opacity(0.05))
                .overlay(RoundedRectangle(cornerRadius: 18, style: .continuous).stroke(Color.white.opacity(0.08), lineWidth: 1))
        )
    }
}

private struct SettingsView: View {
    @ObservedObject var session: UniverseSession
    @Environment(\.dismiss) private var dismiss

    var body: some View {
        NavigationStack {
            Form {
                Section("Gateway") {
                    TextField("Gateway URL", text: $session.serverURL)
                        #if os(iOS)
                        .textInputAutocapitalization(.never)
                        .keyboardType(.URL)
                        .autocorrectionDisabled()
                        #endif
                    TextField("Grafana URL", text: $session.grafanaURL)
                        #if os(iOS)
                        .textInputAutocapitalization(.never)
                        .keyboardType(.URL)
                        .autocorrectionDisabled()
                        #endif
                }

                Section("Credentials") {
                    TextField("Username", text: $session.username)
                        #if os(iOS)
                        .textInputAutocapitalization(.never)
                        .autocorrectionDisabled()
                        #endif
                    SecureField("Password", text: $session.password)
                    SecureField("Bearer token", text: $session.token)
                }

                Section("Actions") {
                    Button("Save & Reload App Shell") {
                        session.persist()
                        session.invalidateWebView()
                        Task { await session.refreshNow() }
                    }
                    Button("Sign In") {
                        session.persist()
                        Task { await session.signIn() }
                    }
                    Button("Clear Stored Token", role: .destructive) {
                        session.signOut()
                    }
                }
            }
            .navigationTitle("Universe Settings")
            .toolbar {
                ToolbarItem(placement: .cancellationAction) {
                    Button("Close") { dismiss() }
                }
            }
        }
    }
}
