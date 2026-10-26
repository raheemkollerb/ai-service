import axios from 'axios'
import type { Request, Response } from 'express'

import { aiConfig } from '../config'

export interface AiMessage {
  role: 'user' | 'assistant'
  content: string
}

export class AiValidationError extends Error {}

const MAX_HISTORY_MESSAGES = 20
const MAX_MESSAGE_CHARS = 8000

function cleanMessages(raw: unknown): AiMessage[] {
  const source = Array.isArray(raw) ? raw : (raw as { messages?: unknown[] } | null)?.messages
  if (!Array.isArray(source)) {
    throw new AiValidationError('Kolom "messages" harus berupa array.')
  }
  const cleaned: AiMessage[] = []
  for (const item of source) {
    const role = (item as { role?: string } | null)?.role
    if (role !== 'user' && role !== 'assistant') continue
    const content = (item as { content?: unknown } | null)?.content
    if (typeof content !== 'string') continue
    const stripped = content.trim()
    if (!stripped) continue
    if (stripped.length > MAX_MESSAGE_CHARS) {
      throw new AiValidationError(`Pesan terlalu panjang (maksimum ${MAX_MESSAGE_CHARS} karakter).`)
    }
    cleaned.push({ role, content: stripped })
  }
  if (!cleaned.length) {
    throw new AiValidationError('Tidak ada pesan yang valid untuk dikirim ke model.')
  }
  if (cleaned.length > MAX_HISTORY_MESSAGES) {
    throw new AiValidationError(`Riwayat percakapan terlalu panjang (maksimum ${MAX_HISTORY_MESSAGES} pesan).`)
  }
  return cleaned
}

export const chatService = {
  validateAiMessages: cleanMessages,

  async streamChat(messages: AiMessage[], req: Request, res: Response): Promise<void> {
    req.headers['x-no-compression'] = 'true'
    res.status(200)
    res.setHeader('Content-Type', 'text/event-stream; charset=utf-8')
    res.setHeader('Cache-Control', 'no-cache, no-transform')
    res.setHeader('Connection', 'keep-alive')
    res.setHeader('X-Accel-Buffering', 'no')
    res.flushHeaders()

    let upstreamStream: NodeJS.ReadableStream | null = null
    try {
      const upstream = await axios.post(`${aiConfig.baseURL}/ai/chat`, { messages }, {
        responseType: 'stream',
        headers: {
          'X-Service-Key': aiConfig.serviceKey,
          'Content-Type': 'application/json',
        },
        timeout: aiConfig.timeout,
      })
      upstreamStream = upstream.data
      upstreamStream.pipe(res)
      upstreamStream.on('error', () => {
        res.destroy()
      })
      res.on('close', () => {
        upstreamStream?.destroy()
      })
      await new Promise<void>((resolve) => {
        res.on('close', resolve)
        res.on('finish', resolve)
      })
    } catch {
      if (upstreamStream) {
        upstreamStream.destroy()
      }
      if (!res.headersSent) {
        res.status(503).json({ error: 'Layanan AI sedang tidak tersedia.' })
      } else {
        res.destroy()
      }
    }
  },

  async healthUpstream(): Promise<Record<string, unknown>> {
    const response = await axios.get(`${aiConfig.baseURL}/ai/health/upstream`, {
      headers: { 'X-Service-Key': aiConfig.serviceKey },
      timeout: 10000,
    })
    return response.data as Record<string, unknown>
  },
}
