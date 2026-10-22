import React from 'react';
import { Menu, Sun, Moon } from 'lucide-react';
import { useNavigate } from 'react-router-dom';
import { useAuth } from '../../context/AuthContext';
import { useTheme } from '../../context/ThemeContext';
import NotificationBell from './NotificationBell';

const Header = ({ toggleSidebar }) => {
  const navigate = useNavigate();
  const { user } = useAuth();
  const { resolvedTheme, toggleTheme } = useTheme();

  return (
    <header className="sticky top-0 z-20 h-16 bg-card border-b border-border px-4 sm:px-6 flex items-center justify-between flex-shrink-0">
      <div className="flex items-center gap-3 sm:gap-4 min-w-0">
        <button
          onClick={toggleSidebar}
          className="lg:hidden p-1 -ml-1 text-muted-foreground hover:text-foreground flex-shrink-0 rounded-lg hover:bg-muted"
          aria-label="Open menu"
        >
          <Menu size={24} />
        </button>
      </div>
      <div className="flex items-center gap-1.5 sm:gap-2 flex-shrink-0">
        {/* 👇 Quick theme toggle (light ⇄ dark) */}
        <button
          onClick={toggleTheme}
          className="w-9 h-9 rounded-lg flex items-center justify-center text-muted-foreground hover:text-foreground hover:bg-muted transition-colors"
          title={resolvedTheme === 'dark' ? 'Switch to light mode' : 'Switch to dark mode'}
        >
          {resolvedTheme === 'dark' ? <Sun size={20} /> : <Moon size={20} />}
        </button>
        {/* 👇 Real-time notifications (orders, cancellations, promotions) */}
        <NotificationBell />
        <div
          onClick={() => navigate('/settings?tab=profile')}
          className="flex items-center gap-2.5 hover:bg-muted rounded-lg p-1.5 mr-0 transition-colors cursor-pointer ml-0.5 sm:ml-1"
          title="Profile settings"
        >
          <div className="w-9 h-9 rounded-full bg-primary flex items-center justify-center text-primary-foreground dark:text-black font-semibold flex-shrink-0">
            {user?.full_name?.[0] || user?.username?.[0] || 'A'}
          </div>
          <span className="text-sm font-medium text-muted-foreground hidden md:block whitespace-nowrap">
            {user?.full_name || user?.username || 'Admin'}
          </span>
        </div>
      </div>
    </header>
  );
};

export default Header;