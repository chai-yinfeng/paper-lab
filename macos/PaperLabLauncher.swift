import AppKit
import Foundation

@main
final class PaperLabLauncher: NSObject, NSApplicationDelegate {
    static func main() {
        let app = NSApplication.shared
        let delegate = PaperLabLauncher()
        app.delegate = delegate
        app.run()
    }

    private let serverURL = URL(string: "http://127.0.0.1:8765/")!
    private var statusItem: NSStatusItem!
    private var statusLine: NSMenuItem!
    private var startItem: NSMenuItem!
    private var restartItem: NSMenuItem!
    private var stopItem: NSMenuItem!
    private var process: Process?
    private var timer: Timer?
    private var restartPending = false
    private var openWhenReady = false

    func applicationDidFinishLaunching(_ notification: Notification) {
        NSApp.setActivationPolicy(.accessory)
        makeMenu()
        probe { [weak self] running in
            guard let self else { return }
            if running {
                self.setStatus("运行中（现有进程）", owned: false, running: true)
                self.openPage(nil)
            } else {
                self.start(openBrowser: true)
            }
        }
    }

    func applicationWillTerminate(_ notification: Notification) {
        timer?.invalidate()
        restartPending = false
        if let process, process.isRunning { process.terminate() }
    }

    func applicationShouldHandleReopen(
        _ sender: NSApplication, hasVisibleWindows flag: Bool
    ) -> Bool {
        openPage(nil)
        return true
    }

    private func makeMenu() {
        statusItem = NSStatusBar.system.statusItem(withLength: NSStatusItem.squareLength)
        if let button = statusItem.button {
            button.image = NSImage(
                systemSymbolName: "doc.text.magnifyingglass",
                accessibilityDescription: "Paper Lab"
            )
            button.image?.isTemplate = true
        }
        let menu = NSMenu()
        statusLine = NSMenuItem(title: "状态：正在检查…", action: nil, keyEquivalent: "")
        statusLine.isEnabled = false
        menu.addItem(statusLine)
        menu.addItem(.separator())
        menu.addItem(menuItem("打开 Paper Lab", #selector(openPage), "o"))
        startItem = menuItem("启动服务", #selector(startFromMenu), "s")
        restartItem = menuItem("重启服务", #selector(restart), "r")
        stopItem = menuItem("停止服务", #selector(stop), "")
        menu.addItem(startItem)
        menu.addItem(restartItem)
        menu.addItem(stopItem)
        menu.addItem(.separator())
        menu.addItem(menuItem("查看日志", #selector(openLog), "l"))
        menu.addItem(.separator())
        menu.addItem(menuItem("退出 Paper Lab", #selector(quit), "q"))
        statusItem.menu = menu
        setStatus("正在检查…", owned: false, running: false)
    }

    private func menuItem(_ title: String, _ action: Selector, _ key: String) -> NSMenuItem {
        let item = NSMenuItem(title: title, action: action, keyEquivalent: key)
        item.target = self
        return item
    }

    @objc private func openPage(_ sender: Any?) {
        NSWorkspace.shared.open(serverURL)
    }

    @objc private func startFromMenu(_ sender: Any?) {
        start(openBrowser: true)
    }

    private func start(openBrowser: Bool) {
        guard process == nil else {
            if openBrowser { openPage(nil) }
            return
        }
        guard let repo = repositoryURL() else {
            showError("找不到 Paper Lab 仓库。请重新运行安装脚本。")
            return
        }
        guard let uv = uvURL() else {
            showError("找不到 uv。请先运行 brew install uv。")
            return
        }
        do {
            let logURL = try logDirectory().appendingPathComponent("server.log")
            if !FileManager.default.fileExists(atPath: logURL.path) {
                FileManager.default.createFile(atPath: logURL.path, contents: nil)
            }
            let log = try FileHandle(forWritingTo: logURL)
            try log.seekToEnd()
            log.write(Data("\n--- Paper Lab started \(Date()) ---\n".utf8))

            let child = Process()
            child.executableURL = uv
            child.arguments = ["run", "--locked", "python", "-m", "paper_lab"]
            child.currentDirectoryURL = repo
            child.standardOutput = log
            child.standardError = log
            var environment = ProcessInfo.processInfo.environment
            environment["PATH"] = "/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin"
            child.environment = environment
            child.terminationHandler = { [weak self] finished in
                DispatchQueue.main.async {
                    try? log.close()
                    guard let self, self.process === finished else { return }
                    self.process = nil
                    self.timer?.invalidate()
                    self.timer = nil
                    if self.restartPending {
                        self.restartPending = false
                        self.start(openBrowser: true)
                    } else {
                        self.setStatus("已停止", owned: false, running: false)
                    }
                }
            }
            try child.run()
            process = child
            openWhenReady = openBrowser
            setStatus("正在启动…", owned: true, running: false)
            waitUntilReady()
        } catch {
            process = nil
            setStatus("启动失败", owned: false, running: false)
            showError("无法启动 Paper Lab：\(error.localizedDescription)")
        }
    }

    private func waitUntilReady() {
        timer?.invalidate()
        var attempts = 0
        timer = Timer.scheduledTimer(withTimeInterval: 0.25, repeats: true) {
            [weak self] timer in
            guard let self else { timer.invalidate(); return }
            attempts += 1
            self.probe { running in
                if running {
                    timer.invalidate()
                    self.timer = nil
                    self.setStatus("运行中", owned: true, running: true)
                    if self.openWhenReady {
                        self.openWhenReady = false
                        self.openPage(nil)
                    }
                } else if attempts >= 80 {
                    timer.invalidate()
                    self.timer = nil
                    self.setStatus("启动超时", owned: true, running: false)
                    self.showError("服务未能在 20 秒内启动，请查看日志。")
                }
            }
        }
    }

    @objc private func stop(_ sender: Any?) {
        restartPending = false
        timer?.invalidate()
        timer = nil
        guard let process, process.isRunning else {
            setStatus("已停止", owned: false, running: false)
            return
        }
        setStatus("正在停止…", owned: true, running: false)
        process.terminate()
    }

    @objc private func restart(_ sender: Any?) {
        guard let process, process.isRunning else {
            start(openBrowser: true)
            return
        }
        restartPending = true
        timer?.invalidate()
        timer = nil
        setStatus("正在重启…", owned: true, running: false)
        process.terminate()
    }

    @objc private func openLog(_ sender: Any?) {
        do {
            let directory = try logDirectory()
            let log = directory.appendingPathComponent("server.log")
            NSWorkspace.shared.open(
                FileManager.default.fileExists(atPath: log.path) ? log : directory
            )
        } catch {
            showError("无法打开日志目录：\(error.localizedDescription)")
        }
    }

    @objc private func quit(_ sender: Any?) { NSApp.terminate(nil) }

    private func setStatus(_ text: String, owned: Bool, running: Bool) {
        statusLine.title = "状态：\(text)"
        startItem.isEnabled = !running && process == nil
        stopItem.isEnabled = owned && process?.isRunning == true
        restartItem.isEnabled = owned && process?.isRunning == true
        statusItem.button?.toolTip = "Paper Lab · \(text)"
    }

    private func probe(completion: @escaping (Bool) -> Void) {
        var request = URLRequest(url: serverURL.appendingPathComponent("api/status"))
        request.timeoutInterval = 0.5
        URLSession.shared.dataTask(with: request) { _, response, _ in
            let ok = (response as? HTTPURLResponse)?.statusCode == 200
            DispatchQueue.main.async { completion(ok) }
        }.resume()
    }

    private func repositoryURL() -> URL? {
        guard
            let resource = Bundle.main.url(forResource: "repo-path", withExtension: "txt"),
            let raw = try? String(contentsOf: resource, encoding: .utf8)
        else { return nil }
        let path = raw.trimmingCharacters(in: .whitespacesAndNewlines)
        let url = URL(fileURLWithPath: path, isDirectory: true)
        return FileManager.default.fileExists(
            atPath: url.appendingPathComponent("pyproject.toml").path
        ) ? url : nil
    }

    private func uvURL() -> URL? {
        let home = FileManager.default.homeDirectoryForCurrentUser
        let candidates = [
            "/opt/homebrew/bin/uv",
            "/usr/local/bin/uv",
            home.appendingPathComponent(".local/bin/uv").path,
        ]
        return candidates.first {
            FileManager.default.isExecutableFile(atPath: $0)
        }.map { URL(fileURLWithPath: $0) }
    }

    private func logDirectory() throws -> URL {
        let url = FileManager.default.homeDirectoryForCurrentUser
            .appendingPathComponent("Library/Logs/Paper Lab", isDirectory: true)
        try FileManager.default.createDirectory(at: url, withIntermediateDirectories: true)
        return url
    }

    private func showError(_ message: String) {
        let alert = NSAlert()
        alert.alertStyle = .warning
        alert.messageText = "Paper Lab"
        alert.informativeText = message
        alert.addButton(withTitle: "好")
        NSApp.activate(ignoringOtherApps: true)
        alert.runModal()
    }
}
