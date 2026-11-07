# LogicSpace 3.0.0

The first source release of LogicSpace, a native Ubuntu/Linux digital circuit editor and logical simulator.

## Highlights

- Editable digital circuits with gates, buses, clocks, registers, RAM/ROM, CPU building blocks and reusable custom components.
- Wired 8-bit CPU and ISA 2.1 Assembly workflow, with ROM programming and debugging.
- Timing Diagram, Logic Analyzer, Signal Tracing, Testbench, Time Travel, Memory Inspector and watchpoints.
- A checked Verilog/SystemVerilog subset that imports to real circuit components; limited export and optional external tool checks.
- First-run half-adder example, templates, tutorials, project gallery and data-only ZIP sharing.
- Release checks through GitHub's API, at most once per day by default. The source distribution opens the official release page for manual updates; it does not replace local code automatically.

## Install

Download the source ZIP, extract it to a directory you own, then run:

~~~bash
./install.sh
./launch.sh
~~~

Python 3.12+ and a graphical Linux session are required. The installer adds PySide6 Essentials to the local .deps directory and creates a user desktop entry. No sudo is needed for the installer; minimal Linux installations may need `sudo apt install libegl1` for Qt.

## Verification and limits

The release candidate must pass the repository's unittest suite, py_compile, existing project load checks and a Wayland launch smoke test before tagging. The LogicSpace simulator models logical steps, not physical timing. HDL support is a subset. FPGA package export is not synthesis or programming. Independent Icarus/Yosys/Verilator runs depend on local tools and sandbox support. There is no safe in-place auto-install for editable source checkouts, nor a prebuilt .deb/AppImage in this release.

No LICENSE has been selected by the repository owner. Public visibility does not itself grant redistribution rights.
