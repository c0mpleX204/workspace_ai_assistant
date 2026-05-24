import React, { useState } from 'react'

export function lineOffset(text, line) {
  const target = Math.max(1, Number(line || 1))
  if (target <= 1) return 0
  let index = 0
  for (let current = 1; current < target; current += 1) {
    const next = String(text || '').indexOf('\n', index)
    if (next < 0) return String(text || '').length
    index = next + 1
  }
  return index
}

export function countTextLines(text) {
  if (!text) return 0
  return String(text).replace(/\r\n/g, '\n').replace(/\r/g, '\n').split('\n').length
}

export function compactOneLine(text, max = 42) {
  const value = String(text || '').replace(/\s+/g, ' ').trim()
  return value.length > max ? value.slice(0, max - 1) + '…' : value
}

export function findWorkspaceNode(items, path) {
  for (const item of items || []) {
    if (item.path === path) return item
    if (item.type === 'directory') {
      const found = findWorkspaceNode(item.children || [], path)
      if (found) return found
    }
  }
  return null
}

export function collectWorkspaceFiles(node, out = []) {
  if (!node) return out
  if (node.type === 'file') {
    out.push(node)
    return out
  }
  for (const child of node.children || []) collectWorkspaceFiles(child, out)
  return out
}

export function FileTreeNode({ item, depth = 0, activePath, openFile }) {
  const isDirectory = item.type === 'directory'
  const children = Array.isArray(item.children) ? item.children : []
  const [expanded, setExpanded] = useState(depth < 1)

  return (
    <div className="workspace-file-node">
      <button
        type="button"
        className={`workspace-file-row${isDirectory ? ' directory' : ' file'}${activePath === item.path ? ' active' : ''}`}
        style={{ paddingLeft: 8 + depth * 14 }}
        onClick={() => {
          if (isDirectory) {
            setExpanded(v => !v)
          } else {
            openFile(item)
          }
        }}
        title={item.path || item.name}
      >
        <span className="workspace-file-icon">{isDirectory ? (expanded ? '▾' : '▸') : '•'}</span>
        <span className="workspace-file-name">{item.name}</span>
      </button>
      {isDirectory && expanded && children.length > 0 && (
        <div className="workspace-file-children">
          {children.map(child => (
            <FileTreeNode
              key={`${child.type}:${child.path}`}
              item={child}
              depth={depth + 1}
              activePath={activePath}
              openFile={openFile}
            />
          ))}
        </div>
      )}
    </div>
  )
}

export function AttachTreeNode({ item, depth = 0, selectedPaths, toggleAttach }) {
  const isDirectory = item.type === 'directory'
  const children = Array.isArray(item.children) ? item.children : []
  const [expanded, setExpanded] = useState(depth < 1)
  const checked = selectedPaths.has(item.path)

  return (
    <div className="attach-tree-node">
      <div className={`attach-tree-row${checked ? ' selected' : ''}`} style={{ paddingLeft: 8 + depth * 14 }}>
        <button
          type="button"
          className="attach-tree-toggle"
          onClick={() => isDirectory && setExpanded(v => !v)}
          title={isDirectory ? (expanded ? '收起' : '展开') : ''}
        >
          {isDirectory ? (expanded ? '▾' : '▸') : '•'}
        </button>
        <input
          type="checkbox"
          checked={checked}
          onChange={() => toggleAttach(item)}
          onClick={e => e.stopPropagation()}
        />
        <button
          type="button"
          className="attach-tree-name"
          onClick={() => toggleAttach(item)}
          title={item.path || item.name}
        >
          <span className="attach-tree-kind">{isDirectory ? '文件夹' : '文件'}</span>
          <span>{item.name}</span>
        </button>
      </div>
      {isDirectory && expanded && children.length > 0 && (
        <div className="attach-tree-children">
          {children.map(child => (
            <AttachTreeNode
              key={`${child.type}:${child.path}`}
              item={child}
              depth={depth + 1}
              selectedPaths={selectedPaths}
              toggleAttach={toggleAttach}
            />
          ))}
        </div>
      )}
    </div>
  )
}
