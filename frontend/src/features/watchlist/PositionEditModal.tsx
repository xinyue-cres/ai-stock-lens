import { useEffect, useState } from 'react'
import {
  Alert,
  AutoComplete,
  Button,
  DatePicker,
  Form,
  Input,
  InputNumber,
  Modal,
  Space,
  Spin,
  Typography,
  message,
} from 'antd'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import dayjs from 'dayjs'
import { deletePosition, getPosition, upsertPosition } from '@/api/positions'
import { searchStocks, StockInfo } from '@/api/stocks'

const { Text } = Typography

interface Props {
  /** 指定 code → 编辑模式；空 → 新增模式，先搜索选股 */
  code?: string | null
  name?: string
  open: boolean
  onClose: () => void
}

/**
 * 持仓编辑弹窗。
 * - 传入 code：直接编辑该 code 持仓
 * - code 为空：新增模式，顶部显示股票搜索
 */
export function PositionEditModal({ code: initialCode, name, open, onClose }: Props) {
  const qc = useQueryClient()
  const [form] = Form.useForm()
  const [selectedCode, setSelectedCode] = useState<string | null>(initialCode || null)
  const [selectedName, setSelectedName] = useState<string | null>(name || null)
  const [keyword, setKeyword] = useState('')

  const isAddMode = !initialCode

  // 弹窗打开时重置 selection
  useEffect(() => {
    if (open) {
      setSelectedCode(initialCode || null)
      setSelectedName(name || null)
      setKeyword('')
    }
  }, [open, initialCode, name])

  const searchQ = useQuery({
    queryKey: ['stock-search', keyword],
    queryFn: () => searchStocks(keyword),
    enabled: isAddMode && keyword.length >= 1,
    staleTime: 60_000,
  })

  const existing = useQuery({
    queryKey: ['position', selectedCode],
    queryFn: () => (selectedCode ? getPosition(selectedCode).catch(() => null) : null),
    enabled: open && !!selectedCode,
    staleTime: 0,
  })

  useEffect(() => {
    if (!open || !selectedCode) return
    if (existing.data) {
      form.setFieldsValue({
        quantity: existing.data.quantity,
        cost_price: existing.data.cost_price,
        opened_at: dayjs(existing.data.opened_at),
        note: existing.data.note || '',
      })
    } else {
      form.resetFields()
      form.setFieldsValue({ opened_at: dayjs() })
    }
  }, [open, selectedCode, existing.data, form])

  const saveMut = useMutation({
    mutationFn: (v: any) =>
      upsertPosition({
        code: selectedCode!,
        quantity: v.quantity,
        cost_price: v.cost_price,
        opened_at: v.opened_at.format('YYYY-MM-DD'),
        note: v.note?.trim() || null,
      }),
    onSuccess: () => {
      message.success('已保存持仓')
      invalidateAll()
      onClose()
    },
    onError: (e: any) => message.error(e?.response?.data?.detail || '保存失败'),
  })

  const delMut = useMutation({
    mutationFn: () => deletePosition(selectedCode!),
    onSuccess: () => {
      message.success('已清除持仓记录')
      invalidateAll()
      onClose()
    },
    onError: () => message.error('清除失败'),
  })

  const invalidateAll = () => {
    qc.invalidateQueries({ queryKey: ['position'] })
    qc.invalidateQueries({ queryKey: ['positions-list'] })
    qc.invalidateQueries({ queryKey: ['signals'] })
    qc.invalidateQueries({ queryKey: ['watchlist'] })
    // 持仓变动会改变 Trader 的建议方向（买入 → 加仓/止盈 等），失效对应缓存让下次
    // 打开操作指示时自然重新拉；依赖状态栏也一并刷新（虽然 deps 只看 K 线+报告，
    // 但兼顾未来可能把 position.updated_at 纳入判定）
    qc.invalidateQueries({ queryKey: ['action-plan'] })
    qc.invalidateQueries({ queryKey: ['action-plan-deps'] })
  }

  const searchOptions = (searchQ.data || []).slice(0, 20).map((s: StockInfo) => ({
    value: s.code,
    label: (
      <Space>
        <Text style={{ fontFamily: 'monospace', fontSize: 12 }}>{s.code}</Text>
        <Text>{s.name}</Text>
        <Text type="secondary" style={{ fontSize: 11 }}>
          {s.market}
        </Text>
      </Space>
    ),
    stock: s,
  }))

  const title = initialCode
    ? `编辑持仓 · ${name || initialCode}`
    : selectedCode
    ? `新增持仓 · ${selectedName || selectedCode}`
    : '新增持仓'

  return (
    <Modal
      open={open}
      onCancel={onClose}
      title={title}
      footer={
        <Space>
          {selectedCode && existing.data && (
            <Button danger onClick={() => delMut.mutate()} loading={delMut.isPending}>
              清除持仓
            </Button>
          )}
          <Button onClick={onClose}>取消</Button>
          <Button
            type="primary"
            disabled={!selectedCode}
            loading={saveMut.isPending}
            onClick={() => form.validateFields().then((v) => saveMut.mutate(v))}
          >
            保存
          </Button>
        </Space>
      }
      destroyOnClose
    >
      <Alert
        type="info"
        showIcon
        style={{ marginBottom: 16, fontSize: 12 }}
        message="录入持仓让 Trader 出个性化建议（加仓/止盈/止损），本工具不涉及交易执行"
      />

      {isAddMode && (
        <Form.Item label="选择股票" style={{ marginBottom: 16 }} required>
          <AutoComplete
            value={selectedCode ? `${selectedCode} · ${selectedName || ''}` : keyword}
            options={searchOptions}
            onSearch={(v) => {
              setKeyword(v)
              setSelectedCode(null)
              setSelectedName(null)
            }}
            onSelect={(_v, opt: any) => {
              setSelectedCode(opt.stock.code)
              setSelectedName(opt.stock.name)
              setKeyword('')
            }}
            placeholder="输入代码或名称搜索，如 600519 / 茅台"
            notFoundContent={searchQ.isFetching ? <Spin size="small" /> : keyword ? '无匹配' : null}
            style={{ width: '100%' }}
            allowClear
            onClear={() => {
              setSelectedCode(null)
              setSelectedName(null)
              setKeyword('')
            }}
          />
        </Form.Item>
      )}

      <Form form={form} layout="vertical" disabled={!selectedCode}>
        <Form.Item
          label="持股数量（股）"
          name="quantity"
          rules={[{ required: true, message: '请填数量' }]}
        >
          <InputNumber min={0} step={100} style={{ width: '100%' }} placeholder="如 1000" />
        </Form.Item>
        <Form.Item
          label="加权平均成本价（元）"
          name="cost_price"
          rules={[{ required: true, message: '请填成本' }]}
        >
          <InputNumber min={0.01} step={0.01} precision={3} style={{ width: '100%' }} placeholder="如 18.50" />
        </Form.Item>
        <Form.Item
          label="建仓日"
          name="opened_at"
          rules={[{ required: true, message: '请选建仓日' }]}
        >
          <DatePicker style={{ width: '100%' }} />
        </Form.Item>
        <Form.Item label="备注（可选）" name="note">
          <Input.TextArea rows={2} placeholder="如：半仓短线 / 长期底仓" maxLength={100} />
        </Form.Item>
      </Form>
    </Modal>
  )
}
