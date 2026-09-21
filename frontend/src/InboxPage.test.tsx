import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor, fireEvent } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import InboxPage from './InboxPage';
import { api, ConversationDTO, ConversationDetailDTO, MessageDTO } from './api';

// Mock api
vi.mock('./api', async () => {
  const actual = await vi.importActual<typeof import('./api')>('./api');
  return {
    ...actual,
    api: {
      getConversations: vi.fn(),
      getConversation: vi.fn(),
      getConversationMessages: vi.fn(),
      sendConversationMessage: vi.fn(),
      updateConversationMode: vi.fn(),
      markConversationRead: vi.fn(),
      retryConversationMessage: vi.fn(),
      getGroupMembers: vi.fn(),
      isAuthenticated: vi.fn().mockReturnValue(true),
    },
  };
});

const mockConversations: ConversationDTO[] = [
  {
    id: 1,
    type: 'dm',
    mode: 'auto',
    signal_id: '+420111222333',
    display_name: 'Alice Cooper',
    group_id: null,
    unread_count: 2,
    is_blocked: false,
    is_active: true,
    message_count: 5,
    has_failed_outbound: false,
    last_message: 'Hi there, how are you?',
    last_message_at: '2026-09-21T10:00:00Z',
    created_at: '2026-09-20T10:00:00Z',
    updated_at: '2026-09-21T10:00:00Z',
  },
  {
    id: 2,
    type: 'group',
    mode: 'manual',
    signal_id: 'group.vip123',
    display_name: 'VIP Market Group',
    group_id: 'group.vip123',
    unread_count: 0,
    is_blocked: false,
    is_active: true,
    message_count: 12,
    has_failed_outbound: false,
    last_message: 'Admin: Special discount today',
    last_message_at: '2026-09-21T09:30:00Z',
    created_at: '2026-09-19T10:00:00Z',
    updated_at: '2026-09-21T09:30:00Z',
  },
];

const mockDetailConv1: ConversationDetailDTO = {
  ...mockConversations[0],
  dm_user_id: 101,
  phone_number: '+420111222333',
  signal_uuid: 'uuid-alice-123',
  members_count: 1,
  admins_count: 0,
};

const mockMessagesConv1: MessageDTO[] = [
  {
    id: 10,
    conversation_id: 1,
    direction: 'inbound',
    actor: 'customer',
    role: 'user',
    sender_name: 'Alice Cooper',
    sender_id: '+420111222333',
    content: 'Hi there, how are you?',
    delivery_status: 'received',
    timestamp: '2026-09-21T10:00:00Z',
    attachments: [],
    reactions: [],
  },
];

describe('InboxPage Component', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    (api.getConversations as any).mockResolvedValue({
      items: mockConversations,
      total: 2,
      unread_conversations: 1,
      total_unread_messages: 2,
    });
    (api.getConversation as any).mockResolvedValue(mockDetailConv1);
    (api.getConversationMessages as any).mockResolvedValue({
      items: mockMessagesConv1,
      total: 1,
      has_more_before: false,
      has_more_after: false,
    });
    (api.markConversationRead as any).mockResolvedValue({
      ok: true,
      conversation_id: 1,
      last_read_message_id: 10,
    });
  });

  it('renders conversation list with unread badge and display names', async () => {
    render(
      <MemoryRouter>
        <InboxPage />
      </MemoryRouter>
    );

    // Verify conversation names are rendered
    await waitFor(() => {
      expect(screen.getByText('Alice Cooper')).toBeInTheDocument();
      expect(screen.getByText('VIP Market Group')).toBeInTheDocument();
    });

    // Unread count 2 should be displayed
    expect(screen.getByText('2')).toBeInTheDocument();
    // Mode badges
    expect(screen.getAllByText(/Auto/i).length).toBeGreaterThanOrEqual(1);
    expect(screen.getAllByText(/Manual/i).length).toBeGreaterThanOrEqual(1);
  });

  it('opens conversation, loads messages, and marks conversation as read', async () => {
    render(
      <MemoryRouter>
        <InboxPage />
      </MemoryRouter>
    );

    await waitFor(() => {
      expect(screen.getByText('Alice Cooper')).toBeInTheDocument();
    });

    // Click on Alice Cooper's conversation
    fireEvent.click(screen.getByText('Alice Cooper'));

    // Should fetch details and messages
    await waitFor(() => {
      expect(api.getConversation).toHaveBeenCalledWith(1);
      expect(api.getConversationMessages).toHaveBeenCalledWith(1, expect.objectContaining({ limit: 50 }));
      expect(api.markConversationRead).toHaveBeenCalledWith(1, 10);
    });

    // Should display the message in the timeline
    expect(screen.getAllByText('Hi there, how are you?').length).toBeGreaterThanOrEqual(1);
  });

  it('handles sending new messages from composer', async () => {
    const sentMessage: MessageDTO = {
      id: 11,
      conversation_id: 1,
      direction: 'outbound',
      actor: 'admin',
      role: 'assistant',
      content: 'Hello Alice, how can I assist you?',
      delivery_status: 'sent',
      timestamp: '2026-09-21T10:05:00Z',
      attachments: [],
      reactions: [],
    };
    (api.sendConversationMessage as any).mockResolvedValue(sentMessage);

    render(
      <MemoryRouter>
        <InboxPage />
      </MemoryRouter>
    );

    await waitFor(() => {
      expect(screen.getByText('Alice Cooper')).toBeInTheDocument();
    });

    fireEvent.click(screen.getByText('Alice Cooper'));

    await waitFor(() => {
      expect(screen.getByPlaceholderText(/Type a manual reply/i)).toBeInTheDocument();
    });

    const textarea = screen.getByPlaceholderText(/Type a manual reply/i);
    fireEvent.change(textarea, { target: { value: 'Hello Alice, how can I assist you?' } });

    const sendBtn = screen.getByRole('button', { name: /Send/i });
    fireEvent.click(sendBtn);

    await waitFor(() => {
      expect(api.sendConversationMessage).toHaveBeenCalledWith(1, 'Hello Alice, how can I assist you?');
      expect(screen.getByText('Hello Alice, how can I assist you?')).toBeInTheDocument();
    });
  });

  it('handles manual takeover mode change', async () => {
    (api.updateConversationMode as any).mockResolvedValue({
      ...mockDetailConv1,
      mode: 'manual',
    });

    render(
      <MemoryRouter>
        <InboxPage />
      </MemoryRouter>
    );

    await waitFor(() => {
      expect(screen.getByText('Alice Cooper')).toBeInTheDocument();
    });

    fireEvent.click(screen.getByText('Alice Cooper'));

    await waitFor(() => {
      expect(screen.getByLabelText('Takeover mode')).toBeInTheDocument();
    });

    // Change selector to manual
    const select = screen.getByLabelText('Takeover mode');
    fireEvent.change(select, { target: { value: 'manual' } });

    await waitFor(() => {
      expect(api.updateConversationMode).toHaveBeenCalledWith(1, 'manual');
    });
  });

  it('displays outbound failure and allows explicit retry', async () => {
    const failedMessage: MessageDTO = {
      id: 999,
      conversation_id: 1,
      direction: 'outbound',
      actor: 'admin',
      role: 'assistant',
      content: 'Important notice',
      delivery_status: 'failed',
      delivery_error: 'Signal Gateway 500 error',
      timestamp: '2026-09-21T10:10:00Z',
      attachments: [],
      reactions: [],
    };
    (api.sendConversationMessage as any).mockResolvedValue(failedMessage);

    const retriedMessage: MessageDTO = {
      ...failedMessage,
      delivery_status: 'sent',
      delivery_error: null,
    };
    (api.retryConversationMessage as any).mockResolvedValue(retriedMessage);

    render(
      <MemoryRouter>
        <InboxPage />
      </MemoryRouter>
    );

    await waitFor(() => {
      expect(screen.getByText('Alice Cooper')).toBeInTheDocument();
    });

    fireEvent.click(screen.getByText('Alice Cooper'));

    await waitFor(() => {
      expect(screen.getByPlaceholderText(/Type a manual reply/i)).toBeInTheDocument();
    });

    const textarea = screen.getByPlaceholderText(/Type a manual reply/i);
    fireEvent.change(textarea, { target: { value: 'Important notice' } });

    const sendBtn = screen.getByRole('button', { name: /Send/i });
    fireEvent.click(sendBtn);

    // Expect message to enter failed state and show Retry button
    await waitFor(() => {
      expect(screen.getByText(/Failed/i)).toBeInTheDocument();
      expect(screen.getByText(/Retry Now/i)).toBeInTheDocument();
    });

    // Click retry
    fireEvent.click(screen.getByText(/Retry Now/i));

    await waitFor(() => {
      expect(api.retryConversationMessage).toHaveBeenCalledWith(1, 999);
      expect(screen.getByText(/Sent/i)).toBeInTheDocument();
    });
  });
});
