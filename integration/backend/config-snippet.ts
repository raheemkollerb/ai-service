export const aiConfig = {
  baseURL: process.env.AI_SERVICE_URL || 'http://localhost:8100',
  serviceKey: process.env.SERVICE_KEY || '',
  timeout: 120000,
  maxHistoryMessages: 20,
  maxMessageChars: 8000,
}
