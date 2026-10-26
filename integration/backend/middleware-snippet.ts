import rateLimit from 'express-rate-limit'

export const chatLimiter = rateLimit({
  windowMs: 60 * 1000,
  limit: 30,
  standardHeaders: 'draft-7',
  legacyHeaders: false,
  message: { detail: 'Terlalu banyak permintaan chat. Coba lagi nanti.' },
})
