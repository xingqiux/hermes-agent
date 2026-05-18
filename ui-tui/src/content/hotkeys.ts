import { isMac, isRemoteShell } from '../lib/platform.js'

const action = isMac ? 'Cmd' : 'Ctrl'
const paste = isMac ? 'Cmd' : 'Alt'

const copyHotkeys: [string, string][] = isMac
  ? [
      ['Cmd+C', '复制选区'],
      ['Ctrl+C', '中断 / 清空草稿 / 退出']
    ]
  : isRemoteShell()
    ? [
        ['Cmd+C', '终端转发时复制选区'],
        ['Ctrl+C', '复制选区 / 中断 / 清空草稿 / 退出']
      ]
    : [['Ctrl+C', '复制选区 / 中断 / 清空草稿 / 退出']]

export const HOTKEYS: [string, string][] = [
  ...copyHotkeys,
  [action + '+D', '退出'],
  [action + '+G / Alt+G', '打开 $EDITOR（VSCode/Cursor 可用 Alt+G）'],
  [action + '+L', '重绘界面'],
  [paste + '+V / /paste', '粘贴文本；/paste 可附加剪贴板图片'],
  ['Tab', '应用补全'],
  ['↑/↓', '补全 / 编辑队列 / 历史记录'],
  ['Ctrl+X', '删除正在编辑的队列消息（Esc 取消编辑）'],
  [action + '+A/E', '跳到行首 / 行尾'],
  [action + '+Z / ' + action + '+Y', '撤销 / 重做输入编辑'],
  [action + '+W', '删除单词'],
  [action + '+U/K', '删除到行首 / 行尾'],
  [action + '+←/→', '按词跳转'],
  ['Home/End', '行首 / 行尾'],
  ['Shift+Enter / Alt+Enter', '插入换行'],
  ['\\+Enter', '多行续写（备用）'],
  ['!<cmd>', '运行 shell 命令（例如 !ls、!git status）'],
  ['{!<cmd>}', '在输入中插入 shell 输出（例如 "branch is {!git branch --show-current}"）']
]
