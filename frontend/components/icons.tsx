import type { SVGProps } from "react";

type P = SVGProps<SVGSVGElement>;

export const CameraIcon = (p: P) => (
  <svg width="20" height="20" viewBox="0 0 24 24" fill="none" {...p}>
    <path d="M3 8.5A2.5 2.5 0 0 1 5.5 6h1.2l1-1.8A1 1 0 0 1 8.6 3.7h6.8a1 1 0 0 1 .9.5l1 1.8h1.2A2.5 2.5 0 0 1 21 8.5v8A2.5 2.5 0 0 1 18.5 19h-13A2.5 2.5 0 0 1 3 16.5v-8Z" stroke="currentColor" strokeWidth="1.7" />
    <circle cx="12" cy="12.3" r="3.4" stroke="currentColor" strokeWidth="1.7" />
  </svg>
);
export const CheckIcon = (p: P) => (
  <svg width="16" height="16" viewBox="0 0 24 24" fill="none" {...p}>
    <path d="M5 12.8 10 17.5 19.5 6.5" stroke="currentColor" strokeWidth="2.6" strokeLinecap="round" strokeLinejoin="round" />
  </svg>
);
export const CrossIcon = (p: P) => (
  <svg width="15" height="15" viewBox="0 0 24 24" fill="none" {...p}>
    <path d="M6 6 18 18M18 6 6 18" stroke="currentColor" strokeWidth="2.6" strokeLinecap="round" />
  </svg>
);
export const WarnIcon = (p: P) => (
  <svg width="15" height="15" viewBox="0 0 24 24" fill="none" {...p}>
    <path d="M12 8.5v5.2M12 17h0" stroke="currentColor" strokeWidth="2.6" strokeLinecap="round" />
  </svg>
);
export const DashIcon = (p: P) => (
  <svg width="14" height="14" viewBox="0 0 24 24" fill="none" {...p}>
    <path d="M7 12h10" stroke="currentColor" strokeWidth="2.4" strokeLinecap="round" />
  </svg>
);
export const ChevRightIcon = (p: P) => (
  <svg width="18" height="18" viewBox="0 0 24 24" fill="none" {...p}>
    <path d="M9 5l7 7-7 7" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
  </svg>
);
export const ChevLeftIcon = (p: P) => (
  <svg width="20" height="20" viewBox="0 0 24 24" fill="none" {...p}>
    <path d="M15 5l-7 7 7 7" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
  </svg>
);
export const ShieldIcon = (p: P) => (
  <svg width="17" height="17" viewBox="0 0 24 24" fill="none" {...p}>
    <path d="M12 3 5 5.6v5.2c0 4.3 2.9 7.6 7 9.2 4.1-1.6 7-4.9 7-9.2V5.6L12 3Z" stroke="currentColor" strokeWidth="1.8" strokeLinejoin="round" />
    <path d="M9 12l2 2 4-4.2" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" />
  </svg>
);
export const CompareIcon = (p: P) => (
  <svg width="18" height="18" viewBox="0 0 24 24" fill="none" {...p}>
    <circle cx="9" cy="12" r="6.2" stroke="currentColor" strokeWidth="1.9" />
    <circle cx="15" cy="12" r="6.2" stroke="currentColor" strokeWidth="1.9" />
  </svg>
);
export const ExtIcon = (p: P) => (
  <svg width="13" height="13" viewBox="0 0 24 24" fill="none" {...p}>
    <path d="M14 5h5v5M19 5l-8 8M17 14v4a1 1 0 0 1-1 1H6a1 1 0 0 1-1-1V8a1 1 0 0 1 1-1h4" stroke="currentColor" strokeWidth="1.9" strokeLinecap="round" strokeLinejoin="round" />
  </svg>
);
export const PlusIcon = (p: P) => (
  <svg width="18" height="18" viewBox="0 0 24 24" fill="none" {...p}>
    <path d="M12 5v14M5 12h14" stroke="currentColor" strokeWidth="2.1" strokeLinecap="round" />
  </svg>
);
