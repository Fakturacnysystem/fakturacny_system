import Foundation
import SwiftUI

@MainActor
final class UniverseSession: ObservableObject {
    @Published var serverURL: String
    @Published var grafanaURL: String
    @Published var username: String
    @Published var password: String
    @Published var token: String

    @Published var connectionState: String = "connecting"
    @Published var mode: String = "Unknown"
    @Published var provider: String = "Unknown"
    @Published var symbol: String = "-"
    @Published var reason: String = "Waiting for runtime"
    @Published var statusMessage: String = "Connect the app to the Universe gateway."
    @Published var lastUpdated: Date?
    @Published var isBusy: Bool = false
    @Published var webViewIdentity: Int = 0
    @Published var role: String = "observer"
    @Published var runID: String = "pending"
    @Published var runtimeMode: String = "unknown"
    @Published var targetMode: String = "unknown"
    @Published var gatewayHealth: String = "unknown"
    @Published var readinessStage: String = "unknown"
    @Published var gateStatus: String = "unknown"
    @Published var runDirectory: String = "run pending"

    private let defaults = UserDefaults.standard
    private var refreshTask: Task<Void, Never>?
    private let isoFormatter = ISO8601DateFormatter()

    init() {
        let defaults = UserDefaults.standard
        self.serverURL = defaults.string(forKey: "universe.apple.serverURL") ?? "http://127.0.0.1:8081"
        self.grafanaURL = defaults.string(forKey: "universe.apple.grafanaURL") ?? "http://127.0.0.1:3000"
        self.username = defaults.string(forKey: "universe.apple.username") ?? "admin"
        self.password = defaults.string(forKey: "universe.apple.password") ?? "universe-admin"
        self.token = defaults.string(forKey: "universe.apple.token") ?? ""
    }

    deinit {
        refreshTask?.cancel()
    }

    func bootstrap() {
        persist()
        startPolling()
        if token.isEmpty, !username.isEmpty, !password.isEmpty {
            Task { await signIn() }
        } else {
            Task { await refreshNow() }
        }
    }

    func persist() {
        defaults.set(serverURL, forKey: "universe.apple.serverURL")
        defaults.set(grafanaURL, forKey: "universe.apple.grafanaURL")
        defaults.set(username, forKey: "universe.apple.username")
        defaults.set(password, forKey: "universe.apple.password")
        defaults.set(token, forKey: "universe.apple.token")
    }

    func invalidateWebView() {
        webViewIdentity += 1
    }

    func reconnectShell() {
        invalidateWebView()
        Task { await refreshNow() }
    }

    var commandCenterURL: URL? {
        guard var components = baseComponents(from: serverURL) else { return nil }
        components.path = "/ui"
        components.query = nil
        return components.url
    }

    var gatewayLinkURL: URL? {
        commandCenterURL
    }

    var grafanaLinkURL: URL? {
        baseURL(from: grafanaURL)
    }

    var connectionBadge: String {
        switch connectionState {
        case "connected":
            return "Connected"
        case "auth-failed":
            return "Auth Failed"
        case "offline":
            return "Offline"
        case "invalid-url":
            return "Invalid URL"
        default:
            return "Connecting"
        }
    }

    var missionHeadline: String {
        if symbol != "-" {
            return "\(mode) / \(symbol) / \(provider)"
        }
        return "Universe gateway ready"
    }

    var missionDetail: String {
        let stage = readinessStage == "unknown" ? gatewayHealth : readinessStage
        return "\(reason) · gate \(gateStatus) · stage \(stage)"
    }

    var lastUpdatedLabel: String {
        guard let lastUpdated else { return "No refresh yet" }
        return lastUpdated.formatted(date: .omitted, time: .standard)
    }

    var runLabel: String {
        runID == "pending" ? runDirectory : "\(runID) · \(runtimeMode)"
    }

    var statusAccent: Color {
        switch connectionState {
        case "connected":
            return .green
        case "offline", "auth-failed":
            return .red
        default:
            return .orange
        }
    }

    func signIn() async {
        guard let baseURL = baseURL(from: serverURL) else {
            connectionState = "invalid-url"
            statusMessage = "Server URL is invalid."
            return
        }
        isBusy = true
        defer { isBusy = false }

        do {
            var request = URLRequest(url: baseURL.appending(path: "api/auth/token"))
            request.httpMethod = "POST"
            request.setValue("application/json", forHTTPHeaderField: "Content-Type")
            request.httpBody = try JSONEncoder().encode(TokenRequest(username: username, password: password))
            let (data, response) = try await URLSession.shared.data(for: request)
            let http = try requireHTTP(response)
            guard (200..<300).contains(http.statusCode) else {
                throw SessionError.http(status: http.statusCode)
            }
            let payload = try JSONDecoder().decode(TokenResponse.self, from: data)
            token = payload.accessToken
            role = payload.role
            persist()
            invalidateWebView()
            statusMessage = "Authenticated as \(payload.username) (\(payload.role))."
            await refreshNow()
        } catch {
            connectionState = "auth-failed"
            statusMessage = "Sign-in failed: \(error.localizedDescription)"
        }
    }

    func signOut() {
        token = ""
        role = "observer"
        persist()
        invalidateWebView()
        statusMessage = "Stored bearer token cleared."
    }

    func refreshNow() async {
        guard let baseURL = baseURL(from: serverURL) else {
            connectionState = "invalid-url"
            statusMessage = "Server URL is invalid."
            return
        }
        do {
            let health = try await fetch(HealthPayload.self, from: baseURL.appending(path: "health"), token: nil)
            apply(health: health)
            if !token.isEmpty {
                async let system: SystemStatusPayload = fetch(SystemStatusPayload.self, from: baseURL.appending(path: "api/system/status"), token: token)
                async let environment: EnvironmentPayload = fetch(EnvironmentPayload.self, from: baseURL.appending(path: "api/system/environment"), token: token)
                async let audit: AuditPayload = fetch(AuditPayload.self, from: baseURL.appending(path: "api/audit/runtime"), token: token)
                let (resolvedSystem, resolvedEnvironment, resolvedAudit) = try await (system, environment, audit)
                apply(system: resolvedSystem)
                apply(environment: resolvedEnvironment)
                apply(audit: resolvedAudit)
            }
            connectionState = "connected"
        } catch {
            connectionState = "offline"
            statusMessage = "Gateway unavailable: \(error.localizedDescription)"
        }
    }

    private func startPolling() {
        refreshTask?.cancel()
        refreshTask = Task { [weak self] in
            while let self, !Task.isCancelled {
                await self.refreshNow()
                try? await Task.sleep(for: .seconds(5))
            }
        }
    }

    private func apply(health: HealthPayload) {
        mode = health.runtime.mode ?? mode
        provider = health.runtime.provider ?? provider
        symbol = health.runtime.symbol ?? symbol
        reason = health.runtime.reason ?? reason
        gatewayHealth = health.runtime.status ?? gatewayHealth
        runDirectory = health.runtime.runDir ?? runDirectory
        if let parsed = isoFormatter.date(from: health.ts) {
            lastUpdated = parsed
        } else {
            lastUpdated = Date()
        }
        statusMessage = "\(health.runtime.status ?? "unknown") / \(health.runtime.runDir ?? "run pending")"
    }

    private func apply(system: SystemStatusPayload) {
        mode = system.mode
        provider = system.provider
        symbol = system.symbol
        reason = system.reason
        gatewayHealth = system.health
        lastUpdated = Date()
        statusMessage = "\(system.health) / \(system.reason)"
    }

    private func apply(environment: EnvironmentPayload) {
        runID = environment.runID
        runtimeMode = environment.runtimeMode
        targetMode = environment.targetMode
        runDirectory = environment.resolvedRunDir
        if mode == "Unknown" {
            mode = environment.mode
        }
    }

    private func apply(audit: AuditPayload) {
        readinessStage = audit.readinessStage
        gateStatus = audit.gateStatus
    }

    private func baseURL(from raw: String) -> URL? {
        baseComponents(from: raw)?.url
    }

    private func baseComponents(from raw: String) -> URLComponents? {
        guard var components = URLComponents(string: raw.trimmingCharacters(in: .whitespacesAndNewlines)),
              let scheme = components.scheme,
              !scheme.isEmpty,
              components.host != nil else {
            return nil
        }
        if components.path.hasSuffix("/") {
            components.path.removeLast()
        }
        return components
    }

    private func fetch<T: Decodable>(_ type: T.Type, from url: URL, token: String?) async throws -> T {
        var request = URLRequest(url: url)
        if let token, !token.isEmpty {
            request.setValue("Bearer \(token)", forHTTPHeaderField: "Authorization")
        }
        let (data, response) = try await URLSession.shared.data(for: request)
        let http = try requireHTTP(response)
        guard (200..<300).contains(http.statusCode) else {
            throw SessionError.http(status: http.statusCode)
        }
        return try JSONDecoder().decode(T.self, from: data)
    }

    private func requireHTTP(_ response: URLResponse) throws -> HTTPURLResponse {
        guard let http = response as? HTTPURLResponse else {
            throw SessionError.invalidResponse
        }
        return http
    }
}

private struct TokenRequest: Encodable {
    let username: String
    let password: String
}

private struct TokenResponse: Decodable {
    let accessToken: String
    let role: String
    let username: String

    enum CodingKeys: String, CodingKey {
        case accessToken = "access_token"
        case role
        case username
    }
}

private struct HealthPayload: Decodable {
    let ts: String
    let runtime: RuntimePayload
}

private struct RuntimePayload: Decodable {
    let status: String?
    let mode: String?
    let provider: String?
    let symbol: String?
    let reason: String?
    let runDir: String?

    enum CodingKeys: String, CodingKey {
        case status
        case mode
        case provider
        case symbol
        case reason
        case runDir = "run_dir"
    }
}

private struct SystemStatusPayload: Decodable {
    let mode: String
    let health: String
    let reason: String
    let provider: String
    let symbol: String
}

private struct EnvironmentPayload: Decodable {
    let mode: String
    let targetMode: String
    let runtimeMode: String
    let runID: String
    let resolvedRunDir: String

    enum CodingKeys: String, CodingKey {
        case mode
        case targetMode = "target_mode"
        case runtimeMode = "runtime_mode"
        case runID = "run_id"
        case resolvedRunDir = "resolved_run_dir"
    }
}

private struct AuditPayload: Decodable {
    let gateStatus: String
    let readinessStage: String

    enum CodingKeys: String, CodingKey {
        case gateStatus = "gate_status"
        case readinessStage = "readiness_stage"
    }
}

enum SessionError: LocalizedError {
    case invalidResponse
    case http(status: Int)

    var errorDescription: String? {
        switch self {
        case .invalidResponse:
            return "Invalid HTTP response"
        case let .http(status):
            return "HTTP \(status)"
        }
    }
}
