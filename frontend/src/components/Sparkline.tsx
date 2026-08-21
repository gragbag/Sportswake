/**
 * Publication volume across a story's lifespan.
 *
 * This is the bit competitors don't show. An article count tells you a story
 * was big; the shape tells you whether it broke all at once or built slowly,
 * which is the thing Presswake is actually about.
 *
 * Inherits color via currentColor, so the parent decides how loud it is.
 *
 * Square ticks, not rounded bars. A 1px radius on a 2px mark is a radius you
 * cannot see and an idiom you can -- and this page has no other rounded
 * corner on it.
 */
export function Sparkline({
  buckets,
  className = "",
}: {
  buckets: number[];
  className?: string;
}) {
  // An empty bucket list would compute a NEGATIVE svg width, which is invalid
  // and silently drops the element. The feed always sends ten, but this
  // component should not be the thing that breaks if an endpoint ever sends
  // none.
  if (buckets.length === 0) return null;

  const peak = Math.max(...buckets, 1);
  const barWidth = 2;
  const gap = 2;
  const height = 16;

  return (
    <svg
      width={buckets.length * (barWidth + gap) - gap}
      height={height}
      className={className}
      aria-hidden="true"
      focusable="false"
    >
      {buckets.map((count, i) => {
        // Floor at 1px so empty stretches still read as a baseline rather
        // than a gap -- a gap looks like missing data, not like quiet.
        const barHeight = Math.max(1, (count / peak) * height);
        return (
          <rect
            key={i}
            x={i * (barWidth + gap)}
            y={height - barHeight}
            width={barWidth}
            height={barHeight}
            fill="currentColor"
            opacity={count === 0 ? 0.3 : 1}
          />
        );
      })}
    </svg>
  );
}
