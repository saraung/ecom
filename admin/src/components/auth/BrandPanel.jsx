// src/components/auth/BrandPanel.jsx
import React from 'react';
import { Package, ShieldCheck, BarChart3, Boxes } from 'lucide-react';

/**
 * Left brand rail of the admin sign-in screen (desktop only).
 * Intentionally fixed dark (neutral-950) in both themes — like Shopify /
 * Vercel login walls — so brand identity stays constant while the form
 * side follows the theme.
 */
const FEATURES = [
  {
    icon: ShieldCheck,
    title: 'Two-step verification',
    text: 'Every sign-in is protected with an email code.',
  },
  {
    icon: Boxes,
    title: 'Catalog, orders & coupons',
    text: 'Manage products, fulfilment and promotions in one place.',
  },
  {
    icon: BarChart3,
    title: 'Reports & insights',
    text: 'Sales, customers and inventory at a glance.',
  },
];

const BrandPanel = () => {
  return (
    <div className="relative hidden lg:flex w-[44%] xl:w-[46%] shrink-0 bg-neutral-950 text-white flex-col justify-between p-10 xl:p-12 overflow-hidden">
      {/* subtle dot texture */}
      <div
        aria-hidden
        className="pointer-events-none absolute inset-0 opacity-[0.35]"
        style={{
          backgroundImage: 'radial-gradient(rgba(255,255,255,0.14) 1px, transparent 1px)',
          backgroundSize: '22px 22px',
        }}
      />
      {/* soft glow */}
      <div
        aria-hidden
        className="pointer-events-none absolute -top-32 -left-32 w-96 h-96 rounded-full opacity-20 blur-3xl"
        style={{ background: 'radial-gradient(circle, #4F46E5 0%, transparent 70%)' }}
      />

      <div className="relative flex items-center gap-3">
        <div className="w-10 h-10 rounded-xl bg-white text-neutral-950 flex items-center justify-center">
          <Package size={22} />
        </div>
        <div>
          <p className="font-bold text-lg leading-tight">Admin Panel</p>
          <p className="text-xs text-neutral-400">Store management console</p>
        </div>
      </div>

      <div className="relative">
        <h2 className="text-3xl xl:text-4xl font-bold leading-tight tracking-tight">
          Run your store
          <br />
          with confidence.
        </h2>
        <p className="mt-3 text-neutral-400 text-sm xl:text-base max-w-sm">
          Orders, products, customers and insights — everything you need to
          operate, secured end to end.
        </p>

        <ul className="mt-8 space-y-5">
          {FEATURES.map((feature) => (
            <li key={feature.title} className="flex items-start gap-3">
              <div className="w-9 h-9 rounded-lg bg-white/10 flex items-center justify-center shrink-0">
                <feature.icon size={18} className="text-white" />
              </div>
              <div>
                <p className="text-sm font-semibold">{feature.title}</p>
                <p className="text-xs text-neutral-400 mt-0.5">{feature.text}</p>
              </div>
            </li>
          ))}
        </ul>
      </div>

      <p className="relative text-xs text-neutral-500">
        Protected with two-step verification · v0.0.0
      </p>
    </div>
  );
};

export default BrandPanel;
