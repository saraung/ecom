// src/components/ui/PageLoader.jsx
import React from 'react';
import { Loader } from 'lucide-react';

/**
 * Neutral full-screen loader for route chunk transitions (top-level
 * Suspense fallback). Deliberately NOT a content skeleton — skeletons must
 * mirror the destination page's shape (NN/g), and the top boundary serves
 * unrelated pages (login, unauthorized), so a table skeleton there is a
 * shape mismatch. Inside the admin layout, AdminLayout's own boundary
 * keeps showing route-aware skeletons.
 */
const PageLoader = () => {
  return (
    <div className="min-h-screen flex flex-col items-center justify-center gap-3 bg-background">
      <div className="w-10 h-10 rounded-xl bg-primary text-primary-foreground flex items-center justify-center font-bold text-lg">
        A
      </div>
      <div className="flex items-center gap-2 text-sm text-muted-foreground">
        <Loader className="animate-spin" size={16} />
        Loading...
      </div>
    </div>
  );
};

export default PageLoader;
