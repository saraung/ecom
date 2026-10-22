// src/components/skeletons/users.jsx
import React from 'react';
import { Filter, ChevronDown, MapPin, ArrowLeft, Shield } from 'lucide-react';
import { Card, Btn, TabHeader, SectionTitle, Count, StaticSearch, HeadRow, MobileRowCards, Skeleton } from './_shared';

export const UsersSkeleton = () => (
  <div>
    <TabHeader
      title="Users"
      subtitle={(
        <>
          <Count w="w-8" /> users found
        </>
      )}
    />

    <div className="flex flex-col sm:flex-row gap-4 mb-6">
      <StaticSearch placeholder="Search users by name, email, or username..." />
      <div className="flex gap-2">
        <Btn className="gap-2 px-4 py-2.5 sm:py-2 border border-input rounded-lg hover:bg-muted transition-colors justify-center">
          <Shield size={18} />
          <span>Role</span>
          <ChevronDown size={16} />
        </Btn>
        <Btn className="gap-2 px-4 py-2.5 sm:py-2 border border-input rounded-lg hover:bg-muted transition-colors justify-center">
          <Filter size={18} />
          <span>Status</span>
          <ChevronDown size={16} />
        </Btn>
      </div>
    </div>

    <Card className="overflow-hidden">
      <div className="hidden md:block overflow-x-auto">
        <table className="w-full">
          <HeadRow cols={['User', 'Email', 'Role', 'Status', 'Joined', 'Actions']} />
          <tbody className="divide-y divide-border">
            {Array.from({ length: 7 }).map((_, i) => (
              <tr key={i}>
                <td className="px-4 py-3">
                  <div className="flex items-center gap-3">
                    <Skeleton className="h-10 w-10 rounded-full bg-primary shrink-0" />
                    <div className="space-y-1.5">
                      <Skeleton className="h-4 w-32" />
                      <Skeleton className="h-3 w-24" />
                    </div>
                  </div>
                </td>
                <td className="px-4 py-3">
                  <Skeleton className="h-4 w-40" />
                </td>
                <td className="px-4 py-3">
                  <Skeleton className="h-6 w-16 rounded-full" />
                </td>
                <td className="px-4 py-3">
                  <Skeleton className="h-6 w-16 rounded-full" />
                </td>
                <td className="px-4 py-3">
                  <Skeleton className="h-3 w-20" />
                </td>
                <td className="px-4 py-3">
                  <Skeleton className="h-5 w-20 ml-auto" />
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <MobileRowCards rows={5} />
    </Card>
  </div>
);

export const UserDetailSkeleton = () => (
  <div>
    {/* Header - static back button + title (matches the real page) */}
    <div className="flex flex-wrap items-center gap-4 mb-6">
      <Btn className="text-muted-foreground">
        <ArrowLeft size={24} />
      </Btn>
      <h1 className="text-xl sm:text-2xl font-bold text-foreground break-words">User Details</h1>
    </div>

    <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
      <div className="lg:col-span-2 space-y-6">
        <Card className="p-6">
          <div className="flex flex-wrap items-start justify-between gap-3">
            <div className="flex items-center gap-4 min-w-0">
              <Skeleton className="h-16 w-16 rounded-full bg-primary shrink-0" />
              <div className="space-y-2 min-w-0">
                <Skeleton className="h-6 w-40" />
                <Skeleton className="h-4 w-32" />
                <div className="flex flex-wrap items-center gap-1.5 pt-1">
                  <Skeleton className="h-6 w-16 rounded-full" />
                  <Skeleton className="h-6 w-20 rounded-full" />
                </div>
              </div>
            </div>
            <Skeleton className="h-9 w-9 rounded-lg shrink-0" />
          </div>
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4 mt-6">
            {[0, 1, 2, 3].map((n) => (
              <div key={n} className="p-3 bg-muted rounded-lg">
                <Skeleton className="h-3 w-20" />
                <Skeleton className="h-4 w-32 mt-2" />
              </div>
            ))}
          </div>
        </Card>

        {/* Saved Addresses - static title + icon, count is dynamic */}
        <Card className="p-6">
          <div className="flex items-center justify-between mb-4">
            <SectionTitle>
              <MapPin size={20} className="text-muted-foreground" />
              Saved Addresses (<Count w="w-6" className="inline-block h-5 align-middle" />)
            </SectionTitle>
          </div>
          <div className="space-y-3">
            {[0, 1].map((r) => (
              <div key={r} className="p-4 rounded-lg border border-border bg-muted">
                <Skeleton className="h-4 w-24" />
                <Skeleton className="h-4 w-48 mt-2" />
                <Skeleton className="h-4 w-36 mt-2" />
              </div>
            ))}
          </div>
        </Card>
      </div>

      <div className="space-y-6">
        {/* Statistics - five icon rows (matches the real page) */}
        <Card className="p-6">
          <SectionTitle className="text-lg font-semibold text-foreground mb-4">Statistics</SectionTitle>
          <div className="space-y-3">
            {[0, 1, 2, 3, 4].map((r) => (
              <div key={r} className="flex items-center justify-between gap-3 p-3 bg-muted rounded-lg">
                <Skeleton className="h-4 w-24" />
                <Skeleton className="h-4 w-12" />
              </div>
            ))}
          </div>
        </Card>
        {/* Actions - single back button (matches the real page) */}
        <Card className="p-6">
          <SectionTitle className="text-lg font-semibold text-foreground mb-4">Actions</SectionTitle>
          <Btn className="w-full flex items-center justify-center gap-2 px-4 py-2 border border-input rounded-lg">
            <ArrowLeft size={18} />
            Back to Users
          </Btn>
        </Card>
      </div>
    </div>
  </div>
);
