'use client'
import {Suspense} from 'react'
import {useSearchParams} from 'next/navigation'
import {activeWorkspaceId} from '@/lib/workspace-scope'
import AutomationReadiness from '@/components/learning/AutomationReadiness'
function ReadinessPage(){const search=useSearchParams();const workspace=search.get('dt_workspace')??activeWorkspaceId();return <AutomationReadiness key={workspace} workspaceId={workspace}/>}
export default function Page(){return <Suspense><ReadinessPage/></Suspense>}
