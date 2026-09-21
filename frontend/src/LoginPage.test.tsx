import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor, fireEvent } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import LoginPage from './LoginPage';
import { api } from './api';

const mockNavigate = vi.fn();
vi.mock('react-router-dom', async () => {
  const actual = await vi.importActual<typeof import('react-router-dom')>('react-router-dom');
  return {
    ...actual,
    useNavigate: () => mockNavigate,
  };
});

vi.mock('./api', async () => {
  const actual = await vi.importActual<typeof import('./api')>('./api');
  return {
    ...actual,
    api: {
      checkAuth: vi.fn(),
      login: vi.fn(),
      setToken: vi.fn(),
      initBootstrap: vi.fn(),
      isAuthenticated: vi.fn().mockReturnValue(false),
    },
  };
});

describe('LoginPage Component', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    (api.checkAuth as any).mockResolvedValue({
      requires_2fa: true,
      bootstrap_required: false,
    });
  });

  it('renders login form and logs in successfully', async () => {
    (api.login as any).mockResolvedValue({
      access_token: 'fake-jwt-token-123',
      token_type: 'bearer',
    });

    render(
      <MemoryRouter>
        <LoginPage />
      </MemoryRouter>
    );

    await waitFor(() => {
      expect(screen.getByLabelText(/Username/i)).toBeInTheDocument();
      expect(screen.getByLabelText(/Password/i)).toBeInTheDocument();
      expect(screen.getByLabelText(/2FA Code/i)).toBeInTheDocument();
    });

    fireEvent.change(screen.getByLabelText(/Username/i), { target: { value: 'admin' } });
    fireEvent.change(screen.getByLabelText(/Password/i), { target: { value: 'Secret1234!' } });
    fireEvent.change(screen.getByLabelText(/2FA Code/i), { target: { value: '123456' } });

    const submitBtn = screen.getByRole('button', { name: /Login/i });
    fireEvent.click(submitBtn);

    await waitFor(() => {
      expect(api.login).toHaveBeenCalledWith('admin', 'Secret1234!', '123456');
      expect(api.setToken).toHaveBeenCalledWith('fake-jwt-token-123');
      expect(mockNavigate).toHaveBeenCalledWith('/');
    });
  });

  it('displays error message when login fails', async () => {
    (api.login as any).mockRejectedValue(new Error('Invalid credentials or TOTP'));

    render(
      <MemoryRouter>
        <LoginPage />
      </MemoryRouter>
    );

    await waitFor(() => {
      expect(screen.getByLabelText(/Username/i)).toBeInTheDocument();
    });

    fireEvent.change(screen.getByLabelText(/Username/i), { target: { value: 'admin' } });
    fireEvent.change(screen.getByLabelText(/Password/i), { target: { value: 'WrongPass' } });

    const submitBtn = screen.getByRole('button', { name: /Login/i });
    fireEvent.click(submitBtn);

    await waitFor(() => {
      expect(screen.getByText('Invalid credentials or TOTP')).toBeInTheDocument();
    });
  });

  it('shows first-time setup form when bootstrap_required is true', async () => {
    (api.checkAuth as any).mockResolvedValue({
      requires_2fa: false,
      bootstrap_required: true,
    });

    render(
      <MemoryRouter>
        <LoginPage />
      </MemoryRouter>
    );

    await waitFor(() => {
      expect(screen.getByText('First-time setup')).toBeInTheDocument();
      expect(screen.getByLabelText(/^Admin Password$/i)).toBeInTheDocument();
      expect(screen.getByLabelText(/^Confirm Password$/i)).toBeInTheDocument();
    });
  });
});
