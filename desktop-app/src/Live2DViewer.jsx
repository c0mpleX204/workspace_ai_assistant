import React, { useEffect, useRef, useState } from 'react'
import * as PIXI from 'pixi.js'

// 暴露 PIXI 到全局，这是 pixi-live2d-display 的前置要求
window.PIXI = PIXI
const CUBISM_CORE_PATH = '/live2d/cubism/live2dcubismcore.min.js'
const STORAGE_KEY = 'live2d-viewer-controls-v1'
const DEFAULT_TRANSFORM = { scalePercent: 92, xPercent: 50, yPercent: 96, opacityPercent: 100 }
const DEFAULT_BUTTON_POS = { x: 12, y: 12 }

function loadPersistedControls() {
  try {
    const raw = window.localStorage.getItem(STORAGE_KEY)
    if (!raw) return { transform: DEFAULT_TRANSFORM, buttonPos: DEFAULT_BUTTON_POS }

    const parsed = JSON.parse(raw)
    const t = parsed?.transform || {}
    const b = parsed?.buttonPos || {}

    const transform = {
      scalePercent: Number.isFinite(t.scalePercent) ? t.scalePercent : DEFAULT_TRANSFORM.scalePercent,
      xPercent: Number.isFinite(t.xPercent) ? t.xPercent : DEFAULT_TRANSFORM.xPercent,
      yPercent: Number.isFinite(t.yPercent) ? t.yPercent : DEFAULT_TRANSFORM.yPercent,
      opacityPercent: Number.isFinite(t.opacityPercent) ? t.opacityPercent : DEFAULT_TRANSFORM.opacityPercent,
    }

    const buttonPos = {
      x: Number.isFinite(b.x) ? b.x : DEFAULT_BUTTON_POS.x,
      y: Number.isFinite(b.y) ? b.y : DEFAULT_BUTTON_POS.y,
    }

    return { transform, buttonPos }
  } catch {
    return { transform: DEFAULT_TRANSFORM, buttonPos: DEFAULT_BUTTON_POS }
  }
}

function patchNonInteractiveTree(node) {
  if (!node) return

  if (typeof node.isInteractive !== 'function') {
    node.isInteractive = () => false
  }

  if (Array.isArray(node.children)) {
    for (const child of node.children) patchNonInteractiveTree(child)
  }
}

export default function Live2DViewer({ backgroundImageUrl = '' }) {
  const persisted = loadPersistedControls()
  const wrapperRef = useRef(null)
  const canvasRef = useRef(null)
  const appRef = useRef(null)
  const modelRef = useRef(null)
  const transformRef = useRef(persisted.transform)
  const dragRef = useRef(null)
  const [error, setError] = useState(null)
  const [loading, setLoading] = useState(true)
  const [showControls, setShowControls] = useState(false)
  const [buttonPos, setButtonPos] = useState(persisted.buttonPos)
  const [transform, setTransform] = useState(persisted.transform)

  const applyTransform = () => {
    const app = appRef.current
    const model = modelRef.current
    if (!app || !model) return

    const w = app.renderer.width || 1
    const h = app.renderer.height || 1
    const bounds = model.getLocalBounds()
    const bw = Math.max(bounds.width || 1, 1)
    const bh = Math.max(bounds.height || 1, 1)

    const fitScale = Math.min(w / bw, h / bh)
    const t = transformRef.current

    model.scale.set(fitScale * (t.scalePercent / 100))
    model.pivot.set(bounds.x + bw * 0.5, bounds.y + bh * 0.92)
    model.position.set(w * (t.xPercent / 100), h * (t.yPercent / 100))
    model.alpha = Math.max(0.1, Math.min(1, t.opacityPercent / 100))
  }

  const startDragButton = e => {
    const wrapper = wrapperRef.current
    if (!wrapper) return
    e.preventDefault()

    const rect = wrapper.getBoundingClientRect()
    dragRef.current = {
      rect,
      offsetX: e.clientX - (rect.left + buttonPos.x),
      offsetY: e.clientY - (rect.top + buttonPos.y),
    }

    const onMove = ev => {
      const state = dragRef.current
      if (!state) return
      const maxX = Math.max(state.rect.width - 42, 0)
      const maxY = Math.max(state.rect.height - 42, 0)
      const x = Math.min(Math.max(ev.clientX - state.rect.left - state.offsetX, 0), maxX)
      const y = Math.min(Math.max(ev.clientY - state.rect.top - state.offsetY, 0), maxY)
      setButtonPos({ x, y })
    }

    const onUp = () => {
      window.removeEventListener('pointermove', onMove)
      window.removeEventListener('pointerup', onUp)
      dragRef.current = null
    }

    window.addEventListener('pointermove', onMove)
    window.addEventListener('pointerup', onUp)
  }

  const handleTransformChange = (key, value) => {
    setTransform(prev => {
      const next = { ...prev, [key]: value }
      transformRef.current = next
      return next
    })
    requestAnimationFrame(() => applyTransform())
  }

  const handleReset = () => {
    transformRef.current = DEFAULT_TRANSFORM
    setTransform(DEFAULT_TRANSFORM)
    requestAnimationFrame(() => applyTransform())
  }

  useEffect(() => {
    if (!canvasRef.current) return

    let disposed = false
    let removeResize = null

    ;(async () => {
      try {
        setError(null)
        setLoading(true)

        if (!window.Live2DCubismCore) {
          throw new Error(`未检测到 Cubism Core，请确认 ${CUBISM_CORE_PATH} 可访问`)
        }

        const app = new PIXI.Application({
          view: canvasRef.current,
          autoStart: true,
          backgroundAlpha: 0,
          resizeTo: canvasRef.current.parentElement,
        })
        appRef.current = app

        const { Live2DModel } = await import('pixi-live2d-display/cubism4')

        const modelUrl = '/live2d/models/hiyori_free_zh/runtime/hiyori_free_t08.model3.json'
        // 显式关闭自动交互，避免在桌面端事件系统上出现兼容问题。
        const model = await Live2DModel.from(modelUrl, { autoInteract: false })

        if (disposed) {
          model.destroy()
          return
        }

        modelRef.current = model
        model.autoInteract = false
        model.interactive = false
        patchNonInteractiveTree(model)
        app.stage.addChild(model)

        applyTransform()
        const onResize = () => applyTransform()
        window.addEventListener('resize', onResize)
        removeResize = () => window.removeEventListener('resize', onResize)
        setLoading(false)
      } catch (err) {
        console.error('Live2D 初始化失败:', err)
        setError(err?.message || 'Live2D 初始化失败')
        setLoading(false)
      }
    })()

    return () => {
      disposed = true
      try {
        if (removeResize) removeResize()
        if (modelRef.current) {
          modelRef.current.destroy()
          modelRef.current = null
        }
        if (appRef.current) {
          appRef.current.destroy(false, { children: true })
          appRef.current = null
        }
      } catch (err) {
        console.error('卸载PIXI组件失败:', err)
      }
    }
  }, [])

  useEffect(() => {
    applyTransform()
  }, [transform])

  useEffect(() => {
    try {
      window.localStorage.setItem(
        STORAGE_KEY,
        JSON.stringify({
          transform,
          buttonPos,
        })
      )
    } catch {
      // 忽略本地存储异常（如隐私模式或写入配额问题）
    }
  }, [transform, buttonPos])

  const bgUrl = String(backgroundImageUrl || '').trim()
  const wrapperStyle = {
    width: '100%',
    height: '100%',
    position: 'relative',
    display: 'flex',
    justifyContent: 'center',
    alignItems: 'center',
    backgroundColor: '#eef6fb',
    backgroundImage: bgUrl
      ? `linear-gradient(rgba(243, 250, 255, 0.28), rgba(243, 250, 255, 0.28)), url("${bgUrl}")`
      : 'radial-gradient(circle at 20% 20%, rgba(144, 214, 230, 0.32), transparent 45%), radial-gradient(circle at 85% 10%, rgba(166, 226, 211, 0.34), transparent 42%), linear-gradient(180deg, #f8fcff, #ecf5fb)',
    backgroundSize: bgUrl ? 'cover' : 'auto',
    backgroundPosition: 'center',
    backgroundRepeat: 'no-repeat',
  }

  return (
    <div ref={wrapperRef} style={wrapperStyle}>
      {loading && !error && (
        <div style={{ position: 'absolute', color: '#6d879b', top: 10, left: 10, fontSize: 12 }}>
          Live2D 加载中...
        </div>
      )}
      {error && (
        <div style={{ position: 'absolute', color: '#bf5d73', top: 10, left: 10, right: 10, fontSize: 13, lineHeight: 1.4 }}>
          模型加载失败: {error}
        </div>
      )}

      <button
        type="button"
        onPointerDown={startDragButton}
        onClick={() => setShowControls(v => !v)}
        style={{
          position: 'absolute',
          left: buttonPos.x,
          top: buttonPos.y,
          width: 32,
          height: 32,
          borderRadius: 999,
          border: '1px solid #bed2e1',
          background: 'rgba(255,255,255,0.9)',
          color: '#245b76',
          boxShadow: '0 8px 18px rgba(42, 101, 136, 0.22)',
          cursor: 'grab',
          zIndex: 20,
          userSelect: 'none',
        }}
        title="拖拽/打开模型控制"
      >
        ⚙
      </button>

      {showControls && (
        <div
          style={{
            position: 'absolute',
            right: 12,
            bottom: 12,
            width: 260,
            background: 'rgba(255, 255, 255, 0.92)',
            border: '1px solid #d4e1eb',
            borderRadius: 10,
            padding: 10,
            zIndex: 19,
            color: '#26445b',
            fontSize: 12,
            boxShadow: '0 16px 32px rgba(53, 106, 137, 0.2)',
          }}
        >
          <div style={{ marginBottom: 8, fontWeight: 600 }}>模型位置与显示</div>

          <label style={{ display: 'block', marginBottom: 6 }}>
            缩放 {transform.scalePercent}%
            <input
              type="range"
              min="40"
              max="170"
              value={transform.scalePercent}
              onChange={e => handleTransformChange('scalePercent', Number(e.target.value))}
              style={{ width: '100%' }}
            />
          </label>

          <label style={{ display: 'block', marginBottom: 6 }}>
            水平 {transform.xPercent}%
            <input
              type="range"
              min="10"
              max="90"
              value={transform.xPercent}
              onChange={e => handleTransformChange('xPercent', Number(e.target.value))}
              style={{ width: '100%' }}
            />
          </label>

          <label style={{ display: 'block', marginBottom: 10 }}>
            垂直 {transform.yPercent}%
            <input
              type="range"
              min="20"
              max="150"
              value={transform.yPercent}
              onChange={e => handleTransformChange('yPercent', Number(e.target.value))}
              style={{ width: '100%' }}
            />
          </label>

          <label style={{ display: 'block', marginBottom: 10 }}>
            透明度 {transform.opacityPercent}%
            <input
              type="range"
              min="20"
              max="100"
              value={transform.opacityPercent}
              onChange={e => handleTransformChange('opacityPercent', Number(e.target.value))}
              style={{ width: '100%' }}
            />
          </label>

          <div style={{ display: 'flex', justifyContent: 'space-between', gap: 8 }}>
            <button
              type="button"
              onClick={handleReset}
              style={{
                flex: 1,
                border: '1px solid #c8d9e6',
                background: '#f6fbff',
                color: '#2a556f',
                borderRadius: 8,
                padding: '5px 8px',
                cursor: 'pointer',
              }}
            >
              复位
            </button>
            <button
              type="button"
              onClick={() => setShowControls(false)}
              style={{
                flex: 1,
                border: '1px solid #c8d9e6',
                background: '#f6fbff',
                color: '#2a556f',
                borderRadius: 8,
                padding: '5px 8px',
                cursor: 'pointer',
              }}
            >
              收起
            </button>
          </div>
        </div>
      )}

      <canvas ref={canvasRef} style={{ width: '100%', height: '100%' }} />
    </div>
  )
}
