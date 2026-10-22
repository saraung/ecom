import React from 'react';
import { AlertTriangle, RefreshCw, Home } from 'lucide-react';

// Catches render-time errors in the storefront so a single bad payload
// (product, order, review…) shows a recoverable fallback instead of
// blanking the whole app.
class ErrorBoundary extends React.Component {
  constructor(props) {
    super(props);
    this.state = { hasError: false };
  }

  static getDerivedStateFromError() {
    return { hasError: true };
  }

  componentDidCatch(error, info) {
    console.error('Unhandled storefront error:', error, info);
  }

  handleReload = () => {
    window.location.reload();
  };

  render() {
    if (this.state.hasError) {
      return (
        <div className="bg-background min-h-screen flex items-center justify-center p-6">
          <div className="bg-card border border-border rounded-3xl shadow-sm p-8 max-w-md w-full text-center">
            <div className="bg-destructive-soft rounded-full w-16 h-16 flex items-center justify-center mx-auto mb-4">
              <AlertTriangle size={32} className="text-destructive" />
            </div>
            <h1 className="text-xl font-extrabold tracking-tight text-foreground mb-2">Something went wrong</h1>
            <p className="text-sm text-muted-foreground font-medium mb-6">
              An unexpected error occurred while displaying this page. Try refreshing, or head back home.
            </p>
            <div className="flex flex-col sm:flex-row gap-3">
              <button
                type="button"
                onClick={this.handleReload}
                className="flex-1 inline-flex items-center justify-center gap-2 px-4 py-3 bg-primary text-primary-foreground rounded-full font-bold uppercase tracking-widest text-xs hover:bg-primary-hover transition-colors"
              >
                <RefreshCw size={16} />
                Reload Page
              </button>
              <a
                href="/"
                className="flex-1 inline-flex items-center justify-center gap-2 px-4 py-3 border border-border text-foreground rounded-full font-bold uppercase tracking-widest text-xs hover:bg-muted transition-colors"
              >
                <Home size={16} />
                Go Home
              </a>
            </div>
          </div>
        </div>
      );
    }

    return this.props.children;
  }
}

export default ErrorBoundary;
