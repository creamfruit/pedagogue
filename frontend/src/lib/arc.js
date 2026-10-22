const TAU = Math.PI * 2;
const GAP = 0.16;

function point(cx, cy, radius, angle) {
  return [cx + radius * Math.cos(angle - Math.PI / 2), cy + radius * Math.sin(angle - Math.PI / 2)];
}

export function arcPath(cx, cy, radius, from, to) {
  const [x1, y1] = point(cx, cy, radius, from);
  const [x2, y2] = point(cx, cy, radius, to);
  const large = to - from > Math.PI ? 1 : 0;
  return `M${x1.toFixed(2)} ${y1.toFixed(2)} A${radius} ${radius} 0 ${large} 1 ${x2.toFixed(2)} ${y2.toFixed(2)}`;
}

export function segmentPaths(count, { size = 56, stroke = 5 } = {}) {
  const centre = size / 2;
  const radius = centre - stroke;
  const span = TAU / Math.max(count, 1);
  const gap = count > 1 ? GAP : 0;
  return Array.from({ length: count }, (_, index) => arcPath(centre, centre, radius, index * span + gap / 2, (index + 1) * span - gap / 2));
}

export function segmentStates(count, progress, activeIndex) {
  return Array.from({ length: count }, (_, index) => {
    const found = progress.find((item) => item.index === index);
    if (found) return found.status;
    return index === activeIndex ? "active" : "todo";
  });
}
