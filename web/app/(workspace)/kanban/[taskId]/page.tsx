'use client'
import {Suspense} from 'react'
import {useParams,useSearchParams} from 'next/navigation'
import {activeWorkspaceId} from '@/lib/workspace-scope'
import TaskDetailPanel from '@/components/tasks/TaskDetailPanel'
function DetailPage(){const params=useParams<{taskId:string}>();const search=useSearchParams();const workspace=search.get('dt_workspace')??activeWorkspaceId();return <TaskDetailPanel key={`${workspace}:${params.taskId}`} taskId={params.taskId} workspaceId={workspace}/>}
export default function Page(){return <Suspense><DetailPage/></Suspense>}
