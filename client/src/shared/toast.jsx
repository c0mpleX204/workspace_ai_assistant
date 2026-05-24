import React, { useCallback, useEffect, useRef, useState } from 'react'

export function useToast() {
  const [toast, setToast] = useState({ msg: '', type: '', visible: false })
  const timerRef = useRef(null)
  const show = useCallback((msg, type = 'info') => {
    clearTimeout(timerRef.current)
    setToast({ msg, type, visible: true })
    timerRef.current = setTimeout(() => setToast(t => ({ ...t, visible: false })), 2800)
  }, [])
  return { toast, show }
}

export function Lightbox({ src, onClose }) {
  useEffect(() => {
    const handler = (e) => { if (e.key === 'Escape') onClose() }
    window.addEventListener('keydown', handler)
    return () => window.removeEventListener('keydown', handler)
  }, [onClose])
  if (!src) return null
  return (
    <div className="lightbox-overlay" onClick={onClose}>
      <img
        className="lightbox-img"
        src={src}
        alt="大图预览"
        onClick={e => e.stopPropagation()}
      />
      <button className="lightbox-close" onClick={onClose}>x</button>
    </div>
  )
}
