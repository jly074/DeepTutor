'use client'
import {Suspense} from 'react'
import {useSearchParams} from 'next/navigation'
import {activeWorkspaceId} from '@/lib/workspace-scope'
import UnsortedInbox from '@/components/learning/UnsortedInbox'
function Intake(){const search=useSearchParams();const workspace=search.get('dt_workspace')??activeWorkspaceId();return <UnsortedInbox key={workspace} workspaceId={workspace}/>}
export default function Page(){return <Suspense><Intake/></Suspense>}
