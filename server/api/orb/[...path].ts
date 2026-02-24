/**
 * Server-side proxy for the standard orb API.
 * Forwards /api/orb/<path> → NUXT_PUBLIC_ORB_API_BASE/api/v1/<path>
 */
import { proxyRequest } from 'h3'

export default defineEventHandler(async (event) => {
  const config = useRuntimeConfig()
  const orbBase = config.public.orbApiBase as string
  const path = getRouterParam(event, 'path') ?? ''
  const targetUrl = `${orbBase}/api/v1/${path}`
  return proxyRequest(event, targetUrl)
})
