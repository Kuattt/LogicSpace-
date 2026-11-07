import { useEffect, useMemo, useState, type ReactNode } from 'react'
import { Link, NavLink, Route, Routes, useLocation, useParams } from 'react-router-dom'
import {
  Activity,
  ArrowDownToLine,
  ArrowLeft,
  ArrowRight,
  ArrowUpRight,
  Binary,
  BookOpen,
  Check,
  ChevronRight,
  CircuitBoard,
  Clock3,
  Code2,
  Copy,
  Cpu,
  ExternalLink,
  FileCode2,
  GitBranch,
  Layers,
  ListChecks,
  Menu,
  Moon,
  Search,
  ShieldCheck,
  Sun,
  Terminal,
  X,
  type LucideIcon,
} from 'lucide-react'
import CircuitDemo from './CircuitDemo'
import {
  CHANGELOG,
  CHECKSUM_FILE,
  docs,
  features,
  GUIDE,
  RELEASE,
  REPO,
  searchDocs,
  SHA256,
  SOURCE_ARCHIVE,
  SOURCE_ZIP,
  t,
  type Feature,
  type Language,
} from './content'

type Theme = 'dark' | 'light'
const icons: Record<string, LucideIcon> = {
  editor: CircuitBoard,
  simulator: Activity,
  bus: Binary,
  cpu: Cpu,
  assembly: Code2,
  hdl: FileCode2,
  debugger: GitBranch,
  analyzer: Activity,
  timing: Clock3,
  testbench: ListChecks,
  fpga: Layers,
}

function readPreference<T extends string>(key: string, allowed: readonly T[], fallback: T): T {
  try {
    const value = localStorage.getItem(key)
    return allowed.find((option) => option === value) ?? fallback
  } catch {
    return fallback
  }
}

function External({
  href,
  children,
  className = '',
}: {
  href: string
  children: ReactNode
  className?: string
}) {
  return (
    <a className={className} href={href} target="_blank" rel="noopener noreferrer">
      {children}
    </a>
  )
}

function Brand() {
  return (
    <Link to="/" className="brand" aria-label="LogicSpace home">
      <img src="/logicspace.svg" width="34" height="34" alt="" />
      <span>
        Logic<span className="brand-light">Space</span>
      </span>
      <span className="brand-version">3.0</span>
    </Link>
  )
}

function SectionEyebrow({ index, children }: { index?: string; children: ReactNode }) {
  return (
    <div className="eyebrow">
      {index && <span className="eyebrow-index">{index}</span>}
      {children}
    </div>
  )
}

function ButtonLink({
  to,
  children,
  variant = 'primary',
  external = false,
}: {
  to: string
  children: ReactNode
  variant?: 'primary' | 'secondary' | 'text'
  external?: boolean
}) {
  const cls = `button button-${variant}`
  return external ? (
    <External href={to} className={cls}>
      {children}
    </External>
  ) : (
    <Link to={to} className={cls}>
      {children}
    </Link>
  )
}

function Header({
  language,
  setLanguage,
  theme,
  setTheme,
}: {
  language: Language
  setLanguage: (lang: Language) => void
  theme: Theme
  setTheme: (theme: Theme) => void
}) {
  const [open, setOpen] = useState(false)
  const location = useLocation()
  useEffect(() => setOpen(false), [location.pathname])
  const tr = (en: string, ru: string) => t(en, ru)[language]
  const nav = [
    ['/', tr('Overview', 'Главная')],
    ['/features', tr('Features', 'Функции')],
    ['/docs', tr('Docs', 'Документация')],
    ['/releases', tr('Releases', 'Релизы')],
    ['/about', tr('About', 'О проекте')],
  ]
  return (
    <header className="site-header">
      <div className="header-inner container">
        <Brand />
        <nav
          className={`main-nav ${open ? 'nav-open' : ''}`}
          id="main-navigation"
          aria-label={tr('Main navigation', 'Основная навигация')}
        >
          {nav.map(([url, title]) => (
            <NavLink
              key={url}
              to={url}
              end={url === '/'}
              className={({ isActive }) => `nav-link ${isActive ? 'active' : ''}`}
            >
              {title}
            </NavLink>
          ))}
          <Link to="/download" className="button button-nav mobile-download">
            {tr('Download', 'Скачать')}
            <ArrowUpRight size={15} />
          </Link>
        </nav>
        <div className="header-actions">
          <button
            type="button"
            className="icon-button lang-button"
            onClick={() => setLanguage(language === 'en' ? 'ru' : 'en')}
            aria-label={tr('Switch to Russian', 'Переключить на английский')}
            title={tr('Switch to Russian', 'Переключить на английский')}
          >
            {language.toUpperCase()} <span aria-hidden="true">/</span>{' '}
            {language === 'en' ? 'RU' : 'EN'}
          </button>
          <button
            type="button"
            className="icon-button theme-button"
            onClick={() => setTheme(theme === 'dark' ? 'light' : 'dark')}
            aria-label={
              theme === 'dark'
                ? tr('Switch to light theme', 'Включить светлую тему')
                : tr('Switch to dark theme', 'Включить тёмную тему')
            }
            title={
              theme === 'dark' ? tr('Light theme', 'Светлая тема') : tr('Dark theme', 'Тёмная тема')
            }
          >
            {theme === 'dark' ? <Sun size={18} /> : <Moon size={18} />}
          </button>
          <Link to="/download" className="button button-nav desktop-download">
            {tr('Download', 'Скачать')}
            <ArrowUpRight size={15} />
          </Link>
          <button
            className="icon-button mobile-toggle"
            type="button"
            aria-controls="main-navigation"
            aria-expanded={open}
            aria-label={open ? tr('Close menu', 'Закрыть меню') : tr('Open menu', 'Открыть меню')}
            onClick={() => setOpen(!open)}
          >
            {open ? <X size={22} /> : <Menu size={22} />}
          </button>
        </div>
      </div>
    </header>
  )
}

function Footer({ language }: { language: Language }) {
  const tr = (en: string, ru: string) => t(en, ru)[language]
  return (
    <footer className="site-footer">
      <div className="container footer-main">
        <div className="footer-about">
          <Brand />
          <p>
            {tr(
              'A native Ubuntu workspace for digital circuits, logical simulation and exploring computer building blocks.',
              'Нативное Ubuntu-пространство для цифровых схем, логической симуляции и изучения компонентов компьютера.',
            )}
          </p>
          <span className="footer-note">
            {tr('Built with Python · PySide6 · Qt', 'Создано на Python · PySide6 · Qt')}
          </span>
        </div>
        <div className="footer-column">
          <strong>{tr('Explore', 'Изучить')}</strong>
          <Link to="/features">{tr('Features', 'Функции')}</Link>
          <Link to="/docs">{tr('Documentation', 'Документация')}</Link>
          <Link to="/download">{tr('Download', 'Скачать')}</Link>
          <Link to="/releases">{tr('Releases', 'Релизы')}</Link>
        </div>
        <div className="footer-column">
          <strong>{tr('Project', 'Проект')}</strong>
          <External href={REPO}>
            GitHub <ArrowUpRight size={13} />
          </External>
          <External href={`${REPO}/issues`}>
            {tr('Issues', 'Задачи')} <ArrowUpRight size={13} />
          </External>
          <External href={CHANGELOG}>
            Changelog <ArrowUpRight size={13} />
          </External>
          <Link to="/about">{tr('About & licensing', 'О проекте и лицензировании')}</Link>
        </div>
      </div>
      <div className="container footer-bottom">
        <span>LogicSpace 3.0.0</span>
        <span>
          {tr(
            'Source release · Ubuntu/Linux · No tracking on this site',
            'Релиз исходников · Ubuntu/Linux · Без отслеживания на сайте',
          )}
        </span>
      </div>
    </footer>
  )
}

function PageHeading({
  eyebrow,
  title,
  lead,
  children,
}: {
  eyebrow: string
  title: string
  lead: string
  children?: ReactNode
}) {
  return (
    <div className="page-heading container">
      <SectionEyebrow>{eyebrow}</SectionEyebrow>
      <h1>{title}</h1>
      <p>{lead}</p>
      {children}
    </div>
  )
}

function Screenshot({ src, alt, label }: { src: string; alt: string; label: string }) {
  return (
    <figure className="screenshot">
      <div className="screenshot-bar">
        <span className="chrome-dots">
          <i />
          <i />
          <i />
        </span>
        <span>LogicSpace / {label}</span>
        <span>3.0.0</span>
      </div>
      <img src={src} alt={alt} loading="lazy" />
      <figcaption>{label} · LogicSpace 3.0.0</figcaption>
    </figure>
  )
}

function Home({ language }: { language: Language }) {
  const tr = (en: string, ru: string) => t(en, ru)[language]
  return (
    <>
      <section className="hero">
        <div className="hero-glow" aria-hidden="true" />
        <div className="container hero-grid">
          <div className="hero-copy">
            <div className="release-pill">
              <span className="release-dot" />{' '}
              {tr('VERSION 3.0.0 · SOURCE RELEASE', 'ВЕРСИЯ 3.0.0 · ИСХОДНЫЙ РЕЛИЗ')}{' '}
              <ChevronRight size={14} />
            </div>
            <h1>
              {tr('Build the circuit.', 'Собери схему.')}
              <br />
              <span>{tr('Understand the signal.', 'Пойми сигнал.')}</span>
            </h1>
            <p className="hero-lead">
              {tr(
                'A focused Ubuntu desktop workspace for building digital circuits, running real logical simulation, and seeing what happens inside the machine.',
                'Нативное рабочее пространство для Ubuntu: собирайте цифровые схемы, запускайте логическую симуляцию и наблюдайте, что происходит внутри машины.',
              )}
            </p>
            <div className="hero-buttons">
              <ButtonLink to="/download">
                {tr('Download for Ubuntu', 'Скачать для Ubuntu')} <ArrowDownToLine size={18} />
              </ButtonLink>
              <ButtonLink to="/docs" variant="secondary">
                {tr('Read documentation', 'Открыть документацию')} <ArrowRight size={17} />
              </ButtonLink>
            </div>
            <div className="hero-subnote">
              <span>{tr('Python 3.12+ · Ubuntu 24.04+', 'Python 3.12+ · Ubuntu 24.04+')}</span>
              <span className="subnote-separator" />
              <span>{tr('No account required', 'Без учётной записи')}</span>
            </div>
          </div>
          <div className="hero-visual">
            <div className="visual-halo" aria-hidden="true" />
            <Screenshot
              src="/images/workspace.png"
              alt={tr(
                'Actual LogicSpace workspace with a half-adder circuit, component library and Inspector',
                'Настоящий холст LogicSpace с полусумматором, библиотекой элементов и Inspector',
              )}
              label={tr('Circuit workspace', 'Холст схемы')}
            />
            <div className="hero-float float-top">
              <span className="float-legend">SIGNAL 1</span>
              <span className="float-led" />
            </div>
            <div className="hero-float float-bottom">
              <Binary size={16} />
              {tr('0 / 1 / X states', 'Состояния 0 / 1 / X')}
            </div>
          </div>
        </div>
      </section>

      <section className="signal-strip">
        <div className="container strip-inner">
          <span>{tr('One connected workflow', 'Единый процесс')}</span>
          <span>
            <CircuitBoard size={17} />
            {tr('Draw', 'Собери')}
          </span>
          <ChevronRight size={14} />
          <span>
            <Activity size={17} />
            {tr('Simulate', 'Запусти')}
          </span>
          <ChevronRight size={14} />
          <span>
            <GitBranch size={17} />
            {tr('Debug', 'Отладь')}
          </span>
          <span className="strip-caption">
            {tr('Canvas → engine → insight', 'Холст → движок → понимание')}
          </span>
        </div>
      </section>

      <section className="section container">
        <div className="section-heading">
          <div>
            <SectionEyebrow index="01">
              {tr('A circuit, not a picture', 'Схема, а не картинка')}
            </SectionEyebrow>
            <h2>{tr('Every wire means something.', 'Каждый провод имеет значение.')}</h2>
          </div>
          <p>
            {tr(
              'Place gates, clocks, registers, memory and buses on the canvas. Connections carry real digital values through LogicSpace’s central simulator.',
              'Размещайте вентили, Clock, регистры, память и шины. Соединения передают реальные цифровые значения через центральный симулятор LogicSpace.',
            )}
          </p>
        </div>
        <div className="proof-grid">
          <div className="proof-item">
            <div className="proof-icon">
              <Binary size={24} />
            </div>
            <strong>1–32 bit</strong>
            <span>{tr('validated bus widths', 'проверяемые ширины шин')}</span>
          </div>
          <div className="proof-item">
            <div className="proof-icon">
              <Activity size={24} />
            </div>
            <strong>0 · 1 · X</strong>
            <span>{tr('visible signal states', 'видимые состояния сигналов')}</span>
          </div>
          <div className="proof-item">
            <div className="proof-icon">
              <Cpu size={24} />
            </div>
            <strong>ISA 2.1</strong>
            <span>{tr('wired 8-bit CPU workflow', 'работа с 8-битным CPU')}</span>
          </div>
        </div>
      </section>

      <section className="section demo-section">
        <div className="container">
          <div className="section-heading">
            <div>
              <SectionEyebrow index="02">{tr('Try a signal', 'Попробуйте сигнал')}</SectionEyebrow>
              <h2>
                {tr('The simplest proof is a switch.', 'Самая простая проверка — переключатель.')}
              </h2>
            </div>
            <p>
              {tr(
                'Toggle the inputs to explore a half-adder. This browser illustration uses the exact XOR and AND truth functions; the desktop app simulates the editable circuit.',
                'Переключайте входы полусумматора. Браузерный пример использует точные функции XOR и AND; настольное приложение симулирует редактируемую схему.',
              )}
            </p>
          </div>
          <CircuitDemo language={language} />
        </div>
      </section>

      <section className="section container focus-section">
        <div className="section-heading">
          <div>
            <SectionEyebrow index="03">
              {tr('From components to systems', 'От компонентов к системе')}
            </SectionEyebrow>
            <h2>{tr('Follow the logic all the way up.', 'Проследите логику до самой системы.')}</h2>
          </div>
          <p>
            {tr(
              'Keep the same circuit model as you move from a first gate to a wired CPU or a supported HDL module.',
              'Используйте одну и ту же модель схемы — от первого вентиля до соединённого CPU или поддерживаемого HDL-модуля.',
            )}
          </p>
        </div>
        <div className="focus-grid">
          <div className="focus-feature">
            <span className="focus-number">01 / DESIGN</span>
            <CircuitBoard size={28} />
            <h3>{tr('Build precisely', 'Собирайте точно')}</h3>
            <p>
              {tr(
                'Visual editor, Inspector, BusWire, custom blocks and JSON projects.',
                'Визуальный редактор, Inspector, BusWire, свои блоки и JSON-проекты.',
              )}
            </p>
            <Link to="/features">
              {tr('Explore features', 'Все возможности')} <ArrowRight size={17} />
            </Link>
          </div>
          <div className="focus-feature">
            <span className="focus-number">02 / PROGRAM</span>
            <Cpu size={28} />
            <h3>{tr('Program the machine', 'Программируйте машину')}</h3>
            <p>
              {tr(
                'Assemble ISA 2.1, load actual ROM or import supported Verilog.',
                'Собирайте ISA 2.1, загружайте настоящую ROM или импортируйте поддерживаемый Verilog.',
              )}
            </p>
            <Link to="/docs/cpu-assembly">
              {tr('CPU & Assembly guide', 'Руководство CPU')} <ArrowRight size={17} />
            </Link>
          </div>
          <div className="focus-feature">
            <span className="focus-number">03 / INSPECT</span>
            <GitBranch size={28} />
            <h3>{tr('See why it changed', 'Узнайте, почему меняется')}</h3>
            <p>
              {tr(
                'Timing Diagram, tracing, testbench and Time Travel reveal state over logical steps.',
                'Timing Diagram, трассировка, тестбенч и Time Travel показывают состояние по шагам.',
              )}
            </p>
            <Link to="/docs/debugger">
              {tr('Debugging guide', 'Руководство по отладке')} <ArrowRight size={17} />
            </Link>
          </div>
        </div>
      </section>

      <section className="section showcase-section">
        <div className="container showcase-grid">
          <div className="showcase-copy">
            <SectionEyebrow index="04">{tr('HDL meets canvas', 'HDL и холст')}</SectionEyebrow>
            <h2>{tr('Read the code. See the circuit.', 'Читайте код. Смотрите схему.')}</h2>
            <p>
              {tr(
                'The HDL panel validates a documented Verilog/SystemVerilog subset. Supported modules import as editable LogicSpace components; unsupported syntax reports a diagnostic.',
                'HDL-панель проверяет документированное подмножество Verilog/SystemVerilog. Поддерживаемые модули становятся редактируемыми элементами LogicSpace; неподдерживаемый синтаксис выдаёт ошибку.',
              )}
            </p>
            <ButtonLink to="/docs/hdl" variant="text">
              {tr('Explore HDL workflow', 'Изучить HDL workflow')}
              <ArrowRight size={18} />
            </ButtonLink>
            <div className="showcase-disclaimer">
              <ShieldCheck size={17} />
              {tr(
                'Subset support, explicitly documented',
                'Подмножество языка, ограничения указаны',
              )}
            </div>
          </div>
          <Screenshot
            src="/images/hdl-editor.png"
            alt={tr(
              'Actual LogicSpace HDL editor next to a circuit',
              'Настоящий HDL-редактор LogicSpace рядом со схемой',
            )}
            label={tr('HDL editor', 'HDL-редактор')}
          />
        </div>
      </section>

      <section className="section container final-cta">
        <div>
          <SectionEyebrow>{tr('Ready to explore?', 'Готовы начать?')}</SectionEyebrow>
          <h2>{tr('Start with a real circuit.', 'Начните с настоящей схемы.')}</h2>
          <p>
            {tr(
              'Download the verified 3.0.0 source release, launch it on Ubuntu and open the half-adder example.',
              'Скачайте проверенный исходный релиз 3.0.0, запустите его на Ubuntu и откройте полусумматор.',
            )}
          </p>
        </div>
        <div className="cta-actions">
          <ButtonLink to="/download">
            {tr('Get LogicSpace', 'Получить LogicSpace')}
            <ArrowDownToLine size={18} />
          </ButtonLink>
          <External href={REPO} className="quiet-link">
            GitHub <ArrowUpRight size={16} />
          </External>
        </div>
      </section>
    </>
  )
}

function FeatureRow({
  feature,
  language,
  index,
}: {
  feature: Feature
  language: Language
  index: number
}) {
  const Icon = icons[feature.id]
  const tr = (en: string, ru: string) => t(en, ru)[language]
  return (
    <article className="feature-row" id={feature.id}>
      <span className="feature-number">{String(index + 1).padStart(2, '0')}</span>
      <span className="feature-symbol">
        <Icon size={23} strokeWidth={1.7} />
      </span>
      <div>
        <h3>{feature.title[language]}</h3>
        <p>{feature.summary[language]}</p>
        <p className="feature-detail">{feature.detail[language]}</p>
      </div>
      <Link
        to={`/docs/${feature.doc}`}
        aria-label={`${tr('Read about', 'Читать о')} ${feature.title[language]}`}
      >
        <ArrowUpRight size={20} />
      </Link>
    </article>
  )
}

function Features({ language }: { language: Language }) {
  const tr = (en: string, ru: string) => t(en, ru)[language]
  const groups = [
    { id: 'build', eyebrow: '01 / BUILD', title: tr('Design the circuit', 'Проектируйте схему') },
    {
      id: 'program',
      eyebrow: '02 / PROGRAM',
      title: tr('Program the machine', 'Программируйте систему'),
    },
    {
      id: 'inspect',
      eyebrow: '03 / INSPECT',
      title: tr('Understand every change', 'Разбирайте каждое изменение'),
    },
  ] as const
  return (
    <>
      <PageHeading
        eyebrow={tr('Capabilities / 3.0.0', 'Возможности / 3.0.0')}
        title={tr(
          'A complete digital logic workspace.',
          'Рабочее пространство для цифровой логики.',
        )}
        lead={tr(
          'From a single gate to a wired 8-bit processor, LogicSpace keeps construction, simulation and debugging in one editor.',
          'От одного вентиля до соединённого 8-битного процессора: LogicSpace объединяет сборку, симуляцию и отладку в одном редакторе.',
        )}
      />
      <div className="container features-page">
        <Screenshot
          src="/images/workspace.png"
          alt={tr(
            'Actual component library and half-adder in LogicSpace',
            'Настоящая библиотека и полусумматор LogicSpace',
          )}
          label={tr('Editor workspace', 'Рабочее пространство')}
        />
        {groups.map((group) => (
          <section key={group.id} className="feature-group">
            <SectionEyebrow>{group.eyebrow}</SectionEyebrow>
            <h2>{group.title}</h2>
            <div className="feature-list">
              {features
                .filter((item) => item.group === group.id)
                .map((item) => (
                  <FeatureRow
                    key={item.id}
                    feature={item}
                    language={language}
                    index={features.indexOf(item)}
                  />
                ))}
            </div>
          </section>
        ))}
        <div className="feature-callout">
          <div>
            <Code2 size={24} />
            <h3>{tr('HDL has a real boundary.', 'У HDL есть точные границы.')}</h3>
            <p>
              {tr(
                'The Verilog/SystemVerilog editor accepts a documented subset. Import produces editable components, while unsupported constructs are diagnosed. FPGA export prepares an iCE40 PCF package; it is not board programming.',
                'Редактор Verilog/SystemVerilog поддерживает документированное подмножество. Импорт создаёт редактируемые элементы, а неподдерживаемые конструкции диагностируются. FPGA-экспорт готовит iCE40 PCF-пакет, но не программирует плату.',
              )}
            </p>
          </div>
          <Link to="/docs/hdl">
            {tr('Read exact support', 'Читать о поддержке')}
            <ArrowRight size={17} />
          </Link>
        </div>
        <Screenshot
          src="/images/hdl-editor.png"
          alt={tr('Actual HDL panel in LogicSpace', 'Настоящая HDL-панель LogicSpace')}
          label={tr('HDL workspace', 'HDL-пространство')}
        />
      </div>
    </>
  )
}

function CodeBlock({ code, language }: { code: string; language: Language }) {
  const [copied, setCopied] = useState(false)
  const tr = (en: string, ru: string) => t(en, ru)[language]
  async function copy() {
    try {
      await navigator.clipboard.writeText(code)
      setCopied(true)
      window.setTimeout(() => setCopied(false), 1800)
    } catch {
      setCopied(false)
    }
  }
  return (
    <div className="code-block">
      <div className="code-label">
        <Terminal size={15} /> terminal{' '}
        <button
          type="button"
          onClick={copy}
          aria-label={tr('Copy commands', 'Скопировать команды')}
        >
          {copied ? <Check size={15} /> : <Copy size={15} />}{' '}
          {copied ? tr('Copied', 'Скопировано') : tr('Copy', 'Копировать')}
        </button>
      </div>
      <pre>
        <code>{code}</code>
      </pre>
    </div>
  )
}

function Download({ language }: { language: Language }) {
  const tr = (en: string, ru: string) => t(en, ru)[language]
  return (
    <>
      <PageHeading
        eyebrow={tr('Release / 3.0.0', 'Релиз / 3.0.0')}
        title={tr('Download LogicSpace.', 'Скачать LogicSpace.')}
        lead={tr(
          'The official 3.0.0 release is a verified source ZIP for Ubuntu/Linux. There is no prebuilt .deb or AppImage in this release.',
          'Официальный релиз 3.0.0 — проверенный исходный ZIP для Ubuntu/Linux. Готового .deb или AppImage в этом выпуске нет.',
        )}
      />
      <div className="container download-layout">
        <div>
          <div className="download-panel">
            <div className="download-head">
              <div className="download-icon">
                <ArrowDownToLine size={27} />
              </div>
              <div>
                <span className="muted-kicker">
                  {tr('LATEST PUBLISHED RELEASE', 'ПОСЛЕДНИЙ ОПУБЛИКОВАННЫЙ РЕЛИЗ')}
                </span>
                <h2>LogicSpace 3.0.0</h2>
              </div>
            </div>
            <p>
              {tr(
                'Source archive · 710,124 bytes · published 7 November 2026',
                'Исходный архив · 710 124 байт · опубликован 7 ноября 2026',
              )}
            </p>
            <div className="download-actions">
              <ButtonLink to={SOURCE_ZIP} external>
                {tr('Download source ZIP', 'Скачать исходный ZIP')}
                <ArrowDownToLine size={18} />
              </ButtonLink>
              <ButtonLink to={RELEASE} variant="secondary" external>
                {tr('View official release', 'Официальный релиз')}
                <ArrowUpRight size={17} />
              </ButtonLink>
            </div>
            <div className="checksum">
              <span>SHA-256</span>
              <code>{SHA256}</code>
              <External href={CHECKSUM_FILE}>
                {tr('Official checksum file', 'Официальный файл суммы')} <ExternalLink size={14} />
              </External>
            </div>
          </div>
          <section className="download-steps">
            <SectionEyebrow index="01">
              {tr('Install in minutes', 'Установите за несколько минут')}
            </SectionEyebrow>
            <h2>{tr('Extract. Install. Launch.', 'Распакуйте. Установите. Запустите.')}</h2>
            <p>
              {tr(
                'Extract the archive into a directory you own, open a terminal there and run:',
                'Распакуйте архив в свой каталог, откройте там терминал и выполните:',
              )}
            </p>
            <CodeBlock
              language={language}
              code={'cd LogicSpace-3.0.0\n./install.sh\n./launch.sh'}
            />
            <p className="small-note">
              {tr(
                'The installer creates a user desktop entry and downloads PySide6 Essentials into .deps if needed. It does not require sudo.',
                'Установщик создаёт пользовательский ярлык и при необходимости загружает PySide6 Essentials в .deps. Для него не нужен sudo.',
              )}
            </p>
            <Link className="inline-link" to="/install">
              {tr('Read the full installation guide', 'Полная инструкция по установке')}
              <ArrowRight size={17} />
            </Link>
          </section>
        </div>
        <aside className="requirement-panel">
          <SectionEyebrow>{tr('Requirements', 'Требования')}</SectionEyebrow>
          <h3>{tr('Built for Ubuntu.', 'Создано для Ubuntu.')}</h3>
          <div className="requirement-row">
            <strong>{tr('Platform', 'Платформа')}</strong>
            <span>Ubuntu 24.04+ / Linux GUI</span>
          </div>
          <div className="requirement-row">
            <strong>Python</strong>
            <span>3.12+</span>
          </div>
          <div className="requirement-row">
            <strong>PySide6</strong>
            <span>Essentials &gt;=6.7,&lt;7</span>
          </div>
          <div className="requirement-row">
            <strong>{tr('Qt graphics', 'Графика Qt')}</strong>
            <span>
              {tr(
                'libegl1 may be needed on minimal Ubuntu installs',
                'В минимальной Ubuntu может потребоваться libegl1',
              )}
            </span>
          </div>
          <p>
            {tr(
              'Icarus, Yosys, Verilator, GTKWave and Bubblewrap are optional external tools. Windows and macOS packages are not offered.',
              'Icarus, Yosys, Verilator, GTKWave и Bubblewrap — необязательные внешние инструменты. Пакетов Windows и macOS нет.',
            )}
          </p>
          <External href={SOURCE_ARCHIVE} className="quiet-link">
            {tr('Browse tagged source', 'Смотреть исходники тега')} <ArrowUpRight size={15} />
          </External>
        </aside>
      </div>
    </>
  )
}

function Installation({ language }: { language: Language }) {
  const tr = (en: string, ru: string) => t(en, ru)[language]
  const steps = [
    {
      n: '01',
      title: tr('Check your environment', 'Проверьте систему'),
      text: tr(
        'Use Ubuntu 24.04+ with a graphical session and Python 3.12 or newer.',
        'Нужна Ubuntu 24.04+ с графической сессией и Python 3.12 или новее.',
      ),
      code: 'python3 --version',
    },
    {
      n: '02',
      title: tr('Get the official source', 'Скачайте официальные исходники'),
      text: tr(
        'Download the v3.0.0 source ZIP from GitHub Releases and extract it to a directory you own.',
        'Скачайте исходный ZIP версии v3.0.0 с GitHub Releases и распакуйте в свой каталог.',
      ),
      code: 'cd LogicSpace-3.0.0',
    },
    {
      n: '03',
      title: tr('Install the desktop entry', 'Установите ярлык приложения'),
      text: tr(
        'Run the included installer. It installs PySide6 Essentials locally only when needed, then creates a desktop entry under your user account.',
        'Запустите входящий в архив установщик. Он при необходимости локально поставит PySide6 Essentials и создаст пользовательский ярлык.',
      ),
      code: './install.sh',
    },
    {
      n: '04',
      title: tr('Launch LogicSpace', 'Запустите LogicSpace'),
      text: tr(
        'Open it from the applications menu or run the launch script. On first launch, try the half-adder example.',
        'Откройте приложение через меню или скрипт запуска. При первом запуске попробуйте пример полусумматора.',
      ),
      code: './launch.sh',
    },
  ]
  return (
    <>
      <PageHeading
        eyebrow={tr('Guide / Ubuntu', 'Руководство / Ubuntu')}
        title={tr('Install LogicSpace on Ubuntu.', 'Установка LogicSpace на Ubuntu.')}
        lead={tr(
          'The published release is a source archive. These are the same commands and requirements used by its install and launch scripts.',
          'Опубликованный релиз — архив исходников. Здесь приведены команды и требования из его скриптов установки и запуска.',
        )}
      />
      <div className="container install-layout">
        <div className="install-steps">
          {steps.map((step) => (
            <section className="install-step" key={step.n}>
              <div className="step-index">{step.n}</div>
              <div>
                <h2>{step.title}</h2>
                <p>{step.text}</p>
                <CodeBlock language={language} code={step.code} />
              </div>
            </section>
          ))}
        </div>
        <aside className="install-aside">
          <h3>{tr('If launch fails', 'Если запуск не удался')}</h3>
          <p>
            {tr(
              'A missing PySide6 module usually means the installer was not run in this copy of the project. Minimal systems may also lack the Qt EGL runtime.',
              'Если PySide6 не найден, возможно, установщик не запускался для этой копии проекта. В минимальной системе также может отсутствовать Qt EGL.',
            )}
          </p>
          <CodeBlock language={language} code={'sudo apt install libegl1'} />
          <p className="small-note">
            {tr(
              'This command changes system packages and may ask for your password. Use it only if the reported error points to the missing EGL runtime.',
              'Эта команда меняет системные пакеты и может запросить пароль. Используйте её только при ошибке отсутствующего EGL runtime.',
            )}
          </p>
          <Link to="/docs/troubleshooting" className="inline-link">
            {tr('Troubleshooting', 'Решение проблем')} <ArrowRight size={16} />
          </Link>
        </aside>
      </div>
    </>
  )
}

function DocsIndex({ language }: { language: Language }) {
  const [query, setQuery] = useState('')
  const tr = (en: string, ru: string) => t(en, ru)[language]
  const filtered = useMemo(() => searchDocs(query, language), [query, language])
  return (
    <>
      <PageHeading
        eyebrow={tr('Documentation / 3.0.0', 'Документация / 3.0.0')}
        title={tr('Learn LogicSpace.', 'Изучите LogicSpace.')}
        lead={tr(
          'Start with a first circuit, then go deeper into buses, CPU, HDL and debugging. These guides follow the published 3.0.0 features.',
          'Начните с первой схемы, затем изучите шины, CPU, HDL и отладку. Руководства соответствуют опубликованным возможностям 3.0.0.',
        )}
      />
      <div className="container docs-index">
        <label className="docs-search">
          <Search size={20} />
          <span className="sr-only">{tr('Search documentation', 'Поиск по документации')}</span>
          <input
            type="search"
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            placeholder={tr('Search documentation…', 'Поиск по документации…')}
            autoComplete="off"
          />
          <span className="search-count">
            {filtered.length} / {docs.length}
          </span>
        </label>
        <div className="docs-list">
          {filtered.map((doc, index) => (
            <Link className="doc-list-item" key={doc.slug} to={`/docs/${doc.slug}`}>
              <span className="doc-index">{String(index + 1).padStart(2, '0')}</span>
              <div>
                <h2>{doc.title[language]}</h2>
                <p>{doc.intro[language]}</p>
              </div>
              <ArrowUpRight size={20} />
            </Link>
          ))}
          {filtered.length === 0 && (
            <div className="empty-state">
              <Search size={28} />
              <h2>{tr('No matching guides', 'Ничего не найдено')}</h2>
              <p>
                {tr(
                  'Try “CPU”, “bus”, “HDL” or a different term.',
                  'Попробуйте «CPU», «шина», «HDL» или другое слово.',
                )}
              </p>
              <button
                type="button"
                className="button button-secondary"
                onClick={() => setQuery('')}
              >
                {tr('Clear search', 'Сбросить поиск')}
              </button>
            </div>
          )}
        </div>
      </div>
    </>
  )
}

function DocsDetail({ language }: { language: Language }) {
  const { slug } = useParams()
  const doc = docs.find((entry) => entry.slug === slug)
  const tr = (en: string, ru: string) => t(en, ru)[language]
  if (!doc) return <NotFound language={language} />
  return (
    <div className="container docs-detail">
      <aside className="docs-sidebar">
        <Link to="/docs" className="sidebar-back">
          <ArrowLeft size={16} />
          {tr('All documentation', 'Вся документация')}
        </Link>
        <nav aria-label={tr('Documentation sections', 'Разделы документации')}>
          {docs.map((entry) => (
            <Link
              key={entry.slug}
              className={entry.slug === slug ? 'selected' : ''}
              to={`/docs/${entry.slug}`}
            >
              {entry.title[language]}
            </Link>
          ))}
        </nav>
      </aside>
      <article className="docs-article">
        <SectionEyebrow>{tr('Documentation / 3.0.0', 'Документация / 3.0.0')}</SectionEyebrow>
        <h1>{doc.title[language]}</h1>
        <p className="article-lead">{doc.intro[language]}</p>
        <div className="article-rule" />
        {doc.sections.map((section) => (
          <section key={section.heading.en}>
            <h2>{section.heading[language]}</h2>
            <p>{section.body[language]}</p>
            {section.code && <CodeBlock language={language} code={section.code} />}{' '}
            {section.link && (
              <External href={section.link.url} className="inline-link">
                {section.link.title[language]} <ArrowUpRight size={16} />
              </External>
            )}
          </section>
        ))}
        <div className="article-end">
          <BookOpen size={20} />
          <div>
            <strong>
              {tr('Need the full technical reference?', 'Нужно полное техническое руководство?')}
            </strong>
            <p>
              {tr(
                'The repository includes a detailed guide and actual example projects.',
                'В репозитории есть подробное руководство и настоящие примеры проектов.',
              )}
            </p>
          </div>
          <External href={GUIDE} className="inline-link">
            {tr('Open guide', 'Открыть')} <ArrowUpRight size={16} />
          </External>
        </div>
      </article>
    </div>
  )
}

function Releases({ language }: { language: Language }) {
  const tr = (en: string, ru: string) => t(en, ru)[language]
  return (
    <>
      <PageHeading
        eyebrow={tr('Release history', 'История релизов')}
        title={tr('Versions, with provenance.', 'Версии с понятным происхождением.')}
        lead={tr(
          'Only 3.0.0 is presented as a published source release here. Earlier numbers in the changelog describe development milestones, not additional downloadable releases.',
          'Здесь только 3.0.0 обозначена опубликованным исходным релизом. Более ранние номера в changelog — этапы разработки, а не отдельные релизы для загрузки.',
        )}
      />
      <div className="container release-page">
        <div className="release-card">
          <div className="release-card-head">
            <span className="release-badge">
              {tr('LATEST · OFFICIAL', 'ПОСЛЕДНИЙ · ОФИЦИАЛЬНЫЙ')}
            </span>
            <time dateTime="2026-11-07">7 {tr('November', 'ноября')} 2026</time>
          </div>
          <h2>LogicSpace 3.0.0</h2>
          <p>
            {tr(
              'First source release: editable circuits, central logic simulator, CPU/Assembly, a checked HDL subset and integrated debugging.',
              'Первый исходный релиз: редактируемые схемы, центральный симулятор, CPU/Assembly, проверенное подмножество HDL и встроенная отладка.',
            )}
          </p>
          <ul>
            <li>
              {tr(
                'Source ZIP with a published SHA-256 checksum',
                'Исходный ZIP с опубликованной SHA-256 суммой',
              )}
            </li>
            <li>
              {tr(
                'Ubuntu source installation through install.sh and launch.sh',
                'Установка исходников на Ubuntu через install.sh и launch.sh',
              )}
            </li>
            <li>
              {tr(
                'No prebuilt Linux package or in-place updater',
                'Без готового Linux-пакета и автоматической замены файлов',
              )}
            </li>
          </ul>
          <div className="release-card-actions">
            <ButtonLink to={RELEASE} external>
              {tr('View release notes', 'Открыть заметки релиза')}
              <ArrowUpRight size={16} />
            </ButtonLink>
            <External href={SOURCE_ZIP} className="inline-link">
              {tr('Source ZIP', 'Исходный ZIP')}
              <ArrowDownToLine size={16} />
            </External>
          </div>
        </div>
        <div className="history-note">
          <GitBranch size={22} />
          <div>
            <h3>{tr('Development history', 'История разработки')}</h3>
            <p>
              {tr(
                'The repository changelog records work on versions 2.1–2.5 and 3.0. Those entries are historical milestones; the official download above remains v3.0.0.',
                'Changelog репозитория описывает работы версий 2.1–2.5 и 3.0. Это этапы разработки; официальный файл загрузки выше — v3.0.0.',
              )}
            </p>
            <External href={CHANGELOG} className="inline-link">
              {tr('Read full changelog', 'Читать весь changelog')} <ArrowUpRight size={16} />
            </External>
          </div>
        </div>
      </div>
    </>
  )
}

function About({ language }: { language: Language }) {
  const tr = (en: string, ru: string) => t(en, ru)[language]
  return (
    <>
      <PageHeading
        eyebrow={tr('About the project', 'О проекте')}
        title={tr('A workspace for thinking in signals.', 'Пространство, где думают сигналами.')}
        lead={tr(
          'LogicSpace grows from a simple visual electronics sandbox into a native workspace for building and understanding digital systems.',
          'LogicSpace вырос из визуальной песочницы электроники в нативное пространство для сборки и понимания цифровых систем.',
        )}
      />
      <div className="container about-layout">
        <div className="about-story">
          <section>
            <SectionEyebrow>01 / {tr('Purpose', 'Цель')}</SectionEyebrow>
            <h2>{tr('Make the invisible visible.', 'Сделать невидимое видимым.')}</h2>
            <p>
              {tr(
                'A wire in LogicSpace carries a simulated value. A clock changes state. A register remembers. The editor is designed to make these relationships understandable while preserving a clean canvas.',
                'Провод в LogicSpace несёт симулируемое значение. Clock меняет состояние. Регистр запоминает. Редактор помогает понять эти связи, сохраняя чистый холст.',
              )}
            </p>
          </section>
          <section>
            <SectionEyebrow>02 / {tr('Technology', 'Технологии')}</SectionEyebrow>
            <h2>{tr('Built on one simulation engine.', 'Основа — единый движок.')}</h2>
            <p>
              {tr(
                'The native Ubuntu application uses Python 3.12+, PySide6 and Qt. Its GUI, JSON circuit model and central engine are separate; CPU, HDL imports, testbenches and debug tools operate on the same circuit model.',
                'Нативное приложение для Ubuntu использует Python 3.12+, PySide6 и Qt. GUI, JSON-модель схемы и центральный движок разделены; CPU, импорт HDL, тестбенчи и отладка работают с одной моделью схемы.',
              )}
            </p>
          </section>
          <section>
            <SectionEyebrow>03 / {tr('Release status', 'Состояние релиза')}</SectionEyebrow>
            <h2>{tr('Honest by design.', 'Честно о границах.')}</h2>
            <p>
              {tr(
                '3.0.0 is a source release. HDL support is a checked subset. FPGA export prepares files and constraints; it does not synthesize or program hardware. Logical simulation steps are not physical timing measurements.',
                '3.0.0 — исходный релиз. Поддержка HDL ограничена проверенным подмножеством. FPGA-экспорт готовит файлы и ограничения, но не синтезирует и не программирует плату. Логические шаги не являются измерениями физического времени.',
              )}
            </p>
          </section>
        </div>
        <aside className="about-aside">
          <img src="/logicspace.svg" alt="" width="62" height="62" />
          <h3>{tr('Licensing status', 'Статус лицензии')}</h3>
          <p>
            {tr(
              'The published v3.0.0 archive contains no project license. Later proprietary source-available and commercial-license drafts are not part of that release and are not final agreements. LogicSpace is not presented as OSI Open Source. Third-party packages retain their own licenses.',
              'Опубликованный архив v3.0.0 не содержит лицензии проекта. Более поздние черновики proprietary source-available и коммерческих условий не входят в релиз и не являются окончательными договорами. LogicSpace не называется OSI Open Source. Сторонние пакеты сохраняют свои лицензии.',
            )}
          </p>
          <p className="small-note">
            {tr(
              'For redistribution or commercial rights, obtain explicit permission from the verified rights holder. Current drafts need legal review.',
              'Для распространения или коммерческих прав нужно явное разрешение подтверждённого правообладателя. Черновики требуют юридической проверки.',
            )}
          </p>
          <External href={REPO} className="inline-link">
            {tr('Visit GitHub repository', 'Открыть GitHub')} <ArrowUpRight size={16} />
          </External>
        </aside>
      </div>
    </>
  )
}

function NotFound({ language }: { language: Language }) {
  const tr = (en: string, ru: string) => t(en, ru)[language]
  return (
    <div className="container not-found">
      <div className="not-found-code">
        404 <span>∅</span>
      </div>
      <SectionEyebrow>{tr('Signal not found', 'Сигнал не найден')}</SectionEyebrow>
      <h1>{tr('This path is disconnected.', 'Этот путь не подключён.')}</h1>
      <p>
        {tr(
          'The page may have moved, or the URL may have a typo. Return to the workspace overview or search the documentation.',
          'Страница могла переместиться или в адресе есть ошибка. Вернитесь на главную или найдите ответ в документации.',
        )}
      </p>
      <div className="hero-buttons">
        <ButtonLink to="/">
          {tr('Go home', 'На главную')}
          <ArrowRight size={16} />
        </ButtonLink>
        <ButtonLink to="/docs" variant="secondary">
          {tr('Browse docs', 'Документация')}
          <BookOpen size={16} />
        </ButtonLink>
      </div>
    </div>
  )
}

function updateMeta(pathname: string, language: Language) {
  const cleanPath = pathname.replace(/\/$/, '') || '/'
  const doc = cleanPath.startsWith('/docs/')
    ? docs.find((item) => `/docs/${item.slug}` === cleanPath)
    : undefined
  const title = doc
    ? doc.title[language]
    : ((
        {
          '/': t('Digital circuit simulator for Ubuntu', 'Симулятор цифровых схем для Ubuntu'),
          '/features': t('Features', 'Возможности'),
          '/download': t('Download', 'Скачать'),
          '/install': t('Installation guide', 'Установка'),
          '/docs': t('Documentation', 'Документация'),
          '/releases': t('Releases', 'Релизы'),
          '/about': t('About', 'О проекте'),
        } as Record<string, ReturnType<typeof t>>
      )[cleanPath]?.[language] ?? 'Page not found')
  const description =
    doc?.intro[language] ??
    t(
      'Build and simulate digital circuits on Ubuntu with LogicSpace 3.0.0. Explore the editor, CPU Assembly, HDL subset and debugging tools.',
      'Собирайте и симулируйте цифровые схемы на Ubuntu с LogicSpace 3.0.0. Изучите редактор, CPU Assembly, HDL и отладку.',
    )[language]
  document.title = `${title} · LogicSpace`
  document.documentElement.lang = language
  document.querySelector('meta[name="description"]')?.setAttribute('content', description)
  document
    .querySelector('meta[property="og:title"]')
    ?.setAttribute('content', `${title} · LogicSpace`)
  document.querySelector('meta[property="og:description"]')?.setAttribute('content', description)
  const canonical = document.querySelector('link[rel="canonical"]')
  const ogUrl = document.querySelector('meta[property="og:url"]')
  if (canonical) canonical.setAttribute('href', window.location.origin + cleanPath)
  if (ogUrl) ogUrl.setAttribute('content', window.location.origin + cleanPath)
}

export default function App() {
  const location = useLocation()
  const [language, setLanguage] = useState<Language>(() =>
    readPreference('logicspace-site-language', ['en', 'ru'] as const, 'en'),
  )
  const [theme, setTheme] = useState<Theme>(() =>
    readPreference('logicspace-site-theme', ['dark', 'light'] as const, 'dark'),
  )
  useEffect(() => {
    document.documentElement.dataset.theme = theme
    try {
      localStorage.setItem('logicspace-site-theme', theme)
    } catch {
      /* local preference is optional */
    }
  }, [theme])
  useEffect(() => {
    try {
      localStorage.setItem('logicspace-site-language', language)
    } catch {
      /* local preference is optional */
    }
  }, [language])
  useEffect(() => {
    updateMeta(location.pathname, language)
  }, [location.pathname, language])
  useEffect(() => {
    window.scrollTo({ top: 0, behavior: 'instant' })
  }, [location.pathname])
  return (
    <>
      <a className="skip-link" href="#main">
        {t('Skip to content', 'Перейти к содержимому')[language]}
      </a>
      <Header language={language} setLanguage={setLanguage} theme={theme} setTheme={setTheme} />
      <main id="main">
        <Routes>
          <Route path="/" element={<Home language={language} />} />
          <Route path="/features" element={<Features language={language} />} />
          <Route path="/download" element={<Download language={language} />} />
          <Route path="/install" element={<Installation language={language} />} />
          <Route path="/docs" element={<DocsIndex language={language} />} />
          <Route path="/docs/:slug" element={<DocsDetail language={language} />} />
          <Route path="/releases" element={<Releases language={language} />} />
          <Route path="/about" element={<About language={language} />} />
          <Route path="*" element={<NotFound language={language} />} />
        </Routes>
      </main>
      <Footer language={language} />
    </>
  )
}
