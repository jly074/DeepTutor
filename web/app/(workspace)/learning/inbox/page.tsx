'use client'
import { Suspense } from 'react'
import { useSearchParams } from 'next/navigation'
import AnnouncementInbox from '@/components/learning/AnnouncementInbox'
import { activeWorkspaceId } from '@/lib/workspace-scope'
function InboxPage() {
  const search=useSearchParams()
  const workspaceId=search.get('dt_workspace')??activeWorkspaceId()
  return <AnnouncementInbox key={workspaceId} workspaceId={workspaceId}/>
}
export default function Page(){return <Suspense><InboxPage/></Suspense>}
