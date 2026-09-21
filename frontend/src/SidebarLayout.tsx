import { ReactNode, useEffect, useState } from 'react';
import { NavLink, useNavigate } from 'react-router-dom';
import { api } from './api';

interface SidebarLayoutProps {
  children: ReactNode;
  title: string;
}

export default function SidebarLayout({ children, title }: SidebarLayoutProps) {
  const navigate = useNavigate();
  const [botName, setBotName] = useState('Signal Market');

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
          setBotName('Signal Market');
          document.title = `${title} | Signal Market`;
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
          <span className="sidebar-logo">🤖</span>
          <span className="sidebar-title">{botName}</span>
        </div>

        <nav className="sidebar-nav">
          <NavLink to="/" className={({ isActive }) => `nav-item ${isActive ? 'active' : ''}`} end>
            <span className="nav-icon">📊</span>
            <span>Overview</span>
          </NavLink>
          <NavLink to="/products" className={({ isActive }) => `nav-item ${isActive ? 'active' : ''}`}>
            <span className="nav-icon">📦</span>
            <span>Products</span>
          </NavLink>
          <NavLink to="/inbox" className={({ isActive }) => `nav-item ${isActive ? 'active' : ''}`}>
            <span className="nav-icon">📥</span>
            <span>Inbox</span>
          </NavLink>
          <NavLink to="/groups" className={({ isActive }) => `nav-item ${isActive ? 'active' : ''}`}>
            <span className="nav-icon">👥</span>
            <span>Groups</span>
          </NavLink>
          <NavLink to="/campaigns" className={({ isActive }) => `nav-item ${isActive ? 'active' : ''}`}>
            <span className="nav-icon">📣</span>
            <span>Campaigns</span>
          </NavLink>
          <NavLink to="/users" className={({ isActive }) => `nav-item ${isActive ? 'active' : ''}`}>
            <span className="nav-icon">👤</span>
            <span>Users</span>
          </NavLink>
          <NavLink to="/settings" className={({ isActive }) => `nav-item ${isActive ? 'active' : ''}`}>
            <span className="nav-icon">⚙️</span>
            <span>Settings</span>
          </NavLink>
          <NavLink to="/devices" className={({ isActive }) => `nav-item ${isActive ? 'active' : ''}`}>
            <span className="nav-icon">📱</span>
            <span>Devices</span>
          </NavLink>
        </nav>

        <div className="sidebar-footer">
          <button type="button" onClick={handleLogout} className="btn-secondary sidebar-logout">
            Logout
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
