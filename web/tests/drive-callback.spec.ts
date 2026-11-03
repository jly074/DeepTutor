import { runInNewContext } from 'node:vm'
import { expect, it } from 'vitest'
import { GET } from '@/app/drive-oauth-callback/route'
it('uses a standalone no-store/referrer callback with a hash-only CSP', async () => {
  const response = GET()
  expect(response.headers.get('Cache-Control')).toBe('no-store')
  expect(response.headers.get('Referrer-Policy')).toBe('no-referrer')
  expect(response.headers.get('Content-Security-Policy')).toMatch(/default-src 'none'; script-src 'sha256-/)
  const html = await response.text()
  expect(html).not.toContain('src=')
  const script = html.match(/<script>([\s\S]+)<\/script>/)![1]
  const data = new Map([['drive.oauth.pending', JSON.stringify({ state: 'synthetic-state', workspace: 'a', expires: Date.now()+60000 })]])
  const actions: string[] = []
  runInNewContext(script, {
    URLSearchParams, Date, JSON, encodeURIComponent,
    sessionStorage: { getItem: (k: string) => data.get(k), setItem: (k: string,v: string) => { actions.push('store'); data.set(k,v) } },
    history: { replaceState: (_a: unknown,_b: string,url: string) => actions.push(url) },
    location: { search: '?state=synthetic-state&code=SYNTHETIC_CODE', replace: (url: string) => actions.push(url) },
  })
  expect(actions[0]).toBe('/drive-oauth-callback')
  expect(actions.at(-1)).toBe('/learning/drive?dt_workspace=a')
  expect(data.get('drive.oauth.callback')).toContain('SYNTHETIC_CODE')
})
