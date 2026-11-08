# LogicSpace changelog

## 3.1.0 — Release candidate (unpublished)

- Prepared Windows 10/11 x64 installer and portable ZIP from the same application and simulator, with per-user data storage and an uninstaller that preserves user files.
- Added a native Windows CI workflow for tests, package builds, checksum checks, launch smoke tests, reinstall and uninstall. Earlier Windows CI for the 3.0.0-based branch passed 337 tests with one platform-specific skip; the 3.1.0 candidate needs its own successful run.
- Kept Ubuntu/Linux source installation and older project formats. The source-release allowlist now includes reviewed Windows build files while excluding the separately built website.
- External HDL tools remain unavailable on Windows because the restricted runner currently depends on Linux Bubblewrap. The packages are unsigned; interactive Windows testing and third-party distribution review remain release gates.

## 3.0.0 — Public source release candidate

- Prepared a project-local Git repository, Ubuntu CI test workflow, source ZIP packaging, contribution/security guidance, issue templates and an English release README with application screenshots.
- Added a bounded GitHub Releases check with SemVer comparison, daily automatic checks, opt-out and prerelease settings. The Update Now action opens the validated official release page for manual installation because editable source checkouts cannot be replaced safely in place.
- Kept user projects and data stores outside release files. No in-place updater, Linux binary package, license or verified external HDL/FPGA toolchain result is claimed.

## 3.0 — Public release preparation (development build)

- Fixed nondeterministic sequential input sampling: clock and asynchronous-reset pins are read after combinational drivers settle. Added stable topological ordering and cached unchanged ordering; validation reuses pin interfaces within each pass.
- Added a checked asynchronous-reset HDL subset for D Flip-Flops and Registers, with active-high or active-low reset priority and Time Travel restoration. Constant-index partial vector assignments preserve known and unknown bits. Unsupported forms remain explicit errors.
- Fixed import of exported HDL register reset logic by accepting the generated known-literal case-equality and concatenation forms; the shipped 8-bit register now passes import → export → import behavior tests.
- Added project search (`Ctrl+F`) and source snapshot navigation between imported HDL signals and actual circuit components. Optional `hdl_sources` metadata is backward compatible with version-1 project JSON.
- Added RAM/ROM address watchpoints to Advanced Debugger, including Time Travel re-arming and confirmed Memory Inspector mutations.
- Added a direct half-adder starter action, in-app guide (`F1`), About dialog, and local comparable benchmark history.
- Added optional VCD export from an actual restricted Icarus testbench run, with bounded output validation. No external-tool result is synthesized when tools are absent.
- Public release acceptance still requires testing on machines with external HDL tools, device-specific FPGA toolchains, and broader physical GUI interaction. Logical steps remain distinct from physical timing.

## 2.5 — Sequential HDL and FPGA workflow (limited subset)

- Added checked procedural HDL parsing for combinational `always` and single-edge clocked `always`/`always_ff`, `if/else`, `case`, blocking and nonblocking assignments. Imported clocked outputs become ordinary D Flip-Flops or Registers and use the existing Simulator and Time Travel.
- Added explicit RAM asynchronous/synchronous read modes, read enable, initialized contents, read-during-write policies and X handling, plus synchronous ROM reads. Legacy RAM read behavior remains the default for old projects.
- Added a strict HDL memory-array subset for single-address RAM with synchronous writes and asynchronous reads, and read-only initialized ROM. Both import as real editable memory components.
- Added a Memory Inspector with confirmed edits, BIN/Intel HEX exchange and Time Travel change display.
- Added a versioned FPGA project workspace with user-supplied device profiles, HDL/port validation, iCE40 PCF generation and self-contained ZIP export with checksums. Added optional detection and restricted execution of Yosys/Verilator, plus GTKWave VCD opening.
- Added sequential HDL vector comparison alignment for optional Icarus checks and first-mismatch reporting. Shipped sequential HDL and RAM circuit examples.
- Arbitrary HDL arrays, asynchronous resets, physical delay simulation, device-specific place-and-route and independent external verification on systems without the tools remain outside this release's tested subset.

## 2.4 — HDL Integration & Advanced Design

- Added an embedded HDL/Verilog dock with syntax colors, line numbers, module navigation, basic completion, `.v`/`.sv` file handling, validation and test vectors.
- Added a checked combinational Verilog subset parser with line/column diagnostics, structured expression/module nodes, width checks and named module instances. Import creates real editable LogicSpace components, BusWire connections and snapshot-based Custom Blocks.
- Added checked Verilog export for supported gates, arithmetic blocks, multiplexers, decoders, registers, D Flip-Flops, bus helpers and nested blocks. Unsupported or disconnected components are reported before export.
- Added isolated HDL vector testing on the existing Simulator, JSON reports and optional sandboxed Icarus comparison. External tools remain optional.
- Added seven HDL lessons and a local teacher-authored lesson editor with behavioral grading. Existing lessons, project JSON format and simulator remain unchanged.
- Added HDL examples and regression tests for import, export, hierarchy, widths, X behavior, lessons, external-tool failure paths and GUI integration.

## 2.3 — Learning & Project Experience

- Added a Start & Learn dock with welcome actions, nine editable project templates, previews, user template saving, ten guided lessons, benchmark reports, a local gallery and ZIP project exchange.
- Lesson checks use an isolated copy of the existing LogicSpace `Simulator` and verify truth tables, clocked state, RAM writes and reads, and ISA 2.1 program execution. Progress is stored separately from project JSON.
- Benchmark presets cover 100/500/1000 gates, larger combinational circuits, registers, RAM and CPU execution. Construction and simulation time are measured separately; output changes are counted from real simulator values. CSV and JSON export are available.
- Project ZIP files contain the native circuit, metadata, a README and linked user templates. Import validates archive entries and project data before creating a new file; existing files are not overwritten.
- Added optional `project_info` metadata to native projects without changing format version 1. Existing projects and the simulator API remain compatible.

## 2.2 — Universal CPU Integration

- Added physical CPU discovery, ISA 2.1 connection validation, multiple CPU bindings, portable architecture profiles, selected-ROM BIN/HEX programming and per-CPU Clock Generator control.

## 2.1 — CPU Architecture & Assembly

- Added the documented 8-bit ISA, two-pass assembler, a wired ISA Control Unit, Assembly editor, CPU debugging panel and example programs.
