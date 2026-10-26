export interface AiStreamResult {
  text: string
  finishReason: string | null
}

export interface StreamHandlers {
  onDelta?: (text: string) => void
  onDone?: (finishReason: string | null) => void
  onError?: (message: string) => void
}

interface GatewayEvent {
  type?: string
  text?: string
  message?: string
  finish_reason?: string | null
  [key: string]: unknown
}

function extractContent(payload: string): GatewayEvent | null {
  const line = payload
    .split('\n')
    .map((part) => part.trim())
    .find((part) => part.startsWith('data:'))
  if (!line) return null
  const body = line.slice(5).trim()
  if (!body || body === '[DONE]') return null
  try {
    return JSON.parse(body) as GatewayEvent
  } catch {
    return null
  }
}

export async function streamChat(
  messages: Array<{ role: 'user' | 'assistant'; content: string }>,
  handlers: StreamHandlers,
  signal?: AbortSignal,
): Promise<AiStreamResult> {
  let response: Response
  try {
    response = await fetch('/api/ai/chat', {
      method: 'POST',
      credentials: 'include',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ messages }),
      signal,
    })
  } catch {
    throw new Error('Tidak dapat menghubungi layanan AI platform.')
  }

  if (response.status === 401) {
    throw new Error('Sesi berakhir, silakan login kembali.')
  }
  if (!response.ok) {
    let detail = `Permintaan gagal (HTTP ${response.status}).`
    try {
      const body = (await response.json()) as { detail?: string }
      if (body?.detail) detail = body.detail
    } catch (error) {
      void error
    }
    throw new Error(detail)
  }

  const reader = response.body?.getReader()
  if (!reader) {
    throw new Error('Streaming tidak didukung oleh jaringan ini.')
  }

  const decoder = new TextDecoder('utf-8')
  let buffer = ''
  let fullText = ''
  let finishReason: string | null = null

  const handleFrames = (block: string): void => {
    const event = extractContent(block)
    if (!event) return
    if (event.type === 'delta' && typeof event.text === 'string' && event.text) {
      fullText += event.text
      handlers.onDelta?.(event.text)
      return
    }
    if (event.type === 'done') {
      finishReason = event.finish_reason ?? 'stop'
      handlers.onDone?.(finishReason)
      void reader.cancel().catch(() => undefined)
      return
    }
    if (event.type === 'error') {
      throw new Error(typeof event.message === 'string' ? event.message : 'Upstream AI error.')
    }
  }

  try {
    while (finishReason === null) {
      const { done, value } = await reader.read()
      if (done) break
      buffer += decoder.decode(value, { stream: true })
      let separator = buffer.indexOf('\n\n')
      while (separator !== -1) {
        handleFrames(buffer.slice(0, separator))
        buffer = buffer.slice(separator + 2)
        if (finishReason !== null) break
        separator = buffer.indexOf('\n\n')
      }
    }
  } finally {
    if (finishReason === null) {
      void reader.cancel().catch(() => undefined)
    }
  }

  return { text: fullText, finishReason }
}

export const aiService = { streamChat }
