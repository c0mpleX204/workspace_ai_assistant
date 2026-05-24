import { useCallback, useRef, useState } from 'react'

export function useSpeechInput(backendUrl, selectedAudioInput) {
  const [listening, setListening] = useState(false)
  const mediaRecorderRef = useRef(null)
  const chunksRef = useRef([])
  const streamRef = useRef(null)

  const startListening = useCallback(async (onResult, onError) => {
    try {
      const constraints = { audio: selectedAudioInput ? { deviceId: { exact: selectedAudioInput } } : true }
      const stream = await navigator.mediaDevices.getUserMedia(constraints)
      streamRef.current = stream
      chunksRef.current = []
      const recorder = new MediaRecorder(stream)
      mediaRecorderRef.current = recorder
      recorder.ondataavailable = (event) => {
        if (event.data.size > 0) chunksRef.current.push(event.data)
      }
      recorder.onstop = async () => {
        stream.getTracks().forEach(track => track.stop())
        const blob = new Blob(chunksRef.current, { type: 'audio/webm' })
        try {
          const form = new FormData()
          form.append('file', blob, 'audio.webm')
          const base = backendUrl || 'http://127.0.0.1:8000'
          const res = await fetch(base + '/stt', { method: 'POST', body: form })
          if (!res.ok) throw new Error(await res.text())
          const data = await res.json()
          onResult?.(data.text || '')
        } catch (err) {
          onError?.('语音识别失败: ' + err.message)
        }
        setListening(false)
      }
      recorder.start()
      setListening(true)
    } catch (err) {
      onError?.('麦克风权限被拒绝或不可用: ' + err.message)
      setListening(false)
    }
  }, [backendUrl, selectedAudioInput])

  const stopListening = useCallback(() => {
    if (mediaRecorderRef.current && mediaRecorderRef.current.state !== 'inactive') {
      mediaRecorderRef.current.stop()
    } else {
      streamRef.current?.getTracks().forEach(track => track.stop())
      setListening(false)
    }
  }, [])

  return { listening, startListening, stopListening }
}
