import { ReactNode } from 'react';
import { NavLink, useNavigate } from 'react-router-dom';
import { api } from './api';

interface SidebarLayoutProps {
  children: ReactNode;
  title: string;
}

export default function SidebarLayout({ children, title }: SidebarLayoutProps) {
  const navigate = useNavigate();

  const handleLogout = () => {
    api.clearToken();
    navigate('/login');
  };

  return (
    <div className="layout-wrapper">
      <aside className="sidebar">
        <div className="sidebar-header">
          <span className="sidebar-logo">🤖</span>
          <span className="sidebar-title">Signal Market</span>
        </div>
        
        <nav className="sidebar-nav">
          <NavLink to="/" className={({isActive}) => `nav-item ${isActive ? 'active' : ''}`} end>
            <span>📊</span> Overview
          </NavLink>
          <NavLink to="/products" className={({isActive}) => `nav-item ${isActive ? 'active' : ''}`}>
            <span>📦</span> Products
          </NavLink>
          <NavLink to="/logs" className={({isActive}) => `nav-item ${isActive ? 'active' : ''}`}>
            <span>💬</span> Chat Logs
          </NavLink>
          <NavLink to="/campaigns" className={({isActive}) => `nav-item ${isActive ? 'active' : ''}`}>
            <span>📣</span> Campaigns
          </NavLink>
          <NavLink to="/users" className={({isActive}) => `nav-item ${isActive ? 'active' : ''}`}>
            <span>👤</span> Users
          </NavLink>
          <NavLink to="/settings" className={({isActive}) => `nav-item ${isActive ? 'active' : ''}`}>
            <span>⚙️</span> Settings
          </NavLink>
        </nav>
        
        <div className="sidebar-footer">
          <button onClick={handleLogout} className="btn-secondary" style={{ width: '100%', borderColor: 'rgba(255,107,107,0.3)', color: '#ff6b6b' }}>
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
