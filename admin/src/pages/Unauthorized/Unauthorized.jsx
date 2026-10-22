// src/pages/Unauthorized/Unauthorized.jsx
import React from 'react';
import { useNavigate } from 'react-router-dom';
import { Shield, ArrowLeft, LogIn } from 'lucide-react';
import { useAuth } from '../../context/AuthContext';
import { firstAllowedPath } from '../../utils/permissions';

const Unauthorized = () => {
  const navigate = useNavigate();
  const { user, logout } = useAuth();

  const handleLogout = () => {
    logout();
    navigate('/login');
  };

  // Figure out where to send them back: their first permitted tab in
  // sidebar order (works for custom slugs no role-string check can name).
  // Authenticated sessions always land somewhere inside the panel — never
  // back at /login, which would look like a logged-out state.
  const getRedirectPath = () => firstAllowedPath(user);

  return (
    <div className="min-h-screen flex items-center justify-center bg-background">
      <div className="text-center max-w-md p-8">
        <div className="bg-destructive/15 rounded-full w-20 h-20 flex items-center justify-center mx-auto mb-4">
          <Shield size={40} className="text-destructive" />
        </div>
        <h1 className="text-3xl font-bold text-foreground mb-2">Access Denied</h1>
        <p className="text-muted-foreground mb-6">
          You don't have permission to access this page. Please contact your administrator if you believe this is an error.
        </p>
        
        <div className="space-y-3">
          {/* Back to Dashboard/Products button */}
          <button
            onClick={() => navigate(getRedirectPath())}
            className="w-full inline-flex items-center justify-center gap-2 px-6 py-3 bg-primary text-primary-foreground rounded-lg hover:bg-primary-hover transition-colors"
          >
            <ArrowLeft size={18} />
            {getRedirectPath() === '/products' ? 'Back to Products' : 'Back to Dashboard'}
          </button>
          
          {/* 👇 ADDED: Login button for when session expired */}
          <button
            onClick={handleLogout}
            className="w-full inline-flex items-center justify-center gap-2 px-6 py-3 border border-input text-muted-foreground rounded-lg hover:bg-muted transition-colors"
          >
            <LogIn size={18} />
            Go to Login
          </button>
        </div>
      </div>
    </div>
  );
};

export default Unauthorized;