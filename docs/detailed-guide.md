> Historical detailed guide for LogicSpace 2.x–3.0. For release installation and updates, see the repository README.

# LogicSpace

LogicSpace is a native Ubuntu digital electronics sandbox built with Python 3.12 and PySide6. The simulator is in `engine.py` and has no GUI dependencies.

## Install and run

On Ubuntu 24.04 or newer:

```bash
cd ~/LogicSpace
./install.sh
./launch.sh
```

The installer puts PySide6 Essentials in the project-local `.deps` directory and creates a desktop entry in `~/.local/share/applications`. It does not modify system Python packages. If PySide6 is already available, `./launch.sh` works without installation.

## First circuit

1. Drag two **INPUT** switches from the library onto the canvas. Drag in an **AND** gate and an **OUTPUT** indicator.
2. Click an output pin, then an input pin to connect them. Click empty canvas while wiring to add a corner. Ctrl click an existing wire to branch from it.
3. Double click an INPUT switch to change its state. Connected wires and the OUTPUT indicator show the resulting signal.
4. Use **Step** or **Run** for clocks and sequential circuits. **Reset** clears volatile state.

You can also open `examples/half_adder.json` for a working starter circuit.

## 3.0 development build: first steps and debugging

On startup, **Start & Learn** includes **Try the half-adder example**. This opens an editable copy, leaving the bundled example untouched. Toggle its input switches to see `SUM` and `CARRY`; use **Step** for clocked circuits. Press **F1** for this guide or choose **Help → About LogicSpace…** for version and simulation scope.

Press **Ctrl+F** to search components, labels, pins and connected wires in the active circuit. Select a result to center it on the canvas. The search is capped at the first 300 matches for large projects. The Components tab remains the drag-and-drop library.

**HDL source navigation.** After **Import to canvas** in the HDL dock, put the text cursor on a signal name and click **Find signal on canvas**. The matching real component is selected. Select an imported component and click **Show HDL source** in Inspector to open the exact source snapshot used for that import. The snapshot is saved with project JSON under optional `hdl_sources` metadata. If the HDL text has changed since import, the source-to-canvas search asks you to import the updated text; it does not guess which old circuit corresponds to the edit. A component with no source link shows no source button. This maps named signals to their generated producers; it is not a source-level debugger for every intermediate gate or nested module.

**Asynchronous reset and partial vectors.** The supported sequential HDL subset now accepts `always @(posedge clk or posedge rst)` and `always_ff @(posedge clk or negedge rst_n)` when the reset branch assigns full literal values to the same targets as the data branch. The generated D Flip-Flop or Register has a real `ARST` pin. Active reset updates state on `evaluate()` without waiting for a clock step; clock sampling gives reset priority. Single-bit writes such as `q[2] <= d` preserve other bits, including their individual `X` states. Combinational partial writes require a complete assignment first, to avoid an implicit latch. Exported generated HDL also accepts explicit concatenations and known-literal case equality, including the reduction-OR pattern emitted for `if` conditions; standalone reduction OR is still rejected. Arbitrary bit slices, multiple reset events and generalized memory-array ports remain unsupported and are diagnosed.

**Memory watchpoints.** In **View → Advanced Debugger…**, choose a RAM or ROM and an address, then click **Watch memory**. It pauses Run when that word changes, including a confirmed edit through Memory Inspector. Time Travel re-arms watchpoints to the restored value. This is a logical-state watchpoint; it does not measure hardware timing.

**Benchmarks.** The Bench tab saves up to 100 local results in `~/.local/share/logicspace/benchmark_history.json` and compares a new run only with a prior run of the same preset, topology counts, steps and reported software platform. These are wall-clock measurements; CPU load and thermal state still affect them. Export CSV/JSON remains available.

**External waveforms.** The HDL test vectors tab can export an **Icarus VCD** after restricted `iverilog` and `vvp` execution. The VCD is created by the external tool, not synthesized from LogicSpace's logical steps. If Icarus, Bubblewrap or usable user namespaces are missing, the action fails clearly and creates no waveform. FPGA package export validates HDL, ports and user-supplied PCF profile; it does not itself prove synthesis, placement, routing or physical timing.

The [3.0 HDL examples](../examples/hdl30/README.md) show an asynchronous-reset Flip-Flop and a partial-vector Register.

## Start & Learn (LogicSpace 2.3)

The **Start & Learn** panel opens when LogicSpace starts. Close it at any time to give the circuit canvas more room; reopen it from the **Projects** menu. It contains seven compact tabs: Start, Templates, Learn, Bench, Gallery, Share and HDL Learn. Projects still open in the normal editable canvas, and all lesson and benchmark checks use the existing `Simulator` in `engine.py`.

**Templates.** Choose **Projects → New from Template…**. Search or filter by category and difficulty, inspect a preview drawn from the template's actual components and wires, then click **Create project**. Nine built-in starters cover Logic Gates, Combinational Circuits, Sequential Circuits, ALU, RAM / ROM, Register File, 8-bit CPU, CPU with Assembly and Custom CPU. The result is a regular JSON project; CPU templates keep their actual ROM and CPU binding. **Save current as template…** stores a cleaned copy in `~/.local/share/logicspace/templates/`. User templates are independent of the project from which they were saved.

**Interactive lessons.** Choose **Projects → Tutorials…**, select one of ten lessons, read its explanation and task, then click **Start lesson**. Most starters provide labelled input and output terminals but leave the logic for you to build; CPU and Assembly lessons use a blank or `NOP/HLT` CPU starter. Click **Check current circuit** to run the real simulator on an isolated copy. The validator drives multiple input values, checks outputs or sequential state, and reports the first wrong value with a wiring/configuration hint. CPU lessons execute ROM instructions through PC, IR, control, registers, ALU and RAM; component presence alone never completes a lesson. Passed lessons are recorded in `~/.local/share/logicspace/tutorial_progress.json`; failures do not change progress or the live circuit. The first lessons cover gates, adders, arithmetic, mux/decoder, flip-flop/register, ALU, RAM, CPU building, ISA 2.1 and Assembly execution.

**Circuit Benchmark.** Choose **Projects → Circuit Benchmark…**. Select 100, 500 or 1000 gates; a larger combinational circuit; registers; RAM; or CPU execution. Set a step count and run or cancel. The panel reports component, wire and BusWire counts, completed steps, separately measured construction and simulation time, average time per step, and changes observed in actual simulator output pins. It runs on a worker thread and exports CSV or JSON. The measured seconds are local wall-clock performance, **not** physical propagation delay. Compare machines only with matching hardware, Python/Qt environment and benchmark settings; the report includes platform information.

**Local Project Gallery.** Choose **Projects → Project Gallery…** to browse bundled examples and registered local projects. Search and filter by category and difficulty, preview the circuit, open it in the editor, or duplicate it to a new JSON file. **Add current** registers the saved project file. **Remove entry** deletes only a user gallery record; it does not delete the project file. Bundled examples cannot be removed. Gallery entries live in `~/.local/share/logicspace/gallery.json`. There is no online gallery or network access.

**Project exchange.** Ordinary `.json` projects remain supported by **File → Open/Save**. The **Share** tab and **File → Import/Export project ZIP…** create a data-only package with `project.json`, `metadata.json`, `README.md` and a linked user template when needed. Import validates ZIP filenames, size, version, checksums where applicable, JSON structure, template data and the native circuit before creating a new project file. It rejects an existing destination rather than overwriting it. Imported JSON and ZIP files are never executed as code. A package does not install arbitrary Python modules or load external resources.

Current limits: lesson interfaces use the specified labels (such as `A`, `B`, `Y`) so the checker can identify the intended pins. User-created alternate circuits can pass if they satisfy the tested behavior; tests cover defined vectors rather than every possible large input space. Benchmarks measure output transitions between simulation steps, not events within a step. A user template is a project snapshot, not a live link back to its source project.

## Controls

| Action | Control |
| --- | --- |
| Zoom | Mouse wheel |
| Pan | Left drag on empty canvas, middle mouse drag, or Space + drag |
| Select multiple | Ctrl/Shift click, or Shift drag empty canvas for a selection box |
| Place component | Drag it from the library onto the canvas; a translucent preview shows the drop position |
| Move | Drag selected components |
| Delete | Select component or wire, then Delete |
| Copy / paste / duplicate | Ctrl+C / Ctrl+V / Ctrl+D |
| Undo / redo | Ctrl+Z / Ctrl+Shift+Z |
| Run / step / reset | F5 / F6 / F7 |
| Open / close Timing Diagram | Ctrl+T or View → Timing Diagram |
| Open Logic Analyzer | Ctrl+Shift+A or View → Logic Analyzer… |
| Open Advanced Debugger | Ctrl+Shift+D or View → Advanced Debugger… |
| Open CPU / Assembly | Ctrl+Shift+P or View → CPU / Assembly… |
| Open Memory Inspector | Ctrl+Shift+M or View → Memory Inspector… |
| Open FPGA Workflow | Ctrl+Shift+F or View → FPGA Workflow… |
| Open templates and learning tools | Projects menu; Ctrl+Shift+N opens Templates |
| Open Testbench Manager | Ctrl+Shift+E or View → Testbench Manager… |
| Choose a canvas tool | Open the **Tools** tab beside Components |
| Cancel placing or wiring | Esc |

The **File** menu contains Open, Save, Save As, import into the current workspace, import as a block, and export selection. Saving uses human-readable JSON.

To make a reusable block, include **INPUT** and **OUTPUT** terminal components in the selection, then use **Circuit → Save selection as block**. Configure each terminal's name to control the block pin labels. The block appears under **Custom Blocks**.

## Global Component Library

Select a circuit including its INPUT and OUTPUT terminals, then choose **Circuit → Save selection as block…**. Enter a name and choose **Save to current project**, **Save to global library**, or both. For the global library, choose a category and optional description. Project blocks stay under **Custom Blocks**; global blocks appear near the top of the Components sidebar under **Library · category** and can be dragged onto any project. The same search box finds them. Favorites also appear under **★ Favorites**.

Open **View → Component Library…** (Ctrl+Shift+L) to browse, search and preview blocks; manage favorites, categories and names; duplicate or delete blocks; import or export JSON; or update a definition from JSON. **Add project block** publishes an existing project block to the global library. **Use on canvas** selects a library block for placement. The default storage folder is `~/.local/share/logicspace/component_library/`, with one category directory and one JSON file per component.

When a global block is placed, LogicSpace embeds a copy of its definition and source version in the project. Its internal circuit, terminal names, bit widths and settings travel with the project. Later changes or deletion in the global library do not alter saved projects. Updating a library definition increases its version; existing project instances keep their original snapshots. Imported JSON is validated as a LogicSpace block or circuit, including terminals, wiring and nested dependencies. Imported files are data only; they do not execute code.

## Custom Block Designer

Open **Circuit → New Custom Block…** (`Ctrl+Shift+B`) or **Component Library → Create New Component…** for a blank component. To start with an existing circuit, select its components, including INPUT and OUTPUT terminals, and choose **Circuit → Design selection as block…**. You can also choose **Create New Component** or **Edit in Designer** in the Component Library Manager. Double-click a placed custom block to open its saved design as an editable copy.

The designer is a separate workspace with the normal LogicSpace component library, canvas, wiring, zoom, selection, and undo/redo. Add external terminals with **+ Input** and **+ Output** in the **Terminals** tab. Select each terminal to set its name, width (1–8 bits), side, order, and description; click **Apply terminal**. Every external bit is backed by a real INPUT or OUTPUT pin on the internal canvas. Wire those pins to the circuit, then use **Run Test** to enter input values and inspect the output bits. Test runs use a copy of the circuit, so they do not change the main project or the designer's working state.

Use **Appearance** to set the name, category, description, body color, size, label, and short text. The live preview uses the same drawing and terminal positions as blocks placed on the main canvas. **Save** offers the current project, the global library, or both; **Save As** creates a new global component when selected. **Export JSON** writes a reusable definition. Existing project instances keep their embedded definitions when a library entry is edited or deleted. Saving a revised block into a project under an occupied name creates a new numbered name instead of changing existing instances.

Each bit of a multibit terminal appears as a separate pin (`A0` through `A7`, for example). Terminal order controls the order on each side; exact free placement is not available. The designer requires at least one input, one output, and a connection to every external output bit before saving or testing. Simulation follows LogicSpace's existing digital engine and simulation-step timing; analog placeholders have no electrical simulation.

## Canvas tools

Open the **Tools** tab in the left sidebar and click a tool to pick it up. The cursor and animated highlight show which pin, component, or wire will be affected. Click the active tool again or press **Esc** to return to normal selection. Middle mouse or Space + drag still pans the canvas.

- **Flip Probe:** Hold the left mouse button on a pin carrying 0 or 1. It temporarily forces that one pin to the opposite value and propagates the result through the existing simulator. Releasing restores the unforced value. For a connected input pin, the force applies at the receiving pin; its upstream wire keeps showing the driver's value. On a one-bit INPUT switch, you can press its body as well as its output pin. Unknown (X) and visual-only analog pins cannot be flipped. A temporary force is not saved in circuit JSON or Undo history.
- **Eraser:** Click a component or wire to remove it. Removing a component also removes its attached wires.
- **Wire Cutters:** Click one wire to disconnect only that connection; other branches remain.

Eraser and Wire Cutters actions can be undone with **Ctrl+Z**. Switching tools, resetting, or leaving the window releases a held Flip Probe.

## Signal model

Each pin carries 0, 1, or X (unknown). Input pins accept one driver; output pins can fan out. Combinational loops are reported and evaluated as X. Clock and sequential components advance on discrete simulation ticks. The period and simulation speed are configurable. RAM and ROM use 1–8 address bits and 1–32 data bits, with a configurable depth up to 256 words. EEPROM and Flash retain stored words on simulation reset. Flash writes can only clear bits; its ERASE input resets all words to ones. DRAM words decay after a configurable number of ticks unless refreshed or accessed. These are digital behavioral models, not physical voltage or timing models. Analog components in the library are explicitly marked as visual placeholders and have no electrical behavior.

The **Displays** category has a warm glass Lamp, a colored LED, a dedicated RGB light, RGB lamp/LED variants driven by separate R/G/B pins, and a seven-segment display driven by A–G pins. They show the actual simulated input levels; the glow is a visual effect, not an analog voltage model.

New ALUs use a 4-bit `OP` bus and the operations listed under **CPU building blocks** below. ALUs in older projects keep their original two-bit `OP1 OP0` codes: `00` add, `01` subtract, `10` AND, and `11` OR. Bit pins use little-endian order: `A0`, `D0`, and `Q0` are the least significant bits.

## Changing bit width

Click a component once to see its **Configuration** fields in the right Inspector. Change a field and click **Apply changes**. Invalid settings are explained in the Inspector without changing the circuit. Double clicking an INPUT still toggles its state. Existing INPUT, OUTPUT and CONST parts retain their 1–8-bit limit. Logic gates, registers, arithmetic units, Program Counter and Instruction Register support widths up to 32 bits. RAM, ROM and related memory have separate **Address bits** and **Data bits** controls. Multibit parts expose one pin per bit, such as `A0…A3` and `Q0…Q3`; the wide parts show a compact bus port by default. Inputs and constants accept a decimal value; its bits appear on those pins. A wire on a one-bit pin is kept on bit 0 when the width increases. Reducing width is blocked if it would remove a connected bit. Naturally one-bit parts such as flip-flops and clocks stay one-bit.

Multibit logic gates, arithmetic units, multiplexers and comparators are drawn as bit-slice racks. Related pins are placed on the same row, so increasing width adds rows rather than stretching one symbol.

## Native buses

The **Bus** category contains Bus Input, Bus Output, Bus Probe, Bus Splitter, Bus Merger and Bit Selector. Native buses support **2, 4, 8, 16 and 32 bits**. Each component still has its existing individual bit signals, with bit 0 as the least significant bit. A larger teal port labeled `A[31:0]`, `D[31:0]` or `Q[31:0]` connects the whole group. Click an output bus port and then an input bus port of the same width to draw one thick, labeled bus. Click the bus while holding Ctrl to branch it to another input port. Select the bus and drag its corner handles to adjust its route; right click it to add or reset corners. Delete, duplicate, copy/paste and Undo/Redo work with bus connections. Connecting a mismatched width or a second driver produces an error and leaves the circuit unchanged. Compact bus components hide redundant bit pins by default; **Show individual bit pins** in Inspector reveals them.

Set a Bus Input's width and value in **Inspector → Configuration**. It accepts `0b1010`, `0xA`, decimal `10`, or binary with unknown digits such as `0b10X0`. Its display can be binary, hex or decimal; values outside the selected width are rejected. Bus Output and Bus Probe show the received value, and the Probe also shows its bit values, hexadecimal and unsigned decimal. Values with any X bit remain explicitly unknown in the nonbinary formats. Bus Splitter has one input bus and selectable one-bit `Q0…Qn` outputs; enter the exposed indices in Inspector. Bus Merger collects individual `D0…Dn` inputs into one output bus; unconnected bits remain X and are listed as warnings. Bit Selector exposes one chosen bit through `Q`; its index is configured in Inspector. Splitter and Merger keep the same bit order.

Existing multibit gates, arithmetic blocks, registers, memory data/address groups and compatible custom blocks can use their new bus ports while retaining their individual bit pins. To connect one bit of a bus, use a Splitter or a component's individual bit pin. A bus is electrically the group of its existing scalar pin signals, so the ordinary LogicSpace simulator remains the only simulator. Bus connections are saved in project JSON with their width and exact bit mapping; old single-bit projects load unchanged. Width changes that would invalidate an attached bus are blocked until that bus is disconnected.

Open `examples/bus_8bit_adder.json` for a ready-made 8-bit bus circuit: `0x3A + 0x17 = 0x51`.

## Timing Diagram

Open **View → Timing Diagram** (Ctrl+T). The panel sits below the canvas; drag the divider to resize it. Right click a pin or wire and choose **Add to Timing Diagram**, click **+ Add** to search and select several pins or wires at once, or select components and click **+ Selected** to add their outputs. Bus ports and bus wires appear as grouped multibit waveform rows with binary and hexadecimal values. Select a bus row and click **Expand bus** to add its individual bit waveforms. Ordinary bit pins remain selectable separately.

Use **Run** or **Step** to capture the actual simulator output. The axis is labeled **simulation steps**: one step is one engine tick, with no physical time unit implied. **Pause** stops capture. **Reset** clears the capture and restarts at step 0. Changing the circuit structure also starts a fresh capture; opening or creating a circuit removes selected traces. The trace list and capture are session data and are not stored in circuit JSON.

Click or drag on a waveform to move the inspection cursor. The readout shows every selected signal's value at that step. Shift click sets a second cursor and shows the distance in steps. Click a trace label to select it, then use **Rename** to change only its display label or **Remove** to delete it from the diagram. **Clear signals** removes all traces; **Clear history** restarts capture while keeping them.

Use **+ / −** or Ctrl+mouse wheel to zoom, mouse wheel or the horizontal scrollbar to move through history, **Fit** to show the full capture, and **Follow** to keep the latest step in view. Scrolling or moving the cursor pauses automatic following. **Limit** sets a bounded number of captured steps (default 2000); unchanged values are stored only once per trace.

The simulator provides 0, 1, and X (unknown). It has no high impedance state or substep event timestamps, so changes made while paused appear on the next captured step. The speed slider changes the delay between steps, not the axis unit.

## Signal Tracing

Right-click a pin, bus port or wire and choose **Trace Backward**, **Trace Forward**, or **Explain Signal**. You can also select a component or wire and click **Trace selected signal** in Inspector, or open **View → Signal Tracing…** (`Ctrl+Shift+T`) and use **Choose signal**. A whole bus expands into bit-level paths; individual bus-wire bits can be chosen in the signal picker. The tracing dock can be resized or closed. **Clear highlight** removes its canvas overlay.

**Backward** lists upstream drivers and the wires feeding the selected signal. **Forward** lists downstream branches and stops at stored-state boundaries. These trees describe *possible connections*. In **Explain**, the panel reads actual simulator inputs, outputs and captured state transitions. For example, `AND(A=0, B=1)` explains that changing A alone changes Q, while changing B alone leaves Q at 0. When both AND inputs are 0, each is sufficient to force Q low, although changing either one alone does not change Q. Blue highlights connected paths; amber marks the locally influential path. Clicking a tree row selects and centers its component or wire.

To inspect an earlier step, add at least one signal to the Timing Diagram, run or step the simulator, then move its cursor. The tracing panel uses the captured values and sampled sequential events for that step. It never substitutes current values when a historical frame is missing. History is bounded by the Timing Diagram limit and is cleared when the circuit structure changes or simulation resets. Historical source settings and nested block internals are not retained; the panel explicitly limits those explanations. A trace through a current custom block can explain its internal output using the existing simulator. Sequential explanations report the actual sampled clock edge, input values and state change; they do not infer an edge from the visible wiring.

Tracing uses simulation steps, not physical time. It describes local input sensitivity at one observed state; a connected input is not automatically a cause of an earlier transition. Very deep or wide paths are truncated with a message to keep the editor responsive.

## Automated Testbenches

Open **View → Testbench Manager…** (`Ctrl+Shift+E`) or right-click empty canvas. `Ctrl+Shift+B` remains the Custom Block Designer shortcut. Use **+ New** to create a testbench; each project can hold several independently named tests. Add one or more **Circuit inputs** and **Observed signals** with the picker. Circuit inputs are output pins or bus ports of INPUT, CONST or Bus Input components. Observed signals can be digital pins, bus ports or wires. Clock and reset sequences are defined by wiring INPUT components to the relevant CLK or RESET pins, then setting their values in the sequence.

Each sequence row represents one **simulation step**. Enter `0`, `1`, or `X` for a one-bit signal. For a bus, enter a decimal value, `0x` hexadecimal, `0b` binary, or a full-width binary pattern with X digits; `X` means every bus bit is unknown. Blank Set cells retain the previous input, and blank Expect cells skip the check. The **Repeat** column repeats a row over consecutive steps. Step 0 evaluates the initial input state at tick 0; each later step advances the existing LogicSpace simulator once. The axis has simulation steps, not physical seconds. Bus values are width checked; no truncation occurs.

The built-in Clock Generator is evaluated at the current tick before a step updates stored state; the waveform shown for the completed step is its new phase. A flip-flop driven by that generator can therefore show its updated Q one displayed step after the visible clock transition. A user-driven INPUT clock is applied before the step and is sampled in that step. Testbench results follow the engine's actual order in both cases.

Use **+ Assertion** for output equals, output does not equal, stable over a step range, change after a selected signal transition, equals at a chosen step, or several outputs equal their expected values together. For an event assertion, choose the observed event signal, its starting and ending values, and the maximum number of steps for the output to change. `X` means unknown; it is never converted to 0 or 1. A known expected bit against an unknown actual bit is **inconclusive**. A testbench needs at least one expected output or assertion before it can run.

**Run selected** or **Run all** executes on an isolated copy of the circuit, beginning at tick 0 with cleared volatile state. The live canvas, simulator and input switch positions are unchanged. **Stop** cancels the active run; **Stop on first failure** is an option for each testbench. The Results tab shows passed, failed and inconclusive checks, duration and first failure. Open a result to inspect actual waveforms, amber dashed expected values and red failure markers in its Timing Diagram tab. Select a failed check and click **Explain Failure**, or double-click the failed row, to open Signal Tracing at the retained failure snapshot. The explanation uses recorded simulator values and state transitions. It explains the observed signal; it cannot prove why a user-entered expectation was chosen. A custom block's historical external value is available, but its internal historical state is not retained for tracing.

Click **Save to project**, then use **File → Save** to write testbenches into the project JSON. Existing projects without testbenches continue to load. Deleted pins are reported so you can repair references; malformed testbench data is preserved in the project until you replace it with a valid set. Project limits default to 64 testbenches and 2000 steps per testbench; the manager can increase them to 256 and 10000. Only the first 128 distinct failure-step snapshots are kept for Explain Failure. Results and waveform captures are session data and are not saved in the project. INPUT or CONST pins are the supported drive points; arbitrary internal pins are observed through the normal simulator rather than forcibly overridden.

## Time Travel Debugger

Open **View → Time Travel Debugger…** (`Ctrl+Shift+H`). The dock records complete simulation snapshots after each step: tick, component state and parameters, temporary pin forces, evaluated pin values and the tracing facts needed to explain the step. A bus wire reads all its source bits from the snapshot; comparison shows the grouped value and pin-level changes. **Back**, **Forward**, **Beginning**, **Latest**, **Jump** and the recorded-position control navigate retained states. **Play replay** walks through recorded states without advancing the simulator; press it again to pause. The header shows the current step, the latest step in the selected branch and when you are viewing history.

Navigating to an older step restores its values on the canvas for inspection without changing the circuit structure or adding an Undo entry. Running or stepping from that state creates a new branch; the old future remains under its branch in the selector. **Continue from this state** creates the branch immediately. Changing an INPUT switch at a recorded step also creates a branch. The normal circuit **Undo/Redo** remains separate; a structural edit or simulation reset starts a new simulation history. When saving a project while viewing an older step, LogicSpace writes the active branch's latest state to JSON and keeps the preview at the selected step. Branches and checkpoints themselves are session data, not project data.

Use **+ Save** to name a checkpoint, then **Jump**, **Rename** or **Delete**. A checkpoint identifies a branch and step. If its snapshot expires, the list marks it `[expired]` and no state is fabricated. In **Compare States**, choose a branch and step for A and B, use **A/B ← current**, or select a checkpoint and use **A/B ← checkpoint**; then click **Compare**. Changed component state, input/output pins and wires appear in the table; **Show unchanged values** includes stable entries. Click a row to select and highlight its component or signal on the canvas.

Moving the main Timing Diagram cursor restores the matching retained debugger step. Navigating in the debugger moves the waveform cursor; changing branch rebuilds selected waveforms from that branch's recorded values. Signal Tracing reads the selected snapshot, including recorded sequential events. If a step is outside retained history, the debugger reports that it cannot restore it. In a failed testbench result, **Open Failed Step**, **Compare Previous** and **Expected vs Actual** open an isolated inspection in this dock. They never restore the testbench state into the live circuit. **Explain Failure** continues to use the recorded testbench tracing snapshot.

History is bounded by both a configurable state count (default 500) and an approximate serialized-size budget (default 64 MiB). Up to 16 branches and 64 checkpoint labels are kept. The newest single snapshot is retained even if it alone exceeds the memory budget, and the dock shows that condition. Old states can expire across branches. Internal historical state of a nested custom block is restored for deterministic simulation, but the Signal Tracing panel still cannot reconstruct an internal causal path that was not recorded. Clock Generator waveforms follow the simulator's pre-advance sampling order described above.

## Advanced memory and CPU blocks

The **Memory** category now includes **Register File** and **Address Decoder** alongside RAM and ROM. RAM has a configurable 1–32-bit data word, 1–8-bit address, and depth up to the number of address combinations. Its `A` and `D` buses, `WE` and `CLK` pins use the ordinary circuit connections. A rising clock edge writes `D` to `A` when `WE=1`. Its `Q` output is a **step-sampled read**: each simulation step samples the addressed word after a same-step write, so a write can be read back on that step. Before the first step, `Q` is X. Unwritten words read as zero. Addresses outside configured depth read X and writes are ignored with a warning. ROM reads asynchronously from its JSON **Contents** table; unwritten valid addresses read zero, and out-of-range addresses read X.

Register File has 2–32 registers of 1–32 bits, one synchronous write port (`WA`, `D`, `WE`, `CLK`) and one or two asynchronous read ports (`RA0`/`R0`, optionally `RA1`/`R1`). Writes become visible on both read ports after the active edge. Its unspecified words start at zero; an out-of-range read produces X and an out-of-range write is ignored with a warning. Address Decoder turns a valid address into one active `S` output; undefined or unrepresented addresses yield X, with a warning for known unrepresented addresses. All stored words live in normal component state, so project JSON, Testbench isolation and Time Travel snapshots retain them. Reset clears volatile RAM and Register File state, as it does other volatile memory in LogicSpace.

The **CPU** category includes **Program Counter**, **Instruction Register** and **Control Unit**. PC and IR accept 1–32-bit data buses. On the configured clock edge, IR loads `D` when `LOAD=1`. PC applies `RESET` first, then, if enabled, `LOAD` takes `D`; otherwise `INC=1` increments modulo its width. The Control Unit decodes a 4- or 8-bit `OP` bus using an editable JSON microcode table and produces `ALU_OP[3:0]`, `REG_WE`, `MEM_WE`, `PC_LOAD`, `PC_INC`, and `IR_LOAD`. The built-in table maps opcodes 0–4 to ALU ADD/SUB/AND/OR/XOR and register write, 5 to memory write, 6 to jump, 7 to branch when `ZERO=1`, and 8 to instruction load. Unknown or undefined opcodes produce X on all controls; malformed microcode is rejected. This is a control block, not a complete instruction decoder or CPU architecture.

New ALUs accept a 4-bit operation bus and expose `ZERO`, `CARRY`, `NEGATIVE`, and `OVERFLOW`. Operation codes are `0 ADD`, `1 SUB`, `2 AND`, `3 OR`, `4 XOR`, `5 NOT A`, `6 SHL A`, `7 SHR A`, `8 A==B`, `9 A<B`, `10 A>B`; comparisons are unsigned and return 0 or 1. Shifts are logical by one bit. `CARRY` on SUB means no borrow. Overflow is signed two's-complement overflow for ADD/SUB; it is zero for logic, shifts and comparisons. Undefined opcodes produce X. Old saved ALUs without `alu_version` keep the original two-bit operations and pins.

Open [the 8-bit CPU example](../examples/cpu_8bit.json) through File → Open. It wires a Clock Generator, PC, program ROM, IR, Control Unit, ALU, two-port Register File, RAM and probes into a small datapath. The ROM program adds, subtracts and ANDs initial register values 5 and 3, stores a result in RAM and jumps back to address 0. Step at least 12 times to see the full loop. The diagram is a teaching datapath: the IR loads each clock edge from a constant enable, and the Control Unit acts on the previously latched instruction during that edge. [Its builder script](../examples/build_cpu_8bit.py) regenerates the JSON through the public `Circuit` API.

## Logic Analyzer and step analysis

Open **View → Logic Analyzer…** (`Ctrl+Shift+A`). **+ Channels** selects multiple pins, bus ports, wires or individual bits. The analyzer shares the Timing Diagram's bounded capture, so Step/Run, pause, reset, history limits and Time Travel branches stay synchronized. Select a waveform row to inspect it; switch binary, hexadecimal or decimal display, search rising/falling/change events, measure complete HIGH pulses and rising-edge periods, zoom, scroll, fit or follow the latest step. Set **From step** and **To** to analyze/export a retained interval; **Export CSV…** writes one column per selected channel and one row per recorded step. **Remove** removes a channel from the shared capture.

The **Step analysis** tab shows complete clock cycles, HIGH/LOW step counts, nearest recorded data changes around rising clock edges, the first observed target transition after a source transition, and differences between two cycles. Spacing and offset actions mark recorded source/clock steps in amber and data/target changes in teal on the waveform. All distances are **simulation steps**. A same-step clock/data change has unresolved ordering at waveform resolution. These observations are not physical propagation delay, setup time, hold time, or proof that one transition caused another. LogicSpace has no gate-delay model or real-time timestamps; physical timing constraints and nanosecond measurements are not implemented.

## Advanced Debugger

Open **View → Advanced Debugger…** (`Ctrl+Shift+D`). Choose a pin, bus, bus bit or wire, then add an exact-value, not-equal, change, watch, unknown, rising-edge or falling-edge condition. For a whole bus, enter decimal, `0x` hexadecimal, `0b` binary or `X`; use an individual bit for edge conditions. **Break on conflict** stops when the simulator reports a new error or warning, including an invalid address or multiple drivers. Enabled breakpoints pause Run after the matching simulation step. Recent hits show their recorded step; double-click a retained hit to inspect it in Time Travel. Choose a one-bit clock signal and click **Step clock cycle** to advance to its next recorded rising edge. The signal history in this panel is bounded and session-only; conditions are evaluated at step boundaries, not inside a step.

Signal Tracing can inspect new bus values and CPU control outputs using recorded simulator values. For stored memory reads, the explanation distinguishes an address connection and retained word from an observed write event; it does not invent an unrecorded historical cause. Time Travel stores RAM, Register File, PC and IR state exactly as ordinary component state, while Testbench executes them on its isolated copy of the same simulator.

The Custom Block Designer still limits its external terminal editor to 1–8-bit terminals. Use native 16/32-bit buses between built-in components; widening custom terminals is a separate interface migration. LogicSpace does not model electrical contention, high impedance, propagation time within a step, physical setup/hold margins, or analog memory cell behavior.

## LogicSpace 8-bit CPU and Assembly

Open **View → CPU / Assembly…** (`Ctrl+Shift+P`). Click **New CPU** to create a reference circuit made of ordinary LogicSpace components and wires: Clock Generator, 8-bit PC, 256×8 ROM, 8-bit IR, ISA Control Unit, 4×8 Register File, 8-bit ALU, 256×8 RAM and five 8-bit multiplexers. You can inspect and edit the circuit on the normal canvas. **Assemble** checks the source and shows its bytes; **Load ROM** writes those bytes to the actual ROM component and resets the live simulator. The panel stores the loaded source and any unassembled draft in the project JSON. Loading a program never runs a separate CPU interpreter.

The CPU uses a **Harvard map**: ROM addresses `0x00–0xFF` hold code, and RAM addresses `0x00–0xFF` hold data. `0xC0–0xFF` of RAM is reserved for the downward-growing stack. Four general registers, `R0–R3`, hold unsigned bytes. PC, IR, flags and stack pointer are 8 bits. Instruction bytes have a one-byte opcode followed by zero, one or two operand bytes. Each register operand is the numeric byte `0–3`; immediates and direct addresses are `0–255`. `MOV R0, 10` and `MOV R0, R1` use different opcodes. All multibyte data directives are little-endian; bit 0 is LSB.

| Opcode | Assembly format | Bytes | Effect |
| --- | --- | ---: | --- |
| `00` | `NOP` | 1 | Complete one instruction without changing data |
| `01` | `HLT` | 1 | Halt after completing this instruction |
| `10` | `MOV Rd, imm` | 3 | `Rd ← imm` |
| `11` | `MOV Rd, Rs` | 3 | `Rd ← Rs` |
| `12` | `LOAD Rd, addr` | 3 | `Rd ← RAM[addr]` |
| `13` | `STORE Rs, addr` | 3 | `RAM[addr] ← Rs` |
| `20` | `ADD Rd, Rs` | 3 | `Rd ← Rd + Rs` modulo 256 |
| `21` | `SUB Rd, Rs` | 3 | `Rd ← Rd − Rs` modulo 256 |
| `22` | `AND Rd, Rs` | 3 | Bitwise AND into `Rd` |
| `23` | `OR Rd, Rs` | 3 | Bitwise OR into `Rd` |
| `24` | `XOR Rd, Rs` | 3 | Bitwise XOR into `Rd` |
| `25` | `NOT Rd` | 2 | Bitwise NOT into `Rd` |
| `26` | `SHL Rd` | 2 | Logical left shift by one into `Rd` |
| `27` | `SHR Rd` | 2 | Logical right shift by one into `Rd` |
| `28` | `CMP Ra, Rb` | 3 | Set flags from `Ra − Rb`; do not write a register |
| `30` | `JMP addr` | 2 | Load PC with `addr` |
| `31` | `JZ addr` | 2 | Jump if stored Z flag is 1 |
| `32` | `JNZ addr` | 2 | Jump if stored Z flag is 0 |
| `33` | `JC addr` | 2 | Jump if stored C flag is 1 |
| `34` | `JNC addr` | 2 | Jump if stored C flag is 0 |
| `35` | `CALL addr` | 2 | Push the address after CALL, then jump |
| `36` | `RET` | 1 | Pop an address into PC |
| `40` | `PUSH Rs` | 2 | Write `Rs` at SP, then decrement SP |
| `41` | `POP Rd` | 2 | Increment SP, read RAM and write `Rd` |

ALU operations and `CMP` update stored **Z** (zero), **C** (carry on ADD/SHL/SHR; no-borrow on SUB/CMP), **N** (result bit 7) and **V** (signed ADD/SUB overflow). MOV, LOAD, STORE and stack operations preserve flags. `JZ/JNZ/JC/JNC` read the stored flags, not a newly calculated value. Reset clears the flags and volatile RAM/register state and returns SP to `0xFF`. Pushing below `0xC0`, popping above `0xFF`, an undefined opcode, an encoded register outside `R0–R3`, an X operand, or a branch on an X flag halts with a visible fault. PC increments while fetching each byte and loads a branch target during execution; as an 8-bit register it wraps modulo 256.

The **ISA Control Unit** has saved microphases: `FETCH → DECODE → ARG1 → ARG2 → READ → EXEC`. It drives external PC, IR, register-file, ALU, RAM and multiplexer pins. RAM reads require a separate `READ` phase; therefore a clock edge is not the same as a completed instruction. The earlier **Control Unit** remains available with its original microcode behavior and old projects keep their original ALU interface. The CPU's instruction counter increments only when an instruction completes; HLT is counted, faults are not.

The Assembly editor has line numbers, syntax colors, auto-indent after labels, mnemonic suggestions (also `Ctrl+Space`), and clickable line-numbered errors. Comments start with `;`. Labels and `.EQU NAME, value` constants are case-insensitive. `.ORG address` places subsequent bytes at a ROM address, `.BYTE` emits byte values, and `.WORD` emits little-endian 16-bit values. Decimal, `0x` hexadecimal, `0b` binary, and a label/constant with a single `+` or `−` offset are accepted. `.ORG` uses symbols already defined earlier; overlapping or overflowing ROM bytes are errors. **Export BIN** writes all 256 ROM bytes, **Export HEX** writes Intel HEX records, and **Export listing** maps source lines to machine bytes. Assembly is deterministic.

Use **Start / Resume**, **Pause**, **Stop**, **Reset**, **Step instruction**, **Step clock**, or the speed control in the CPU state tab. The state view shows PC, IR, current/next decoded instruction, register values, ALU output, flags, SP, microphase and completed-instruction count. The Memory tab has a hex viewer, address inspector, RAM editing and a raw dump; ROM changes through **Load ROM**. RAM edits are recorded as Time Travel mutations. The Debug tab supports breakpoints by Assembly line, instruction address, register value and RAM read/write address, plus Step Into/Over/Out and retained instruction history. CPU breakpoint hits also appear in the existing Advanced Debugger event list. Selecting a recorded instruction opens that step in Time Travel. If the ROM is edited outside **Load ROM**, source-line breakpoints are disabled until source and bytes match again; address breakpoints remain available.

Five [Assembly example projects](../examples/assembly/README.md) ship with `.asm` sources, machine-code `.bin` and `.hex` files, complete wired `.json` circuits, expected results and regeneration instructions: arithmetic, loop, memory, Fibonacci and stack. Open a `.json` example directly or use **New CPU** and load its `.asm` source.

Instruction breakpoints stop when `EXEC` is entered, before its write edge; register and memory watchpoints stop after the completed instruction. History is bounded by the existing Time Travel settings. The ISA models digital steps, not physical clock period or gate delay.

## CPU Architecture Discovery and Binding (2.2)

Open **View → CPU / Assembly… → Architecture**. **Detect** finds each real `ISA Control Unit` and follows its connected ports to identify its Clock, PC, ROM, IR, Register File, ALU, RAM, constants and five multiplexers. Component labels and the reference-board wiring manifest are not used to establish compatibility. **Validate** lists all found problems at once; incomplete circuits remain editable. Select a discovered CPU and click **Bind**. The Assembly, Memory, CPU state and Debug tabs then use that binding. Use the binding selector to switch CPUs, **Unbind** to detach the panel without deleting circuit components, or **Rebind** after replacing components. A stale binding is shown as an error and cannot program a missing ROM.

To assemble your own ISA 2.1 CPU, place an 8-bit Program Counter and Instruction Register, ROM and RAM with **8 address bits, 8 data bits and 256 words**, a **4×8 Register File with two read ports**, an 8-bit ALU version 2, an ISA Control Unit, one Clock Generator, two CONST components (`ENABLE=1`, `RESET=0`), and five 8-bit Multiplexers. Set the multiplexers' purposes to immediate/register write (`rf_imm`), RAM writeback (`rf_mem`), register copy (`rf_reg`), PC target (`pc_data`) and RAM data (`mem_data`). The Architecture tab identifies those purposes from their select-pin connections.

| Required physical path | Ports |
| --- | --- |
| Clock to sequential components | Clock.Q → PC, IR, ISA Control Unit, Register File and RAM `CLK` |
| PC fetch | PC.Q → ROM.A and Control.PC; ROM.Q → IR.D and Control.ROM_D; IR.Q → Control.IR |
| PC control | CONST(1).Q → PC.ENABLE; CONST(0).Q → PC.RESET; Control.PC_INC/PC_LOAD → PC.INC/LOAD; `pc_data.Q → PC.D` |
| Register addresses and write | Control.RA0/RA1/WA/RF_WE → Register File.RA0/RA1/WA/WE; `rf_reg.Q → Register File.D` |
| ALU | Register File.R0/R1 → ALU.A/B; Control.ALU_OP → ALU.OP; ALU flags ZERO/CARRY/NEGATIVE/OVERFLOW → matching Control.ALU_* inputs |
| Register writeback | ALU.Q → rf_imm.A; Control.IMM → rf_imm.B; Control.RF_IMM → rf_imm.SEL; rf_imm.Q → rf_mem.A; RAM.Q → rf_mem.B; Control.RF_MEM → rf_mem.SEL; rf_mem.Q → rf_reg.A; Register File.R1 → rf_reg.B; Control.RF_REG → rf_reg.SEL |
| Branch target | Control.IMM → pc_data.A; RAM.Q → pc_data.B; Control.PC_MEM → pc_data.SEL |
| RAM data and address | Register File.R0 → mem_data.A; PC.Q → mem_data.B; Control.MEM_PC → mem_data.SEL; Control.MEM_A/MEM_WE → RAM.A/WE; mem_data.Q → RAM.D; RAM.Q → Control.MEM_Q |

Use native BusWire for the 2, 4 and 8-bit paths; the validator checks exact width and LSB-first pin mapping. A wire to a visually nearby pin does not count unless its actual source, destination and port are correct. The complete machine-readable contract is `REQUIRED_LINKS` in `cpu_architecture.py`. Address Decoder and Bus Input/Output can be added around the CPU, but they do not replace the ISA 2.1 core ports.

**ISA compatibility** currently means exactly the 8-bit, four-register ISA 2.1 datapath above. Detection reports unsupported widths, missing components, disconnected inputs, invalid BusWire mapping and wrong ROM/RAM capacity. It does not claim that an arbitrary alternate datapath or another ISA can execute the 2.1 instruction set. Profiles store the validated role types, port links, widths, memory sizes, ISA version and supported operations in project JSON. **Export profile** writes a portable JSON description; **Import profile** checks that description against a newly discovered physical circuit before binding it. Profiles do not contain executable code or substitute for wires.

To program the selected CPU, use **Assemble → Load ROM** or **Architecture → Load BIN / Load HEX**. BIN accepts 1–256 bytes. Intel HEX accepts data and EOF records, checks checksums, address range and overlap, then loads the bytes into the selected ROM. Only that ROM is programmed. Assembly source-line mapping is available when ROM bytes match the loaded source; raw BIN/HEX with different bytes leaves address breakpoints and signal debugging available, while source-line mapping is disabled. Loading a program resets the selected CPU's volatile state when multiple CPUs are bound; it does not clear another CPU's RAM or registers.

Each bound CPU needs a separate Clock Generator. Selecting one makes its real Clock Generator run and pauses the other bound CPU clocks, so **Step clock**, **Step instruction** and **Run** act on the chosen CPU while the shared Simulator still evaluates the whole circuit. Switching is recorded as a Time Travel mutation; navigating to a historical state restores the corresponding active-clock selection. A global **Circuit → Reset** still resets the whole circuit; the CPU tab's **Reset** clears only the selected CPU when several CPUs are bound. Instruction and signal breakpoints continue to use the existing debugger and Time Travel histories.

Open [hand_wired.json](../examples/universal_cpu/hand_wired.json) for a manifest-free CPU made with public component and connection APIs, or [two_cpus.json](../examples/universal_cpu/two_cpus.json) for two independent ROM programs. Their `.asm` sources are in the same folder. [The builder](../examples/build_universal_cpus.py) regenerates both projects. The 2.1 reference board and old CPU JSON projects continue to load without migration.

## HDL / Verilog (LogicSpace 2.4)

Open **View → HDL / Verilog…** (`Ctrl+Shift+V`). The dock has a code editor with line numbers, syntax colors, module navigation, basic completion (`Ctrl+Space`), indentation and line diagnostics. **Open .v/.sv** and **Save/Save As** manage ordinary UTF-8 HDL files. Editing HDL does not silently change the canvas. **Validate** checks the supported subset; **Import to canvas** adds editable components and wires to the current project, including a nested custom block for each named module instance. The project JSON embeds those definitions, so it remains independent of the original HDL file. **Export canvas** generates Verilog from the current project and lists every unsupported or disconnected component before changing the editor text. Save the generated text as `.v` or `.sv`.

LogicSpace 2.4 introduced a small **combinational** subset of Verilog/SystemVerilog:

- `module … endmodule`, ANSI or simple non-ANSI `input`/`output` declarations, `wire` and simple `logic` declarations, `assign`, named module instances such as `child u(.a(a), .y(y))`.
- Widths 1, 2, 4, 8, 16 and 32 using `[N:0]`; bit 0 is LSB. Scalar bit selects such as `a[2]`; decimal and sized binary/hex/decimal constants, including full-width binary X literals. Z is unsupported.
- Unary `~` and `!`; bitwise `&`, `|`, `^`; one-bit logical `&&`, `||`; `+`, `-`, `*`, `/`; and `sel ? b : a`. Arithmetic uses the existing LogicSpace word width and wraps at that width. Division by zero produces X. Widths must match; there is no implicit truncation, sign extension or inferred clock behavior.
- Each imported expression becomes ordinary LogicSpace gates, arithmetic blocks, constants, multiplexers and wires. Wide compatible pin groups use BusWire, including 16/32-bit links to imported nested modules. Named instances become existing Custom Blocks whose internal circuits run on the same `Simulator`.

In 2.4 the importer rejected procedural blocks. LogicSpace 2.5 adds the limited sequential subset described below. `initial`, delays, parameters, generate statements, concatenation, slices, positional instances and unrestricted SystemVerilog remain unsupported and produce diagnostics. Internal validation checks syntax, widths, drivers, module ports and recursive dependencies. It does not certify synthesis or all Verilog language rules.

The exporter supports labelled INPUT/OUTPUT, Bus Input/Output, constants, logic gates, multiplexers, decoders, comparators, Adder/Subtractor/Multiplier/Divider, D Flip-Flop, Register, Bus Splitter/Merger, Bit Selector and compatible nested Custom Blocks. Registers export as edge-triggered `always @(posedge …)` with zero initialization to match LogicSpace reset behavior. RAM, ROM, CPU control, clocks and other components without a checked translation are explicitly rejected. Internal LogicSpace component IDs become stable wire names in one export; wires without labels have generated names. Check the export diagnostics before saving.

### HDL test vectors and Icarus

Use the **Test vectors** tab. Enter a JSON list whose rows contain all external `inputs`, optional `expected` outputs and optional `step: true`. Values are unsigned integers or `null` for X. **Run LogicSpace** compiles the HDL into a fresh circuit and evaluates each row with the existing `Simulator`; it never alters the live canvas. The result lists actual values and pass/fail for each vector. **Export report** writes JSON. For example, with `examples/hdl/and4.v`:

```json
[
  {"inputs": {"a": 10, "b": 12}, "expected": {"y": 8}},
  {"inputs": {"a": 15, "b": 3}, "expected": {"y": 3}}
]
```

**Compare Icarus** is optional. Install `iverilog`, `vvp` and Bubblewrap (`bwrap`) to enable it. The DUT must pass the internal parser first. LogicSpace creates a numeric-only testbench in a temporary work directory, compiles and executes it in a Bubblewrap filesystem/network namespace with CPU, memory, file and wall-time limits, then compares each output with the LogicSpace Simulator. If a tool or namespace facility is unavailable, the panel shows a direct error. Arbitrary external testbench text is not executed. Icarus is never required to run LogicSpace or the internal HDL tests. X propagation in arithmetic can differ between Verilog and LogicSpace because the current arithmetic blocks produce whole-word X when any input bit is unknown; such vectors must not be treated as proven equivalent. Sequential comparison requires `step: true` on vectors that change a clock; the first clock value must be at its inactive level (0 for `posedge`, 1 for `negedge`). A vector may use `step: false` for an asynchronous reset transition while keeping all clocks unchanged. Clocks and resets in nested modules must be exposed by the same name on the top module for this comparison.

### HDL lessons and custom lessons

Open **Projects → HDL Tutorials…**. Seven lessons cover a first module, combinational logic, multiplexers, registers, HDL import, HDL export and validation. Each passes only after actual simulation vectors match; the sequential lesson also checks an edge-triggered export. Progress uses the existing local tutorial progress file. **Create lesson…** and **Edit custom…** let a teacher enter an explanation, task, starter HDL, expected vectors and an optional canvas starter. Choose HDL or canvas grading. Custom lessons are stored as validated JSON in `~/.local/share/logicspace/hdl_lessons/`; their checks run on isolated circuit copies. The editor does not execute imported code.

HDL examples live in [examples/hdl](../examples/hdl/README.md) and [examples/hdl25](../examples/hdl25). Arbitrary bit slicing and signed arithmetic remain unsupported. LogicSpace 2.5 accepts the limited memory-array form below. External Icarus depends on local installation and user-namespace support. The HDL editor manages separate `.v/.sv` files; the new FPGA project workspace embeds chosen source files in project JSON. Previously saved projects retain their version-1 circuit format.

## Sequential HDL and FPGA workflow (LogicSpace 2.5)

The HDL dock accepts `always @(*)`, `always_comb`, `always @(posedge clk)`, `always @(negedge clk)`, `always_ff @(posedge/negedge clk)`, `begin/end`, `if/else`, and `case/default`. Combinational assignments use `=`; clocked assignments use `<=`. Full scalar or vector targets are supported. The importer rejects incomplete combinational assignment instead of creating an implicit latch. Partial vector writes, asynchronous reset sensitivity lists, mixed assignment styles, delay controls and arbitrary SystemVerilog are not accepted. Diagnostics identify source line and column and include a suggested fix for common cases. `always_ff` here means a single edge-sensitive block, not full SystemVerilog `always_ff` rule coverage.

**Import and simulation.** A clocked scalar target becomes an ordinary D Flip-Flop; a clocked vector becomes an ordinary Register, including feedback for counters and state machines. Procedural `if` and `case` compile to normal logic components and wires. The canvas import option **Use Clock Generator** replaces direct top-level clock input terminals with wired, editable Clock Generator components; uncheck it to keep those ports as manual INPUT controls. An imported Clock Generator exports back to a Verilog input clock port, because the generator is a simulation source rather than synthesizable oscillator hardware. The isolated HDL vector runner always uses explicit input clocks. The existing Simulator evaluates combinational inputs, samples each sequential component's pre-edge values, commits all states together, then reevaluates outputs. A clock transition is recognized when the simulator advances one logical step; changing an INPUT value alone does not commit an edge. Imported state starts X unless reset by the circuit. A synchronous reset can be described inside a clocked `if` and is sampled on the selected edge. Multiple clock domains may be wired, but all are resolved on the same logical simulation step; there is no event queue or intra-step timing model. Time Travel captures the actual component state, including imported registers and memory. The Advanced Debugger shows the current step, clock outputs and recent state changes from the Simulator's transition facts. Existing edge breakpoints and register signal watchpoints apply.

**Memory.** RAM adds explicit `read_mode` values `async` and `sync`; old projects without a mode keep their prior `legacy` step-based read behavior. ROM defaults to asynchronous read and optionally supports synchronous read. Writes to RAM occur on the configured clock edge. Synchronous reads hold their output between read edges; `RE=0` holds the previous value and `RE=X` makes it unknown. RAM read-during-write selects `new`, `old` or `no_change` data. `async` RAM always shows the committed new word. Addresses outside `depth` produce X and a simulator warning. New RAM modes conservatively propagate X when write enable or write address is unknown; legacy RAM behavior remains unchanged. RAM `init` and ROM `contents` are address-to-value maps saved in circuit JSON. The Memory Inspector lets you inspect and confirm edits, choose binary/hex/decimal display, go to an address, load/export BIN or Intel HEX for memories up to 8 data bits, and view retained Time Travel memory changes. Inspector edits are Time Travel mutations. Current memory cells are ordinary component state, with no duplicate memory simulator.

**HDL memory arrays.** The importer accepts one dimensional `logic`/`reg`/`wire [W-1:0] mem [0:N]` with a single named address signal, `assign q = mem[addr]`, and optional literal initialization such as `initial begin mem[0] = 8'h12; end`. A read-only array becomes a real ROM component. One optional `always_ff @(posedge/negedge clk) if (we) mem[addr] <= d;` writer becomes a real RAM component with asynchronous read and synchronous write. The same address signal must serve reads and writes because the current RAM component has one address port. Address and data widths must match exactly. Multiple writers, separate read/write addresses, nonliteral initialization, indexed bit writes and alternative memory processes are rejected. Exporting RAM/ROM back to HDL is deliberately blocked until their exact read/write timing can be represented; the importer does not disguise a memory as a Python array.

**FPGA package.** Open **View → FPGA Workflow…** (`Ctrl+Shift+F`). Add `.v`/`.sv` files or copy the current HDL editor buffer, set the top module, load a user device profile, assign every top-level scalar bit to a package pin and set clock frequencies in MHz for sequential designs. **Validate** checks project schema, parse/import compatibility, top module, port assignments, duplicate pins, profile pins and clock pin constraints, and reports all found issues. **Save in project** stores the versioned FPGA workspace in the ordinary circuit JSON. **Export ZIP** writes the embedded HDL files, `manifest.json` with SHA-256 checksums, a README and a nextpnr iCE40 PCF file. [nextpnr documents `set_io` and `set_frequency` for iCE40 PCF](https://github.com/YosysHQ/nextpnr/blob/main/docs/ice40.md). LogicSpace provides **no built-in physical device pin tables**; a profile must be supplied by the user with its provenance. Verify that profile against the actual board and package files. Export does not synthesize, place, route or prove physical timing.

**Optional tools.** The Toolchain tab detects Icarus, Yosys, Verilator and GTKWave with executable paths and version probes. Yosys performs generic HDL synthesis and produces a checked JSON netlist when installed; Verilator runs lint; GTKWave opens an existing VCD. Yosys/Verilator/Icarus processes use a bounded temporary directory, Bubblewrap isolation, a fixed argument list, timeouts and cancellable process groups. If the executable or usable sandbox is absent, the action reports that condition. The toolchain never uploads HDL or runs shell commands from project data. A successful generic Yosys run is **not** an FPGA implementation or timing result.

**Equivalence.** HDL test vectors are run on an isolated imported LogicSpace circuit. If Icarus is available, the same vectors are run through a generated testbench and the panel identifies the first differing signal and vector. Internal vector success alone is not independent verification. There is no guaranteed equivalence for partial X bus values, multi-event activity within one logical step or unsupported HDL. No nanosecond value, propagation delay, setup/hold requirement or actual hardware timing is inferred from simulation steps. The existing Logic Analyzer measures transitions, periods and data spacing in **logical steps only**.

The [2.5 examples](../examples/hdl25) include a D Flip-Flop, 8-bit register, counter, four-stage shift chain, simple FSM, importable RAM/ROM HDL arrays and an editable RAM circuit project. FPGA profiles are user supplied; there is no device-specific place-and-route flow or verified board database. The new FPGA metadata is optional in version-1 project JSON, so older projects need no migration.

## Tests

```bash
python3 -m unittest discover -s tests -v
```
