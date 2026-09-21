import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor, fireEvent } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import SettingsPage from './SettingsPage';
import { api } from './api';

vi.mock('./api', async () => {
  const actual = await vi.importActual<typeof import('./api')>('./api');
  return {
    ...actual,
    api: {
      getSettings: vi.fn(),
      updateSettings: vi.fn(),
      getAuditLogs: vi.fn(),
      testSignalConnection: vi.fn(),
      probeAiCompatibility: vi.fn(),
      verifyAiModel: vi.fn(),
      cleanupData: vi.fn(),
      rollbackSettings: vi.fn(),
      isAuthenticated: vi.fn().mockReturnValue(true),
    },
  };
});

const mockSettings = {
  bot_name: 'ProductionBot',
  bot_default_language: 'cs',
  signal_api_url: 'http://127.0.0.1:8080',
  signal_phone_number: '+420123456789',
  signal_api_token_masked: 'tok_***99',
  has_signal_api_token: true,
  ai_prompt: 'You are an intelligent shopping assistant.',
  is_ai_enabled: true,
  is_market_enabled: true,
  ai_api_base_url: 'https://api.openai.com/v1',
  ai_model: 'gpt-4o',
  ai_api_key_masked: 'sk-***abc',
  ai_provider_detected: 'openai',
  ai_models_cached: ['gpt-4o', 'gpt-4o-mini'],
  ai_models_listed_total: 2,
  ai_temperature: 0.7,
  ai_max_tokens: 1000,
  ai_context_messages: 20,
  retention_days: 45,
  ad_automation_enabled: true,
  ad_min_interval_minutes: 120,
  ad_quiet_hour_start: 22,
  ad_quiet_hour_end: 7,
  ad_group_blacklist: ['group.blocked1'],
};

describe('SettingsPage Component', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    (api.getSettings as any).mockResolvedValue(mockSettings);
    (api.getAuditLogs as any).mockResolvedValue({ items: [], total: 0, page: 1, page_size: 15 });
  });

  it('renders general settings and displays loaded values', async () => {
    render(
      <MemoryRouter>
        <SettingsPage />
      </MemoryRouter>
    );

    await waitFor(() => {
      expect(screen.getByDisplayValue('ProductionBot')).toBeInTheDocument();
      expect(screen.getByDisplayValue('cs')).toBeInTheDocument();
      expect(screen.getByDisplayValue('You are an intelligent shopping assistant.')).toBeInTheDocument();
    });
  });

  it('switches between tabs and shows masked secrets', async () => {
    render(
      <MemoryRouter>
        <SettingsPage />
      </MemoryRouter>
    );

    await waitFor(() => {
      expect(screen.getByDisplayValue('ProductionBot')).toBeInTheDocument();
    });

    // Switch to Signal Gateway tab
    fireEvent.click(screen.getByRole('tab', { name: /Signal Gateway/i }));

    await waitFor(() => {
      expect(screen.getByDisplayValue('http://127.0.0.1:8080')).toBeInTheDocument();
      expect(screen.getByDisplayValue('+420123456789')).toBeInTheDocument();
      expect(screen.getByText(/Current: tok_\*\*\*99/i)).toBeInTheDocument();
    });

    // Switch to AI Engine tab
    fireEvent.click(screen.getByRole('tab', { name: /AI Engine/i }));

    await waitFor(() => {
      expect(screen.getByDisplayValue('https://api.openai.com/v1')).toBeInTheDocument();
      expect(screen.getByDisplayValue('gpt-4o')).toBeInTheDocument();
      expect(screen.getByText(/Current: sk-\*\*\*abc/i)).toBeInTheDocument();
    });

    // Switch to Campaign tab
    fireEvent.click(screen.getByRole('tab', { name: /Campaigns/i }));

    await waitFor(() => {
      expect(screen.getByDisplayValue('120')).toBeInTheDocument();
      expect(screen.getByDisplayValue('group.blocked1')).toBeInTheDocument();
    });
  });

  it('saves settings with modified values', async () => {
    (api.updateSettings as any).mockResolvedValue({
      ...mockSettings,
      bot_name: 'RenamedBot',
    });

    render(
      <MemoryRouter>
        <SettingsPage />
      </MemoryRouter>
    );

    await waitFor(() => {
      expect(screen.getByDisplayValue('ProductionBot')).toBeInTheDocument();
    });

    const nameInput = screen.getByDisplayValue('ProductionBot');
    fireEvent.change(nameInput, { target: { value: 'RenamedBot' } });

    const saveBtn = screen.getByRole('button', { name: /Save Settings/i });
    fireEvent.click(saveBtn);

    await waitFor(() => {
      expect(api.updateSettings).toHaveBeenCalledWith(
        expect.objectContaining({
          bot_name: 'RenamedBot',
        })
      );
      expect(screen.getByText('Settings saved successfully!')).toBeInTheDocument();
    });
  });
});
