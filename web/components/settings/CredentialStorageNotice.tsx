'use client'

import { useEffect, useState } from 'react'
import { ShieldCheck, ShieldAlert } from 'lucide-react'
import { useTranslation } from 'react-i18next'
import { apiFetch, apiUrl } from '@/lib/api'
import { subPanelClass } from '@/components/settings/shared'

type StorageState = { available: boolean; enabled: boolean; files: Record<string, string> }
export default function CredentialStorageNotice() {
  const { t } = useTranslation()
  const [state, setState] = useState<StorageState | null>(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState(false)
  const [consent, setConsent] = useState(false)
  useEffect(() => {
    const controller = new AbortController()
    apiFetch(apiUrl('/api/settings/credential-storage'), { signal: controller.signal, cache: 'no-store' })
      .then(async r => { if (!r.ok) throw new Error(); setState(await r.json()) })
      .catch(() => { if (!controller.signal.aborted) setError(true) })
    return () => controller.abort()
  }, [])
  async function protect() {
    if (!consent || !state?.available) return
    setBusy(true); setError(false)
    try {
      const response = await apiFetch(apiUrl('/api/settings/credential-storage/protect'), { method: 'POST' })
      if (!response.ok) throw new Error()
      setState(await response.json()); setConsent(false)
    } catch { setError(true) } finally { setBusy(false) }
  }
  const protectedNow = state?.enabled && Object.values(state.files).every(value => value === 'protected' || value === 'absent')
  const Icon = protectedNow ? ShieldCheck : ShieldAlert
  return <section className={`${subPanelClass} mb-6 space-y-3 p-4`} aria-label={t('credentialStorage.title')}>
    <h2 className="flex items-center gap-2 font-medium"><Icon size={18} aria-hidden="true" />{t('credentialStorage.title')}</h2>
    <p role="status" className="text-sm">{t(!state ? 'credentialStorage.loading' : !state.available ? 'credentialStorage.unsupported' : protectedNow ? 'credentialStorage.protected' : 'credentialStorage.plaintext')}</p>
    <p className="text-sm text-muted-foreground">{t('credentialStorage.scope')}</p>
    {state?.available && !protectedNow && <>
      <label className="flex items-start gap-2 text-sm"><input type="checkbox" checked={consent} disabled={busy} onChange={e => setConsent(e.target.checked)} />{t('credentialStorage.consent')}</label>
      <button type="button" onClick={() => void protect()} disabled={!consent || busy} className="rounded-lg bg-primary px-3 py-2 text-sm text-primary-foreground disabled:opacity-40">{t(busy ? 'credentialStorage.protecting' : 'credentialStorage.enable')}</button>
    </>}
    {error && <p role="alert" className="text-sm text-red-500">{t('credentialStorage.error')}</p>}
  </section>
}
