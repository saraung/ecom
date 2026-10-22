// src/components/cards/StatCard.jsx
import React from 'react';

const StatCard = ({ 
  title, 
  value, 
  icon: Icon, 
  color = 'blue',
  subtitle,
  trend,
  onClick 
}) => {
  const colorClasses = {
    blue: { bg: 'bg-primary-soft', text: 'text-primary', gradient: 'from-blue-500 to-blue-600' },
    green: { bg: 'bg-success/10', text: 'text-success', gradient: 'from-green-500 to-green-600' },
    purple: { bg: 'bg-purple-500/10', text: 'text-purple-500', gradient: 'from-purple-500 to-purple-600' },
    orange: { bg: 'bg-orange-500/10', text: 'text-orange-500', gradient: 'from-orange-500 to-orange-600' },
    red: { bg: 'bg-destructive/10', text: 'text-destructive', gradient: 'from-red-500 to-red-600' },
    yellow: { bg: 'bg-warning/10', text: 'text-warning', gradient: 'from-yellow-500 to-yellow-600' },
  };

  const classes = colorClasses[color] || colorClasses.blue;

  return (
    <div
      onClick={onClick}
      className={`bg-card rounded-xl shadow-sm border border-border p-4 sm:p-6 transition-all hover:shadow-md min-w-0 ${
        onClick ? 'cursor-pointer hover:scale-105' : ''
      }`}
    >
      <div className="flex items-start justify-between gap-2 min-w-0">
        <div className="flex-1 min-w-0">
          <p className="text-xs sm:text-sm text-muted-foreground font-medium truncate">{title}</p>
          <p className="text-lg sm:text-2xl font-bold text-foreground mt-1 truncate">{value}</p>
          {subtitle && (
            <p className="text-xs text-muted-foreground mt-1 truncate">{subtitle}</p>
          )}
          {trend && (
            <div className={`flex items-center gap-1 mt-2 text-xs font-medium ${
              trend > 0 ? 'text-success' : trend < 0 ? 'text-destructive' : 'text-muted-foreground'
            }`}>
              {trend > 0 ? '↑' : trend < 0 ? '↓' : '→'}
              {Math.abs(trend)}%
            </div>
          )}
        </div>
        {Icon && (
          <div className={`${classes.bg} p-2.5 sm:p-3 rounded-lg flex-shrink-0`}>
            <Icon className={classes.text} />
          </div>
        )}
      </div>
    </div>
  );
};

export default StatCard;