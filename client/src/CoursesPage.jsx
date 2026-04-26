import React, { useState, useEffect } from 'react'
import { listCoursesApi, createCourseApi, deleteCourseApi, getMaterialViewUrl } from './api'

export default function CoursesPage({ backendUrl, userId, onEnterCourse, showToast }) {
  const [courses, setCourses] = useState([])
  const [creating, setCreating] = useState(false)
  const [newName, setNewName] = useState('')
  const [newTerm, setNewTerm] = useState('')
  const [loading, setLoading] = useState(false)

  useEffect(() => { fetchCourses() }, [])

  async function fetchCourses() {
    try {
      const res = await listCoursesApi(backendUrl, userId)
      setCourses(res.items || [])
    } catch (e) {
      showToast('获取课程失败: ' + e.message, 'error')
    }
  }

  async function handleCreate(e) {
    e.preventDefault()
    if (!newName.trim()) return
    setLoading(true)
    try {
      await createCourseApi(backendUrl, { name: newName.trim(), term: newTerm.trim() || null, owner_id: userId })
      setNewName('')
      setNewTerm('')
      setCreating(false)
      showToast('课程已创建', 'success')
      fetchCourses()
    } catch (e) {
      showToast('创建失败: ' + e.message, 'error')
    } finally {
      setLoading(false)
    }
  }

  async function handleDelete(courseId, name) {
    if (!window.confirm(`确认删除课程「${name}」及其所有资料？`)) return
    try {
      await deleteCourseApi(backendUrl, courseId)
      showToast('已删除', 'success')
      fetchCourses()
    } catch (e) {
      showToast('删除失败: ' + e.message, 'error')
    }
  }

  return (
    <div className="courses-page">
      <div className="courses-header">
        <h2 className="courses-title">我的课程</h2>
        <button className="btn-primary" onClick={() => setCreating(true)}>+ 新建课程</button>
      </div>

      {creating && (
        <div className="course-create-modal-bg" onClick={() => setCreating(false)}>
          <form className="course-create-modal" onClick={e => e.stopPropagation()} onSubmit={handleCreate}>
            <div className="modal-title">新建课程</div>
            <input
              className="field-input"
              placeholder="课程名称（必填）"
              value={newName}
              onChange={e => setNewName(e.target.value)}
              autoFocus
            />
            <input
              className="field-input"
              placeholder="学期（选填，如 2024秋）"
              value={newTerm}
              onChange={e => setNewTerm(e.target.value)}
            />
            <div className="modal-actions">
              <button type="button" className="ghost-btn" onClick={() => setCreating(false)}>取消</button>
              <button type="submit" className="btn-primary" disabled={loading || !newName.trim()}>{loading ? '创建中…' : '创建'}</button>
            </div>
          </form>
        </div>
      )}

      {courses.length === 0 && (
        <div className="courses-empty">
          <div className="courses-empty-icon">📚</div>
          <p>还没有课程</p>
          <span style={{color:'var(--text-muted)',fontSize:'13px'}}>点击右上角「新建课程」开始添加</span>
        </div>
      )}

      <div className="courses-grid">
        {courses.map(c => (
          <div key={c.course_id} className="course-card" onClick={() => onEnterCourse(c)}>
            <div className="course-card-cover">
              {c.cover_document_id
                ? <img src={`${getMaterialViewUrl(backendUrl, c.cover_document_id)}?thumb=1`} alt="" onError={e => e.target.style.display='none'} />
                : <div className="course-card-cover-placeholder">📄</div>
              }
            </div>
            <div className="course-card-body">
              <div className="course-card-name">{c.name}</div>
              <div className="course-card-meta">
                {c.term && <span>{c.term}</span>}
                <span>{c.doc_count} 份资料</span>
              </div>
            </div>
            <button
              className="course-card-del"
              title="删除课程"
              onClick={e => { e.stopPropagation(); handleDelete(c.course_id, c.name) }}
            >×</button>
          </div>
        ))}
      </div>
    </div>
  )
}
