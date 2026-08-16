import Observation
import PrintworksCore
import SwiftUI
import UserNotifications

@main
struct PrintworksApp: App {
    @State private var runtime = AppRuntime()

    var body: some Scene {
        WindowGroup {
            MainWindow(model: runtime.model)
                .frame(minWidth: 900, minHeight: 600)
                .task(id: runtime.configurationRevision) {
                    let model = runtime.model
                    let watcher = runtime.watcher
                    await observeRepo(model: model, watcher: watcher)
                }
                .onChange(of: runtime.model.busyExternally) { _, _ in
                    updatePolling(model: runtime.model, watcher: runtime.watcher)
                }
        }
        .windowToolbarStyle(.unified)
        .commands { SidebarCommands() }

        Settings {
            SettingsSheet(
                initialRepoPath: runtime.repoPath,
                initialPythonPath: runtime.pythonPath,
                onSave: runtime.save(repoPath:pythonPath:))
        }
    }

    @MainActor
    private func observeRepo(model: AppModel, watcher: RepoWatcher) async {
        // Accessing `changes` registers this consumer. Do that before start so
        // an app-launch filesystem event cannot be emitted into an empty set.
        let changes = watcher.changes
        await model.refresh()
        guard !Task.isCancelled else { return }

        watcher.start()
        updatePolling(model: model, watcher: watcher)

        // The watcher is shared by every WindowGroup scene. A cancelled scene
        // removes only its stream continuation; RepoWatcher.deinit owns stop().
        for await _ in changes {
            guard !Task.isCancelled else { break }
            await model.refresh()
            updatePolling(model: model, watcher: watcher)
        }
    }

    private func updatePolling(model: AppModel, watcher: RepoWatcher) {
        if model.busyExternally {
            watcher.startPolling()
        } else {
            watcher.stopPolling()
        }
    }
}

@Observable
@MainActor
private final class AppRuntime {
    private let defaults: UserDefaults
    private let notifier: PublishNotifier

    private(set) var model: AppModel
    private(set) var watcher: RepoWatcher
    private(set) var repoPath: String
    private(set) var pythonPath: String
    private(set) var configurationRevision = 0

    init(defaults: UserDefaults = .standard) {
        self.defaults = defaults
        let defaultRepoPath = NSString(
            string: "~/Projects/rawdog-printworks"
        ).expandingTildeInPath
        let repoPath = defaults.string(forKey: "repoPath") ?? defaultRepoPath
        let repo = Self.repoURL(repoPath)
        let defaultPythonPath = repo
            .appendingPathComponent(".venv/bin/python").path
        let pythonPath = defaults.string(forKey: "pythonPath")
            ?? defaultPythonPath
        let notifier = PublishNotifier()

        self.repoPath = repoPath
        self.pythonPath = pythonPath
        self.notifier = notifier
        self.model = Self.makeModel(
            repoPath: repoPath, pythonPath: pythonPath, notifier: notifier)
        self.watcher = RepoWatcher(repo: repo)
    }

    func save(repoPath: String, pythonPath: String) {
        // Expand before constructing either URL. Persist the user's spelling so
        // Settings can continue to show a concise ~/ path.
        let repo = Self.repoURL(repoPath)
        let python = Self.pathURL(pythonPath)
        defaults.set(repoPath, forKey: "repoPath")
        defaults.set(pythonPath, forKey: "pythonPath")

        let retiredWatcher = watcher
        Task.detached(priority: .utility) {
            retiredWatcher.stop()
        }
        model = Self.makeModel(repo: repo, python: python, notifier: notifier)
        watcher = RepoWatcher(repo: repo)
        self.repoPath = repoPath
        self.pythonPath = pythonPath
        configurationRevision &+= 1
    }

    private static func makeModel(
        repoPath: String, pythonPath: String, notifier: PublishNotifier
    ) -> AppModel {
        makeModel(repo: repoURL(repoPath), python: pathURL(pythonPath),
                  notifier: notifier)
    }

    private static func makeModel(
        repo: URL, python: URL, notifier: PublishNotifier
    ) -> AppModel {
        let client = PipelineClient(config: PipelineConfig(
            repo: repo, python: python))
        return AppModel(client: client, repo: repo) { published in
            Task { await notifier.post(published) }
        }
    }

    private static func repoURL(_ path: String) -> URL {
        URL(fileURLWithPath: NSString(string: path).expandingTildeInPath,
            isDirectory: true)
    }

    private static func pathURL(_ path: String) -> URL {
        URL(fileURLWithPath: NSString(string: path).expandingTildeInPath)
    }
}

private actor PublishNotifier {
    private var requestedAuthorization = false

    func post(_ photos: [PublishedPhoto]) async {
        guard !photos.isEmpty else { return }
        let center = UNUserNotificationCenter.current()
        if !requestedAuthorization {
            requestedAuthorization = true
            do {
                _ = try await center.requestAuthorization(options: [.alert, .sound])
            } catch {
                return
            }
        }

        let settings = await center.notificationSettings()
        switch settings.authorizationStatus {
        case .authorized, .provisional, .ephemeral:
            break
        case .notDetermined, .denied:
            return
        @unknown default:
            return
        }

        for photo in photos {
            let noun = photo.artifactCount == 1 ? "file" : "files"
            let content = UNMutableNotificationContent()
            content.title = "\(photo.stem) published (\(photo.version), "
                + "\(photo.artifactCount) \(noun))"
            content.sound = .default
            let request = UNNotificationRequest(
                identifier: "publish-\(photo.stem)-\(photo.version)",
                content: content, trigger: nil)
            try? await center.add(request)
        }
    }
}
