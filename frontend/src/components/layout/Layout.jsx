import React from 'react';
import Header from './Header';
import Footer from './Footer';
import AnnouncementBar from '../common/AnnouncementBar';

const Layout = ({ children }) => {
  return (
    <div className="min-h-screen flex flex-col bg-background text-foreground">
      <Header />
      <main className="flex-1 pt-20 sm:pt-24 md:pt-28 lg:pt-32 flex flex-col">
        {/* In-flow below the fixed header: the header paints over anything
            at viewport-top, so the strip lives here and scrolls naturally. */}
        <AnnouncementBar />
        {children}
      </main>
      <Footer />
    </div>
  );
};

export default Layout;  