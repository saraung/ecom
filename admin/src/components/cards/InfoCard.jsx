// src/components/cards/InfoCard.jsx
import React from 'react';

const InfoCard = ({ 
  title, 
  icon: Icon,
  children,
  action,
  className = ''
}) => {
  return (
    <div className={`bg-card rounded-xl shadow-sm border border-border p-4 sm:p-6 ${className}`}>
      <div className="flex items-center justify-between gap-3 mb-4">
        <h2 className="text-base sm:text-lg font-semibold text-foreground flex items-center gap-2 min-w-0">
          {Icon && <Icon size={20} className="text-muted-foreground flex-shrink-0" />}
          <span className="truncate">{title}</span>
        </h2>
        {action && <div className="flex-shrink-0">{action}</div>}
      </div>
      {children}
    </div>
  );
};

export default InfoCard;