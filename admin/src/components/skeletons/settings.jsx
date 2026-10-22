// src/components/skeletons/settings.jsx
import React from 'react';
import { User, Shield, Palette, Bell } from 'lucide-react';
import { Card, Btn, Skeleton } from './_shared';

export const SettingsSkeleton = () => (
  <div>
    <div className="mb-6">
      <h1 className="text-xl sm:text-2xl font-bold text-foreground break-words">Settings</h1>
      <p className="text-sm text-muted-foreground mt-1">Manage your account and preferences</p>
    </div>

    <div className="grid grid-cols-1 lg:grid-cols-4 gap-6">
      {/* Settings tab list - static labels */}
      <div className="lg:col-span-1">
        <Card className="p-3 lg:p-4 lg:sticky lg:top-6">
          <div className="flex lg:flex-col gap-1 lg:space-y-1 overflow-x-auto">
            {[
              { label: 'Profile', icon: User, active: true },
              { label: 'Security', icon: Shield, active: false },
              { label: 'Preferences', icon: Palette, active: false },
              { label: 'Notifications', icon: Bell, active: false },
            ].map(({ label, icon: Icon, active }) => (
              <Btn
                key={label}
                className={`flex-none lg:w-full justify-start gap-3 px-4 py-2.5 rounded-lg whitespace-nowrap ${
                  active ? 'bg-primary-soft text-primary font-medium' : 'text-muted-foreground'
                }`}
              >
                <Icon size={18} />
                <span>{label}</span>
              </Btn>
            ))}
          </div>
        </Card>
      </div>

      {/* Active panel - static labels, dynamic values are bars */}
      <div className="lg:col-span-3">
        <Card className="p-4 sm:p-6">
          <h2 className="text-lg font-semibold text-foreground mb-4">Profile Settings</h2>
          <p className="text-sm text-muted-foreground mb-6">Update your personal information</p>
          <div className="space-y-4">
            {['Full Name', 'Username', 'Email Address', 'Phone Number'].map((label) => (
              <div key={label}>
                <label className="block text-sm font-medium text-muted-foreground mb-1">
                  {label}
                </label>
                <Skeleton className="h-10 w-full rounded-lg" />
              </div>
            ))}
          </div>
          <Btn className="mt-6 px-6 py-2 bg-primary text-primary-foreground rounded-lg gap-2">
            Save Changes
          </Btn>
        </Card>
      </div>
    </div>
  </div>
);
