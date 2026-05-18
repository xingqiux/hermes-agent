import { Box, Text, useInput, useStdout } from '@hermes/ink'
import { useEffect, useState } from 'react'

import type { GatewayClient } from '../gatewayClient.js'
import type { SessionDeleteResponse, SessionListItem, SessionListResponse } from '../gatewayTypes.js'
import { asRpcResult, rpcErrorMessage } from '../lib/rpc.js'
import type { Theme } from '../theme.js'

import { OverlayHint, useOverlayKeys, windowOffset } from './overlayControls.js'

const VISIBLE = 15
const MIN_WIDTH = 60
const MAX_WIDTH = 120

const age = (ts: number) => {
  const d = (Date.now() / 1000 - ts) / 86400

  if (d < 1) {
    return '今天'
  }

  if (d < 2) {
    return '昨天'
  }

  return `${Math.floor(d)} 天前`
}

export function SessionPicker({ gw, onCancel, onSelect, t }: SessionPickerProps) {
  const [items, setItems] = useState<SessionListItem[]>([])
  const [err, setErr] = useState('')
  const [sel, setSel] = useState(0)
  const [loading, setLoading] = useState(true)
  // When non-null, the user pressed `d` on this index and we're waiting for
  // a second `d`/`D` to confirm deletion.  Any other key cancels the prompt.
  const [confirmDelete, setConfirmDelete] = useState<null | number>(null)
  const [deleting, setDeleting] = useState(false)

  const { stdout } = useStdout()
  const width = Math.max(MIN_WIDTH, Math.min(MAX_WIDTH, (stdout?.columns ?? 80) - 6))

  useOverlayKeys({ onClose: onCancel })

  useEffect(() => {
    gw.request<SessionListResponse>('session.list', { limit: 200 })
      .then(raw => {
        const r = asRpcResult<SessionListResponse>(raw)

        if (!r) {
          setErr('无效响应：session.list')
          setLoading(false)

          return
        }

        setItems(r.sessions ?? [])
        setErr('')
        setLoading(false)
      })
      .catch((e: unknown) => {
        setErr(rpcErrorMessage(e))
        setLoading(false)
      })
  }, [gw])

  const performDelete = (index: number) => {
    const target = items[index]

    if (!target || deleting) {
      return
    }

    setDeleting(true)
    gw.request<SessionDeleteResponse>('session.delete', { session_id: target.id })
      .then(raw => {
        const r = asRpcResult<SessionDeleteResponse>(raw)

        if (!r || r.deleted !== target.id) {
          setErr('无效响应：session.delete')
          setDeleting(false)

          return
        }

        setItems(prev => {
          const next = prev.filter((_, i) => i !== index)
          setSel(s => Math.max(0, Math.min(s, next.length - 1)))

          return next
        })
        setErr('')
        setDeleting(false)
      })
      .catch((e: unknown) => {
        setErr(rpcErrorMessage(e))
        setDeleting(false)
      })
  }

  useInput((ch, key) => {
    if (deleting) {
      return
    }

    if (confirmDelete !== null) {
      if (ch?.toLowerCase() === 'd') {
        const idx = confirmDelete
        setConfirmDelete(null)
        performDelete(idx)
      } else {
        setConfirmDelete(null)
      }

      return
    }

    if (key.upArrow && sel > 0) {
      setSel(s => s - 1)
    }

    if (key.downArrow && sel < items.length - 1) {
      setSel(s => s + 1)
    }

    if (key.return && items[sel]) {
      onSelect(items[sel]!.id)

      return
    }

    if (ch?.toLowerCase() === 'd' && items[sel]) {
      setConfirmDelete(sel)

      return
    }

    const n = parseInt(ch)

    if (n >= 1 && n <= Math.min(9, items.length)) {
      onSelect(items[n - 1]!.id)
    }
  })

  if (loading) {
    return <Text color={t.color.muted}>正在加载会话…</Text>
  }

  if (err && !items.length) {
    return (
      <Box flexDirection="column">
        <Text color={t.color.label}>错误：{err}</Text>
        <OverlayHint t={t}>Esc/q 取消</OverlayHint>
      </Box>
    )
  }

  if (!items.length) {
    return (
      <Box flexDirection="column">
        <Text color={t.color.muted}>没有历史会话</Text>
        <OverlayHint t={t}>Esc/q 取消</OverlayHint>
      </Box>
    )
  }

  const offset = windowOffset(items.length, sel, VISIBLE)

  return (
    <Box flexDirection="column" width={width}>
      <Text bold color={t.color.accent}>
        继续会话
      </Text>

      {offset > 0 && <Text color={t.color.muted}>  ↑ 还有 {offset} 个</Text>}

      {items.slice(offset, offset + VISIBLE).map((s, vi) => {
        const i = offset + vi
        const selected = sel === i
        const pendingDelete = confirmDelete === i

        return (
          <Box key={s.id}>
            <Text bold={selected} color={selected ? t.color.accent : t.color.muted} inverse={selected}>
              {selected ? '▸ ' : '  '}
            </Text>

            <Box width={30}>
              <Text bold={selected} color={selected ? t.color.accent : t.color.muted} inverse={selected}>
                {String(i + 1).padStart(2)}. [{s.id}]
              </Text>
            </Box>

            <Box width={30}>
              <Text bold={selected} color={selected ? t.color.accent : t.color.muted} inverse={selected}>
                ({s.message_count} 条消息, {age(s.started_at)}, {s.source || 'tui'})
              </Text>
            </Box>

            <Text
              bold={selected}
              color={pendingDelete ? t.color.label : selected ? t.color.accent : t.color.muted}
              inverse={selected}
              wrap="truncate-end"
            >
              {pendingDelete ? '再次按 d 删除' : s.title || s.preview || '(无标题)'}
            </Text>
          </Box>
        )
      })}

      {offset + VISIBLE < items.length && <Text color={t.color.muted}>  ↓ 还有 {items.length - offset - VISIBLE} 个</Text>}
      {err && <Text color={t.color.label}>错误：{err}</Text>}
      {deleting ? (
        <OverlayHint t={t}>正在删除…</OverlayHint>
      ) : (
        <OverlayHint t={t}>↑/↓ 选择 · Enter 继续 · 1-9 快速选择 · d 删除 · Esc/q 取消</OverlayHint>
      )}
    </Box>
  )
}

interface SessionPickerProps {
  gw: GatewayClient
  onCancel: () => void
  onSelect: (id: string) => void
  t: Theme
}
