/** "3m ago", "5h ago", "2d ago". Shared so cards and comments agree. */
export function timeAgo(iso: string): string {
  const minutes = (Date.now() - new Date(iso).getTime()) / 60000;
  if (minutes < 60) return `${Math.max(1, Math.round(minutes))}m ago`;
  if (minutes < 2880) return `${Math.round(minutes / 60)}h ago`;
  return `${Math.round(minutes / 1440)}d ago`;
}
