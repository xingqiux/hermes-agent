import type { PanelSection } from '../types.js'

export const SETUP_REQUIRED_TITLE = '需要先完成设置'

export const buildSetupRequiredSections = (): PanelSection[] => [
  {
    text: 'Hermes 需要先配置模型提供商，TUI 才能开始会话。'
  },
  {
    rows: [
      ['/model', '在当前界面配置提供商和模型'],
      ['/setup', '在当前界面运行首次设置向导'],
      ['Ctrl+C', '退出后手动运行 `hermes setup`']
    ],
    title: '可执行操作'
  }
]
