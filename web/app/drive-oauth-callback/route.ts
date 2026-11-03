import { createHash } from 'node:crypto'

// No React layout, analytics, images or external scripts may run with the code URL.
// The callback is not a credential endpoint: completion still requires the user's
// authenticated API context AND the initiating tab's nonce and server PKCE state.
import { driveOAuthCallbackScript as callbackScript } from '@/shared/storage/drive-oauth-callback'

export function GET() {
  const hash = createHash('sha256').update(callbackScript).digest('base64')
  return new Response(`<!doctype html><html><head><meta charset="utf-8"><meta name="referrer" content="no-referrer"><title>Drive authorization</title></head><body><p>Returning to Learning OS…</p><script>${callbackScript}</script></body></html>`, {
    headers: {
      'Content-Type': 'text/html; charset=utf-8', 'Cache-Control': 'no-store',
      'Referrer-Policy': 'no-referrer', 'X-Frame-Options': 'DENY',
      'Content-Security-Policy': `default-src 'none'; script-src 'sha256-${hash}'; base-uri 'none'; frame-ancestors 'none'`,
    },
  })
}
