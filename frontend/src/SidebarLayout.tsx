import { ReactNode, useEffect, useState } from 'react';
import { NavLink, useNavigate } from 'react-router-dom';
import {
  LayoutDashboard,
  Package,
  Inbox,
  Users,
  Megaphone,
  UserCheck,
  Settings,
  Smartphone,
  Bot,
  LogOut,
  Sparkles,
} from 'lucide-react';
import { api } from './api';

interface SidebarLayoutProps {
  children: ReactNode;
  title: string;
}

export default function SidebarLayout({ children, title }: SidebarLayoutProps) {
  const navigate = useNavigate();
  const [botName, setBotName] = useState('Signal AI Agent');

  useEffect(() => {
    let cancelled = false;

    fetch('/health')
      .then(r => r.json())
      .then(data => {
        if (!cancelled && data?.bot_name) {
          const name = String(data.bot_name);
          setBotName(name);
          document.title = `${title} | ${name}`;
        }
      })
      .catch(() => {
        if (!cancelled) {
          setBotName('Signal AI Agent');
          document.title = `${title} | Signal AI Agent`;
        }
      });

    return () => {
      cancelled = true;
    };
  }, []);

  const handleLogout = () => {
    api.clearToken();
    navigate('/login');
  };

  return (
    <div className="layout-wrapper">
      <aside className="sidebar">
        <div className="sidebar-header">
          <div className="w-8 h-8 rounded-lg bg-[rgba(108,92,231,0.2)] border border-[rgba(108,92,231,0.4)] flex items-center justify-center text-[var(--accent)] shadow-[0_0_12px_rgba(108,92,231,0.3)]">
            <Bot className="w-5 h-5" />
          </div>
          <span className="sidebar-title">{botName}</span>
        </div>

        <nav className="sidebar-nav">
          <NavLink to="/" className={({ isActive }) => `nav-item ${isActive ? 'active' : ''}`} end>
            <LayoutDashboard className="w-4 h-4 mr-2.5 opacity-80" />
            <span>Overview</span>
          </NavLink>
          <NavLink to="/products" className={({ isActive }) => `nav-item ${isActive ? 'active' : ''}`}>
            <Package className="w-4 h-4 mr-2.5 opacity-80" />
            <span>Products</span>
          </NavLink>
          <NavLink to="/inbox" className={({ isActive }) => `nav-item ${isActive ? 'active' : ''}`}>
            <Inbox className="w-4 h-4 mr-2.5 opacity-80" />
            <span>Inbox</span>
          </NavLink>
          <NavLink to="/ai-studio" className={({ isActive }) => `nav-item ${isActive ? 'active' : ''}`}>
            <Sparkles className="w-4 h-4 mr-2.5 text-[var(--accent)]" />
            <span className="font-semibold text-[var(--accent-light)]">AI Studio</span>
          </NavLink>
          <NavLink to="/groups" className={({ isActive }) => `nav-item ${isActive ? 'active' : ''}`}>
            <Users className="w-4 h-4 mr-2.5 opacity-80" />
            <span>Groups</span>
          </NavLink>
          <NavLink to="/campaigns" className={({ isActive }) => `nav-item ${isActive ? 'active' : ''}`}>
            <Megaphone className="w-4 h-4 mr-2.5 opacity-80" />
            <span>Campaigns</span>
          </NavLink>
          <NavLink to="/users" className={({ isActive }) => `nav-item ${isActive ? 'active' : ''}`}>
            <UserCheck className="w-4 h-4 mr-2.5 opacity-80" />
            <span>Users</span>
          </NavLink>
          <NavLink to="/settings" className={({ isActive }) => `nav-item ${isActive ? 'active' : ''}`}>
            <Settings className="w-4 h-4 mr-2.5 opacity-80" />
            <span>Settings</span>
          </NavLink>
          <NavLink to="/devices" className={({ isActive }) => `nav-item ${isActive ? 'active' : ''}`}>
            <Smartphone className="w-4 h-4 mr-2.5 opacity-80" />
            <span>Devices</span>
          </NavLink>
        </nav>

        <div className="sidebar-footer">
          <button type="button" onClick={handleLogout} className="btn-secondary sidebar-logout flex items-center justify-center gap-1.5 w-full">
            <LogOut className="w-3.5 h-3.5" />
            <span>Logout</span>
          </button>
        </div>
      </aside>

      <main className="main-content">
        <header className="page-header">
          <h1 className="page-title">{title}</h1>
        </header>
        <div className="page-content">
          {children}
        </div>
      </main>
    </div>
  );
}
