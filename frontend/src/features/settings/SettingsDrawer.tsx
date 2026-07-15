import { useEffect, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import {
  Alert,
  Button,
  Drawer,
  Form,
  Input,
  message,
  Select,
  Space,
  Tag,
  Typography,
} from 'antd'
import { ExperimentOutlined, LinkOutlined } from '@ant-design/icons'
import {
  AiConfigPayload,
  getAiConfig,
  getPresets,
  ProviderPreset,
  saveAiConfig,
  testAiConfig,
} from '@/api/settings'

const { Text, Link } = Typography

interface Props {
  open: boolean
  onClose: () => void
}

/** AI 配置抽屉：右上角齿轮打开。 */
export function SettingsDrawer({ open, onClose }: Props) {
  const qc = useQueryClient()
  const [form] = Form.useForm<AiConfigPayload>()
  const [presetId, setPresetId] = useState<string>('custom')
  const [testResult, setTestResult] = useState<{ ok: boolean; msg: string } | null>(null)

  const presetsQ = useQuery({ queryKey: ['ai-presets'], queryFn: getPresets })
  const configQ = useQuery({ queryKey: ['ai-config'], queryFn: getAiConfig, enabled: open })

  // 抽屉打开时用当前配置回填
  useEffect(() => {
    if (!open || !configQ.data) return
    form.setFieldsValue({
      provider: configQ.data.provider || 'custom',
      base_url: configQ.data.base_url || '',
      model: configQ.data.model || '',
      api_key: '', // 不回填 key（打码后无法还原）
    })
    setPresetId(configQ.data.provider || 'custom')
    setTestResult(null)
  }, [open, configQ.data])

  const saveMut = useMutation({
    mutationFn: saveAiConfig,
    onSuccess: () => {
      message.success('已保存')
      qc.invalidateQueries({ queryKey: ['ai-config'] })
    },
    onError: (e: any) => message.error(e?.response?.data?.detail || '保存失败'),
  })

  const testMut = useMutation({
    mutationFn: testAiConfig,
    onSuccess: (r) => {
      if (r.ok) {
        setTestResult({ ok: true, msg: `连通成功 · ${r.model} · 回复：${r.reply || '(空)'}` })
      } else {
        setTestResult({ ok: false, msg: r.error || '连通失败' })
      }
    },
    onError: (e: any) => setTestResult({ ok: false, msg: e?.message || '请求失败' }),
  })

  const applyPreset = (id: string) => {
    setPresetId(id)
    const p: ProviderPreset | undefined = (presetsQ.data || []).find((x) => x.id === id)
    if (!p || id === 'custom') return
    form.setFieldsValue({
      provider: p.id,
      base_url: p.base_url,
      model: p.default_model,
    })
  }

  const currentPreset = (presetsQ.data || []).find((p) => p.id === presetId)

  const runTest = async () => {
    const values = await form.validateFields(['base_url', 'model', 'api_key'])
    testMut.mutate({
      provider: form.getFieldValue('provider'),
      base_url: values.base_url!,
      model: values.model!,
      api_key: values.api_key!,
    })
  }

  const runSave = async () => {
    const values = await form.validateFields()
    // 先测通再存；若已有 key（用户没输入新 key）跳过测试直接存其他字段
    const hasNewKey = !!values.api_key
    if (hasNewKey) {
      const r = await testAiConfig({
        provider: values.provider,
        base_url: values.base_url!,
        model: values.model!,
        api_key: values.api_key!,
      })
      if (!r.ok) {
        setTestResult({ ok: false, msg: r.error || '连通失败，未保存' })
        return
      }
      setTestResult({ ok: true, msg: `连通成功 · ${r.model}` })
    }
    // 空 api_key 不覆盖已存的
    const payload: AiConfigPayload = {
      provider: values.provider,
      base_url: values.base_url,
      model: values.model,
    }
    if (hasNewKey) payload.api_key = values.api_key
    saveMut.mutate(payload)
  }

  return (
    <Drawer
      title="设置 · AI 模型"
      open={open}
      onClose={onClose}
      width={480}
      extra={
        <Space>
          <Button icon={<ExperimentOutlined />} loading={testMut.isPending} onClick={runTest}>
            连通测试
          </Button>
          <Button type="primary" loading={saveMut.isPending} onClick={runSave}>
            保存
          </Button>
        </Space>
      }
    >
      {configQ.data && (
        <Alert
          type="info"
          showIcon
          style={{ marginBottom: 16 }}
          message={
            <span>
              当前生效：
              <Tag>{configQ.data.provider || '-'}</Tag>
              <Tag>{configQ.data.model || '-'}</Tag>
              {configQ.data.has_api_key ? (
                <Tag color="success">Key: {configQ.data.api_key_masked}</Tag>
              ) : (
                <Tag color="warning">未设置 API Key</Tag>
              )}
            </span>
          }
        />
      )}

      <Form form={form} layout="vertical">
        <Form.Item label="服务商预设">
          <Select
            value={presetId}
            onChange={applyPreset}
            options={(presetsQ.data || []).map((p) => ({ value: p.id, label: p.name }))}
          />
          {currentPreset?.docs_url && (
            <Text type="secondary" style={{ fontSize: 12 }}>
              <LinkOutlined /> <Link href={currentPreset.docs_url} target="_blank">获取 API Key</Link>
            </Text>
          )}
        </Form.Item>

        <Form.Item name="provider" label="Provider ID" hidden>
          <Input />
        </Form.Item>

        <Form.Item
          name="base_url"
          label="Base URL（OpenAI 兼容协议入口）"
          rules={[{ required: true, message: '必填' }, { type: 'url', message: '需为合法 URL' }]}
        >
          <Input placeholder="如 https://api.deepseek.com/v1" />
        </Form.Item>

        <Form.Item name="model" label="Model" rules={[{ required: true, message: '必填' }]}>
          <Input placeholder="如 deepseek-chat / qwen-plus / gpt-4o-mini" />
        </Form.Item>

        <Form.Item
          name="api_key"
          label={
            <span>
              API Key{' '}
              {configQ.data?.has_api_key && (
                <Text type="secondary" style={{ fontSize: 12 }}>
                  · 留空则保留原值
                </Text>
              )}
            </span>
          }
          rules={configQ.data?.has_api_key ? [] : [{ required: true, message: '首次配置需填写' }]}
        >
          <Input.Password autoComplete="new-password" placeholder="sk-…" />
        </Form.Item>

        {testResult && (
          <Alert
            type={testResult.ok ? 'success' : 'error'}
            showIcon
            message={testResult.msg}
            style={{ marginTop: 8 }}
          />
        )}
      </Form>

      <div style={{ marginTop: 32, color: '#94a3b8', fontSize: 12, lineHeight: 1.6 }}>
        <p>· 配置存在本地 SQLite（backend/data/app.db），不上传任何服务器。</p>
        <p>· 支持所有兼容 OpenAI 协议的服务：DeepSeek / 通义 / 智谱 / OpenAI / 自建 LLM。</p>
        <p>· 保存前会用一次极简调用验证 key/url/model 是否可用。</p>
      </div>
    </Drawer>
  )
}
