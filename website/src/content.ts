export type Language = 'en' | 'ru'
export type Localized = { en: string; ru: string }
export const t = (en: string, ru: string): Localized => ({ en, ru })

export const REPO = 'https://github.com/Kuattt/LogicSpace-'
export const RELEASE = `${REPO}/releases/tag/v3.1.0`
export const SOURCE_ZIP = `${REPO}/releases/download/v3.1.0/LogicSpace-3.1.0-source.zip`
export const WINDOWS_SETUP = `${REPO}/releases/download/v3.1.0/LogicSpace-Setup.exe`
export const WINDOWS_PORTABLE = `${REPO}/releases/download/v3.1.0/LogicSpace-Windows-x64.zip`
export const QT_SOURCES = `${REPO}/releases/download/v3.1.0/Qt-sources-6.9.3.zip`
export const CHECKSUM_FILE = `${REPO}/releases/download/v3.1.0/SHA256SUMS.txt`
export const SOURCE_ARCHIVE = `${REPO}/archive/refs/tags/v3.1.0.zip`
export const GUIDE = `${REPO}/blob/v3.1.0/docs/detailed-guide.md`
export const CHANGELOG = `${REPO}/blob/v3.1.0/CHANGELOG.md`
export const SHA256 = '78a3ba53975f012a41e70e500f526d1e917ade9f24ea3271cd930f9ae52bf85f'
export const QT_SOURCES_SHA256 = '7d07f2354f09a423939d3e3055541497d205ecbc9baa5cb3d0b703d646f387ac'

export interface Feature {
  id: string
  title: Localized
  summary: Localized
  detail: Localized
  doc: string
  group: 'build' | 'program' | 'inspect'
}

export const features: Feature[] = [
  {
    id: 'editor',
    title: t('Digital circuit editor', 'Редактор цифровых схем'),
    summary: t(
      'Place components, route wires, and work on a spacious canvas.',
      'Размещайте элементы, соединяйте их и работайте на большом холсте.',
    ),
    detail: t(
      'Selection, box selection, undo/redo, snapping and an Inspector keep the editor practical for real circuits.',
      'Выделение, отмена действий, привязка к сетке и Inspector помогают собирать настоящие схемы.',
    ),
    doc: 'circuit-editor',
    group: 'build',
  },
  {
    id: 'simulator',
    title: t('Logic simulator', 'Логический симулятор'),
    summary: t(
      'Run, pause, step and reset actual connected circuits.',
      'Запускайте, ставьте на паузу и пошагово проверяйте соединённые схемы.',
    ),
    detail: t(
      'The central engine propagates 0, 1 and X and preserves sequential state. Steps are logical, not physical nanoseconds.',
      'Центральный движок распространяет 0, 1 и X и хранит состояние последовательных элементов. Шаги логические, не физические наносекунды.',
    ),
    doc: 'simulator',
    group: 'build',
  },
  {
    id: 'bus',
    title: t('Native bus system', 'Система шин'),
    summary: t(
      'Connect multibit signals without drawing every bit separately.',
      'Передавайте многобитные сигналы одним соединением.',
    ),
    detail: t(
      'BusWire supports 1, 2, 4, 8, 16 and 32 bits, with width validation and bit 0 as LSB.',
      'BusWire поддерживает 1, 2, 4, 8, 16 и 32 бита, проверяет ширины и использует bit 0 как LSB.',
    ),
    doc: 'components',
    group: 'build',
  },
  {
    id: 'memory',
    title: t('Memory components', 'Компоненты памяти'),
    summary: t(
      'Connect RAM, ROM and register files directly in a circuit.',
      'Подключайте RAM, ROM и регистровые файлы прямо в схеме.',
    ),
    detail: t(
      'Inspect addresses and values, define supported read/write modes and track state through Time Travel.',
      'Просматривайте адреса и значения, выбирайте поддерживаемые режимы чтения и записи и отслеживайте состояние через Time Travel.',
    ),
    doc: 'components',
    group: 'build',
  },
  {
    id: 'cpu',
    title: t('Wired CPU architecture', 'CPU из компонентов'),
    summary: t(
      'Build or bind an 8-bit processor from real components.',
      'Собирайте или привязывайте 8-битный процессор из реальных компонентов.',
    ),
    detail: t(
      'PC, ROM, IR, Control Unit, Register File, ALU and RAM execute through the same simulator and circuit connections.',
      'PC, ROM, IR, Control Unit, Register File, ALU и RAM работают через тот же симулятор и соединения схемы.',
    ),
    doc: 'cpu-assembly',
    group: 'program',
  },
  {
    id: 'assembly',
    title: t('Assembly environment', 'Среда Assembly'),
    summary: t(
      'Assemble ISA 2.1 source and load the bytes into wired ROM.',
      'Собирайте ISA 2.1 и загружайте байты в ROM подключённой схемы.',
    ),
    detail: t(
      'The two-pass assembler resolves labels, exports BIN/HEX and gives line-based diagnostics.',
      'Двухпроходный ассемблер разрешает метки, экспортирует BIN/HEX и показывает ошибки по строкам.',
    ),
    doc: 'cpu-assembly',
    group: 'program',
  },
  {
    id: 'hdl',
    title: t('Verilog / SystemVerilog subset', 'Подмножество Verilog / SystemVerilog'),
    summary: t(
      'Edit, validate and import supported HDL into editable circuits.',
      'Редактируйте, проверяйте и импортируйте поддерживаемый HDL в редактируемые схемы.',
    ),
    detail: t(
      'Includes a checked combinational and limited sequential subset. Unsupported constructs produce diagnostics; full language coverage is not claimed.',
      'Поддерживается проверенное комбинационное и ограниченное последовательное подмножество. Неподдерживаемые конструкции дают диагностику.',
    ),
    doc: 'hdl',
    group: 'program',
  },
  {
    id: 'debugger',
    title: t('Debugging & Time Travel', 'Отладка и Time Travel'),
    summary: t(
      'Trace values, watch signals and restore earlier simulation states.',
      'Трассируйте значения, отслеживайте сигналы и восстанавливайте прежние состояния.',
    ),
    detail: t(
      'Breakpoints, watchpoints, historical state snapshots and branch navigation help investigate a circuit.',
      'Точки останова, watchpoint, исторические снимки и ветви помогают разбирать работу схемы.',
    ),
    doc: 'debugger',
    group: 'inspect',
  },
  {
    id: 'time-travel',
    title: t('Time Travel', 'Перемотка симуляции'),
    summary: t(
      'Restore and compare recorded simulation states.',
      'Восстанавливайте и сравнивайте записанные состояния симуляции.',
    ),
    detail: t(
      'Navigate bounded history, place checkpoints and continue from an earlier step on a new branch.',
      'Перемещайтесь по ограниченной истории, ставьте контрольные точки и продолжайте с прежнего шага в новой ветке.',
    ),
    doc: 'debugger',
    group: 'inspect',
  },
  {
    id: 'analyzer',
    title: t('Logic analyzer', 'Логический анализатор'),
    summary: t(
      'Inspect multiple channels and transitions across logical steps.',
      'Изучайте несколько каналов и переходы по логическим шагам.',
    ),
    detail: t(
      'Capture signal history, search edges and changes, and view multibit values in binary, decimal or hex.',
      'Записывайте историю, ищите фронты и изменения, просматривайте шины в двоичном, десятичном и шестнадцатеричном виде.',
    ),
    doc: 'debugger',
    group: 'inspect',
  },
  {
    id: 'timing',
    title: t('Timing diagram', 'Временная диаграмма'),
    summary: t(
      'See selected pin waveforms and inspect a recorded step.',
      'Смотрите формы сигналов выбранных пинов и значения на записанном шаге.',
    ),
    detail: t(
      'The axis represents logical simulation steps; it is not a calibrated hardware timing measurement.',
      'Ось показывает логические шаги симуляции, а не калиброванное аппаратное время.',
    ),
    doc: 'debugger',
    group: 'inspect',
  },
  {
    id: 'testbench',
    title: t('Testbench', 'Тестбенч'),
    summary: t(
      'Check circuits against input sequences and expected outputs.',
      'Проверяйте схемы входными последовательностями и ожидаемыми результатами.',
    ),
    detail: t(
      'Testbenches run on isolated copies so the live circuit state is preserved.',
      'Тестбенчи выполняются на изолированных копиях, сохраняя состояние живой схемы.',
    ),
    doc: 'debugger',
    group: 'inspect',
  },
  {
    id: 'fpga',
    title: t('FPGA preparation', 'Подготовка FPGA-проекта'),
    summary: t(
      'Validate HDL, profiles and constraints, then export a project package.',
      'Проверяйте HDL, профили и ограничения, затем экспортируйте пакет проекта.',
    ),
    detail: t(
      'Exports a self-contained HDL and iCE40 PCF package. It does not synthesize, place, route or program a board.',
      'Экспортирует автономный пакет HDL и iCE40 PCF. Не синтезирует, не размещает и не программирует плату.',
    ),
    doc: 'fpga',
    group: 'program',
  },
]

export interface DocSection {
  heading: Localized
  body: Localized
  code?: string
  link?: { title: Localized; url: string }
}
export interface Doc {
  slug: string
  title: Localized
  intro: Localized
  sections: DocSection[]
}

export const docs: Doc[] = [
  {
    slug: 'getting-started',
    title: t('Getting started', 'С чего начать'),
    intro: t(
      'Open a working example and see a circuit respond in a few minutes.',
      'Откройте рабочий пример и за несколько минут увидите схему в действии.',
    ),
    sections: [
      {
        heading: t('Install and launch', 'Установка и запуск'),
        body: t(
          'On Ubuntu 24.04+, download the source ZIP, extract it into a directory you own, and run the two scripts below. The installer creates a desktop entry and installs PySide6 Essentials locally if needed.',
          'На Ubuntu 24.04+ загрузите исходный ZIP, распакуйте в свой каталог и выполните две команды. Установщик создаст ярлык и при необходимости локально поставит PySide6 Essentials.',
        ),
        code: './install.sh\n./launch.sh',
      },
      {
        heading: t('Try the half-adder', 'Попробуйте полусумматор'),
        body: t(
          'On the Start screen select “Try the half-adder example”. Toggle INPUT A and B. The SUM and CARRY outputs and wire colors change with the simulated values. The example opens as an editable copy.',
          'На стартовом экране выберите «Try the half-adder example». Переключайте INPUT A и B: SUM, CARRY и цвет проводов меняются по результатам симуляции. Пример откроется как редактируемая копия.',
        ),
      },
      {
        heading: t('Go further', 'Что дальше'),
        body: t(
          'Use Step on a clocked example, open View → Timing Diagram to record pins, then press F1 for the full in-app guide. Ctrl+F searches components and signals.',
          'Используйте Step для схемы с тактом, откройте View → Timing Diagram для записи пинов и нажмите F1 для встроенного руководства. Ctrl+F ищет компоненты и сигналы.',
        ),
      },
    ],
  },
  {
    slug: 'linux-guide',
    title: t('Ubuntu / Linux guide', 'Руководство для Ubuntu / Linux'),
    intro: t(
      'Install the published source package on Ubuntu 24.04+.',
      'Установите опубликованный исходный пакет на Ubuntu 24.04+.',
    ),
    sections: [
      {
        heading: t('Get the official archive', 'Скачайте официальный архив'),
        body: t(
          'Use the latest published source ZIP on GitHub Releases. Extract it into a directory you own. The v3.1.0 source ZIP is the current Linux download.',
          'Используйте опубликованный исходный ZIP на GitHub Releases. Распакуйте его в свой каталог. Текущая загрузка для Linux — исходный ZIP v3.1.0.',
        ),
      },
      {
        heading: t('Install and launch', 'Установите и запустите'),
        body: t(
          'Python 3.12+ and a graphical session are required. Run both scripts inside the extracted directory. The installer uses a local .deps folder and creates a user desktop entry; it does not require sudo.',
          'Нужны Python 3.12+ и графическая сессия. Запустите оба скрипта из распакованного каталога. Установщик использует локальную .deps и создаёт пользовательский ярлык без sudo.',
        ),
        code: './install.sh\n./launch.sh',
      },
      {
        heading: t('Missing Qt runtime', 'Не хватает библиотек Qt'),
        body: t(
          'A minimal Ubuntu installation may need libegl1. Read the launch error before changing packages.',
          'Для минимальной Ubuntu может потребоваться libegl1. Сначала прочитайте ошибку запуска.',
        ),
        code: 'sudo apt install libegl1',
      },
    ],
  },
  {
    slug: 'windows-guide',
    title: t('Windows installation guide', 'Руководство по установке в Windows'),
    intro: t(
      'Install the published Windows 10/11 x64 packages and understand their limits.',
      'Установите опубликованные пакеты для Windows 10/11 x64 и узнайте об их ограничениях.',
    ),
    sections: [
      {
        heading: t('Publication status', 'Статус публикации'),
        body: t(
          'The v3.1.0 installer and portable ZIP are available from GitHub Releases. Native Windows CI checked startup, installation, reinstall and removal. Interactive testing on a separate Windows 10/11 computer is still outstanding.',
          'Установщик и portable ZIP v3.1.0 доступны на GitHub Releases. Windows CI проверил запуск, установку, повторную установку и удаление. Интерактивная проверка на отдельном компьютере с Windows 10/11 ещё не проводилась.',
        ),
      },
      {
        heading: t('Installer and portable', 'Установщик и portable'),
        body: t(
          'The installer runs for the current user with a Start menu shortcut and optional desktop shortcut. Extract the portable ZIP completely, then run LogicSpace/LogicSpace.exe. Python and PySide6 are bundled. Install the official Microsoft Visual C++ Redistributable x64 separately if needed.',
          'Установщик работает для текущего пользователя и добавляет ярлык в меню Start; ярлык на рабочем столе необязателен. Полностью распакуйте portable ZIP и запустите LogicSpace/LogicSpace.exe. Python и PySide6 включены. При необходимости отдельно установите официальный Microsoft Visual C++ Redistributable x64.',
        ),
      },
      {
        heading: t('Data and limitations', 'Данные и ограничения'),
        body: t(
          'Keep projects outside the application folder. Settings and libraries use %LOCALAPPDATA%\\LogicSpace. External Icarus, Yosys and Verilator execution is unavailable because the current sandbox uses Linux Bubblewrap. The packages are unsigned; do not disable Windows security protections.',
          'Храните проекты вне каталога приложения. Настройки и библиотеки используют %LOCALAPPDATA%\\LogicSpace. Внешний запуск Icarus, Yosys и Verilator недоступен: текущая изоляция использует Linux Bubblewrap. Пакеты не подписаны; не отключайте защиту Windows.',
        ),
      },
      {
        heading: t('Visual C++ runtime', 'Библиотеки Visual C++'),
        body: t(
          'Install the official Microsoft Visual C++ Redistributable x64 if it is not already present. LogicSpace does not bundle copies of Microsoft runtime DLLs.',
          'Если компонент ещё не установлен, установите официальный Microsoft Visual C++ Redistributable x64. LogicSpace не включает копии DLL Microsoft runtime.',
        ),
        link: {
          title: t('Microsoft download', 'Загрузка Microsoft'),
          url: 'https://learn.microsoft.com/en-us/cpp/windows/latest-supported-vc-redist',
        },
      },
      {
        heading: t('Qt library source', 'Исходники Qt'),
        body: t(
          'The release supplies upstream Qt/PySide6 sources and replacement instructions for the bundled libraries. These libraries retain their own licenses.',
          'Релиз содержит исходники Qt/PySide6 и инструкции по замене включённых библиотек. Для них действуют собственные лицензии.',
        ),
        link: {
          title: t('Download library sources', 'Скачать исходники библиотек'),
          url: QT_SOURCES,
        },
      },
    ],
  },
  {
    slug: 'interface',
    title: t('Interface overview', 'Обзор интерфейса'),
    intro: t(
      'The canvas stays central; tools are available when you need them.',
      'Холст остаётся главным; инструменты доступны по мере необходимости.',
    ),
    sections: [
      {
        heading: t('Canvas and sidebars', 'Холст и панели'),
        body: t(
          'The left sidebar contains the component library and tools. The center is the circuit workspace. Select a component to see its pins and configuration in the right Inspector.',
          'Слева находятся библиотека компонентов и инструменты, в центре — схема. Выберите элемент, чтобы увидеть его пины и параметры в Inspector справа.',
        ),
      },
      {
        heading: t('Toolbar and menus', 'Панель и меню'),
        body: t(
          'Run, Step, Reset and simulation Speed sit above the workspace. View opens Timing Diagram, HDL, debugging and other analysis panels. File manages projects.',
          'Run, Step, Reset и скорость симуляции находятся над холстом. Через View открываются Timing Diagram, HDL и отладочные панели. File управляет проектами.',
        ),
      },
      {
        heading: t('Keyboard', 'Клавиатура'),
        body: t(
          'Ctrl+F finds components or signals. F1 opens the in-app guide. Most commands are also in menus; inspect each menu for current shortcuts.',
          'Ctrl+F ищет элементы и сигналы, F1 открывает встроенное руководство. Остальные команды и актуальные сочетания есть в меню.',
        ),
      },
    ],
  },
  {
    slug: 'circuit-editor',
    title: t('Circuit editor', 'Редактор схем'),
    intro: t(
      'Build a connected circuit rather than a static drawing.',
      'Собирайте соединённую схему, а не статичный рисунок.',
    ),
    sections: [
      {
        heading: t('Place and connect', 'Размещение и соединение'),
        body: t(
          'Drag a component from the left library onto the canvas. Click an output pin and then a compatible input pin to create a real wire. Component movement updates connected wire paths.',
          'Перетащите элемент из библиотеки слева. Нажмите выходной пин, затем совместимый входной: появится настоящий провод. При перемещении элемента путь провода обновляется.',
        ),
      },
      {
        heading: t('Navigate', 'Навигация'),
        body: t(
          'Pan the empty canvas by dragging; zoom with the wheel. Use multi-selection, box selection, duplication and undo/redo for larger edits. Snapping can be toggled from the toolbar.',
          'Перемещайте пустой холст перетаскиванием, масштабируйте колесом. Используйте множественное и рамочное выделение, дублирование и отмену. Привязка к сетке переключается в панели.',
        ),
      },
      {
        heading: t('Save and reuse', 'Сохранение и повторное использование'),
        body: t(
          'Projects use JSON. Custom Blocks can be built from a selection or in the Block Designer and saved in the global library. Imported project data is validated.',
          'Проекты сохраняются в JSON. Пользовательские блоки создаются из выделения или в Block Designer и сохраняются в глобальную библиотеку. Импортируемые данные проходят проверку.',
        ),
      },
    ],
  },
  {
    slug: 'simulator',
    title: t('Simulator', 'Симулятор'),
    intro: t(
      'LogicSpace runs actual connected circuits with its central simulation engine.',
      'LogicSpace вычисляет реальные соединённые схемы центральным движком.',
    ),
    sections: [
      {
        heading: t('Controls', 'Управление'),
        body: t(
          'Use Run to advance continuously, Pause to stop advancing, Step for one logical step and Reset for a fresh state. Speed changes how often steps run; it does not assign physical frequency.',
          'Run запускает непрерывное выполнение, Pause останавливает, Step выполняет один логический шаг, Reset сбрасывает состояние. Speed меняет частоту шагов, но не задаёт физическую частоту.',
        ),
      },
      {
        heading: t('Signal values', 'Значения сигналов'),
        body: t(
          'Wires and pins carry 0, 1 or X. Sequential elements retain state across steps. Clock edges are processed by the existing engine. X is unknown, not zero.',
          'Пины и провода несут 0, 1 или X. Последовательные элементы хранят состояние между шагами, а фронты Clock обрабатывает существующий движок. X — неизвестное значение, не ноль.',
        ),
      },
      {
        heading: t('Time model', 'Модель времени'),
        body: t(
          'The step counter and waveform axes count logical simulation steps. LogicSpace does not claim physical propagation delays, setup/hold timing or a full Verilog delta-cycle model.',
          'Счётчик и ось диаграммы показывают логические шаги. LogicSpace не моделирует физические задержки, setup/hold и полную очередь delta-cycle Verilog.',
        ),
      },
    ],
  },
  {
    slug: 'components',
    title: t('Components and buses', 'Компоненты и шины'),
    intro: t(
      'From gates to memory, every supported digital connection has a simulation meaning.',
      'От вентилей до памяти: каждое поддерживаемое цифровое соединение участвует в симуляции.',
    ),
    sections: [
      {
        heading: t('Digital building blocks', 'Цифровые блоки'),
        body: t(
          'The library includes gates, adders, multiplexers, flip-flops, registers, counters, clocks, RAM, ROM, register files, ALU and CPU blocks. Select a component to adjust supported settings in Inspector.',
          'Библиотека включает вентили, сумматоры, мультиплексоры, триггеры, регистры, счётчики, Clock, RAM, ROM, файлы регистров, ALU и CPU-блоки. Поддерживаемые параметры меняются в Inspector.',
        ),
      },
      {
        heading: t('BusWire', 'BusWire'),
        body: t(
          'Native buses support widths 1, 2, 4, 8, 16 and 32. Bit 0 is the least significant bit. The editor validates mismatched widths. Splitter, Merger, Bit Selector, Bus Input, Bus Output and Bus Probe work with the same bus model.',
          'Шины поддерживают 1, 2, 4, 8, 16 и 32 бита. Bit 0 — младший. Редактор проверяет несовместимые ширины. Splitter, Merger, Bit Selector, Bus Input, Bus Output и Bus Probe работают с единой моделью.',
        ),
      },
      {
        heading: t('Analog limits', 'Ограничения аналоговых элементов'),
        body: t(
          'Use the component inspector and documentation to distinguish simulated digital behavior from visual-only analog placeholders. LogicSpace is a digital logic simulator, not a SPICE model.',
          'По Inspector и документации отличайте симулируемые цифровые элементы от визуальных аналоговых заготовок. LogicSpace — цифровой симулятор, а не SPICE.',
        ),
      },
    ],
  },
  {
    slug: 'cpu-assembly',
    title: t('CPU & Assembly', 'CPU и Assembly'),
    intro: t(
      'Program a processor assembled from connected LogicSpace components.',
      'Программируйте процессор, собранный из соединённых компонентов LogicSpace.',
    ),
    sections: [
      {
        heading: t('Architecture', 'Архитектура'),
        body: t(
          'ISA 2.1 is an 8-bit data and address architecture with R0–R3, PC, ROM, RAM, ALU, IR and a wired Control Unit. The CPU binder validates component types, ports, widths and connections.',
          'ISA 2.1 использует 8-битные данные и адреса, R0–R3, PC, ROM, RAM, ALU, IR и соединённый Control Unit. Привязка CPU проверяет типы, порты, ширины и соединения.',
        ),
      },
      {
        heading: t('Assemble and execute', 'Сборка и выполнение'),
        body: t(
          'The two-pass assembler resolves labels and exports BIN or Intel HEX. Loading a program writes the selected CPU ROM. Clock-driven execution then proceeds through actual components rather than a hidden CPU interpreter.',
          'Двухпроходный ассемблер разрешает метки и экспортирует BIN или Intel HEX. Загрузка записывает выбранную ROM CPU. Затем Clock проводит инструкции через реальные компоненты без скрытого интерпретатора.',
        ),
        code: 'START:\n    MOV R0, 10\n    MOV R1, 5\n    ADD R0, R1\n    HLT',
      },
      {
        heading: t('Debug', 'Отладка'),
        body: t(
          'Use CPU binding and the CPU debugger to inspect PC, registers, memory and instruction history. Multiple CPUs can be bound independently. See the source guide for the full ISA table.',
          'Через привязку и CPU debugger смотрите PC, регистры, память и историю инструкций. Несколько CPU можно привязать независимо. Полная таблица ISA есть в руководстве.',
        ),
        link: {
          title: t('Open the detailed CPU guide', 'Открыть подробное руководство CPU'),
          url: GUIDE,
        },
      },
    ],
  },
  {
    slug: 'hdl',
    title: t('HDL / Verilog', 'HDL / Verilog'),
    intro: t(
      'A checked HDL subset turns supported modules into real editable circuits.',
      'Проверенное подмножество HDL преобразует поддерживаемые модули в настоящие редактируемые схемы.',
    ),
    sections: [
      {
        heading: t('Editor and validation', 'Редактор и проверка'),
        body: t(
          'Open View → HDL / Verilog. Edit .v or .sv files, validate syntax and widths, use line diagnostics and test vectors. Syntax support is deliberately limited and documented.',
          'Откройте View → HDL / Verilog. Редактируйте .v или .sv, проверяйте синтаксис и ширины, используйте диагностику по строкам и тестовые векторы. Поддержка языка ограничена и документирована.',
        ),
      },
      {
        heading: t('Import and export', 'Импорт и экспорт'),
        body: t(
          'Supported combinational logic and limited sequential blocks import into ordinary gates, wires, registers and memory components. Export reports unsupported elements instead of silently replacing them.',
          'Поддерживаемая комбинационная и ограниченная последовательная логика импортируется в обычные вентили, провода, регистры и память. Экспорт сообщает о неподдерживаемых элементах.',
        ),
        code: 'module gate(input a, input b, output y);\n  assign y = a & b;\nendmodule',
      },
      {
        heading: t('External verification', 'Внешняя проверка'),
        body: t(
          'Icarus Verilog can compare results only if iverilog, vvp and a usable Bubblewrap sandbox are installed. Yosys and Verilator are optional. Internal LogicSpace vector tests are not independent HDL verification.',
          'Icarus Verilog сравнивает результаты только при наличии iverilog, vvp и работающего Bubblewrap. Yosys и Verilator необязательны. Внутренние тесты LogicSpace не являются независимой HDL-проверкой.',
        ),
        link: {
          title: t('Read the HDL examples', 'Смотреть примеры HDL'),
          url: `${REPO}/tree/v3.1.0/examples/hdl30`,
        },
      },
    ],
  },
  {
    slug: 'debugger',
    title: t('Debugger and analysis', 'Отладка и анализ'),
    intro: t(
      'Inspect the cause and history of digital values without changing circuit structure.',
      'Изучайте причины и историю цифровых значений, не меняя структуру схемы.',
    ),
    sections: [
      {
        heading: t('Waveforms and traces', 'Диаграммы и трассировка'),
        body: t(
          'Timing Diagram records selected pins as logical-step waveforms. Logic Analyzer monitors multiple channels and edges. Signal Tracing shows connectivity and, when recorded data supports it, simulation-backed explanations.',
          'Timing Diagram записывает выбранные пины по логическим шагам. Logic Analyzer наблюдает каналы и фронты. Signal Tracing показывает связи и, когда данных достаточно, объяснения на основе симуляции.',
        ),
      },
      {
        heading: t('Testbench', 'Тестбенч'),
        body: t(
          'Define input sequences and expected outputs. Tests run on isolated copies, so the live editor and active simulation state are preserved. Failures can be inspected with existing debugging tools.',
          'Задайте последовательности входов и ожидаемых выходов. Тесты идут на изолированных копиях и не меняют живую схему. Ошибки можно изучать отладочными инструментами.',
        ),
      },
      {
        heading: t('Time Travel and memory', 'Time Travel и память'),
        body: t(
          'Bounded state history supports backward/forward navigation, checkpoints, branches and comparison. Memory Inspector displays and edits RAM/ROM with confirmed changes. Retained history is session-limited.',
          'Ограниченная история позволяет переходить по шагам, сохранять контрольные точки, ветви и сравнивать состояния. Memory Inspector показывает и редактирует RAM/ROM с подтверждением. История ограничена текущим сеансом.',
        ),
      },
    ],
  },
  {
    slug: 'fpga',
    title: t('FPGA workflow', 'FPGA workflow'),
    intro: t(
      'Prepare an HDL package and validate constraints before using external toolchains.',
      'Подготовьте HDL-пакет и проверьте ограничения перед внешними инструментами.',
    ),
    sections: [
      {
        heading: t('Prepare', 'Подготовка'),
        body: t(
          'Choose a top module, add HDL sources and a user-supplied device profile, then assign pins and clock constraints. LogicSpace validates known issues and exports an HDL + iCE40 PCF ZIP.',
          'Выберите верхний модуль, добавьте HDL, пользовательский профиль устройства, назначения пинов и ограничения Clock. LogicSpace проверит известные ошибки и экспортирует ZIP с HDL и iCE40 PCF.',
        ),
      },
      {
        heading: t('Scope', 'Границы'),
        body: t(
          'LogicSpace does not ship a verified FPGA pin database. Package export is not synthesis, place-and-route, programming or physical timing verification. Run and validate external tools separately.',
          'LogicSpace не поставляет проверенную базу пинов FPGA. Экспорт пакета — не синтез, размещение, программирование или проверка физического времени. Внешние инструменты проверяются отдельно.',
        ),
      },
    ],
  },
  {
    slug: 'faq',
    title: t('FAQ', 'Частые вопросы'),
    intro: t(
      'Straight answers about platform, licensing and simulator scope.',
      'Короткие ответы о платформе, лицензии и границах симуляции.',
    ),
    sections: [
      {
        heading: t('Does it run on Windows or macOS?', 'Работает ли на Windows или macOS?'),
        body: t(
          'v3.1.0 supports Ubuntu 24.04+ from source and provides Windows 10/11 x64 installer and portable packages. Windows CI passed; interactive Windows testing on a separate computer is outstanding. No macOS package is offered.',
          'v3.1.0 поддерживает Ubuntu 24.04+ из исходников и содержит установщик и portable-пакет для Windows 10/11 x64. Windows CI пройден, но ручная проверка на отдельном компьютере остаётся. Пакета для macOS нет.',
        ),
      },
      {
        heading: t('Is LogicSpace open source?', 'LogicSpace — open source?'),
        body: t(
          'v3.1.0 includes the author-accepted LogicSpace Proprietary Source-Available License text, still marked as a draft for legal review. It is not OSI Open Source. Distribution and commercial rights require separate written permission; third-party libraries retain their own licenses. v3.0.0 is unchanged.',
          'v3.1.0 содержит принятый автором текст LogicSpace Proprietary Source-Available License, всё ещё помеченный как проект для юридической проверки. Это не OSI Open Source. Для распространения и коммерческого использования нужно отдельное письменное разрешение; у сторонних библиотек свои лицензии. v3.0.0 не изменён.',
        ),
      },
      {
        heading: t('Is there a ready-made package?', 'Есть готовый пакет?'),
        body: t(
          'v3.1.0 provides a Linux source ZIP and Windows x64 installer and portable ZIP. There is no verified .deb, AppImage or automatic in-place updater.',
          'v3.1.0 содержит исходный ZIP для Linux и установщик и portable ZIP для Windows x64. Проверенного .deb, AppImage и автоматической замены файлов нет.',
        ),
      },
    ],
  },
  {
    slug: 'known-limitations',
    title: t('Known limitations', 'Известные ограничения'),
    intro: t(
      'The simulator and release packages have deliberate, documented boundaries.',
      'У симулятора и пакетов выпуска есть чётко обозначенные границы.',
    ),
    sections: [
      {
        heading: t('Logical time', 'Логическое время'),
        body: t(
          'Timing Diagram and Time Travel operate on logical simulation steps. They do not measure physical propagation delay or hardware setup and hold time.',
          'Timing Diagram и Time Travel работают с логическими шагами симуляции. Они не измеряют физические задержки и аппаратные времена setup/hold.',
        ),
      },
      {
        heading: t('HDL and FPGA', 'HDL и FPGA'),
        body: t(
          'Only the documented HDL subset is imported as editable components. FPGA export prepares HDL and constraints; it does not synthesize or program a device. External checks require separately installed tools and the supported sandbox.',
          'В редактируемые компоненты импортируется только документированное подмножество HDL. FPGA-экспорт готовит HDL и ограничения, но не выполняет синтез и программирование. Внешние проверки требуют отдельных инструментов и поддерживаемой изоляции.',
        ),
      },
      {
        heading: t('Installation and release status', 'Установка и статус выпуска'),
        body: t(
          'The current Linux distribution is a source ZIP, and Windows has installer and portable packages. No .deb or AppImage is verified. Windows interactive testing on a separate computer remains open. Automatic in-place updates are unavailable.',
          'Текущий дистрибутив Linux — исходный ZIP, для Windows доступны установщик и portable. Проверенного .deb или AppImage нет. Ручная проверка на отдельном Windows-компьютере остаётся. Автоматической замены файлов нет.',
        ),
      },
    ],
  },
  {
    slug: 'troubleshooting',
    title: t('Troubleshooting', 'Устранение проблем'),
    intro: t(
      'Check the actual runtime and installation paths before changing the circuit.',
      'Сначала проверьте установку и графическую среду, затем схему.',
    ),
    sections: [
      {
        heading: t('PySide6 is missing', 'PySide6 не найден'),
        body: t(
          'Run ./install.sh from the extracted project folder. The script installs PySide6 Essentials into .deps when it is unavailable. Verify you are launching from that same folder.',
          'Запустите ./install.sh из распакованного каталога. Скрипт установит PySide6 Essentials в .deps, если пакет недоступен. Убедитесь, что запускаете ту же копию проекта.',
        ),
        code: './install.sh\n./launch.sh',
      },
      {
        heading: t('Qt EGL error', 'Ошибка Qt EGL'),
        body: t(
          'Minimal Ubuntu installations may lack libegl1. The launch script reports this possible missing runtime. Install the Ubuntu package using your normal system package manager, then retry.',
          'В минимальной Ubuntu может отсутствовать libegl1. Скрипт запуска сообщает об этом возможном компоненте. Установите пакет штатным менеджером и повторите запуск.',
        ),
        code: 'sudo apt install libegl1',
      },
      {
        heading: t('HDL tool unavailable', 'HDL-инструмент недоступен'),
        body: t(
          'Icarus, Yosys, Verilator, GTKWave and Bubblewrap are optional and not included. External HDL execution also needs usable Bubblewrap namespaces. The app still runs without them.',
          'Icarus, Yosys, Verilator, GTKWave и Bubblewrap необязательны и не входят в пакет. Для внешнего HDL требуется рабочая изоляция Bubblewrap. Само приложение работает без этих инструментов.',
        ),
      },
      {
        heading: t('Circuit output is X', 'Выход схемы равен X'),
        body: t(
          'Inspect pin connectivity, component widths and the Inspector values. X represents an unknown digital value; it is not silently converted to 0.',
          'Проверьте соединения пинов, ширины компонентов и значения в Inspector. X означает неизвестное цифровое значение и не преобразуется в 0.',
        ),
      },
    ],
  },
]

export function searchDocs(query: string, lang: Language): Doc[] {
  const normalized = query.trim().toLocaleLowerCase()
  if (!normalized) return docs
  return docs.filter((doc) =>
    [
      doc.title[lang],
      doc.intro[lang],
      ...doc.sections.flatMap((section) => [section.heading[lang], section.body[lang]]),
    ].some((value) => value.toLocaleLowerCase().includes(normalized)),
  )
}
