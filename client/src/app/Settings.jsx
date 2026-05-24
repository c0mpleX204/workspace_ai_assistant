import React from 'react'

export const MASKED_KEY_VALUE = '••••••••'
export const PROVIDER_API_PLACEHOLDER = 'https://api.deepseek.com'
export const DEFAULT_PROVIDER_SETTINGS = {
  api_base_url: '',
  api_key_masked: '',
  has_api_key: false,
  fast_model: '',
  heavy_model: '',
}

export default function Settings({
  backendUrl,
  setBackendUrl,
  userId,
  setUserId,
  providerDraft,
  setProviderDraft,
  providerSettings,
  savingProvider,
  saveProviderSettings,
  loadProviderSettings,
  live2dBgUrl,
  setLive2dBgUrl,
  audioInputs,
  audioOutputs,
  selectedAudioInput,
  setSelectedAudioInput,
  selectedAudioOutput,
  setSelectedAudioOutput,
  requestMicPermission,
  ttsEnabled,
  setTtsEnabled,
}) {
  return (
    <div className="page-container">
      <div className="page-title">设置</div>

      <div className="settings-card">
        <div className="settings-card-title">服务连接</div>
        <div className="field-group">
          <div className="field">
            <label className="field-label">后端地址</label>
            <input className="field-input" value={backendUrl} onChange={e => setBackendUrl(e.target.value)} placeholder="http://127.0.0.1:8000" />
          </div>
          <div className="field">
            <label className="field-label">用户 ID</label>
            <input className="field-input" value={userId} onChange={e => setUserId(e.target.value)} placeholder="user1" />
          </div>
        </div>
      </div>

      <div className="settings-card">
        <div className="settings-card-title">模型 API</div>
        <div className="field-group">
          <div className="field">
            <label className="field-label">API 地址</label>
            <input
              className="field-input"
              value={providerDraft.api_base_url}
              onChange={e => setProviderDraft(v => ({ ...v, api_base_url: e.target.value }))}
              placeholder={PROVIDER_API_PLACEHOLDER}
            />
          </div>
          <div className="field">
            <label className="field-label">API Key</label>
            <input
              className="field-input"
              type="password"
              autoComplete="off"
              value={providerDraft.api_key}
              onFocus={() => {
                if (providerDraft.api_key === MASKED_KEY_VALUE) {
                  setProviderDraft(v => ({ ...v, api_key: '' }))
                }
              }}
              onChange={e => setProviderDraft(v => ({ ...v, api_key: e.target.value }))}
              placeholder={providerSettings.has_api_key ? '已保存，输入新 Key 可替换' : 'DeepSeek API Key'}
            />
          </div>
          <div className="provider-model-grid">
            <div className="provider-model-item">
              <span>轻对话模型</span>
              <strong>{providerSettings.fast_model || '后端读取中'}</strong>
            </div>
            <div className="provider-model-item">
              <span>重任务模型</span>
              <strong>{providerSettings.heavy_model || '后端读取中'}</strong>
            </div>
          </div>
          <div className="field-row">
            <button className="ghost-btn" onClick={saveProviderSettings} disabled={savingProvider}>
              {savingProvider ? '保存中' : '保存模型 API'}
            </button>
            <button className="ghost-btn" onClick={() => loadProviderSettings(true)} disabled={savingProvider}>
              重新读取
            </button>
          </div>
        </div>
      </div>

      <div className="settings-card">
        <div className="settings-card-title">显示</div>
        <div className="field-group">
          <div className="field">
            <label className="field-label">Live2D 背景图 URL</label>
            <div className="field-row">
              <input
                className="field-input"
                value={live2dBgUrl}
                onChange={e => setLive2dBgUrl(e.target.value)}
                placeholder="https://... 或留空使用默认背景"
              />
              <button className="ghost-btn" onClick={() => setLive2dBgUrl('')} title="恢复默认背景">清空</button>
            </div>
          </div>
        </div>
      </div>

      <div className="settings-card">
        <div className="settings-card-title">音频设备</div>
        <div className="field-group">
          <div className="field">
            <label className="field-label">麦克风（输入）</label>
            <div className="field-row">
              <select className="field-input field-select" value={selectedAudioInput} onChange={e => setSelectedAudioInput(e.target.value)}>
                <option value="">系统默认</option>
                {audioInputs.map(device => (
                  <option key={device.deviceId} value={device.deviceId}>{device.label || `麦克风 ${device.deviceId.slice(0, 8)}`}</option>
                ))}
              </select>
              <button className="ghost-btn" onClick={requestMicPermission} title="授权后可显示设备名称">授权</button>
            </div>
          </div>
          <div className="field">
            <label className="field-label">扬声器（输出）</label>
            <select className="field-input field-select" value={selectedAudioOutput} onChange={e => setSelectedAudioOutput(e.target.value)}>
              <option value="">系统默认</option>
              {audioOutputs.map(device => (
                <option key={device.deviceId} value={device.deviceId}>{device.label || `扬声器 ${device.deviceId.slice(0, 8)}`}</option>
              ))}
            </select>
          </div>
          <div className="field">
            <label className="field-label">AI 回复朗读（TTS）</label>
            <button
              className={`retrieval-toggle${ttsEnabled ? ' active' : ''}`}
              onClick={() => setTtsEnabled(v => !v)}
              style={{ alignSelf: 'flex-start' }}
            >
              {ttsEnabled ? '已开启' : '已关闭'}
            </button>
          </div>
        </div>
      </div>
    </div>
  )
}
