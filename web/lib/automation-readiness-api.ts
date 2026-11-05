import {apiFetch} from '@/shared/api/client'
import {taskBoardUrl} from '@/lib/task-board-api'
export interface Readiness {
 observed_at:string;read_only:boolean;external_sources_checked:string[];notification_policy:string;
 local_tasks:{state:string;source:string;counts:Record<string,number>|null};
 rows:{id:string;route:string;evidence_doc:string;inventory_source:string;v2_state:string;v3_state:string;validation_scope:string;external_connection:string;sole_writer:string;cutover_ready:boolean;gaps:string[]}[];
}
export async function readReadiness(workspace:string):Promise<Readiness>{
 const response=await apiFetch(taskBoardUrl('/automation-readiness',workspace),{cache:'no-store'})
 if(!response.ok)throw new Error('readiness_unavailable')
 return response.json()
}
