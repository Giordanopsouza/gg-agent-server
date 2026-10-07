const paths = {
  home: "m3 10 9-7 9 7v10a1 1 0 0 1-1 1h-5v-8H9v8H4a1 1 0 0 1-1-1Z",
  tasks: "m3 6 2 2 3-4M11 6h10M3 12l2 2 3-4M11 12h10M3 18l2 2 3-4M11 18h10",
  settings: "M4 6h16M4 12h16M4 18h16M8 3v6M16 9v6M10 15v6",
  search: "M21 21l-5-5M18 10a8 8 0 1 1-16 0 8 8 0 0 1 16 0",
  panel: "M9 3v18M4 3h16a1 1 0 0 1 1 1v16a1 1 0 0 1-1 1H4a1 1 0 0 1-1-1V4a1 1 0 0 1 1-1Z",
  plus: "M12 5v14M5 12h14",
  chevron: "m6 9 6 6 6-6",
  branch: "M6 7v10M18 7v3a5 5 0 0 1-5 5H6M9 4a3 3 0 1 1-6 0 3 3 0 0 1 6 0M9 20a3 3 0 1 1-6 0 3 3 0 0 1 6 0M21 4a3 3 0 1 1-6 0 3 3 0 0 1 6 0",
  send: "m21 3-7 18-4-7-7-4 18-7ZM10 14 21 3",
  sparkles: "m12 3 2.5 6.5L21 12l-6.5 2.5L12 21l-2.5-6.5L3 12l6.5-2.5L12 3Z",
  refresh: "M20 7a9 9 0 1 0 1 9M20 3v5h-5",
  arrow: "M5 12h14m-6-6 6 6-6 6",
  check: "m5 12 4 4L19 6",
  circle: "M21 12a9 9 0 1 1-18 0 9 9 0 0 1 18 0",
  logout: "M9 3H4v18h5M10 12h11m-5-5 5 5-5 5",
  loader: "M21 12a9 9 0 1 1-9-9",
  logo: "M3 3h12v5H3ZM3 10h7v11H3ZM12 10h9v5h-9ZM16 17h5v4h-5Z",
} as const;

export function Icon({ name }: { name: keyof typeof paths }) {
  return <svg className={`icon icon-${name}`} width="20" height="20" viewBox="0 0 24 24" fill={name === "logo" ? "currentColor" : "none"} stroke={name === "logo" ? "none" : "currentColor"} strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><path d={paths[name]} /></svg>;
}
