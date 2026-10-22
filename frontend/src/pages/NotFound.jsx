import React from 'react';
import { Link } from 'react-router-dom';
import { Home, Search, ArrowLeft } from 'lucide-react';

/**
 * Catch-all route. Rendered inside <Layout> so the header, footer and
 * announcement bar stay visible; the shopper can recover without using the
 * browser back button.
 */
const NotFound = () => {
  return (
    <section className="min-h-[60vh] flex items-center justify-center px-4 py-16">
      <div className="max-w-md w-full text-center">
        <p className="text-7xl font-extrabold tracking-tight text-primary">404</p>

        <h1 className="mt-4 text-2xl font-semibold text-foreground">
          We couldn&rsquo;t find that page
        </h1>

        <p className="mt-2 text-sm text-muted-foreground">
          The link may be broken, or the product may have been removed.
        </p>

        <div className="mt-8 flex flex-col sm:flex-row gap-3 justify-center">
          <Link
            to="/"
            className="inline-flex items-center justify-center gap-2 rounded-lg bg-primary px-5 py-2.5 text-sm font-medium text-primary-foreground hover:opacity-90 transition-opacity"
          >
            <Home className="h-4 w-4" />
            Back to home
          </Link>

          <Link
            to="/products"
            className="inline-flex items-center justify-center gap-2 rounded-lg border border-border px-5 py-2.5 text-sm font-medium text-foreground hover:bg-muted transition-colors"
          >
            <Search className="h-4 w-4" />
            Browse products
          </Link>
        </div>

        <button
          type="button"
          onClick={() => window.history.back()}
          className="mt-6 inline-flex items-center gap-1.5 text-sm text-muted-foreground hover:text-foreground transition-colors"
        >
          <ArrowLeft className="h-4 w-4" />
          Go back
        </button>
      </div>
    </section>
  );
};

export default NotFound;
