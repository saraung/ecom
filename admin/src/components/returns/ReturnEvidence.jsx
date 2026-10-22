import React, { useEffect, useState } from 'react';
import { returnAPI } from '../../api/returns';

export default function ReturnEvidence({ returnId, image }) {
  const [url, setUrl] = useState(null);
  const [failed, setFailed] = useState(false);
  const [retry, setRetry] = useState(0);
  useEffect(() => {
    let active = true;
    let value;
    returnAPI.evidence(returnId, image.id).then(({ data }) => {
      if (!active) return;
      value = URL.createObjectURL(data);
      setUrl(value); setFailed(false);
    }).catch(() => { if (active) setFailed(true); });
    return () => { active = false; if (value) URL.revokeObjectURL(value); };
  }, [returnId, image.id, retry]);
  return <div className="rounded-xl border border-border overflow-hidden">
    {url ? <a href={url} target="_blank" rel="noreferrer" aria-label="Open full return evidence photo"><img src={url} alt="Customer return evidence" className="aspect-square w-full object-cover" /></a>
      : <div className="aspect-square flex items-center justify-center text-xs text-muted-foreground bg-muted p-3 text-center">{failed ? <button type="button" onClick={() => { setFailed(false); setRetry((value) => value + 1); }}>Photo unavailable · Retry</button> : 'Loading private photo…'}</div>}
    <p className="p-2 text-xs text-muted-foreground">{Math.ceil(image.size_bytes / 1024)} KB · Private</p>
  </div>;
}
