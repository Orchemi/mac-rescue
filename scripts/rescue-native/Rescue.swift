import SwiftUI
import AppKit

struct ProcessRow: Decodable, Identifiable {
    let pid: Int, ppid: Int, age: Double, name: String
    let footprint: Double?, rss: Double?, cwd: String, ports: [Int], can_stop: Bool
    var id: Int { pid }
    var title: String { URL(fileURLWithPath: name).lastPathComponent }
}
struct RunGroup: Decodable, Identifiable {
    let root: Int, kind: String, pids: [Int], footprint: Double, age: Double
    let project: String, cwd: String, ports: [Int], reasons: [String], can_stop: Bool, partial: Bool
    var id: Int { root }
    var title: String { project.isEmpty ? "경로 미확인" : URL(fileURLWithPath: project).lastPathComponent }
    var kindLabel: String { kind == "chrome" ? "자동화 Chrome" : "개발 서버" }
}
struct SystemMemory: Decodable {
    let ram: Double, pressure: String, compressed: Double?, swap_used: Double?, disk_free: Double
}
struct Snapshot: Decodable {
    let time: String, system: SystemMemory, rows: [ProcessRow], groups: [RunGroup], warnings: [String]
}
struct StopPlan: Decodable, Identifiable {
    let id: String, phrase: String, force: Bool, mode: String, target: Int, project: String
    let rows: [ProcessRow], footprint: Double
}
struct StopResult: Decodable { let sent: [Int], remaining: [Int], errors: [String], new_children: [Int] }
struct BridgeError: LocalizedError { let message: String; var errorDescription: String? { message } }
func memory(_ bytes: Double?) -> String {
    guard let bytes else { return "측정 불가" }
    return bytes >= 1_073_741_824 ? String(format: "%.2f GiB", bytes / 1_073_741_824) : String(format: "%.0f MiB", bytes / 1_048_576)
}
func age(_ seconds: Double) -> String {
    if seconds >= 86400 { return "\(Int(seconds / 86400))일 \(Int(seconds.truncatingRemainder(dividingBy: 86400) / 3600))시간" }
    if seconds >= 3600 { return "\(Int(seconds / 3600))시간 \(Int(seconds.truncatingRemainder(dividingBy: 3600) / 60))분" }
    return "\(max(1, Int(seconds / 60)))분"
}

// A serial, private pipe carries structured requests. Neither a shell nor HTTP is used.
final class NativeBridge: @unchecked Sendable {
    private let queue = DispatchQueue(label: "dev.horbis.rescue.bridge", qos: .utility)
    private var process: Process?
    private var input: FileHandle?
    private var output: FileHandle?
    private var buffered = Data()
    private func start() throws {
        if let process, process.isRunning { return }
        guard let resources = Bundle.main.resourceURL,
              let config = NSDictionary(contentsOf: resources.appendingPathComponent("Engine.plist")),
              let python = config["Python"] as? String else {
            throw BridgeError(message: "설치 파일을 찾을 수 없습니다. 설치기를 다시 실행해 주세요.")
        }
        let task = Process(), stdin = Pipe(), stdout = Pipe()
        task.executableURL = URL(fileURLWithPath: python)
        task.arguments = ["-u", resources.appendingPathComponent("engine/rescue_native.py").path]
        task.standardInput = stdin; task.standardOutput = stdout; task.standardError = FileHandle.nullDevice
        try task.run()
        process = task; input = stdin.fileHandleForWriting; output = stdout.fileHandleForReading
        buffered.removeAll()
    }
    func request<T: Decodable>(_ values: [String: Any], as type: T.Type) async throws -> T {
        let payload = try JSONSerialization.data(withJSONObject: values) + Data([10])
        let response: Data = try await withCheckedThrowingContinuation { continuation in
            queue.async {
                do {
                    try self.start()
                    try self.input?.write(contentsOf: payload)
                    while !self.buffered.contains(10) {
                        guard let chunk = self.output?.availableData, !chunk.isEmpty else {
                            throw BridgeError(message: "조회 도우미 연결이 끊겼습니다. 새로고침해 주세요.")
                        }
                        self.buffered.append(chunk)
                        if self.buffered.count > 32_000_000 { throw BridgeError(message: "조회 결과가 너무 큽니다.") }
                    }
                    let end = self.buffered.firstIndex(of: 10)!
                    let line = self.buffered.subdata(in: 0..<end)
                    self.buffered.removeSubrange(0...end)
                    guard let envelope = try JSONSerialization.jsonObject(with: line) as? [String: Any] else {
                        throw BridgeError(message: "잘못된 도우미 응답입니다.")
                    }
                    if let error = envelope["error"] as? String { throw BridgeError(message: error) }
                    guard let data = envelope["data"] else { throw BridgeError(message: "응답이 비어 있습니다.") }
                    continuation.resume(returning: try JSONSerialization.data(withJSONObject: data))
                } catch { continuation.resume(throwing: error) }
            }
        }
        return try JSONDecoder().decode(type, from: response)
    }
    func close() {
        // Closing stdin ends the owned helper. It does not signal any observed process.
        queue.async { try? self.input?.close(); self.input = nil }
    }
}

@MainActor final class Monitor: ObservableObject {
    @Published var snapshot: Snapshot?
    @Published var refreshing = false
    @Published var mutating = false
    @Published var error: String?
    @Published var message = ""
    @Published var plan: StopPlan?
    let bridge = NativeBridge()
    func refresh() async {
        guard !refreshing, !mutating else { return }
        refreshing = true
        defer { refreshing = false }
        do { snapshot = try await bridge.request(["method":"status"], as: Snapshot.self); error = nil }
        catch { self.error = error.localizedDescription }
    }
    func preview(_ pid: Int, mode: String, force: Bool = false) async {
        guard !mutating else { return }
        mutating = true
        defer { mutating = false }
        do { plan = try await bridge.request(["method":"plan", "target":pid, "mode":mode, "force":force], as: StopPlan.self) }
        catch { self.error = error.localizedDescription }
    }
    func execute(_ plan: StopPlan, phrase: String) async {
        guard !mutating else { return }
        mutating = true
        do {
            let result = try await bridge.request(["method":"execute", "id":plan.id, "phrase":phrase], as: StopResult.self)
            message = "\(result.sent.count)개 프로세스에 종료 신호를 보냈습니다." + (result.remaining.isEmpty ? "" : " \(result.remaining.count)개가 아직 실행 중입니다.")
            if !result.errors.isEmpty { message += " " + result.errors.joined(separator: " · ") }
            if !result.new_children.isEmpty { message += " 새 자식 \(result.new_children.count)개는 종료 대상에 추가하지 않았습니다." }
            self.plan = nil
        } catch { self.error = error.localizedDescription; self.plan = nil }
        mutating = false
        await refresh()
    }
}

struct NativeSearch: NSViewRepresentable {
    @Binding var text: String
    func makeCoordinator() -> Coordinator { Coordinator(self) }
    func makeNSView(context: Context) -> NSSearchField {
        let field = NSSearchField()
        field.placeholderString = "프로젝트, 프로세스, PID 검색"
        field.setAccessibilityLabel("프로젝트, 프로세스, PID 검색")
        field.delegate = context.coordinator
        field.sendsSearchStringImmediately = true
        return field
    }
    func updateNSView(_ field: NSSearchField, context: Context) {
        context.coordinator.parent = self
        if field.stringValue != text { field.stringValue = text }
    }
    final class Coordinator: NSObject, NSSearchFieldDelegate {
        var parent: NativeSearch
        init(_ parent: NativeSearch) { self.parent = parent }
        func controlTextDidChange(_ notification: Notification) {
            if let field = notification.object as? NSSearchField { parent.text = field.stringValue }
        }
    }
}

struct Metric: View {
    let title: String, value: String, caption: String, symbol: String
    var color: Color = .primary
    var body: some View {
        VStack(alignment: .leading, spacing: 10) {
            Label(title, systemImage: symbol).font(.subheadline).foregroundStyle(.secondary)
            Text(value).font(.system(size: 26, weight: .semibold, design: .rounded)).monospacedDigit().foregroundStyle(color)
            Text(caption).font(.caption).foregroundStyle(.secondary).lineLimit(2)
        }.frame(maxWidth: .infinity, minHeight: 94, alignment: .leading).padding(16)
            .background(.background, in: RoundedRectangle(cornerRadius: 12))
            .overlay(RoundedRectangle(cornerRadius: 12).stroke(.quaternary))
    }
}

struct RescueWindow: View {
    @StateObject private var model = Monitor()
    @State private var page = "groups"
    @State private var selection: Int?
    @State private var selectedProcess: Int?
    @State private var query = ""
    @State private var filter = "all"
    @State private var order = "memory"
    @State private var automatic = true
    @Environment(\.scenePhase) private var phase
    private let timer = Timer.publish(every: 15, on: .main, in: .common).autoconnect()
    var groups: [RunGroup] {
        (model.snapshot?.groups ?? []).filter {
            (query.isEmpty || "\($0.project) \($0.cwd) \($0.root)".localizedCaseInsensitiveContains(query)) &&
            (filter == "all" || (filter == "large" ? $0.footprint >= 2_147_483_648 : $0.age >= 86400))
        }.sorted { order == "age" ? $0.age > $1.age : order == "name" ? $0.title < $1.title : $0.footprint > $1.footprint }
    }
    var processes: [ProcessRow] {
        (model.snapshot?.rows ?? []).filter {
            (query.isEmpty || "\($0.name) \($0.pid) \($0.cwd)".localizedCaseInsensitiveContains(query)) &&
            (filter == "all" || (filter == "large" ? ($0.footprint ?? 0) >= 2_147_483_648 : $0.age >= 86400))
        }.sorted { order == "age" ? $0.age > $1.age : order == "name" ? $0.title < $1.title : ($0.footprint ?? 0) > ($1.footprint ?? 0) }
    }
    var body: some View {
        NavigationSplitView {
            List(selection: $page) {
                Label("실행 그룹", systemImage: "square.stack.3d.up").tag("groups")
                Label("전체 프로세스", systemImage: "list.bullet.rectangle").tag("processes")
                Label("실행과 복구", systemImage: "lifepreserver").tag("guide")
            }.navigationTitle("Rescue").navigationSplitViewColumnWidth(min: 170, ideal: 190, max: 240)
            VStack(alignment: .leading, spacing: 6) {
                Label("이 Mac에서만 실행", systemImage: "desktopcomputer").font(.caption)
                Text("오래됐다는 이유만으로\n종료할 필요는 없습니다.").font(.caption).foregroundStyle(.secondary)
            }.padding()
        } detail: {
            if page == "guide" { guide }
            else {
                VStack(alignment: .leading, spacing: 18) {
                    HStack(alignment: .firstTextBaseline) {
                        VStack(alignment: .leading, spacing: 5) {
                            Text(page == "groups" ? "실행 그룹" : "전체 프로세스").font(.largeTitle.bold())
                            Text(page == "groups" ? "프로젝트별 메모리와 실행 시간을 확인하세요." : "개발·자동화 프로세스만 여기에서 종료할 수 있습니다.").foregroundStyle(.secondary)
                        }
                        Spacer()
                        if model.refreshing { ProgressView().controlSize(.small) }
                        Toggle("자동 갱신", isOn: $automatic).toggleStyle(.switch).controlSize(.small)
                    }
                    if let snap = model.snapshot {
                        HStack(spacing: 12) {
                            Metric(title: "메모리 압력", value: snap.system.pressure, caption: "물리 RAM \(memory(snap.system.ram))", symbol: "gauge.with.dots.needle.67percent", color: snap.system.pressure == "정상" ? .green : .orange)
                            Metric(title: "실행 그룹 점유량", value: memory(snap.groups.reduce(0) { $0 + $1.footprint }), caption: "\(snap.groups.count)개 그룹 · 압축·스왑 포함", symbol: "memorychip")
                            Metric(title: "스왑 사용", value: memory(snap.system.swap_used), caption: "압축 \(memory(snap.system.compressed))", symbol: "arrow.left.arrow.right")
                            Metric(title: "디스크 여유", value: memory(snap.system.disk_free), caption: "데이터 볼륨", symbol: "internaldrive")
                        }
                    }
                    HStack {
                        NativeSearch(text: $query).frame(width: 270, height: 24)
                        Spacer()
                    }
                    HStack {
                        Picker("검토 조건", selection: $filter) {
                            Text("전체").tag("all"); Text("2 GiB 이상").tag("large"); Text("24시간 이상").tag("old")
                        }.pickerStyle(.segmented).frame(width: 300)
                        Spacer()
                        Picker("정렬", selection: $order) {
                            Text("메모리 높은 순").tag("memory"); Text("오래된 순").tag("age"); Text("이름순").tag("name")
                        }.frame(width: 195)
                    }
                    if page == "groups" { groupTable } else { processTable }
                    HStack {
                        Text("점유량은 종료 후 확보되는 RAM과 다릅니다.")
                        Spacer()
                        Text(model.snapshot.map { String($0.time.suffix(14).prefix(8)) + " 측정" } ?? "조회 중…")
                    }.font(.caption).foregroundStyle(.secondary)
                    if !model.message.isEmpty {
                        HStack { Label(model.message, systemImage: "checkmark.circle"); Spacer(); Button("닫기") { model.message = "" } }.font(.callout)
                    }
                    if let warnings = model.snapshot?.warnings, !warnings.isEmpty {
                        Text(warnings.joined(separator: " · ")).font(.caption).foregroundStyle(.orange)
                    }
                }.padding(24).background(Color(nsColor: .windowBackgroundColor))
            }
        }

        .toolbar {
            ToolbarItem { Button { Task { await model.refresh() } } label: { Label("새로고침", systemImage: "arrow.clockwise") }.keyboardShortcut("r").disabled(model.refreshing || model.mutating) }
        }
        .inspector(isPresented: Binding(get: { selection != nil || selectedProcess != nil }, set: { if !$0 { selection = nil; selectedProcess = nil } })) {
            VStack(spacing: 0) {
                HStack {
                    Text("상세").font(.headline)
                    Spacer()
                    Button { selection = nil; selectedProcess = nil } label: { Image(systemName: "xmark") }
                        .buttonStyle(.plain).accessibilityLabel("상세 닫기").help("상세 닫기")
                }.padding(16)
                Divider()
            if let id = selection, let group = model.snapshot?.groups.first(where: { $0.root == id }) {
                GroupDetail(group: group, rows: model.snapshot?.rows ?? [], model: model)
            } else if let id = selectedProcess, let row = model.snapshot?.rows.first(where: { $0.pid == id }) {
                ProcessDetail(row: row, model: model)
            } else { Text("선택한 실행이 종료됐습니다.").foregroundStyle(.secondary).padding() }
            }
        }.inspectorColumnWidth(min: 300, ideal: 360, max: 480)
        .sheet(item: $model.plan) { plan in Confirmation(plan: plan, model: model) }
        .alert("작업을 완료하지 못했습니다", isPresented: Binding(get: { model.error != nil }, set: { if !$0 { model.error = nil } })) {
            Button("확인") { model.error = nil }
        } message: { Text(model.error ?? "") }
        .task { await model.refresh() }
        .onReceive(timer) { _ in if automatic && phase == .active && model.plan == nil { Task { await model.refresh() } } }
        .onChange(of: page) { _, _ in selection = nil; selectedProcess = nil; query = "" }
        .onReceive(NotificationCenter.default.publisher(for: NSApplication.willTerminateNotification)) { _ in model.bridge.close() }
    }
    var groupTable: some View {
        Table(groups, selection: $selection) {
            TableColumn("프로젝트 / 실행") { group in
                HStack(spacing: 10) {
                    Image(systemName: group.kind == "chrome" ? "globe" : "terminal").foregroundStyle(.teal).frame(width: 20)
                    VStack(alignment: .leading, spacing: 4) {
                        Text(group.title).fontWeight(.medium).lineLimit(1)
                        Text("\(group.kindLabel) · \(group.pids.count)개 · ROOT \(String(group.root))").font(.caption).foregroundStyle(.secondary)
                    }.padding(.vertical, 7)
                }
            }.width(min: 190, ideal: 270)
            TableColumn("메모리") { Text(memory($0.footprint) + ($0.partial ? " *" : "")).monospacedDigit().fontWeight(.medium) }.width(105)
            TableColumn("실행 시간") { Text(age($0.age)).monospacedDigit() }.width(100)
            TableColumn("검토 근거") { Text($0.reasons.joined(separator: " · ")).font(.caption).foregroundStyle(.secondary).lineLimit(2) }.width(min: 100, ideal: 200)
        }.overlay { if groups.isEmpty && !model.refreshing { ContentUnavailableView("표시할 실행이 없습니다", systemImage: "line.3.horizontal.decrease.circle", description: Text("검색어 또는 검토 조건을 바꿔 보세요.")) } }
    }
    var processTable: some View {
        Table(processes, selection: $selectedProcess) {
            TableColumn("프로세스") { Text($0.title).help($0.name) }.width(min: 160, ideal: 240)
            TableColumn("PID") { Text(String($0.pid)).monospacedDigit() }.width(65)
            TableColumn("부모 PID") { Text(String($0.ppid)).monospacedDigit() }.width(70)
            TableColumn("메모리") { Text(memory($0.footprint)).monospacedDigit() }.width(110)
            TableColumn("실행 시간") { Text(age($0.age)).monospacedDigit() }.width(100)
            TableColumn("관리") { Text($0.can_stop ? "종료 가능" : "조회 전용").foregroundStyle(.secondary) }.width(75)
        }.overlay { if processes.isEmpty { ContentUnavailableView.search(text: query) } }
    }
    var guide: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 24) {
                Label("실행과 복구", systemImage: "lifepreserver").font(.largeTitle.bold())
                Text("Mac에서는 Rescue 앱, 모바일에서는 rescue 한 단어.").font(.title3)
                GroupBox("Termius로 이 Mac에 연결한 뒤") {
                    VStack(alignment: .leading, spacing: 14) {
                        command("rescue", "메모리와 실행 그룹 조회")
                        command("rescue watch", "15초마다 비교 · Ctrl-C로 종료")
                        command("rescue remote-check", "Tailscale·SSH 상태 확인")
                        command("rescue config", "개인 설정 검증 · 값은 마스킹")
                    }.padding(12).frame(maxWidth: .infinity, alignment: .leading)
                }
                GroupBox("포맷 후 복원") {
                    VStack(alignment: .leading, spacing: 12) {
                        Text("Python 3과 Xcode Command Line Tools를 준비하고, 백업한 mac-rescue 저장소에서 실행하세요.")
                        command("python3 scripts/install-rescue.py", "앱과 짧은 명령을 함께 재설치")
                        Text("개인 설정은 비공개 Obsidian 노트에서 .env.local로 복원한 뒤 설치하세요. .env.local.example은 마스킹된 키 목록이며 실제 값은 Git과 앱 번들에 포함되지 않습니다.").foregroundStyle(.secondary)
                        Text("원격 Git 백업은 커밋·푸시가 끝나야 완료됩니다. Tailscale 로그인과 Mac 원격 로그인은 새 Mac에서 다시 설정합니다.").foregroundStyle(.secondary)
                    }.padding(12)
                }
                Text("Rescue는 SwiftUI 창과 전용 조회 도우미로 동작합니다. 앱을 종료하면 도우미도 끝납니다. 시스템 전체 멈춤·절전·FileVault 재부팅 잠금은 SSH만으로 복구할 수 있다고 보장하지 않습니다.").foregroundStyle(.secondary)
                Text("개발 서버·자동화 Chrome의 검토 근거를 표시하며, 오래된 실행이나 메모리 누수를 자동 확정하지 않습니다.").foregroundStyle(.secondary)
            }.padding(32).frame(maxWidth: 760, alignment: .leading)
        }
    }
    func command(_ value: String, _ caption: String) -> some View {
        HStack { VStack(alignment: .leading, spacing: 4) { Text(value).font(.system(.body, design: .monospaced)).textSelection(.enabled); Text(caption).font(.caption).foregroundStyle(.secondary) }; Spacer(); Button("복사") { NSPasteboard.general.clearContents(); NSPasteboard.general.setString(value, forType: .string) } }
    }
}

struct GroupDetail: View {
    let group: RunGroup, rows: [ProcessRow]
    @ObservedObject var model: Monitor
    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 20) {
                Label(group.kindLabel, systemImage: group.kind == "chrome" ? "globe" : "terminal").foregroundStyle(.secondary)
                Text(group.title).font(.title2.bold()).textSelection(.enabled)
                Text(group.cwd.isEmpty ? "작업 경로 미확인" : group.cwd).font(.caption).foregroundStyle(.secondary).textSelection(.enabled)
                HStack { Text(memory(group.footprint)).font(.title.bold()).monospacedDigit(); Spacer(); Text(age(group.age)).foregroundStyle(.secondary) }
                Text("ROOT \(String(group.root)) · \(group.pids.count)개 프로세스").font(.callout).monospacedDigit()
                if !group.ports.isEmpty { Text("포트 " + group.ports.map(String.init).joined(separator: ", ")).font(.callout).textSelection(.enabled) }
                if !group.reasons.isEmpty { Label(group.reasons.joined(separator: "\n"), systemImage: "exclamationmark.circle").font(.callout).foregroundStyle(.orange) }
                Text("이 실행 묶음을 종료하면 개발 페이지 또는 자동화 작업이 중단됩니다.").font(.callout).foregroundStyle(.secondary)
                Button("그룹 종료…", role: .destructive) { Task { await model.preview(group.root, mode: "group") } }.buttonStyle(.borderedProminent).tint(.red).disabled(!group.can_stop || model.mutating)
                Button("강제 종료…", role: .destructive) { Task { await model.preview(group.root, mode: "group", force: true) } }.disabled(!group.can_stop || model.mutating)
                Divider()
                Text("구성 프로세스").font(.headline)
                ForEach(rows.filter { group.pids.contains($0.pid) }) { row in
                    VStack(alignment: .leading, spacing: 6) {
                        Text(row.title).fontWeight(.medium).lineLimit(2)
                        Text("PID \(String(row.pid)) ← 부모 \(String(row.ppid))").font(.caption).monospacedDigit().foregroundStyle(.secondary)
                        HStack { Text(memory(row.footprint)).monospacedDigit(); Spacer(); Button("개별 종료…") { Task { await model.preview(row.pid, mode: "pid") } }.disabled(!row.can_stop || model.mutating) }.font(.caption)
                    }.padding(.vertical, 4)
                    Divider()
                }
            }.padding(20)
        }
    }
}
struct ProcessDetail: View {
    let row: ProcessRow
    @ObservedObject var model: Monitor
    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 18) {
                Text(row.title).font(.title2.bold())
                Text(row.name).font(.caption).textSelection(.enabled)
                Text(memory(row.footprint)).font(.largeTitle).monospacedDigit()
                Text("PID \(String(row.pid)) ← 부모 \(String(row.ppid))").monospacedDigit()
                Text("실행 시간 \(age(row.age))")
                Text(row.cwd).font(.caption).textSelection(.enabled)
                if row.can_stop {
                    Button("프로세스 종료…", role: .destructive) { Task { await model.preview(row.pid, mode: "pid") } }.disabled(model.mutating)
                    Button("강제 종료…", role: .destructive) { Task { await model.preview(row.pid, mode: "pid", force: true) } }.disabled(model.mutating)
                } else { Label("보호 대상 또는 관리 범위 밖입니다.\n여기에서는 조회만 가능합니다.", systemImage: "lock").foregroundStyle(.secondary) }
            }.padding(24)
        }
    }
}
struct Confirmation: View {
    let plan: StopPlan
    @ObservedObject var model: Monitor
    @Environment(\.dismiss) private var dismiss
    @State private var phrase = ""
    @FocusState private var focused: Bool
    var body: some View {
        VStack(alignment: .leading, spacing: 18) {
            Label(plan.force ? "강제 종료 확인" : "실행 종료 확인", systemImage: "exclamationmark.triangle.fill").font(.title2.bold()).foregroundStyle(.red)
            Text("\(URL(fileURLWithPath: plan.project).lastPathComponent) · \(plan.rows.count)개 · \(memory(plan.footprint))").font(.headline)
            Text(plan.force ? "즉시 중단되어 정리 작업이 실행되지 않고 저장하지 않은 내용이 사라질 수 있습니다." : "아래 프로세스에 종료 신호를 보냅니다. 해당 개발 페이지나 자동화 작업이 중단될 수 있습니다.").foregroundStyle(.secondary)
            Table(plan.rows) {
                TableColumn("프로세스") { Text($0.title) }
                TableColumn("PID") { Text(String($0.pid)) }.width(65)
                TableColumn("메모리") { Text(memory($0.footprint)) }.width(100)
            }.frame(height: 180)
            Text("60초 안에 ‘\(plan.phrase)’를 입력하세요.").font(.callout)
            TextField("확인 문구", text: $phrase).textFieldStyle(.roundedBorder).focused($focused).accessibilityLabel("확인 문구")
            HStack {
                Spacer()
                Button("취소") { dismiss() }.keyboardShortcut(.cancelAction).disabled(model.mutating)
                Button(plan.force ? "강제 종료" : "종료 실행", role: .destructive) { Task { await model.execute(plan, phrase: phrase) } }.buttonStyle(.borderedProminent).tint(.red).disabled(phrase != plan.phrase || model.mutating)
            }
        }.padding(28).frame(width: 550).interactiveDismissDisabled(model.mutating).onAppear { focused = true }
    }
}

final class RescueDelegate: NSObject, NSApplicationDelegate {
    func applicationShouldTerminateAfterLastWindowClosed(_ sender: NSApplication) -> Bool { true }
}
@main struct RescueApp: App {
    @NSApplicationDelegateAdaptor(RescueDelegate.self) private var delegate
    var body: some Scene {
        Window("Rescue", id: "main") { RescueWindow().frame(minWidth: 1000, minHeight: 640) }
            .defaultSize(width: 1220, height: 820)
            .commands { CommandGroup(replacing: .newItem) {} }
    }
}
