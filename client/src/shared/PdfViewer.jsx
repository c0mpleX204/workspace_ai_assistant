import React, { useState } from 'react'
import { Document, Page, pdfjs } from 'react-pdf'

pdfjs.GlobalWorkerOptions.workerSrc = new URL(
  'pdfjs-dist/build/pdf.worker.min.mjs',
  import.meta.url,
).toString()

export default function PdfViewer({ url, initialPage = 1 }) {
  const [numPages, setNumPages] = useState(null)
  const [pageNumber, setPageNumber] = useState(Number(initialPage) || 1)
  const [scale, setScale] = useState(1.2)

  function onDocumentLoadSuccess({ numPages: nextNumPages }) {
    setNumPages(nextNumPages)
    const clamped = Math.max(1, Math.min(Number(initialPage) || 1, nextNumPages))
    setPageNumber(clamped)
  }

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

  return (
    <div className="pdf-viewer">
      <div className="pdf-viewer-toolbar">
        <div className="pdf-viewer-pages">
          <button className="pdf-viewer-btn" onClick={() => changePage(-1)} disabled={pageNumber <= 1}>◂</button>
          <span className="pdf-viewer-page-info">
            <input
              className="pdf-viewer-page-input"
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
          <button className="pdf-viewer-btn" onClick={() => changePage(1)} disabled={!numPages || pageNumber >= numPages}>▸</button>
        </div>
        <div className="pdf-viewer-zoom">
          <button className="pdf-viewer-btn" onClick={() => changeScale(-0.1)} disabled={scale <= 0.5}>−</button>
          <span className="pdf-viewer-scale">{Math.round(scale * 100)}%</span>
          <button className="pdf-viewer-btn" onClick={() => changeScale(0.1)} disabled={scale >= 3}>+</button>
        </div>
      </div>
      <div className="pdf-viewer-canvas">
        <Document
          file={url}
          onLoadSuccess={onDocumentLoadSuccess}
          loading={<div className="pdf-viewer-status">加载 PDF...</div>}
          error={<div className="pdf-viewer-status error">PDF 加载失败</div>}
        >
          <Page
            pageNumber={pageNumber}
            scale={scale}
            renderTextLayer={false}
            renderAnnotationLayer={false}
            loading={<div className="pdf-viewer-status">渲染页面...</div>}
            error={<div className="pdf-viewer-status error">页面渲染失败</div>}
          />
        </Document>
      </div>
    </div>
  )
}
