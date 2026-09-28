import { isNative } from "./platform.js";

const SITE = (import.meta.env.VITE_WEBSITE_URL || "").trim().replace(/\/+$/, "");

export function siteUrl(path = "/") {
  const base = SITE || (isNative ? "" : window.location.origin);
  return base ? `${base}${path}` : "";
}

function cancelled(error) {
  const message = String(error?.message || error || "").toLowerCase();
  return error?.name === "AbortError" || message.includes("cancel");
}

export async function shareLink({ title, text, url }) {
  try {
    if (isNative) {
      const { Share } = await import("@capacitor/share");
      await Share.share({ title, text, url: url || undefined, dialogTitle: title });
      return "shared";
    }
    if (navigator.share) {
      await navigator.share({ title, text, url: url || undefined });
      return "shared";
    }
    await navigator.clipboard.writeText([text, url].filter(Boolean).join(" "));
    return "copied";
  } catch (error) {
    if (cancelled(error)) return "cancelled";
    throw error;
  }
}

function base64Of(blob) {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(String(reader.result).split(",")[1] || "");
    reader.onerror = () => reject(reader.error);
    reader.readAsDataURL(blob);
  });
}

export async function shareFile(blob, fileName, { title = fileName } = {}) {
  const [{ Filesystem, Directory }, { Share }] = await Promise.all([
    import("@capacitor/filesystem"),
    import("@capacitor/share"),
  ]);
  const written = await Filesystem.writeFile({ path: fileName, data: await base64Of(blob), directory: Directory.Cache });
  try {
    await Share.share({ title, files: [written.uri], dialogTitle: title });
  } catch (error) {
    if (!cancelled(error)) throw error;
  }
  return fileName;
}

function snapshot(canvas, background) {
  const copy = document.createElement("canvas");
  copy.width = canvas.width;
  copy.height = canvas.height;
  const context = copy.getContext("2d");
  context.fillStyle = background;
  context.fillRect(0, 0, copy.width, copy.height);
  context.drawImage(canvas, 0, 0);
  return copy;
}

function toBlob(canvas) {
  return new Promise((resolve, reject) => {
    canvas.toBlob((blob) => (blob ? resolve(blob) : reject(new Error("Could not capture the image"))), "image/png");
  });
}

export async function shareCanvas(canvas, { title, text, fileName, background }) {
  const image = snapshot(canvas, background);
  try {
    if (isNative) {
      const [{ Filesystem, Directory }, { Share }] = await Promise.all([
        import("@capacitor/filesystem"),
        import("@capacitor/share"),
      ]);
      const data = image.toDataURL("image/png").split(",")[1];
      const written = await Filesystem.writeFile({ path: fileName, data, directory: Directory.Cache });
      await Share.share({ title, text, files: [written.uri], dialogTitle: title });
      return "shared";
    }
    const blob = await toBlob(image);
    const file = new File([blob], fileName, { type: "image/png" });
    if (navigator.canShare?.({ files: [file] })) {
      await navigator.share({ title, text, files: [file] });
      return "shared";
    }
    const link = document.createElement("a");
    link.href = URL.createObjectURL(blob);
    link.download = fileName;
    document.body.append(link);
    link.click();
    link.remove();
    setTimeout(() => URL.revokeObjectURL(link.href), 1000);
    return "downloaded";
  } catch (error) {
    if (cancelled(error)) return "cancelled";
    throw error;
  }
}
