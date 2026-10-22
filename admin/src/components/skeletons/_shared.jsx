// src/components/skeletons/_shared.jsx
import React from 'react';
import { Search } from 'lucide-react';
import Skeleton from '../ui/Skeleton';

export { Skeleton };

export const Card = ({ className = '', children }) => (
  <div className={`bg-card rounded-xl shadow-sm border border-border ${className}`}>
    {children}
  </div>
);

export const Btn = ({ className = '', children }) => (
  <span className={`${className} inline-flex items-center`}>{children}</span>
);

export const TabHeader = ({
  title,
  subtitle,
  actions = null,
  className = 'mb-6',
  titleClassName = 'text-xl sm:text-2xl font-bold text-foreground',
}) => (
  <div className={`flex flex-col sm:flex-row justify-between items-start sm:items-center gap-4 ${className}`}>
    <div className="min-w-0">
      <h1 className={titleClassName}>{title}</h1>
      {subtitle && <p className="text-sm text-muted-foreground mt-1">{subtitle}</p>}
    </div>
    {actions && <div className="flex flex-col sm:flex-row w-full sm:w-auto gap-2 sm:items-center">{actions}</div>}
  </div>
);

export const SectionTitle = ({ children, className = 'text-lg font-semibold text-foreground' }) => (
  <h2 className={`${className} flex items-center gap-2 min-w-0`}>{children}</h2>
);

export const Count = ({ w = 'w-8', className = 'inline-block h-4 align-middle' }) => (
  <span className={`animate-pulse bg-foreground/10 rounded ${className} ${w}`} />
);

export const StaticSearch = ({ placeholder, className = 'relative w-full sm:flex-1 max-w-md' }) => (
  <div className={className}>
    <Search className="absolute left-3 top-1/2 transform -translate-y-1/2 text-muted-foreground" size={18} />
    <input
      type="text"
      readOnly
      tabIndex={-1}
      placeholder={placeholder}
      className="w-full pl-10 pr-4 py-2 border border-input rounded-lg focus:outline-none"
    />
  </div>
);

export const HeadRow = ({ cols }) => (
  <thead className="bg-muted">
    <tr>
      {cols.map((label, i) => (
        <th
          key={i}
          className={`px-4 py-3 text-xs font-medium text-muted-foreground uppercase tracking-wider ${
            label === 'Actions' ? 'text-right' : 'text-left'
          }`}
        >
          {label === 'checkbox' ? (
            <input type="checkbox" readOnly tabIndex={-1} className="rounded border-input" />
          ) : (
            label
          )}
        </th>
      ))}
    </tr>
  </thead>
);

export const MobileRowCards = ({ rows = 5, thumb = false }) => (
  <div className="md:hidden divide-y divide-border">
    {Array.from({ length: rows }).map((_, i) => (
      <div key={i} className="p-4 space-y-3">
        <div className="flex items-start gap-3">
          {thumb && <Skeleton className="h-12 w-12 rounded-lg shrink-0" />}
          <div className="flex-1 space-y-2 min-w-0">
            <Skeleton className="h-4 w-2/3" />
            <Skeleton className="h-3 w-1/3" />
          </div>
          <Skeleton className="h-6 w-16 rounded-full shrink-0" />
        </div>
        <div className="flex items-center justify-between">
          <Skeleton className="h-4 w-20" />
          <Skeleton className="h-7 w-16 rounded-lg" />
        </div>
      </div>
    ))}
  </div>
);

export const ChartCard = ({ title, icon: Icon, action = null, body = 'h-52 sm:h-64', round = false }) => (
  <Card className="p-4 sm:p-6">
    <div className="flex items-center justify-between gap-3 mb-4">
      <h2 className="text-base sm:text-lg font-semibold text-foreground flex items-center gap-2 min-w-0">
        {Icon && <Icon size={20} className="text-muted-foreground flex-shrink-0" />}
        <span className="truncate">{title}</span>
      </h2>
      {action}
    </div>
    <Skeleton className={`${body} w-full ${round ? 'rounded-full max-w-56 mx-auto' : 'rounded-lg'}`} />
  </Card>
);

export const ListFooter = () => (
  <div className="px-4 py-3 border-t border-border flex flex-col sm:flex-row items-start sm:items-center justify-between gap-3">
    <p className="text-sm text-muted-foreground">
      Showing <Count w="w-6" /> - <Count w="w-6" /> of <Count w="w-10" />
    </p>
    <div className="flex items-center gap-2">
      <Skeleton className="h-7 w-[76px] rounded" />
      <Skeleton className="h-4 w-24" />
      <Skeleton className="h-7 w-[60px] rounded" />
    </div>
  </div>
);
