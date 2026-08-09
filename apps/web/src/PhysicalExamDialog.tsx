import { useEffect, useState } from 'react'

import { PhysicalExamResult } from './api/client'

function fileSize(bytes: number) {
  if (bytes < 1024 * 1024) return `${Math.max(1, Math.round(bytes / 1024))} KB`
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`
}

export function PhysicalExamDialog({
  result,
  open,
  onClose,
}: {
  result: PhysicalExamResult | null
  open: boolean
  onClose: () => void
}) {
  const [selectedImage, setSelectedImage] = useState('')

  useEffect(() => {
    if (open && result) setSelectedImage(result.images[0]?.content_url ?? '')
  }, [open, result])

  useEffect(() => {
    if (!open) return undefined
    function handleKeyDown(event: KeyboardEvent) {
      if (event.key === 'Escape') onClose()
    }
    globalThis.addEventListener('keydown', handleKeyDown)
    return () => globalThis.removeEventListener('keydown', handleKeyDown)
  }, [open, onClose])

  if (!open || !result) return null

  return (
    <div className="physical-exam-dialog__backdrop" onMouseDown={onClose}>
      <section
        className="physical-exam-dialog"
        role="dialog"
        aria-modal="true"
        aria-labelledby="physical-exam-dialog-title"
        onMouseDown={(event) => event.stopPropagation()}
      >
        <header>
          <div>
            <span>检查记录</span>
            <h2 id="physical-exam-dialog-title">口腔体格检查所见</h2>
          </div>
          <button type="button" onClick={onClose} aria-label="关闭体格检查结果" autoFocus>×</button>
        </header>
        <div className="physical-exam-dialog__content">
          <section>
            <h3>文字所见</h3>
            <p className="physical-exam-findings">{result.findings_text}</p>
          </section>
          {result.images.length > 0 && (
            <section>
              <h3>检查图片（{result.images.length}）</h3>
              {selectedImage && (
                <a
                  className="physical-exam-dialog__preview"
                  href={selectedImage}
                  target="_blank"
                  rel="noreferrer"
                  aria-label="在新窗口查看原图"
                >
                  <img src={selectedImage} alt="当前口腔体格检查图片" />
                </a>
              )}
              <div className="physical-exam-dialog__thumbnails">
                {result.images.map((item, index) => (
                  <button
                    className={selectedImage === item.content_url ? 'is-selected' : ''}
                    type="button"
                    key={item.id}
                    onClick={() => setSelectedImage(item.content_url)}
                    aria-label={`查看检查图片 ${index + 1}：${item.filename}`}
                  >
                    <img src={item.content_url} alt="" />
                  </button>
                ))}
              </div>
            </section>
          )}
          {result.attachments.length > 0 && (
            <section>
              <h3>附件（{result.attachments.length}）</h3>
              <div className="physical-exam-attachments">
                {result.attachments.map((item) => (
                  <a href={item.content_url} key={item.id} download>
                    <span>{item.filename}</span>
                    <small>{fileSize(item.size_bytes)} · 下载查看</small>
                  </a>
                ))}
              </div>
            </section>
          )}
        </div>
      </section>
    </div>
  )
}
