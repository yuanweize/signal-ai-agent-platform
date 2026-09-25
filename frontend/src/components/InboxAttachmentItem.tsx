import React, { useState } from 'react';
import {
  Paperclip,
  Image as ImageIcon,
  Mic,
  ChevronDown,
  ChevronUp,
  CheckCircle,
  RotateCw,
  AlertCircle,
} from 'lucide-react';
import type { AttachmentDTO } from '../types/inbox';

interface InboxAttachmentItemProps {
  attachment: AttachmentDTO;
}

export const InboxAttachmentItem: React.FC<InboxAttachmentItemProps> = ({ attachment }) => {
  const [expanded, setExpanded] = useState(false);
  const mime = (attachment.mime_type || '').toLowerCase();
  const isImage = mime.startsWith('image/');
  const isAudio = mime.startsWith('audio/');
  const status = attachment.processing_status || 'unsupported';
  const hasExtracted = !!attachment.extracted_text;

  return (
    <div className="rounded-lg bg-[rgba(0,0,0,0.3)] border border-[rgba(255,255,255,0.08)] p-2.5 text-xs space-y-1.5 transition-all">
      <div className="flex items-center justify-between gap-2">
        <div className="flex items-center gap-2 min-w-0">
          {isImage ? (
            <div className="w-5 h-5 rounded bg-indigo-500/20 text-indigo-400 flex items-center justify-center shrink-0">
              <ImageIcon className="w-3 h-3" />
            </div>
          ) : isAudio ? (
            <div className="w-5 h-5 rounded bg-amber-500/20 text-amber-400 flex items-center justify-center shrink-0">
              <Mic className="w-3 h-3" />
            </div>
          ) : (
            <div className="w-5 h-5 rounded bg-white/10 text-[var(--text-muted)] flex items-center justify-center shrink-0">
              <Paperclip className="w-3 h-3" />
            </div>
          )}
          <span className="font-medium truncate text-[var(--text-primary)]">
            {attachment.filename || (isImage ? 'Signal Image' : isAudio ? 'Signal Voice Note' : 'Attachment')}
          </span>
          {attachment.size ? (
            <span className="text-[10px] text-[var(--text-muted)] shrink-0">
              ({Math.round(attachment.size / 1024)} KB)
            </span>
          ) : null}
        </div>

        {/* Multimodal Status Badges */}
        {status === 'understood' && (
          <span className="px-2 py-0.5 rounded-full text-[10px] font-semibold bg-emerald-500/20 text-emerald-400 border border-emerald-500/30 flex items-center gap-1 shrink-0">
            <CheckCircle className="w-2.5 h-2.5" /> Understood
          </span>
        )}
        {status === 'transcript_available' && (
          <span className="px-2 py-0.5 rounded-full text-[10px] font-semibold bg-cyan-500/20 text-cyan-400 border border-cyan-500/30 flex items-center gap-1 shrink-0">
            <Mic className="w-2.5 h-2.5" /> Transcript Ready
          </span>
        )}
        {(status === 'processing' || status === 'pending') && (
          <span className="px-2 py-0.5 rounded-full text-[10px] font-semibold bg-amber-500/20 text-amber-400 border border-amber-500/30 animate-pulse flex items-center gap-1 shrink-0">
            <RotateCw className="w-2.5 h-2.5 animate-spin" /> Processing
          </span>
        )}
        {status === 'failed' && (
          <span
            className="px-2 py-0.5 rounded-full text-[10px] font-semibold bg-red-500/20 text-red-400 border border-red-500/30 flex items-center gap-1 shrink-0"
            title={attachment.processing_error || 'Processing failed'}
          >
            <AlertCircle className="w-2.5 h-2.5" /> Failed
          </span>
        )}
        {status === 'unsupported' && (
          <span className="px-2 py-0.5 rounded-full text-[10px] font-medium bg-white/5 text-[var(--text-muted)] border border-white/10 shrink-0">
            File
          </span>
        )}
      </div>

      {/* Extracted text / transcript collapsible section */}
      {hasExtracted && (
        <div className="pt-1 border-t border-[rgba(255,255,255,0.06)]">
          <button
            type="button"
            onClick={() => setExpanded(!expanded)}
            className="text-[10px] text-[var(--accent-light)] hover:underline flex items-center gap-1 cursor-pointer font-medium"
          >
            <span>
              {isAudio
                ? expanded
                  ? 'Hide Voice Transcript'
                  : 'View Voice Transcript'
                : expanded
                ? 'Hide Visual Analysis'
                : 'View Visual Analysis'}
            </span>
            {expanded ? <ChevronUp className="w-3 h-3" /> : <ChevronDown className="w-3 h-3" />}
          </button>
          {expanded && (
            <div className="mt-1.5 p-2 rounded-lg bg-[rgba(0,0,0,0.45)] border border-[rgba(255,255,255,0.06)] text-[11px] text-[var(--text-secondary)] whitespace-pre-wrap leading-relaxed animate-in fade-in-50">
              <p className="font-sans">{attachment.extracted_text}</p>
              {attachment.processor_model && (
                <div className="mt-1 pt-1 border-t border-[rgba(255,255,255,0.05)] text-[9px] text-[var(--text-muted)] font-mono flex items-center justify-between">
                  <span>Model: {attachment.processor_model}</span>
                  {attachment.processor_type && (
                    <span className="uppercase text-[8px] px-1 py-0.5 rounded bg-white/5">
                      {attachment.processor_type}
                    </span>
                  )}
                </div>
              )}
            </div>
          )}
        </div>
      )}
    </div>
  );
};
