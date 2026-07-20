import { StockGroup } from '@/api/groups'

interface GroupNavProps {
  groups: StockGroup[]
  totalCount: number
  activeGroup: number | 'all'
  onGroupChange: (g: number | 'all') => void
  onManage: () => void
}

export default function GroupNav({ groups, totalCount, activeGroup, onGroupChange, onManage }: GroupNavProps) {
  return (
    <div style={{
      position: 'fixed',
      top: '35%',
      left: 'max(8px, calc(50% - 450px - 130px))',
      transform: 'translateY(-50%)',
      width: 110,
      zIndex: 50,
    }}>
      <div style={{ background: '#fff', borderRadius: 8, border: '1px solid #f0f0f0', padding: '8px 0', boxShadow: '0 2px 8px rgba(0,0,0,0.06)' }}>
        <GroupNavItem
          label={`全部 (${totalCount})`}
          active={activeGroup === 'all'}
          onClick={() => onGroupChange('all')}
        />
        {groups.map(g => (
          <GroupNavItem
            key={g.id}
            label={`${g.name} (${g.stock_count})`}
            active={activeGroup === g.id}
            onClick={() => onGroupChange(g.id)}
          />
        ))}
        <div style={{ borderTop: '1px solid #f0f0f0', margin: '4px 0' }} />
        <GroupNavItem
          label="管理分组"
          active={false}
          onClick={onManage}
          muted
        />
      </div>
    </div>
  )
}

function GroupNavItem({ label, active, onClick, muted }: { label: string; active: boolean; onClick: () => void; muted?: boolean }) {
  return (
    <div
      onClick={onClick}
      style={{
        padding: '6px 12px',
        cursor: 'pointer',
        fontSize: 12,
        fontWeight: active ? 600 : 400,
        color: muted ? '#9ca3af' : active ? '#1d4ed8' : '#374151',
        background: active ? '#eff6ff' : 'transparent',
        borderLeft: active ? '3px solid #3b82f6' : '3px solid transparent',
        transition: 'all 0.1s',
      }}
    >
      {label}
    </div>
  )
}
