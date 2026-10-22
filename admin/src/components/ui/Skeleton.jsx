import React from 'react';

const Skeleton = ({ className = '' }) => {
  return (
    <div className={`animate-pulse bg-foreground/10 rounded ${className}`} />
  );
};

export default Skeleton;