'use client'
import { Suspense } from 'react'
import { useSearchParams } from 'next/navigation'
import DriveSourcesPanel from '@/components/learning/DriveSourcesPanel'
import { activeWorkspaceId } from '@/lib/workspace-scope'

function DrivePage() {
  const search = useSearchParams()
  const workspaceId = search.get('dt_workspace') ?? activeWorkspaceId()
  return <DriveSourcesPanel key={workspaceId} workspaceId={workspaceId} />
}
export default function Page() {
  return <Suspense><DrivePage /></Suspense>
}
