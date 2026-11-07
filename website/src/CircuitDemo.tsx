import { useState } from 'react'
import { t, type Language } from './content'

export function halfAdder(a: 0 | 1, b: 0 | 1) {
  return { sum: (a ^ b) as 0 | 1, carry: (a & b) as 0 | 1 }
}

export default function CircuitDemo({ language }: { language: Language }) {
  const [a, setA] = useState<0 | 1>(0)
  const [b, setB] = useState<0 | 1>(1)
  const { sum, carry } = halfAdder(a, b)
  const label = (en: string, ru: string) => t(en, ru)[language]

  return (
    <div
      className="demo"
      aria-label={label('Interactive half-adder example', 'Интерактивный пример полусумматора')}
    >
      <div className="demo-topline">
        <div className="demo-file">
          <span className="demo-file-dot" /> half_adder.logicspace{' '}
          <span className="demo-caption">{label('browser illustration', 'пример в браузере')}</span>
        </div>
        <div className="demo-top-status">
          <span className="status-pulse" /> {label('LIVE LOGIC', 'ЛОГИКА В ДЕЙСТВИИ')}
        </div>
      </div>
      <div className="demo-stage">
        <div className="demo-switches">
          {(
            [
              ['A', a, setA],
              ['B', b, setB],
            ] as const
          ).map(([name, value, setter]) => (
            <button
              key={name}
              className={`demo-switch ${value ? 'is-on' : ''}`}
              type="button"
              aria-label={`${label('Toggle input', 'Переключить вход')} ${name}`}
              aria-pressed={Boolean(value)}
              onClick={() => setter(value ? 0 : 1)}
            >
              <span className="switch-name">INPUT {name}</span>
              <span className="switch-track">
                <span className="switch-thumb" />
              </span>
              <strong>{value}</strong>
            </button>
          ))}
        </div>
        <div className="demo-schematic" aria-hidden="true">
          <svg viewBox="0 0 660 300" role="presentation" preserveAspectRatio="xMidYMid meet">
            <defs>
              <linearGradient id="gateFill" x1="0" x2="1" y1="0" y2="1">
                <stop stopColor="#223b55" />
                <stop offset="1" stopColor="#172538" />
              </linearGradient>
            </defs>
            <text x="6" y="76" className="port-label">
              A
            </text>
            <text x="6" y="237" className="port-label">
              B
            </text>
            <path
              d="M30 69H116V103H226 M116 69V188H226"
              fill="none"
              stroke={a ? '#6de2b0' : '#72869e'}
              strokeWidth="4"
            />
            <path
              d="M30 230H138V136H226 M138 230V220H226"
              fill="none"
              stroke={b ? '#6de2b0' : '#72869e'}
              strokeWidth="4"
            />
            <circle cx="30" cy="69" r="6" fill={a ? '#6de2b0' : '#8ba0b8'} />
            <circle cx="30" cy="230" r="6" fill={b ? '#6de2b0' : '#8ba0b8'} />
            <circle cx="116" cy="69" r="7" fill={a ? '#6de2b0' : '#8ba0b8'} />
            <circle cx="138" cy="230" r="7" fill={b ? '#6de2b0' : '#8ba0b8'} />
            <path
              d="M226 79 C260 86 306 79 322 79 C359 79 392 106 414 120 C388 150 356 162 322 162 C299 162 264 157 226 162 C246 138 248 106 226 79Z"
              fill="url(#gateFill)"
              stroke="#82b7ea"
              strokeWidth="3"
            />
            <path
              d="M214 79 C236 107 235 138 214 162"
              fill="none"
              stroke="#82b7ea"
              strokeWidth="3"
            />
            <text x="310" y="127" textAnchor="middle">
              XOR
            </text>
            <path
              d="M226 181 H319 C354 181 379 206 379 220 C379 242 355 264 319 264 H226Z"
              fill="url(#gateFill)"
              stroke="#82b7ea"
              strokeWidth="3"
            />
            <text x="303" y="228" textAnchor="middle">
              AND
            </text>
            <path
              d="M414 120 H605"
              stroke={sum ? '#6de2b0' : '#72869e'}
              strokeWidth="4"
              fill="none"
            />
            <circle cx="414" cy="120" r="6" fill={sum ? '#6de2b0' : '#91a2b4'} />
            <circle cx="379" cy="220" r="6" fill={carry ? '#6de2b0' : '#91a2b4'} />
            <path d="M379 220H605" stroke={carry ? '#6de2b0' : '#72869e'} strokeWidth="4" />
            <circle cx="605" cy="120" r="6" fill={sum ? '#6de2b0' : '#91a2b4'} />
            <circle cx="605" cy="220" r="6" fill={carry ? '#6de2b0' : '#91a2b4'} />
            <text x="616" y="126" className="port-label">
              S
            </text>
            <text x="616" y="226" className="port-label">
              C
            </text>
          </svg>
        </div>
        <div className="demo-outputs" aria-live="polite">
          <div className="demo-output">
            <span className={`demo-led ${sum ? 'lit' : ''}`} />
            <span>SUM</span>
            <strong>{sum}</strong>
          </div>
          <div className="demo-output">
            <span className={`demo-led ${carry ? 'lit' : ''}`} />
            <span>CARRY</span>
            <strong>{carry}</strong>
          </div>
        </div>
      </div>
      <div className="demo-bottom">
        <span>{label('Try all four input states', 'Попробуйте все четыре комбинации')}</span>
        <code>SUM = A ⊕ B · CARRY = A ∧ B</code>
      </div>
    </div>
  )
}
