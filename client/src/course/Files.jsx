import React, { useState, useCallback, useRef, useEffect } from 'react'

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

export function FileTreeNode({ item, depth = 0, activePath, openFile, onCreateFile, onCreateFolder, onDelete, onRename }) {
  const isDirectory = item.type === 'directory'
  const children = Array.isArray(item.children) ? item.children : []
  const [expanded, setExpanded] = useState(depth < 1)
  const [contextMenu, setContextMenu] = useState(null)
  const [renaming, setRenaming] = useState(false)
  const [renameValue, setRenameValue] = useState('')
  const [creating, setCreating] = useState(null) // 'file' | 'folder' | null
  const [createValue, setCreateValue] = useState('')
  const renameInputRef = useRef(null)
  const createInputRef = useRef(null)
  const renameGuardRef = useRef(false)
  const createGuardRef = useRef(false)

  const closeContextMenu = useCallback(() => setContextMenu(null), [])

  useEffect(() => {
    if (renaming && renameInputRef.current) renameInputRef.current.focus()
  }, [renaming])

  useEffect(() => {
    if (creating && createInputRef.current) createInputRef.current.focus()
  }, [creating])

  const handleContextMenu = (e) => {
    e.preventDefault()
    e.stopPropagation()
    setContextMenu({ x: e.clientX, y: e.clientY })
  }

  const handleRenameStart = () => {
    setRenameValue(item.name)
    setRenaming(true)
    setContextMenu(null)
  }

  const handleRenameConfirm = () => {
    if (renameGuardRef.current) return
    renameGuardRef.current = true
    const val = renameValue.trim()
    setRenaming(false)
    if (val && val !== item.name && onRename) {
      onRename(item, val)
    }
    renameGuardRef.current = false
  }

  const handleRenameCancel = () => {
    if (renameGuardRef.current) return
    setRenaming(false)
  }

  const handleCreateStart = (type) => {
    setExpanded(true)
    setCreating(type)
    setCreateValue('')
    setContextMenu(null)
  }

  const handleCreateConfirm = () => {
    if (createGuardRef.current) return
    createGuardRef.current = true
    const type = creating
    const val = createValue.trim()
    setCreating(null)
    if (!val || !type) { createGuardRef.current = false; return }
    const parentPath = item.path || ''
    if (type === 'file' && onCreateFile) {
      onCreateFile(parentPath, val)
    } else if (type === 'folder' && onCreateFolder) {
      onCreateFolder(parentPath, val)
    }
    createGuardRef.current = false
  }

  const handleCreateCancel = () => {
    if (createGuardRef.current) return
    setCreating(null)
  }

  const handleDelete = () => {
    setContextMenu(null)
    if (onDelete) onDelete(item)
  }

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
        onContextMenu={handleContextMenu}
        title={item.path || item.name}
      >
        <span className="workspace-file-icon">{isDirectory ? (expanded ? '▾' : '▸') : '•'}</span>
        {renaming ? (
          <input
            ref={renameInputRef}
            className="workspace-inline-input"
            value={renameValue}
            onChange={e => setRenameValue(e.target.value)}
            onBlur={handleRenameCancel}
            onKeyDown={e => {
              if (e.key === 'Enter') handleRenameConfirm()
              if (e.key === 'Escape') { setRenaming(false); renameGuardRef.current = false }
            }}
            onClick={e => e.stopPropagation()}
            onContextMenu={e => e.stopPropagation()}
          />
        ) : (
          <span className="workspace-file-name">{item.name}</span>
        )}
      </button>

      {isDirectory && expanded && (
        <div className="workspace-file-children">
          {children.map(child => (
            <FileTreeNode
              key={`${child.type}:${child.path}`}
              item={child}
              depth={depth + 1}
              activePath={activePath}
              openFile={openFile}
              onCreateFile={onCreateFile}
              onCreateFolder={onCreateFolder}
              onDelete={onDelete}
              onRename={onRename}
            />
          ))}
          {creating && (
            <div className="workspace-file-node">
              <div className="workspace-file-row creating" style={{ paddingLeft: 8 + (depth + 1) * 14 }}>
                <span className="workspace-file-icon">{creating === 'folder' ? '▸' : '•'}</span>
                <input
                  ref={createInputRef}
                  className="workspace-inline-input"
                  value={createValue}
                  placeholder={creating === 'file' ? '新建文件...' : '新建文件夹...'}
                  onChange={e => setCreateValue(e.target.value)}
                  onBlur={handleCreateCancel}
                  onKeyDown={e => {
                    if (e.key === 'Enter') handleCreateConfirm()
                    if (e.key === 'Escape') { setCreating(null); createGuardRef.current = false }
                  }}
                />
              </div>
            </div>
          )}
        </div>
      )}

      {contextMenu && (
        <>
          <div className="context-menu-backdrop" onClick={closeContextMenu} onContextMenu={e => { e.preventDefault(); closeContextMenu() }} />
          <div className="context-menu" style={{ left: contextMenu.x, top: contextMenu.y }}>
            {isDirectory && (
              <>
                <button className="context-menu-item" onClick={() => handleCreateStart('file')}>新建文件</button>
                <button className="context-menu-item" onClick={() => handleCreateStart('folder')}>新建文件夹</button>
                <div className="context-menu-divider" />
              </>
            )}
            <button className="context-menu-item" onClick={handleRenameStart}>重命名</button>
            <div className="context-menu-divider" />
            <button className="context-menu-item danger" onClick={handleDelete}>删除</button>
          </div>
        </>
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
