// src/contexts/NotificationContext.jsx
import React, {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useState,
} from 'react';
import { useAuth } from '../hooks/useAuth';
import notificationService from '../services/notificationService';

const NotificationContext = createContext(null);

export const NotificationProvider = ({ children }) => {
  const { user } = useAuth();
  const [connectionStatus, setConnectionStatus] = useState(
    () => notificationService.getConnectionStatus()
  );

  useEffect(() => {
    if (user) {
      const token = localStorage.getItem('access_token');
      if (token) {
        notificationService.connect({
          userId: user.id,
          token,
        });
      }
    } else {
      notificationService.disconnect();
    }
  }, [user]);

  useEffect(() => {
    return notificationService.addStatusListener(setConnectionStatus);
  }, []);

  const subscribe = useCallback(
    (callback) => notificationService.addListener(callback),
    []
  );

  const value = {
    connectionStatus,
    subscribe,
  };

  return (
    <NotificationContext.Provider value={value}>
      {children}
    </NotificationContext.Provider>
  );
};

export const useNotifications = () => {
  const context = useContext(NotificationContext);
  if (!context) {
    throw new Error(
      'useNotifications must be used within a NotificationProvider'
    );
  }
  return context;
};