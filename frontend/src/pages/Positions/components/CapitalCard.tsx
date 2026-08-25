/** 总资金设置卡（Trader 仓位建议的基准）。 */
import { Button, Card, InputNumber, Tooltip, Typography, message } from 'antd'
import { WalletOutlined } from '@ant-design/icons'
import { useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { getCapital, saveCapital } from '@/api/settings'

const { Text } = Typography

export function CapitalCard() {
  const qc = useQueryClient()
  const capitalQ = useQuery({
    queryKey: ['total-capital'],
    queryFn: getCapital,
  })
  const capitalMut = useMutation({
    mutationFn: (amount: number) => saveCapital(amount),
    onSuccess: () => {
      message.success('总资金已保存')
      qc.invalidateQueries({ queryKey: ['total-capital'] })
      qc.invalidateQueries({ queryKey: ['action-plan'] })
    },
  })
  const [capitalInput, setCapitalInput] = useState<number | null>(null)
  const currentCapital = capitalQ.data?.total_capital ?? null

  return (
    <Card size="small" style={{ marginBottom: 16 }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
        <Tooltip title="总资金用于 Trader 计算具体仓位建议（股数 = 100 的整数倍）">
          <Text style={{ fontSize: 13 }}>
            <WalletOutlined style={{ marginRight: 4 }} />
            总资金
          </Text>
        </Tooltip>
        <InputNumber
          size="small"
          style={{ width: 150 }}
          min={1000}
          step={10000}
          placeholder="如 100000"
          value={capitalInput ?? currentCapital ?? undefined}
          onChange={(v) => setCapitalInput(v)}
          formatter={(v) => v ? `¥ ${Number(v).toLocaleString()}` : ''}
          parser={(v) => Number((v || '').replace(/[¥,\s]/g, '')) as any}
        />
        <Button
          size="small"
          type="primary"
          disabled={!capitalInput || capitalInput === currentCapital}
          loading={capitalMut.isPending}
          onClick={() => capitalInput && capitalMut.mutate(capitalInput)}
        >
          保存
        </Button>
        {currentCapital && (
          <Text type="secondary" style={{ fontSize: 12 }}>
            当前：¥{currentCapital.toLocaleString()}
          </Text>
        )}
      </div>
    </Card>
  )
}
