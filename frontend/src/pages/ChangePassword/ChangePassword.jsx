// src/pages/ChangePassword/ChangePassword.jsx
import React, { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { RefreshCw, ArrowLeft, Shield } from 'lucide-react';
import { authAPI } from '../../api/auth';
import toast from 'react-hot-toast';

const ChangePassword = () => {
  const navigate = useNavigate();
  const [loading, setLoading] = useState(false);
  const [formData, setFormData] = useState({
    current_password: '',
    new_password: '',
    confirm_password: '',
  });

  const handleChange = (e) => {
    setFormData({
      ...formData,
      [e.target.name]: e.target.value,
    });
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    
    // Validate passwords match
    if (formData.new_password !== formData.confirm_password) {
      toast.error('New passwords do not match');
      return;
    }
    
    if (formData.new_password.length < 8) {
      toast.error('New password must be at least 8 characters');
      return;
    }

    if (formData.current_password === formData.new_password) {
      toast.error('New password must be different from current password');
      return;
    }

    try {
      setLoading(true);
      
      await authAPI.changePassword({
        current_password: formData.current_password,
        new_password: formData.new_password,
      });
      
      toast.success('✅ Password changed successfully!');
      
      // Clear form
      setFormData({
        current_password: '',
        new_password: '',
        confirm_password: '',
      });
      
      // Optional: Redirect to profile or settings
      // navigate('/settings');
      
    } catch (error) {
      console.error('Change password error:', error);
      console.error('Error response:', error.response?.data);
      
      let errorMessage = 'Failed to change password. Please try again.';
      
      if (error.response?.status === 401) {
        errorMessage = 'Current password is incorrect. Please try again.';
      } else if (error.response?.data?.detail) {
        errorMessage = error.response.data.detail;
      }
      
      toast.error(errorMessage);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="max-w-md mx-auto p-6">
      <div className="flex items-center gap-3 mb-6">
        <button
          onClick={() => navigate(-1)}
          className="text-muted-foreground hover:text-foreground"
        >
          <ArrowLeft size={24} />
        </button>
        <h1 className="text-2xl font-bold text-foreground">Change Password</h1>
      </div>

      <div className="bg-card rounded-xl shadow-sm border border-border p-6">
        <div className="flex items-center gap-2 text-sm text-muted-foreground mb-6">
          <Shield size={16} />
          <span>Update your password to keep your account secure</span>
        </div>

        <form onSubmit={handleSubmit} className="space-y-5">
          {/* Current Password */}
          <div>
            <label className="block text-sm font-medium text-muted-foreground mb-1">
              Current Password
            </label>
            <input
              type="password"
              name="current_password"
              value={formData.current_password}
              onChange={handleChange}
              className="w-full px-4 py-2 border border-border rounded-lg focus:ring-2 focus:ring-ring focus:border-transparent"
              placeholder="Enter current password"
              required
            />
          </div>

          {/* New Password */}
          <div>
            <label className="block text-sm font-medium text-muted-foreground mb-1">
              New Password
            </label>
            <input
              type="password"
              name="new_password"
              value={formData.new_password}
              onChange={handleChange}
              className="w-full px-4 py-2 border border-border rounded-lg focus:ring-2 focus:ring-ring focus:border-transparent"
              placeholder="Enter new password"
              required
              minLength={8}
            />
            <p className="text-xs text-muted-foreground mt-1">Must be at least 8 characters</p>
          </div>

          {/* Confirm Password */}
          <div>
            <label className="block text-sm font-medium text-muted-foreground mb-1">
              Confirm New Password
            </label>
            <input
              type="password"
              name="confirm_password"
              value={formData.confirm_password}
              onChange={handleChange}
              className="w-full px-4 py-2 border border-border rounded-lg focus:ring-2 focus:ring-ring focus:border-transparent"
              placeholder="Confirm new password"
              required
            />
            {formData.confirm_password && formData.new_password !== formData.confirm_password && (
              <p className="text-xs text-destructive mt-1">Passwords do not match</p>
            )}
          </div>

          {/* Submit Button */}
          <button
            type="submit"
            disabled={loading}
            className="w-full btn-accent py-3 rounded-lg font-medium disabled:opacity-50 flex items-center justify-center gap-2"
          >
            {loading ? (
              <>
                <RefreshCw size={18} className="animate-spin" />
                Changing Password...
              </>
            ) : (
              'Change Password'
            )}
          </button>
        </form>
      </div>
    </div>
  );
};

export default ChangePassword;