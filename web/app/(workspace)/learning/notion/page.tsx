'use client'
import { Suspense } from 'react'
import { useSearchParams } from 'next/navigation'
import NotionSourcesPanel from '@/components/learning/NotionSourcesPanel'
import { activeWorkspaceId } from '@/lib/workspace-scope'
function NotionPage() {
  const search=useSearchParams()
  const workspaceId=search.get('dt_workspace')??activeWorkspaceId()
  return <NotionSourcesPanel key={workspaceId} workspaceId={workspaceId}/>
}
export default function Page(){return <Suspense><NotionPage/></Suspense>}
