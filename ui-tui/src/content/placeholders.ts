import { pick } from '../lib/text.js'

export const PLACEHOLDERS = [
  '随便问我点什么…',
  '试试“解释这个代码库”',
  '试试“为这个功能写测试”',
  '试试“重构 auth 模块”',
  '试试输入 /help 查看命令',
  '试试“修复 lint 错误”',
  '试试“配置加载器是怎么工作的？”'
]

export const PLACEHOLDER = pick(PLACEHOLDERS)
