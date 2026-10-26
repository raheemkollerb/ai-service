import aiRoutes from './routes/ai.routes'

app.use('/api', preserveSessionCookie, requireSsoSession)

app.use('/api/ai', aiRoutes)
