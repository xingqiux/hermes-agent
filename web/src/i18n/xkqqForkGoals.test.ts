import { describe, expect, it } from 'vitest'
import { zhHant } from './zh-hant'
import { zh } from './zh'

const criticalPaths = [
  'chat.copyLastResponse',
  'chat.reconnectEventsFeed',
  'chat.switchModel',
  'models.page.auxiliaryTasks',
  'models.page.currentModel',
  'models.page.modelSettings',
  'models.page.switchModel',
  'oauth.disconnectConfirm',
  'oauth.openDocs'
] as const

function atPath(value: unknown, path: string): unknown {
  return path.split('.').reduce<unknown>((current, key) => {
    if (!current || typeof current !== 'object') return undefined
    return (current as Record<string, unknown>)[key]
  }, value)
}

describe('xkqq Chinese Dashboard goals', () => {
  it.each([
    ['zh', zh],
    ['zh-hant', zhHant]
  ])('translates critical model, chat, and OAuth controls in %s', (_locale, messages) => {
    for (const path of criticalPaths) {
      const message = atPath(messages, path)
      expect(message, path).toBeTypeOf('string')
      expect(message, path).toMatch(/[\u3400-\u9fff]/u)
    }
  })
})
