import { describe, expect, it } from 'vitest'
import { docs, features, searchDocs, SHA256, SOURCE_ZIP, t } from './content'
import { halfAdder } from './CircuitDemo'

describe('interactive circuit illustration', () => {
  it.each([
    [0, 0, 0, 0],
    [0, 1, 1, 0],
    [1, 0, 1, 0],
    [1, 1, 0, 1],
  ] as const)('half adder %i + %i yields SUM %i and CARRY %i', (a, b, sum, carry) => {
    expect(halfAdder(a, b)).toEqual({ sum, carry })
  })
})

describe('published content', () => {
  it('has unique documentation routes and valid feature destinations', () => {
    const slugs = docs.map((doc) => doc.slug)
    expect(new Set(slugs).size).toBe(slugs.length)
    expect(docs.length).toBeGreaterThanOrEqual(10)
    expect(slugs).toContain('linux-guide')
    expect(slugs).toContain('windows-guide')
    expect(slugs).toContain('known-limitations')
    for (const feature of features) expect(slugs).toContain(feature.doc)
  })

  it('searches each active language without hiding the full index', () => {
    expect(searchDocs('', 'en')).toHaveLength(docs.length)
    expect(searchDocs('flip-flop', 'en').length).toBeGreaterThan(0)
    expect(searchDocs('триггер', 'ru').length).toBeGreaterThan(0)
    expect(searchDocs('not-an-actual-topic', 'en')).toHaveLength(0)
  })

  it('points to the official source asset and its verified digest', () => {
    expect(SOURCE_ZIP).toBe(
      'https://github.com/Kuattt/LogicSpace-/releases/download/v3.1.0/LogicSpace-3.1.0-source.zip',
    )
    expect(SHA256).toMatch(/^[0-9a-f]{64}$/)
  })

  it('keeps English and Russian copy distinct', () => {
    expect(t('Download', 'Скачать')).toEqual({ en: 'Download', ru: 'Скачать' })
    for (const doc of docs) {
      expect(doc.title.en).toBeTruthy()
      expect(doc.title.ru).toBeTruthy()
    }
  })
})
