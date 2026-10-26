import { useEffect, useRef, useState } from 'react'

import { aiService, type AiStreamResult } from '../services/aiService'
import type { ChatMessage } from '../types/chat.types'

const WELCOME_MESSAGE: ChatMessage = {
  role: 'model',
  content:
    'Selamat datang! Saya adalah asisten AI internal RCC. Ajukan pertanyaan tentang data riset.',
}

export type ChatStatus = 'online' | 'offline' | 'unknown'

export function useChat() {
  const [messages, setMessages] = useState<ChatMessage[]>([WELCOME_MESSAGE])
  const [input, setInput] = useState('')
  const [isLoading, setIsLoading] = useState(false)
  const [status, setStatus] = useState<ChatStatus>('unknown')
  const scrollRef = useRef<HTMLDivElement | null>(null)

  useEffect(() => {
    let cancelled = false
    fetch('/api/ai/health/upstream', { credentials: 'include' })
      .then((res) => (res.ok ? res.json() : null))
      .then((body: { available?: boolean } | null) => {
        if (!cancelled) setStatus(body?.available ? 'online' : 'offline')
      })
      .catch(() => {
        if (!cancelled) setStatus('offline')
      })
    return () => {
      cancelled = true
    }
  }, [])

  const scrollToBottom = () => {
    requestAnimationFrame(() => {
      const node = scrollRef.current
      if (node) node.scrollTop = node.scrollHeight
    })
  }

  const handleSend = async () => {
    const text = input.trim()
    if (!text || isLoading) return
    setInput('')
    setIsLoading(true)

    const history: Array<{ role: 'user' | 'assistant'; content: string }> = messages
      .slice(1)
      .map((message) => ({
        role: message.role === 'model' ? 'assistant' : message.role,
        content: message.content,
      }))
    history.push({ role: 'user', content: text })

    const userMessage: ChatMessage = { role: 'user', content: text }
    const draft: ChatMessage = { role: 'model', content: '' }
    setMessages((current) => [...current, userMessage, draft])
    scrollToBottom()

    let receivedDelta = false

    const upsertDraft = (chunk: string) => {
      setMessages((current) => {
        const next = [...current]
        const last = next[next.length - 1]
        if (last?.role === 'model') {
          next[next.length - 1] = { ...last, content: last.content + chunk }
        } else {
          next.push({ role: 'model', content: chunk })
        }
        return next
      })
      scrollToBottom()
    }

    try {
      const handlers = {
        onDelta: (delta: string) => {
          receivedDelta = true
          upsertDraft(delta)
        },
        onDone: () => undefined,
        onError: (message: string) => {
          setStatus('offline')
          setMessages((current) => {
            const next = [...current]
            const last = next[next.length - 1]
            if (last?.role === 'model' && !last.content) {
              next[next.length - 1] = { ...last, content: message }
            }
            return next
          })
        },
      }
      const result: AiStreamResult = await aiService.streamChat(history, handlers)
      if (!receivedDelta && !result.finishReason) {
        setStatus('offline')
        setMessages((current) => {
          const next = [...current]
          const last = next[next.length - 1]
          if (last?.role === 'model' && !last.content) {
            next[next.length - 1] = {
              ...last,
              content:
                'Asisten AI belum terhubung ke LLM lokal. Periksa status workstation dan coba lagi.',
            }
          }
          return next
        })
      }
      setStatus('online')
    } catch (error) {
      const message = error instanceof Error ? error.message : 'Terjadi kesalahan tak terduga.'
      if (message.includes('sesi berakhir')) {
        window.location.reload()
        return
      }
      setStatus('offline')
      setMessages((current) => {
        const next = [...current]
        const last = next[next.length - 1]
        if (last?.role === 'model' && !last.content) {
          next[next.length - 1] = { ...last, content: message }
        }
        return next
      })
    } finally {
      setIsLoading(false)
    }
  }

  return { messages, input, setInput, isLoading, status, scrollRef, handleSend }
}
