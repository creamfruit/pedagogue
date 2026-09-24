export const DRIFT = {
  linearDrag: 0.026,
  quadraticDrag: 0.0032,
  maxDamping: 0.20,
  currentStrength: 0.0058,
  currentScale: 0.0021,
  currentSpeed: 0.0022,
  turbulence: 0.0014,
  creepDamping: 0.085,
  creepSpeed: 4.5,
  wakeRadius: 130,
  wakeStrength: 0.22,
  wakeThreshold: 1.6,
  grabStiffness: 0.24,
  grabDamping: 0.55,
  throwBoost: 1.25,
  maxThrowSpeed: 34,
  wallPadding: 6,
  wallBounce: 0.32,
  wallSlip: 0.86,
  restSpeed: 0.035,
};

export function massOf(node) {
  const radius = node.radius || 8;
  return Math.max(0.45, (radius * radius) / 190);
}

export function prepareNodes(nodes) {
  nodes.forEach((node) => {
    node.mass = massOf(node);
    node.buoyancy = 1 / node.mass;
    node.phase = Math.random() * Math.PI * 2;
    node.grab = null;
  });
  return nodes;
}

export function forceDrift(options = {}) {
  const config = { ...DRIFT, ...options };
  let nodes = [];
  let bounds = null;
  let clock = 0;
  let ambient = true;

  function currentAt(x, y, phase) {
    const t = clock * config.currentSpeed;
    const sx = x * config.currentScale;
    const sy = y * config.currentScale;
    return {
      x: Math.sin(sy + t + phase) + 0.55 * Math.sin(sx * 0.7 - t * 1.31),
      y: Math.cos(sx - t * 1.17) + 0.55 * Math.cos(sy * 0.8 + t * 0.83 + phase),
    };
  }

  function force() {
    clock += 1;
    let fastest = 0;

    for (const node of nodes) {
      if (node.fx != null || node.fy != null) continue;

      if (node.grab) {
        const dx = node.grab.x - node.x;
        const dy = node.grab.y - node.y;
        const pull = config.grabStiffness / Math.sqrt(node.mass);
        node.vx += dx * pull - node.vx * config.grabDamping;
        node.vy += dy * pull - node.vy * config.grabDamping;
        continue;
      }

      const speed = Math.hypot(node.vx, node.vy);
      if (speed > fastest) fastest = speed;

      const creep =
        speed < config.creepSpeed
          ? (1 - speed / config.creepSpeed) * config.creepDamping
          : 0;
      const damping =
        Math.min(
          config.linearDrag + config.quadraticDrag * speed + creep,
          config.maxDamping
        ) / Math.sqrt(node.mass);
      node.vx -= node.vx * damping;
      node.vy -= node.vy * damping;

      if (ambient) {
        const flow = currentAt(node.x, node.y, node.phase);
        const lift = config.currentStrength * node.buoyancy;
        node.vx += flow.x * lift;
        node.vy += flow.y * lift;
        node.vx += (Math.random() - 0.5) * config.turbulence * node.buoyancy;
        node.vy += (Math.random() - 0.5) * config.turbulence * node.buoyancy;
      }

      if (speed < config.restSpeed && !ambient) {
        node.vx = 0;
        node.vy = 0;
      }
    }

    if (fastest > config.wakeThreshold) applyWake();
    if (bounds) applyWalls();
  }

  function applyWake() {
    const radiusSq = config.wakeRadius * config.wakeRadius;
    for (const source of nodes) {
      const speed = Math.hypot(source.vx, source.vy);
      if (speed < config.wakeThreshold) continue;
      const push = (speed / config.maxThrowSpeed) * config.wakeStrength;
      for (const other of nodes) {
        if (other === source || other.grab) continue;
        const dx = other.x - source.x;
        const dy = other.y - source.y;
        const distSq = dx * dx + dy * dy;
        if (distSq > radiusSq || distSq < 1) continue;
        const falloff = 1 - distSq / radiusSq;
        const dist = Math.sqrt(distSq);
        const scale = (push * falloff * falloff) / Math.sqrt(other.mass);
        other.vx += (dx / dist) * scale;
        other.vy += (dy / dist) * scale;
      }
    }
  }

  function applyWalls() {
    const { width, height } = bounds;
    for (const node of nodes) {
      const pad = (node.radius || 8) + config.wallPadding;
      if (node.x < pad) {
        node.x = pad;
        node.vx = Math.abs(node.vx) * config.wallBounce;
        node.vy *= config.wallSlip;
      } else if (node.x > width - pad) {
        node.x = width - pad;
        node.vx = -Math.abs(node.vx) * config.wallBounce;
        node.vy *= config.wallSlip;
      }
      if (node.y < pad) {
        node.y = pad;
        node.vy = Math.abs(node.vy) * config.wallBounce;
        node.vx *= config.wallSlip;
      } else if (node.y > height - pad) {
        node.y = height - pad;
        node.vy = -Math.abs(node.vy) * config.wallBounce;
        node.vx *= config.wallSlip;
      }
    }
  }

  force.initialize = (loaded) => {
    nodes = loaded;
    prepareNodes(nodes);
  };

  force.bounds = (value) => {
    bounds = value;
    return force;
  };

  force.ambient = (value) => {
    if (value === undefined) return ambient;
    ambient = value;
    return force;
  };

  force.config = config;
  return force;
}

export function grab(node, point) {
  node.grab = { x: point.x, y: point.y };
  node.grabbedAt = { x: point.x, y: point.y, time: performance.now() };
}

export function moveGrab(node, point) {
  if (!node.grab) return;
  node.grab.x = point.x;
  node.grab.y = point.y;
}

export function release(node, pointerVelocity, config = DRIFT) {
  if (!node.grab) return { x: 0, y: 0 };
  node.grab = null;
  const blended = {
    x: node.vx + (pointerVelocity?.x || 0) * config.throwBoost,
    y: node.vy + (pointerVelocity?.y || 0) * config.throwBoost,
  };
  const speed = Math.hypot(blended.x, blended.y);
  if (speed > config.maxThrowSpeed) {
    const scale = config.maxThrowSpeed / speed;
    blended.x *= scale;
    blended.y *= scale;
  }
  node.vx = blended.x;
  node.vy = blended.y;
  return blended;
}

export function createPointerTracker(sampleWindow = 90) {
  let samples = [];
  return {
    reset() {
      samples = [];
    },
    push(point) {
      const now = performance.now();
      samples.push({ x: point.x, y: point.y, time: now });
      while (samples.length > 2 && now - samples[0].time > sampleWindow) samples.shift();
    },
    velocity() {
      if (samples.length < 2) return { x: 0, y: 0 };
      const first = samples[0];
      const last = samples[samples.length - 1];
      const elapsed = last.time - first.time;
      if (elapsed <= 0) return { x: 0, y: 0 };
      const perFrame = 16.67 / elapsed;
      return { x: (last.x - first.x) * perFrame, y: (last.y - first.y) * perFrame };
    },
  };
}

export function createRipples(limit = 12) {
  const ripples = [];
  return {
    spawn(x, y, energy) {
      ripples.push({ x, y, life: 1, energy: Math.min(energy, 1) });
      while (ripples.length > limit) ripples.shift();
    },
    step(decay = 0.022) {
      for (let index = ripples.length - 1; index >= 0; index -= 1) {
        ripples[index].life -= decay;
        if (ripples[index].life <= 0) ripples.splice(index, 1);
      }
    },
    get all() {
      return ripples;
    },
  };
}
