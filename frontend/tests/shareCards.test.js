import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

function recorder() {
  const calls = [];
  const target = {
    calls,
    texts: () => calls.filter((call) => call.name === "fillText").map((call) => call.args[0]),
    measureText: (text) => ({ width: String(text).length * 20 }),
    createLinearGradient: () => ({ addColorStop: () => {} }),
  };
  return new Proxy(target, {
    get(object, key) {
      if (key in object) return object[key];
      return (...args) => {
        calls.push({ name: String(key), args });
      };
    },
    set(object, key, value) {
      object[key] = value;
      return true;
    },
  });
}

async function cards() {
  vi.resetModules();
  return import("../src/lib/shareCards.js");
}

beforeEach(() => {
  document.body.innerHTML = '<div id="toasts"></div>';
});

afterEach(() => {
  vi.restoreAllMocks();
  vi.unstubAllEnvs();
});

describe("the streak card", () => {
  it("shows the streak, how far it is to the next milestone and the best streak", async () => {
    const { streakCardModel } = await cards();
    expect(streakCardModel({ current: 12, longest: 30 })).toMatchObject({ current: 12, longest: 30, label: "days in a row", next: 14, toNext: 2, message: "2 more days to 14" });
    expect(streakCardModel({ current: 1, longest: 1 })).toMatchObject({ label: "day in a row", next: 3, message: "2 more days to 3" });
    expect(streakCardModel({ current: 13, longest: 13 }).message).toBe("1 more day to 14");
  });

  it("starts from zero without breaking", async () => {
    const { streakCardModel } = await cards();
    const model = streakCardModel(null);
    expect(model).toMatchObject({ current: 0, longest: 0, progress: 0, message: "Practise today to start a streak" });
  });

  it("never says the longest streak is shorter than the current one", async () => {
    const { streakCardModel } = await cards();
    expect(streakCardModel({ current: 9, longest: 4 }).longest).toBe(9);
  });

  it("draws the number, its label and the milestone onto the card", async () => {
    const { drawStreakCard, streakCardModel, CARD_WIDTH, CARD_HEIGHT } = await cards();
    const context = recorder();
    drawStreakCard(context, streakCardModel({ current: 12, longest: 30 }), { footer: "pedagogue.test" });
    const texts = context.texts();
    expect(texts).toEqual(expect.arrayContaining(["12", "days in a row", "2 more days to 14", "longest streak 30", "pedagogue.test", "PEDAGOGUE", "PRACTICE STREAK"]));
    expect(context.calls.some((call) => call.name === "fillRect" && call.args.join() === `0,0,${CARD_WIDTH},${CARD_HEIGHT}`)).toBe(true);
    expect(context.calls.filter((call) => call.name === "arc").length).toBeGreaterThan(90);
  });
});

describe("the piece difficulty card", () => {
  const overview = {
    title: "Étude in D-sharp minor",
    composer: { name: "Alexander Scriabin" },
    difficulty_score: "72.04",
    difficulty_band: "advanced",
    key_signature: "D-sharp minor",
    year_composed: 1895,
    duration_sec: 150,
    duration_label: "2 min 30 sec",
    sections: [
      { label: "Opening", measure_span: "bars 1–4", difficulty_score: "20" },
      { label: "Running thirds", measure_span: "bars 17–24", difficulty_score: "81" },
    ],
    techniques: [{ name: "Octaves" }, { name: "Leaps" }, { name: "Trills" }, { name: "Voicing" }],
  };

  it("summarises the score, band, hardest section and top techniques", async () => {
    const { pieceCardModel } = await cards();
    expect(pieceCardModel(overview)).toEqual({
      title: "Étude in D-sharp minor",
      composer: "Alexander Scriabin",
      score: 72,
      band: "advanced",
      facts: ["D-sharp minor", "1895", "2 min 30 sec"],
      techniques: ["Octaves", "Leaps", "Trills"],
      hardest: "Running thirds · bars 17–24",
    });
  });

  it("copes with a piece that has nothing measured yet", async () => {
    const { pieceCardModel } = await cards();
    expect(pieceCardModel({ title: "Sketch", difficulty_band: "unrated" })).toEqual({ title: "Sketch", composer: "", score: null, band: "", facts: [], techniques: [], hardest: "" });
  });

  it("colours the score by how hard it is", async () => {
    const { bandColor, PALETTE } = await cards();
    expect([bandColor(10), bandColor(45), bandColor(80)]).toEqual([PALETTE.good, PALETTE.warn, PALETTE.hot]);
  });

  it("draws the title, composer, score and sections", async () => {
    const { drawPieceCard, pieceCardModel } = await cards();
    const context = recorder();
    drawPieceCard(context, pieceCardModel(overview), { footer: "pedagogue.test" });
    expect(context.texts()).toEqual(expect.arrayContaining(["Alexander Scriabin", "72", "out of 100", "advanced", "HARDEST SECTION", "Running thirds · bars 17–24", "TECHNIQUES", "Octaves", "Leaps", "Trills", "HOW HARD IS IT?"]));
    expect(context.texts().join(" ")).toContain("Étude in D-sharp minor");
  });

  it("wraps and shortens a very long title instead of running off the card", async () => {
    const { wrapLines } = await cards();
    const lines = wrapLines(recorder(), "Grand Sonata for the Pianoforte in A-flat major with a very long descriptive title indeed", 400, 2);
    expect(lines).toHaveLength(2);
    expect(lines[1].endsWith("…")).toBe(true);
  });

  it("gives the card a file name made from the title", async () => {
    const { CARD_COPY, pieceCardModel } = await cards();
    const copy = CARD_COPY.piece(pieceCardModel(overview));
    expect(copy.fileName).toBe("pedagogue-tude-in-d-sharp-minor.png");
    expect(copy.text).toBe("Étude in D-sharp minor by Alexander Scriabin scores 72 out of 100 for difficulty on Pedagogue.");
  });
});

describe("the constellation card", () => {
  it("counts the stars", async () => {
    const { constellationCardModel, CARD_COPY } = await cards();
    expect(constellationCardModel(1)).toEqual({ count: 1, label: "star" });
    expect(CARD_COPY.constellation(constellationCardModel(14)).text).toContain("14 stars");
  });

  it("draws the sky, scaled to fit inside its frame, with the star count", async () => {
    const { drawConstellationCard, constellationCardModel } = await cards();
    const context = recorder();
    const sky = { width: 2000, height: 1000 };
    drawConstellationCard(context, constellationCardModel(14), sky, { footer: "pedagogue.test", background: "#060b15" });
    const drawn = context.calls.find((call) => call.name === "drawImage");
    expect(drawn.args[0]).toBe(sky);
    const [, x, y, width, height] = drawn.args;
    expect(width).toBeCloseTo(936);
    expect(height).toBeCloseTo(468);
    expect(x).toBeGreaterThanOrEqual(72);
    expect(y).toBeGreaterThanOrEqual(190);
    expect(context.texts()).toEqual(expect.arrayContaining(["14 stars", "MY CONSTELLATION"]));
  });

  it("still draws a card when there is no sky yet", async () => {
    const { drawConstellationCard, constellationCardModel } = await cards();
    const context = recorder();
    drawConstellationCard(context, constellationCardModel(0), null);
    expect(context.calls.some((call) => call.name === "drawImage")).toBe(false);
    expect(context.texts()).toContain("0 stars");
  });
});

describe("sharing a card", () => {
  function fakeCanvasFactory() {
    const real = document.createElement.bind(document);
    vi.spyOn(document, "createElement").mockImplementation((tag) => {
      if (tag !== "canvas") return real(tag);
      return {
        width: 0,
        height: 0,
        getContext: () => recorder(),
        toBlob: (done) => done(new Blob(["png"], { type: "image/png" })),
        toDataURL: () => "data:image/png;base64,AAAA",
      };
    });
  }

  it("downloads a PNG on the website even where the browser could share files", async () => {
    vi.resetModules();
    vi.doMock("../src/lib/platform.js", () => ({ isNative: false, isIOS: false, isAndroid: false, platformName: "web" }));
    fakeCanvasFactory();
    const share = vi.fn();
    Object.defineProperty(navigator, "canShare", { value: () => true, configurable: true });
    Object.defineProperty(navigator, "share", { value: share, configurable: true });
    URL.createObjectURL = vi.fn(() => "blob:card");
    URL.revokeObjectURL = vi.fn();
    const clicked = [];
    const original = HTMLAnchorElement.prototype.click;
    HTMLAnchorElement.prototype.click = function () {
      clicked.push(this.download);
    };
    const { shareCard, CARD_COPY, streakCardModel } = await import("../src/lib/shareCards.js");
    const result = await shareCard({ width: 1080, height: 1350 }, CARD_COPY.streak(streakCardModel({ current: 5, longest: 5 })));
    HTMLAnchorElement.prototype.click = original;
    expect(result).toBe("downloaded");
    expect(clicked).toEqual(["pedagogue-streak-5.png"]);
    expect(share).not.toHaveBeenCalled();
  });

  it("opens the share sheet inside the apps", async () => {
    vi.resetModules();
    vi.doMock("../src/lib/platform.js", () => ({ isNative: true, isIOS: true, isAndroid: false, platformName: "ios" }));
    const written = vi.fn(async () => ({ uri: "file:///cache/pedagogue-streak-5.png" }));
    const sheet = vi.fn(async () => {});
    vi.doMock("@capacitor/filesystem", () => ({ Filesystem: { writeFile: written }, Directory: { Cache: "CACHE" } }));
    vi.doMock("@capacitor/share", () => ({ Share: { share: sheet } }));
    fakeCanvasFactory();
    const { shareCard, CARD_COPY, streakCardModel } = await import("../src/lib/shareCards.js");
    const result = await shareCard({ width: 1080, height: 1350 }, CARD_COPY.streak(streakCardModel({ current: 5, longest: 5 })));
    expect(result).toBe("shared");
    expect(written).toHaveBeenCalledWith(expect.objectContaining({ path: "pedagogue-streak-5.png", directory: "CACHE" }));
    expect(sheet).toHaveBeenCalledWith(expect.objectContaining({ files: ["file:///cache/pedagogue-streak-5.png"], title: "My practice streak" }));
  });
});

describe("the share card button", () => {
  async function button({ pro, native = false }) {
    vi.resetModules();
    vi.doMock("../src/lib/platform.js", () => ({ isNative: native, isIOS: native, isAndroid: false, platformName: native ? "ios" : "web" }));
    const shared = vi.fn(async () => "downloaded");
    vi.doMock("../src/lib/shareCards.js", async (original) => ({ ...(await original()), shareCard: shared }));
    vi.doMock("../src/lib/plan.js", () => ({
      canUse: () => pro,
      planLimits: () => null,
      isPro: () => pro,
      upgradeCopy: () => ({ message: "Share cards are part of Pro.", upgrade: "Move to Pro to share your progress as a card." }),
    }));
    const { shareCardButton } = await import("../src/components/shareCardButton.js");
    const build = vi.fn(async () => ({ canvas: { width: 1 }, copy: { title: "t", text: "x", fileName: "card.png" } }));
    const node = shareCardButton({ label: "Share streak", build });
    document.body.append(node);
    return { node, build, shared };
  }

  it("makes and shares the card for Pro", async () => {
    const { node, build, shared } = await button({ pro: true });
    expect(node.textContent).toBe("Share streak");
    node.click();
    await new Promise((resolve) => setTimeout(resolve, 0));
    expect(build).toHaveBeenCalled();
    expect(shared).toHaveBeenCalledWith({ width: 1 }, { title: "t", text: "x", fileName: "card.png" });
    expect(document.querySelector(".toast-success").textContent).toContain("Saved the card");
    expect(node.disabled).toBe(false);
  });

  it("offers Pro instead of a card on Free, and builds nothing", async () => {
    const { node, build, shared } = await button({ pro: false });
    expect(node.textContent).toBe("Share streak · Pro");
    node.click();
    await new Promise((resolve) => setTimeout(resolve, 0));
    expect(build).not.toHaveBeenCalled();
    expect(shared).not.toHaveBeenCalled();
    expect(document.querySelector(".modal").textContent).toContain("Share cards are part of Pro.");
    expect(document.querySelector(".modal").textContent).toContain("See Pro");
  });

  it("shows no way to buy Pro inside the apps", async () => {
    const { node } = await button({ pro: false, native: true });
    node.click();
    await new Promise((resolve) => setTimeout(resolve, 0));
    const modal = document.querySelector(".modal");
    expect(modal.textContent).toContain("Share cards are part of Pro.");
    expect(modal.textContent).not.toContain("See Pro");
    expect(modal.textContent).not.toContain("Move to Pro");
  });

  it("says what went wrong when the card can't be drawn", async () => {
    const { node, build } = await button({ pro: true });
    build.mockRejectedValue(new Error("This browser can't draw the card"));
    node.click();
    await new Promise((resolve) => setTimeout(resolve, 0));
    expect(document.querySelector(".toast-error").textContent).toBe("This browser can't draw the card");
    expect(node.disabled).toBe(false);
  });
});
