import {fireEvent,render,screen,waitFor} from '@testing-library/react'
import {expect,it,vi} from 'vitest'
import {AvailabilityPanel} from '@/features/calendar/components/AvailabilityPanel'
const get=vi.hoisted(()=>vi.fn())
vi.mock('@/features/calendar/transport/api',()=>({getAvailability:get}))
vi.mock('react-i18next',()=>({useTranslation:()=>({t:(s:string)=>s})}))
it('calculates explicitly, invalidates edited results and clears stale data on failure',async()=>{
 get.mockResolvedValueOnce({date:'2026-10-17',revision:4,busy_count:1,free:[{start:'2026-10-17T02:00:00Z',end:'2026-10-17T03:00:00Z'}],conflicts:[]})
 render(<AvailabilityPanel/>);expect(get).not.toHaveBeenCalled()
 fireEvent.click(screen.getByText('availability.title'))
 fireEvent.change(screen.getByLabelText('availability.date'),{target:{value:'2026-10-17'}})
 fireEvent.click(screen.getByRole('button',{name:'availability.calculate'}))
 await screen.findByTestId('availability-result')
 expect(get).toHaveBeenCalledWith('2026-10-17','Asia/Taipei',30)
 fireEvent.change(screen.getByLabelText('availability.date'),{target:{value:'2026-10-18'}})
 expect(screen.queryByTestId('availability-result')).not.toBeInTheDocument()
 get.mockRejectedValueOnce(new Error('synthetic failure'))
 fireEvent.click(screen.getByRole('button',{name:'availability.calculate'}))
 await waitFor(()=>expect(screen.getByRole('alert')).toHaveTextContent('availability.error'))
 expect(screen.queryByTestId('availability-result')).not.toBeInTheDocument()
})
