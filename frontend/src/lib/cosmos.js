import { isNative } from "./platform.js";
import { onMotionChange, reducedMotion } from "./motion.js";

export const PHONE_WIDTH = 760;
export const PHONE_STAR_SHARE = 0.4;
const PHONE_FRAME_MS = 1000 / 20;

export function isPhoneScreen(width = window.innerWidth) {
  return width <= PHONE_WIDTH;
}

export function starShare(width) {
  return isPhoneScreen(width) ? PHONE_STAR_SHARE : 1;
}

const LAYERS = [
  { density: 0.00022, size: [0.35, 0.9], alpha: [0.25, 0.6], depth: 0.02, twinkle: 0.25 },
  { density: 0.00008, size: [0.7, 1.3], alpha: [0.4, 0.8], depth: 0.06, twinkle: 0.45 },
  { density: 0.000018, size: [1.1, 1.9], alpha: [0.6, 1], depth: 0.12, twinkle: 0.7 },
];
const TINTS = ["238,245,243", "206,233,226", "111,183,179", "181,161,175", "255,244,226"];
const FRAME_MS = 1000 / 30;

function rand(min, max) {
  return min + Math.random() * (max - min);
}

function paintNebula(width, height) {
  const canvas = document.createElement("canvas");
  canvas.width = width;
  canvas.height = height;
  const ctx = canvas.getContext("2d");
  const clouds = [
    [0.12, 0.08, 0.55, "17,65,75", 0.55],
    [0.86, 0.2, 0.42, "181,161,175", 0.16],
    [0.7, 0.78, 0.5, "33,48,79", 0.5],
    [0.25, 0.9, 0.38, "111,183,179", 0.08],
    [0.5, 0.45, 0.3, "206,233,226", 0.035],
  ];
  const span = Math.max(width, height);
  clouds.forEach(([x, y, r, rgb, a]) => {
    const gradient = ctx.createRadialGradient(x * width, y * height, 0, x * width, y * height, r * span);
    gradient.addColorStop(0, `rgba(${rgb},${a})`);
    gradient.addColorStop(0.5, `rgba(${rgb},${a * 0.35})`);
    gradient.addColorStop(1, `rgba(${rgb},0)`);
    ctx.fillStyle = gradient;
    ctx.fillRect(0, 0, width, height);
  });
  ctx.save();
  ctx.translate(width * 0.5, height * 0.5);
  ctx.rotate(-0.42);
  const band = ctx.createLinearGradient(0, -height * 0.18, 0, height * 0.18);
  band.addColorStop(0, "rgba(206,233,226,0)");
  band.addColorStop(0.5, "rgba(206,233,226,0.045)");
  band.addColorStop(1, "rgba(206,233,226,0)");
  ctx.fillStyle = band;
  ctx.fillRect(-span, -height * 0.18, span * 2, height * 0.36);
  for (let i = 0; i < (width * height) / 900; i += 1) {
    const along = rand(-span, span);
    const across = (Math.random() + Math.random() + Math.random() - 1.5) * height * 0.12;
    ctx.fillStyle = `rgba(238,245,243,${rand(0.04, 0.22)})`;
    ctx.fillRect(along, across, 1, 1);
  }
  ctx.restore();
  return canvas;
}

export function starCount(width, height, layer) {
  return Math.round(width * height * layer.density * starShare(width));
}

function makeStars(width, height) {
  return LAYERS.flatMap((layer, depthIndex) =>
    Array.from({ length: starCount(width, height, layer) }, () => ({
      x: Math.random() * width,
      y: Math.random() * height,
      r: rand(...layer.size),
      a: rand(...layer.alpha),
      tint: TINTS[Math.random() < 0.7 ? 0 : Math.floor(rand(1, TINTS.length))],
      phase: Math.random() * Math.PI * 2,
      speed: rand(0.4, 1.4),
      twinkle: layer.twinkle,
      depth: layer.depth,
      glint: depthIndex === 2 && Math.random() < 0.35,
    }))
  );
}

export function startCosmos() {
  if (document.querySelector(".cosmos")) return () => {};
  const canvas = document.createElement("canvas");
  canvas.className = "cosmos";
  canvas.setAttribute("aria-hidden", "true");
  document.body.prepend(canvas);
  const ctx = canvas.getContext("2d");
  const phone = () => isPhoneScreen();
  let hidden = false;
  let width = 0;
  let height = 0;
  let dpr = 1;
  let stars = [];
  let nebula = null;
  let meteor = null;
  let nextMeteor = performance.now() + rand(4000, 9000);
  let raf = null;
  let last = 0;
  let pointerX = 0;
  let pointerY = 0;
  let targetX = 0;
  let targetY = 0;

  function resize() {
    dpr = phone() ? 1 : Math.min(window.devicePixelRatio || 1, 1.5);
    width = window.innerWidth;
    height = window.innerHeight;
    canvas.width = Math.round(width * dpr);
    canvas.height = Math.round(height * dpr);
    canvas.style.width = `${width}px`;
    canvas.style.height = `${height}px`;
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    stars = makeStars(width, height);
    nebula = paintNebula(Math.round(width / 2), Math.round(height / 2));
    draw(performance.now());
  }

  function spawnMeteor(now) {
    const fromLeft = Math.random() < 0.5;
    const angle = rand(0.35, 0.65) * (fromLeft ? 1 : -1);
    meteor = {
      x: fromLeft ? rand(-40, width * 0.5) : rand(width * 0.5, width + 40),
      y: rand(-20, height * 0.35),
      vx: Math.cos(angle) * (fromLeft ? 1 : -1) * rand(0.9, 1.3),
      vy: Math.abs(Math.sin(angle)) * rand(0.9, 1.3),
      born: now,
      life: rand(700, 1100),
      length: rand(90, 170),
    };
    nextMeteor = now + rand(9000, 22000);
  }

  function drawMeteor(now) {
    if (!meteor) return;
    const age = now - meteor.born;
    if (age > meteor.life) {
      meteor = null;
      return;
    }
    const t = age / meteor.life;
    const travel = age * 0.9;
    const headX = meteor.x + meteor.vx * travel;
    const headY = meteor.y + meteor.vy * travel;
    const tailX = headX - meteor.vx * meteor.length;
    const tailY = headY - meteor.vy * meteor.length;
    const fade = Math.sin(Math.PI * t);
    const gradient = ctx.createLinearGradient(headX, headY, tailX, tailY);
    gradient.addColorStop(0, `rgba(238,245,243,${0.9 * fade})`);
    gradient.addColorStop(0.3, `rgba(206,233,226,${0.35 * fade})`);
    gradient.addColorStop(1, "rgba(206,233,226,0)");
    ctx.strokeStyle = gradient;
    ctx.lineWidth = 1.4;
    ctx.lineCap = "round";
    ctx.beginPath();
    ctx.moveTo(headX, headY);
    ctx.lineTo(tailX, tailY);
    ctx.stroke();
  }

  function draw(now) {
    pointerX += (targetX - pointerX) * 0.06;
    pointerY += (targetY - pointerY) * 0.06;
    ctx.clearRect(0, 0, width, height);
    const still = reducedMotion();
    const scroll = still ? 0 : window.scrollY || 0;
    if (nebula) {
      ctx.globalAlpha = 1;
      ctx.drawImage(nebula, pointerX * -6, (scroll * -0.01) % height + pointerY * -6, width + 12, height + 12);
    }
    const seconds = now / 1000;
    stars.forEach((star) => {
      const shimmer = still ? 1 : 1 - star.twinkle * 0.5 * (1 + Math.sin(seconds * star.speed + star.phase));
      const x = (star.x - pointerX * star.depth * 40 + width) % width;
      const y = (((star.y - scroll * star.depth) % height) + height - pointerY * star.depth * 40) % height;
      const alpha = star.a * shimmer;
      ctx.fillStyle = `rgba(${star.tint},${alpha})`;
      ctx.beginPath();
      ctx.arc(x, y, star.r, 0, Math.PI * 2);
      ctx.fill();
      if (star.glint && alpha > 0.55) {
        ctx.strokeStyle = `rgba(${star.tint},${(alpha - 0.45) * 0.6})`;
        ctx.lineWidth = 0.6;
        ctx.beginPath();
        ctx.moveTo(x - star.r * 4, y);
        ctx.lineTo(x + star.r * 4, y);
        ctx.moveTo(x, y - star.r * 4);
        ctx.lineTo(x, y + star.r * 4);
        ctx.stroke();
      }
    });
    if (!still && !phone()) {
      if (!meteor && now > nextMeteor) spawnMeteor(now);
      drawMeteor(now);
    }
  }

  function frame(now) {
    raf = requestAnimationFrame(frame);
    if (now - last < (phone() ? PHONE_FRAME_MS : FRAME_MS)) return;
    last = now;
    draw(now);
  }

  function paused() {
    return document.hidden || hidden || document.body.classList.contains("immersive");
  }

  function play() {
    if (raf || reducedMotion() || paused()) return;
    raf = requestAnimationFrame(frame);
  }

  function pause() {
    if (raf) cancelAnimationFrame(raf);
    raf = null;
  }

  function onVisibility() {
    if (paused()) pause();
    else play();
  }

  function onAppState({ isActive }) {
    hidden = !isActive;
    onVisibility();
  }

  const immersive = new MutationObserver(onVisibility);
  immersive.observe(document.body, { attributes: true, attributeFilter: ["class"] });
  let appListener = null;
  if (isNative) {
    import("@capacitor/app")
      .then(({ App }) => App.addListener("appStateChange", onAppState))
      .then((handle) => {
        appListener = handle;
      })
      .catch(() => null);
  }

  function onPointer(event) {
    targetX = event.clientX / Math.max(width, 1) - 0.5;
    targetY = event.clientY / Math.max(height, 1) - 0.5;
  }

  function onScroll() {
    if (!raf && !reducedMotion() && !paused()) draw(performance.now());
  }

  function onMotion() {
    if (reducedMotion()) {
      pause();
      draw(performance.now());
    } else play();
  }

  resize();
  play();
  window.addEventListener("resize", resize);
  window.addEventListener("scroll", onScroll, { passive: true });
  if (!phone()) window.addEventListener("pointermove", onPointer, { passive: true });
  document.addEventListener("visibilitychange", onVisibility);
  window.addEventListener("pagehide", pause);
  window.addEventListener("pageshow", onVisibility);
  const stopMotion = onMotionChange(onMotion);

  return () => {
    stopMotion();
    immersive.disconnect();
    if (appListener) appListener.remove();
    window.removeEventListener("pagehide", pause);
    window.removeEventListener("pageshow", onVisibility);
    pause();
    window.removeEventListener("resize", resize);
    window.removeEventListener("scroll", onScroll);
    window.removeEventListener("pointermove", onPointer);
    document.removeEventListener("visibilitychange", onVisibility);
    canvas.remove();
  };
}
