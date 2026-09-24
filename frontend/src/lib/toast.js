const HOST_ID = "toasts";

export function toast(message, variant = "info", timeout = 4200) {
  const host = document.getElementById(HOST_ID);
  if (!host) return;
  const node = document.createElement("div");
  node.className = `toast toast-${variant}`;
  node.textContent = message;
  host.append(node);
  setTimeout(() => {
    node.style.opacity = "0";
    node.style.transition = "opacity 160ms";
    setTimeout(() => node.remove(), 180);
  }, timeout);
}

export const notify = {
  info: (message) => toast(message, "info"),
  success: (message) => toast(message, "success"),
  error: (message) => toast(message, "error", 6000),
};
