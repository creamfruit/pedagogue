const cache = new Map();
let osmdModule = null;

function loadEngine() {
  if (!osmdModule) {
    osmdModule = import("opensheetmusicdisplay").catch((error) => {
      osmdModule = null;
      throw error;
    });
  }
  return osmdModule;
}

function fetchText(url) {
  if (!cache.has(url)) {
    cache.set(
      url,
      fetch(url).then((response) => {
        if (!response.ok) {
          cache.delete(url);
          throw new Error("Score file missing");
        }
        return response.text();
      })
    );
  }
  return cache.get(url);
}

function ink() {
  const styles = getComputedStyle(document.documentElement);
  return (styles.getPropertyValue("--score-ink") || styles.getPropertyValue("--text") || "#e8e6f0").trim();
}

export async function renderScore(host, url, { zoom = 0.72 } = {}) {
  const [{ OpenSheetMusicDisplay }, xml] = await Promise.all([loadEngine(), fetchText(url)]);
  const color = ink();
  host.replaceChildren();
  const display = new OpenSheetMusicDisplay(host, {
    autoResize: true,
    backend: "svg",
    drawTitle: false,
    drawSubtitle: false,
    drawComposer: false,
    drawLyricist: false,
    drawCredits: false,
    drawPartNames: false,
    drawPartAbbreviations: false,
    drawMeasureNumbers: true,
    drawMetronomeMarks: false,
    drawingParameters: "compacttight",
    defaultColorMusic: color,
    defaultColorNotehead: color,
    defaultColorStem: color,
    defaultColorRest: color,
    defaultColorLabel: color,
    defaultColorTitle: color,
  });
  await display.load(xml);
  display.zoom = zoom;
  display.render();
  return display;
}
