import SwiftUI
import WebKit

struct UniverseWebView: View {
    let url: URL
    let token: String

    var body: some View {
        WebViewRepresentable(url: url, token: token)
            .clipShape(RoundedRectangle(cornerRadius: 26, style: .continuous))
            .overlay(
                RoundedRectangle(cornerRadius: 26, style: .continuous)
                    .stroke(.white.opacity(0.08), lineWidth: 1)
            )
    }
}

private func makeConfiguration(token: String) -> WKWebViewConfiguration {
    let configuration = WKWebViewConfiguration()
    let controller = WKUserContentController()
    if !token.isEmpty {
        let escaped = token
            .replacingOccurrences(of: "\\", with: "\\\\")
            .replacingOccurrences(of: "'", with: "\\'")
        let script = "window.localStorage.setItem('universe.token', '\(escaped)');"
        controller.addUserScript(WKUserScript(source: script, injectionTime: .atDocumentStart, forMainFrameOnly: false))
    }
    configuration.userContentController = controller
    configuration.defaultWebpagePreferences.allowsContentJavaScript = true
    return configuration
}

#if os(iOS)
struct WebViewRepresentable: UIViewRepresentable {
    let url: URL
    let token: String

    func makeUIView(context: Context) -> WKWebView {
        let view = WKWebView(frame: .zero, configuration: makeConfiguration(token: token))
        view.navigationDelegate = context.coordinator
        view.allowsBackForwardNavigationGestures = true
        view.isOpaque = false
        view.backgroundColor = .clear
        view.scrollView.backgroundColor = .clear
        view.load(URLRequest(url: url))
        return view
    }

    func updateUIView(_ webView: WKWebView, context: Context) {
        if webView.url != url {
            webView.load(URLRequest(url: url))
        }
    }

    func makeCoordinator() -> Coordinator { Coordinator() }
}
#else
struct WebViewRepresentable: NSViewRepresentable {
    let url: URL
    let token: String

    func makeNSView(context: Context) -> WKWebView {
        let view = WKWebView(frame: .zero, configuration: makeConfiguration(token: token))
        view.navigationDelegate = context.coordinator
        view.allowsBackForwardNavigationGestures = true
        view.setValue(false, forKey: "drawsBackground")
        view.load(URLRequest(url: url))
        return view
    }

    func updateNSView(_ webView: WKWebView, context: Context) {
        if webView.url != url {
            webView.load(URLRequest(url: url))
        }
    }

    func makeCoordinator() -> Coordinator { Coordinator() }
}
#endif

final class Coordinator: NSObject, WKNavigationDelegate {}
