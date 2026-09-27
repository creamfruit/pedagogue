const CLUSTER_X = 0.8;
const CLUSTER_Y = 0.2;
const TAIL = 30;
const HEAD = 3.4;

export function layoutMeteors(pieces, width, height) {
  const open = pieces.filter((piece) => piece.state === "open");
  const cx = width * CLUSTER_X;
  const cy = height * CLUSTER_Y;
  const spread = Math.min(width, height) * 0.14;
  return open.map((piece, index) => {
    const angle = index * 2.399963 + 0.6;
    const reach = spread * Math.sqrt((index + 0.6) / Math.max(open.length, 1));
    return {
      piece,
      x: Math.min(Math.max(cx + Math.cos(angle) * reach, 40), width - 24),
      y: Math.min(Math.max(cy + Math.sin(angle) * reach, 36), height - 24),
      phase: index * 1.7,
    };
  });
}

export function clusterCentre(width, height) {
  return { x: width * CLUSTER_X, y: height * CLUSTER_Y };
}

export function meteorAt(meteors, point, slack) {
  let best = null;
  let bestDistance = Infinity;
  meteors.forEach((meteor) => {
    const distance = Math.hypot(meteor.x - point.x, meteor.y - point.y);
    if (distance <= slack && distance < bestDistance) {
      best = meteor;
      bestDistance = distance;
    }
  });
  return best;
}

export function drawMeteors(ctx, meteors, { colors, clock, reduceMotion, hovered, k, label, centre, bounds }) {
  if (!meteors.length) return;
  const direction = { x: 0.78, y: -0.62 };
  meteors.forEach((meteor) => {
    const active = meteor === hovered;
    const shimmer = reduceMotion ? 1 : 0.8 + 0.2 * Math.sin(clock * 0.07 + meteor.phase);
    const length = (TAIL * shimmer * (active ? 1.25 : 1)) / Math.sqrt(k);
    const tail = ctx.createLinearGradient(meteor.x, meteor.y, meteor.x + direction.x * length, meteor.y + direction.y * length);
    tail.addColorStop(0, colors.accent);
    tail.addColorStop(1, "rgba(0,0,0,0)");
    ctx.strokeStyle = tail;
    ctx.lineCap = "round";
    ctx.lineWidth = (active ? 2.6 : 1.8) / k;
    ctx.globalAlpha = active ? 1 : 0.85;
    ctx.beginPath();
    ctx.moveTo(meteor.x, meteor.y);
    ctx.lineTo(meteor.x + direction.x * length, meteor.y + direction.y * length);
    ctx.stroke();

    const glow = ctx.createRadialGradient(meteor.x, meteor.y, 0, meteor.x, meteor.y, HEAD * 4);
    glow.addColorStop(0, colors.accent);
    glow.addColorStop(1, "rgba(0,0,0,0)");
    ctx.globalAlpha = (active ? 0.5 : 0.3) * shimmer;
    ctx.fillStyle = glow;
    ctx.beginPath();
    ctx.arc(meteor.x, meteor.y, HEAD * 4, 0, Math.PI * 2);
    ctx.fill();

    ctx.globalAlpha = 1;
    ctx.fillStyle = colors.starlight;
    ctx.beginPath();
    ctx.arc(meteor.x, meteor.y, (active ? HEAD * 1.2 : HEAD) / Math.sqrt(k), 0, Math.PI * 2);
    ctx.fill();

    if (active) {
      ctx.font = `${11 / k}px 'JetBrains Mono', monospace`;
      ctx.fillStyle = colors.text;
      ctx.textAlign = "center";
      const title = meteor.piece.title.length > 30 ? `${meteor.piece.title.slice(0, 29)}…` : meteor.piece.title;
      ctx.fillText(title, meteor.x, meteor.y + 18 / k);
    }
  });
  if (label && centre) {
    const top = Math.min(...meteors.map((meteor) => meteor.y));
    ctx.globalAlpha = 0.9;
    ctx.font = `${10.5 / k}px 'JetBrains Mono', monospace`;
    ctx.fillStyle = colors.accent;
    ctx.textAlign = "center";
    const half = ctx.measureText(label).width / 2 + 8 / k;
    const x = bounds ? Math.min(Math.max(centre.x, bounds.left + half), bounds.right - half) : centre.x;
    ctx.fillText(label, x, Math.max(top - 22 / k, 14));
  }
  ctx.globalAlpha = 1;
  ctx.lineCap = "butt";
}
