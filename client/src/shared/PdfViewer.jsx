import React, { useState, useEffect, useRef, useCallback } from 'react'
import { Document, Page, pdfjs } from 'react-pdf'
import { chatStreamApi } from '../api'
import 'react-pdf/dist/esm/Page/TextLayer.css'

// polyfills for Electron 26 (Chromium 116) - main thread
if (!Promise.withResolvers) {
  Promise.withResolvers = function () {
    let resolve, reject
    const promise = new Promise((res, rej) => { resolve = res; reject = rej })
    return { promise, resolve, reject }
  }
}
if (typeof URL.parse !== 'function') {
  URL.parse = (url, base) => { try { return new URL(url, base) } catch { return null } }
}

// Create Blob worker with polyfills injected synchronously (Vite ?raw inlines the code)
import workerCode from 'react-pdf/node_modules/pdfjs-dist/build/pdf.worker.min.mjs?raw'

const polyfills = `
if(typeof Promise.withResolvers!=='function'){Promise.withResolvers=function(){let r,j;const p=new Promise((a,b)=>{r=a;j=b});return{promise:p,resolve:r,reject:j}}}
if(typeof URL.parse!=='function'){URL.parse=function(u,b){try{return new URL(u,b)}catch(e){return null}}}
`

const blob = new Blob([polyfills + workerCode], { type: 'text/javascript' })
pdfjs.GlobalWorkerOptions.workerSrc = URL.createObjectURL(blob)

function loadNotes(threadId) {
  try {
    const raw = localStorage.getItem(`pdf_notes_v2:${threadId}`)
    return raw ? JSON.parse(raw) : []
  } catch { return [] }
}

function saveNotes(threadId, notes) {
  try {
    localStorage.setItem(`pdf_notes_v2:${threadId}`, JSON.stringify(notes))
  } catch (e) { void e }
}

export default function PdfViewer({
  url,
  documentId,
  backendUrl,
  userId,
  initialPage = 1,
  onClose,
  threadId,
  pdfWidth,
  style,
}) {
  const [numPages, setNumPages] = useState(null)
  const [pageNumber, setPageNumber] = useState(Number(initialPage) || 1)
  const [scale, setScale] = useState(1.2)
  const [notes, setNotes] = useState(() => loadNotes(threadId))
  const [selectedText, setSelectedText] = useState('')
  const [selectedPage, setSelectedPage] = useState(Number(initialPage) || 1)
  const [question, setQuestion] = useState('')
  const [asking, setAsking] = useState(false)
  const [pdfBlobUrl, setPdfBlobUrl] = useState(null)
  const [pdfDataError, setPdfDataError] = useState(null)
  const [pdfLoadError, setPdfLoadError] = useState(null)
  const docContainerRef = useRef(null)
  const blobUrlRef = useRef(null)
  const indexedDocumentId = /^\d+$/.test(String(documentId || '')) ? Number(documentId) : null

  useEffect(() => {
    setNotes(loadNotes(threadId))
    setSelectedText('')
    setQuestion('')
  }, [threadId])

  useEffect(() => {
    if (!url) return
    let cancelled = false
    setPdfBlobUrl(null)
    setPdfDataError(null)
    // revoke previous blob URL
    if (blobUrlRef.current) URL.revokeObjectURL(blobUrlRef.current)
    async function loadPdf() {
      try {
        const resp = await fetch(url)
        if (!resp.ok) throw new Error(`HTTP ${resp.status}: ${resp.statusText}`)
        const blob = await resp.blob()
        const objUrl = URL.createObjectURL(blob)
        blobUrlRef.current = objUrl
        if (!cancelled) setPdfBlobUrl(objUrl)
      } catch (err) {
        if (!cancelled) setPdfDataError(err?.message || String(err))
      }
    }
    loadPdf()
    return () => { cancelled = true }
  }, [url])

  useEffect(() => {
    return () => {
      if (blobUrlRef.current) URL.revokeObjectURL(blobUrlRef.current)
    }
  }, [])

  useEffect(() => {
    saveNotes(threadId, notes)
  }, [notes, threadId])

  const handleTextSelection = useCallback(() => {
    setTimeout(() => {
      const sel = window.getSelection()
      const text = sel?.toString()?.trim()
      if (text && text.length > 0) {
        setSelectedText(text)
        setSelectedPage(pageNumber)
      }
    }, 100)
  }, [pageNumber])

  function changePage(delta) {
    setPageNumber(prev => {
      const next = prev + delta
      if (!numPages) return prev
      return Math.max(1, Math.min(next, numPages))
    })
  }

  function changeScale(delta) {
    setScale(prev => Math.max(0.5, Math.min(3, +(prev + delta).toFixed(1))))
  }

  function handleWheel(e) {
    if (e.ctrlKey || e.metaKey) return
    const target = e.currentTarget
    const atTop = target.scrollTop <= 2
    const atBottom = target.scrollTop + target.clientHeight >= target.scrollHeight - 2
    if (e.deltaY > 0 && atBottom) {
      e.preventDefault()
      changePage(1)
    } else if (e.deltaY < 0 && atTop) {
      e.preventDefault()
      changePage(-1)
    }
  }

  async function askAboutSelection() {
    if (!question.trim() || asking) return
    setAsking(true)
    const q = question.trim()
    const selectionText = String(selectedText || '').trim()
    const selectionPage = Number(selectedPage || pageNumber || 1)
    setQuestion('')
    const tempNote = {
      id: Date.now(),
      page: selectionText ? selectionPage : null,
      selectedText: selectionText,
      question: q,
      answer: '',
      created_at: new Date().toISOString(),
      streaming: true,
    }
    setNotes(prev => [tempNote, ...prev])

    try {
      let fullAnswer = ''
      await chatStreamApi(backendUrl, {
        user_id: userId || 'user1',
        session_id: `pdf_note_${documentId}`,
        use_retrieval: Boolean(indexedDocumentId),
        document_id: indexedDocumentId || undefined,
        messages: [{
          role: 'user',
          content: selectionText
            ? `以下是我从 PDF 第 ${selectionPage} 页选中的文本：\n\n"""\n${selectionText}\n"""\n\n我的问题是：${q}\n\n请把选中文本作为重点上下文，同时优先结合这个 PDF 已解析入库的页码文本回答，并在能确定时说明依据页码。`
            : `我的问题是：${q}\n\n请阅读并检索这份 PDF 已解析入库的全文页码文本来回答；如果资料中找不到，请明确说“资料中未找到”。回答时在能确定的地方说明依据页码。`,
        }],
      }, {
        onDelta: (_delta, fullText) => {
          fullAnswer = fullText
          setNotes(prev => prev.map(n => n.id === tempNote.id ? { ...n, answer: fullText, streaming: true } : n))
        },
      })
      setNotes(prev => prev.map(n => n.id === tempNote.id ? { ...n, answer: fullAnswer, streaming: false } : n))
    } catch (err) {
      setNotes(prev => prev.map(n => n.id === tempNote.id ? { ...n, answer: '请求失败: ' + (err?.message || err), streaming: false } : n))
    } finally {
      setAsking(false)
      setSelectedText('')
    }
  }

  function deleteNote(noteId) {
    setNotes(prev => prev.filter(n => n.id !== noteId))
  }

  return (
    <div className="pdf-inline-viewer" style={style}>
      <div className="pdf-inline-toolbar">
        <div className="pdf-inline-pages">
          <button className="pdf-inline-btn" onClick={() => changePage(-1)} disabled={pageNumber <= 1}>◂</button>
          <span className="pdf-inline-page-info">
            <input
              className="pdf-inline-page-input"
              type="number"
              min={1}
              max={numPages || 1}
              value={pageNumber}
              onChange={e => {
                const v = parseInt(e.target.value, 10)
                if (v >= 1 && numPages && v <= numPages) setPageNumber(v)
              }}
            />
            <span> / {numPages || '?'}</span>
          </span>
          <button className="pdf-inline-btn" onClick={() => changePage(1)} disabled={!numPages || pageNumber >= numPages}>▸</button>
        </div>
        <div className="pdf-inline-zoom">
          <button className="pdf-inline-btn" onClick={() => changeScale(-0.1)} disabled={scale <= 0.5}>−</button>
          <span className="pdf-inline-scale">{Math.round(scale * 100)}%</span>
          <button className="pdf-inline-btn" onClick={() => changeScale(0.1)} disabled={scale >= 3}>+</button>
        </div>
        <button className="pdf-inline-close-btn" onClick={onClose} title="关闭 PDF">×</button>
      </div>

      <div className="pdf-inline-body">
        <div className="pdf-inline-doc" ref={docContainerRef} onWheel={handleWheel} onMouseUp={handleTextSelection}>
          {pdfDataError && <div className="pdf-inline-status error">获取PDF数据失败: {pdfDataError}</div>}
          {pdfLoadError && <div className="pdf-inline-status error">PDF 解析失败: {pdfLoadError}</div>}
          {!pdfBlobUrl && !pdfDataError && <div className="pdf-inline-status">获取 PDF 数据...</div>}
          {pdfBlobUrl && !pdfLoadError && (
          <Document
            file={pdfBlobUrl}
            onLoadSuccess={({ numPages: n }) => { setNumPages(n); setPageNumber(prev => Math.min(prev, n)) }}
            onLoadError={(err) => { setPdfLoadError(err?.message || String(err)) }}
            loading={<div className="pdf-inline-status">加载 PDF...</div>}
            error={<div className="pdf-inline-status error">PDF 加载失败</div>}
          >
            <Page
              pageNumber={pageNumber}
              scale={scale}
              renderTextLayer={true}
              renderAnnotationLayer={false}
              loading={<div className="pdf-inline-status">渲染页面...</div>}
              error={<div className="pdf-inline-status error">页面渲染失败</div>}
            />
          </Document>
          )}
        </div>

        <div className="pdf-inline-chat">
          <div className="pdf-inline-chat-header">
            <span>PDF 笔记</span>
            <span className="pdf-inline-chat-count">{notes.length > 0 ? `${notes.length} 条笔记` : ''}</span>
          </div>
          <div className="pdf-inline-chat-notes">
            {notes.length === 0 && (
              <div className="pdf-inline-chat-empty">可以直接问整份 PDF；选中文字后会自动作为额外上下文</div>
            )}
            {notes.map(note => (
              <div key={note.id} className={`pdf-inline-note-card${note.streaming ? ' streaming' : ''}`}>
                <div className="pdf-inline-note-meta">
                  <span>{note.page ? `第 ${note.page} 页选区` : '全文 PDF'}</span>
                  <button className="pdf-inline-note-delete" onClick={() => deleteNote(note.id)} title="删除笔记">×</button>
                </div>
                {note.selectedText && (
                  <div className="pdf-inline-note-selected">
                    <span className="pdf-inline-note-label">选中文本:</span>
                    <span>{note.selectedText.slice(0, 200)}{note.selectedText.length > 200 ? '...' : ''}</span>
                  </div>
                )}
                <div className="pdf-inline-note-question">
                  <span className="pdf-inline-note-label">问题:</span>
                  <span>{note.question}</span>
                </div>
                {note.answer && (
                  <div className="pdf-inline-note-answer">
                    <span className="pdf-inline-note-label">AI 回答:</span>
                    <span>{note.answer}</span>
                  </div>
                )}
                {note.streaming && <div className="pdf-inline-note-loading">AI 正在回答...</div>}
              </div>
            ))}
          </div>

          <div className="pdf-inline-chat-input-area">
            {selectedText ? (
              <div className="pdf-inline-selected-preview">
                <span className="pdf-inline-note-label">已选中 (第 {selectedPage} 页):</span>
                <span className="pdf-inline-selected-text">{selectedText.slice(0, 150)}{selectedText.length > 150 ? '...' : ''}</span>
              </div>
            ) : (
              <div className="pdf-inline-selected-preview">
                <span className="pdf-inline-note-label">全文 PDF:</span>
                <span className="pdf-inline-selected-text">未选择文字，将按整份 PDF 的解析文本提问</span>
              </div>
            )}
            <div className="pdf-inline-chat-input-row">
              <input
                className="pdf-inline-chat-input"
                value={question}
                onChange={e => setQuestion(e.target.value)}
                onKeyDown={e => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); askAboutSelection() } }}
                placeholder={selectedText ? '对此文本提问... (Enter 发送)' : '问整份 PDF... (Enter 发送)'}
                disabled={asking}
              />
              <button className="pdf-inline-chat-send" onClick={askAboutSelection} disabled={asking || !question.trim()}>发送</button>
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}
