const AddressCard = ({ title, address, fallback = 'Not available' }) => (
  <div className="bg-card rounded-[2rem] border border-border shadow-sm p-5 sm:p-6 transition-colors duration-700">
    <h3 className="text-sm font-extrabold uppercase tracking-widest text-foreground mb-4 flex items-center gap-2">
      <span aria-hidden="true">📍</span> {title}
    </h3>
    {address ? (
      <div className="text-sm text-muted-foreground leading-relaxed space-y-0.5">
        {address.label && (
          <span className="inline-block bg-primary-soft text-primary-soft-foreground px-2.5 py-1 rounded-full mb-2 text-[10px] font-bold uppercase tracking-wider">
            {address.label}
          </span>
        )}
        {address.full_name && <p className="font-bold text-foreground m-0">{address.full_name}</p>}
        <p className="m-0">{address.line1}</p>
        {address.line2 && <p className="m-0">{address.line2}</p>}
        <p className="m-0">{[address.city, address.state, address.postal_code].filter(Boolean).join(', ')}</p>
        {address.country && <p className="m-0">{address.country}</p>}
        {address.phone && <p className="m-0 mt-1">{address.phone}</p>}
      </div>
    ) : (
      <p className="text-sm text-muted-foreground">{fallback}</p>
    )}
  </div>
);

export default AddressCard;