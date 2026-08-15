import SwiftUI
import PrintworksCore

@main
struct PrintworksApp: App {
    @State private var model: AppModel
    private let watcher: RepoWatcher

    init() {
        let defaults = UserDefaults.standard
        let defaultRepoPath = NSString(
            string: "~/Projects/rawdog-printworks"
        ).expandingTildeInPath
        let repoPath = NSString(
            string: defaults.string(forKey: "repoPath") ?? defaultRepoPath
        ).expandingTildeInPath
        let repo = URL(fileURLWithPath: repoPath, isDirectory: true)
        let defaultPythonPath = repo
            .appendingPathComponent(".venv/bin/python").path
        let pythonPath = NSString(
            string: defaults.string(forKey: "pythonPath") ?? defaultPythonPath
        ).expandingTildeInPath
        let client = PipelineClient(config: PipelineConfig(
            repo: repo,
            python: URL(fileURLWithPath: pythonPath)
        ))

        _model = State(initialValue: AppModel(client: client, repo: repo))
        watcher = RepoWatcher(repo: repo)
    }

    var body: some Scene {
        WindowGroup {
            MainWindow(model: model)
                .frame(minWidth: 900, minHeight: 600)
                .task { await observeRepo() }
                .onChange(of: model.busyExternally) { _, _ in
                    updatePolling()
                }
        }
        .windowToolbarStyle(.unified)
        .commands { SidebarCommands() }
    }

    @MainActor
    private func observeRepo() async {
        // Accessing `changes` registers this consumer. Do that before start so
        // an app-launch filesystem event cannot be emitted into an empty set.
        let changes = watcher.changes
        await model.refresh()
        guard !Task.isCancelled else { return }

        watcher.start()
        updatePolling()

        // The watcher is shared by every WindowGroup scene. A cancelled scene
        // removes only its stream continuation; RepoWatcher.deinit owns stop().
        for await _ in changes {
            guard !Task.isCancelled else { break }
            await model.refresh()
            updatePolling()
        }
    }

    private func updatePolling() {
        if model.busyExternally {
            watcher.startPolling()
        } else {
            watcher.stopPolling()
        }
    }
}
