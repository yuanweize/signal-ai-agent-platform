import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor, fireEvent } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import DevicesPage from './DevicesPage';
import { api } from './api';

vi.mock('./api', async () => {
  const actual = await vi.importActual<typeof import('./api')>('./api');
  return {
    ...actual,
    api: {
      getProfile: vi.fn(),
      updateProfile: vi.fn(),
      listDevices: vi.fn(),
      removeDevice: vi.fn(),
      isAuthenticated: vi.fn().mockReturnValue(true),
    },
  };
});

describe('DevicesPage Component', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('renders profile and devices when both API calls succeed', async () => {
    (api.getProfile as any).mockResolvedValue({
      name: 'Signal Bot Pro',
      about: '24/7 AI-powered assistant',
    });
    (api.listDevices as any).mockResolvedValue({
      devices: [
        { id: 1, name: 'Primary Device', created: 1726000000000, lastSeen: 1726900000000 },
      ],
    });

    render(
      <MemoryRouter>
        <DevicesPage />
      </MemoryRouter>
    );

    await waitFor(() => {
      expect(screen.getByDisplayValue('Signal Bot Pro')).toBeInTheDocument();
      expect(screen.getByDisplayValue('24/7 AI-powered assistant')).toBeInTheDocument();
      expect(screen.getByText('Primary Device')).toBeInTheDocument();
      expect(screen.getByText('#1')).toBeInTheDocument();
    });
  });

  it('isolates profile failure: devices still load when profile throws an error', async () => {
    (api.getProfile as any).mockRejectedValue(new Error('Signal profile service unavailable'));
    (api.listDevices as any).mockResolvedValue({
      devices: [
        { id: 2, name: 'Linked Tablet', created: 1726000000, lastSeen: 1726900000 },
      ],
    });

    render(
      <MemoryRouter>
        <DevicesPage />
      </MemoryRouter>
    );

    await waitFor(() => {
      // Profile card shows error banner
      expect(screen.getByText('Signal profile service unavailable')).toBeInTheDocument();
      // Linked devices section still renders correctly
      expect(screen.getByText('Linked Tablet')).toBeInTheDocument();
      expect(screen.getByText('#2')).toBeInTheDocument();
    });
  });

  it('isolates devices failure: profile still loads and can be edited when devices call throws an error', async () => {
    (api.getProfile as any).mockResolvedValue({
      name: 'Bot Operator',
      about: 'Online support',
    });
    (api.listDevices as any).mockRejectedValue(new Error('Device listing endpoint 502'));
    (api.updateProfile as any).mockResolvedValue({ ok: true });

    render(
      <MemoryRouter>
        <DevicesPage />
      </MemoryRouter>
    );

    await waitFor(() => {
      expect(screen.getByDisplayValue('Bot Operator')).toBeInTheDocument();
      expect(screen.getByText('Device listing endpoint 502')).toBeInTheDocument();
    });

    // Edit profile and save
    const nameInput = screen.getByDisplayValue('Bot Operator');
    fireEvent.change(nameInput, { target: { value: 'Updated Bot Operator' } });

    const saveBtn = screen.getByRole('button', { name: /Save Profile/i });
    fireEvent.click(saveBtn);

    await waitFor(() => {
      expect(api.updateProfile).toHaveBeenCalledWith({
        name: 'Updated Bot Operator',
        about: 'Online support',
      });
      expect(screen.getByText('Profile updated successfully')).toBeInTheDocument();
    });
  });
});
