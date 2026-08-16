// 静态附件卡片：按 type 渲染已完成的媒体结果（视频/图片/文本）
// 与 TaskCard（任务状态机）解耦，供历史消息附件与任务完成态复用
import type { Attachment } from '../../types'

interface AttachmentCardProps {
  attachment: Attachment
}

export function AttachmentCard({ attachment }: AttachmentCardProps) {
  switch (attachment.type) {
    case 'video':
      return (
        <div className="attachment-card">
          <video controls src={attachment.url} poster={attachment.poster} />
        </div>
      )
    case 'image':
      return (
        <div className="attachment-card">
          <img src={attachment.url} alt={attachment.alt ?? '图片'} />
        </div>
      )
    case 'text':
      return <div className="attachment-card">{attachment.content ?? ''}</div>
    default:
      return null
  }
}
