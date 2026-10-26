import type { NextFunction, Request, Response } from 'express'
import { Router } from 'express'

import { aiConfig } from '../config'
import { chatLimiter } from '../middleware/rateLimit.middleware'
import { AiValidationError, chatService } from '../services/ai.service'

const router = Router()

router.post(
  '/chat',
  chatLimiter,
  async (req: Request, res: Response, next: NextFunction): Promise<void> => {
    let messages
    try {
      messages = chatService.validateAiMessages(req.body)
    } catch (error) {
      if (error instanceof AiValidationError) {
        res.status(400).json({ detail: error.message })
        return
      }
      next(error)
      return
    }
    await chatService.streamChat(messages, req, res)
  },
)

router.get('/health/upstream', async (_req: Request, res: Response): Promise<void> => {
  try {
    const data = await chatService.healthUpstream()
    res.json(data)
  } catch {
    res.status(503).json({
      llm_base_url: aiConfig.baseURL,
      model: null,
      available: false,
      error: 'AI Gateway tidak dapat dihubungi.',
    })
  }
})

export default router
