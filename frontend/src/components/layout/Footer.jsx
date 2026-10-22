import React from 'react';
import { Link } from 'react-router-dom';

const Footer = () => {
  const currentYear = new Date().getFullYear();

  return (
    <footer className="bg-background border-t border-border transition-colors duration-700">
      <div className="max-w-6xl mx-auto px-6 lg:px-8 py-16 md:py-24">
        
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-12 lg:gap-8 mb-16">
          
          {/* Brand & Mission */}
          <div className="col-span-1 md:col-span-2 lg:col-span-1 pr-4">
            <Link to="/" className="inline-block text-2xl font-extrabold tracking-tighter text-foreground hover:opacity-70 transition-opacity">
              E-Shop.
            </Link>
            <p className="mt-4 text-sm text-muted-foreground font-medium leading-relaxed max-w-sm">
              Engineered for excellence. Your curated destination for premium pieces designed to elevate your everyday experience.
            </p>
            
            {/* Social Pills */}
            <div className="flex gap-3 mt-8">
              {['📱', '📷', '🐦', '📺'].map((icon, i) => (
                <a 
                  key={i}
                  href="#" 
                  className="w-10 h-10 rounded-full bg-primary-soft flex items-center justify-center text-muted-foreground hover:bg-primary hover:text-primary-foreground transition-all duration-300 hover:scale-110 active:scale-95 shadow-sm"
                >
                  {icon}
                </a>
              ))}
            </div>
          </div>

          {/* Quick Links */}
          <div>
            <h4 className="text-xs font-bold uppercase tracking-widest text-foreground mb-6">Explore</h4>
            <ul className="space-y-4">
              {['Products', 'Cart', 'Orders', 'Wishlist'].map((item) => (
                <li key={item}>
                  <Link 
                    to={`/${item.toLowerCase()}`} 
                    className="group inline-flex items-center text-sm font-medium text-muted-foreground hover:text-foreground transition-colors"
                  >
                    <span className="transform transition-transform duration-300 group-hover:translate-x-1">
                      {item}
                    </span>
                  </Link>
                </li>
              ))}
            </ul>
          </div>

          {/* Customer Service */}
          <div>
            <h4 className="text-xs font-bold uppercase tracking-widest text-foreground mb-6">Support</h4>
            <ul className="space-y-4">
              {['Contact Us', 'Shipping Info', 'FAQs'].map((item) => (
                <li key={item}>
                  <a 
                    href="#" 
                    className="group inline-flex items-center text-sm font-medium text-muted-foreground hover:text-foreground transition-colors"
                  >
                    <span className="transform transition-transform duration-300 group-hover:translate-x-1">
                      {item}
                    </span>
                  </a>
                </li>
              ))}
            </ul>
          </div>

          {/* Contact */}
          <div>
            <h4 className="text-xs font-bold uppercase tracking-widest text-foreground mb-6">Get in Touch</h4>
            <ul className="space-y-4 text-sm font-medium text-muted-foreground">
              <li className="flex items-start gap-3 hover:text-foreground transition-colors cursor-pointer">
                <span className="text-lg leading-none mt-0.5">📞</span> 
                <span>+1 234 567 890</span>
              </li>
              <li className="flex items-start gap-3 hover:text-foreground transition-colors cursor-pointer break-all">
                <span className="text-lg leading-none mt-0.5">📧</span> 
                <span>support@eshop.com</span>
              </li>
              <li className="flex items-start gap-3 hover:text-foreground transition-colors cursor-pointer">
                <span className="text-lg leading-none mt-0.5">📍</span> 
                <span>123 Main St, Design District<br/>City, State 10001</span>
              </li>
            </ul>
          </div>
        </div>

        {/* Bottom Bar */}
        <div className="border-t border-border pt-8 flex flex-col md:flex-row items-center justify-between gap-4">
          <p className="text-xs font-bold uppercase tracking-wider text-muted-foreground text-center md:text-left">
            © {currentYear} E-Shop. All rights reserved.
          </p>
          
          <div className="flex items-center gap-6 text-xs font-bold uppercase tracking-wider text-muted-foreground">
            <a href="#" className="hover:text-foreground transition-colors">Privacy</a>
            <a href="#" className="hover:text-foreground transition-colors">Terms</a>
            <a href="#" className="hover:text-foreground transition-colors">Accessibility</a>
          </div>
        </div>

      </div>
    </footer>
  );
};

export default Footer;