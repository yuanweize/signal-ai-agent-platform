import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { InboxAttachmentItem } from './components/InboxAttachmentItem';
import { StreamingCopilotCard } from './components/StreamingCopilotCard';
import type { AttachmentDTO } from './types/inbox';

describe('v0.5.0 Multimodal & Streaming UI Features', () => {
  it('renders image attachment with understood status and expands visual description', () => {
    const imageAttachment: AttachmentDTO = {
      id: 101,
      filename: 'sample_product.jpg',
      mime_type: 'image/jpeg',
      size: 20480,
      processing_status: 'understood',
      extracted_text: 'A high quality blue ergonomic wireless mouse on a wooden desk.',
      processor_model: 'gpt-4o-mini',
      processor_type: 'vision',
    };

    render(<InboxAttachmentItem attachment={imageAttachment} />);

    expect(screen.getByText('sample_product.jpg')).toBeInTheDocument();
    expect(screen.getByText('Understood')).toBeInTheDocument();

    const expandBtn = screen.getByText('View Visual Analysis');
    expect(expandBtn).toBeInTheDocument();

    fireEvent.click(expandBtn);
    expect(
      screen.getByText('A high quality blue ergonomic wireless mouse on a wooden desk.')
    ).toBeInTheDocument();
    expect(screen.getByText(/Model: gpt-4o-mini/)).toBeInTheDocument();

    fireEvent.click(screen.getByText('Hide Visual Analysis'));
    expect(
      screen.queryByText('A high quality blue ergonomic wireless mouse on a wooden desk.')
    ).not.toBeInTheDocument();
  });

  it('renders voice note with transcript ready status and expands transcript', () => {
    const voiceAttachment: AttachmentDTO = {
      id: 102,
      filename: 'voice_note_1.ogg',
      mime_type: 'audio/ogg',
      size: 15360,
      processing_status: 'transcript_available',
      extracted_text: 'Hello, I want to inquire about the pricing for bulk orders.',
      processor_model: 'whisper-1',
      processor_type: 'audio',
    };

    render(<InboxAttachmentItem attachment={voiceAttachment} />);

    expect(screen.getByText('voice_note_1.ogg')).toBeInTheDocument();
    expect(screen.getByText('Transcript Ready')).toBeInTheDocument();

    const expandBtn = screen.getByText('View Voice Transcript');
    fireEvent.click(expandBtn);

    expect(
      screen.getByText('Hello, I want to inquire about the pricing for bulk orders.')
    ).toBeInTheDocument();
  });

  it('renders streaming copilot card with live text and calls onCancel', () => {
    const handleCancel = vi.fn();
    const { rerender } = render(
      <StreamingCopilotCard text="Hello, thank you for" onCancel={handleCancel} />
    );

    expect(screen.getByText(/AI Copilot Generating \(Streaming\)/)).toBeInTheDocument();
    expect(screen.getByText(/Hello, thank you for/)).toBeInTheDocument();

    // Rerender with more streamed tokens
    rerender(
      <StreamingCopilotCard
        text="Hello, thank you for reaching out to us today!"
        onCancel={handleCancel}
      />
    );
    expect(
      screen.getByText(/Hello, thank you for reaching out to us today!/)
    ).toBeInTheDocument();

    const cancelBtn = screen.getByRole('button', { name: /Cancel/i });
    fireEvent.click(cancelBtn);
    expect(handleCancel).toHaveBeenCalledTimes(1);
  });
});
