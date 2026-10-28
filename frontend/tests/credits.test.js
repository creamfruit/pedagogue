import { describe, expect, it } from "vitest";
import settingsSource from "../src/views/settings.js?raw";
import mainSource from "../src/main.js?raw";
import { CREDITS } from "../src/lib/credits.js";
import { creditsView } from "../src/views/credits.js";

function render() {
  const outlet = document.createElement("main");
  creditsView(outlet);
  return outlet;
}

describe("credits page", () => {
  it("credits the piano samples, first editions, MIDI and Wikipedia", () => {
    const text = render().textContent;
    expect(text).toContain("Salamander Grand Piano V3");
    expect(text).toContain("Alexander Holm");
    expect(text).toContain("CC BY 3.0");
    expect(text).toContain("Copyright 2017-2021 The Fryderyk Chopin Institute (https://nifc.pl)");
    expect(text).toContain("Bernd Krueger");
    expect(text).toContain("Wikipedia contributors");
    expect(text).toContain("CC BY-SA 4.0");
  });

  it("credits Mutopia and OpenScore with their licences", () => {
    const outlet = render();
    const mutopia = outlet.querySelector("#mutopia").textContent;
    expect(mutopia).toContain("The Mutopia Project");
    expect(mutopia).toContain("Public Domain or CC BY");
    expect(mutopia).toContain("typesetter");
    const openscore = outlet.querySelector("#openscore").textContent;
    expect(openscore).toContain("The OpenScore Lieder Corpus");
    expect(openscore).toContain("CC0 1.0");
  });

  it("says Wikidata is used to check composers' dates", () => {
    expect(render().querySelector("#catalogue").textContent).toContain("died more than seventy years ago");
  });

  it("carries the first five lines of the Chopin Institute notice", () => {
    const notice = render().querySelector("#first-editions .credit-notice");
    expect(notice.textContent.split("\n")).toHaveLength(5);
    expect(notice.textContent.split("\n")[0]).toBe("First Editions of Fryderyk Chopin's Music");
  });

  it("links every licence and source", () => {
    const outlet = render();
    for (const credit of CREDITS) {
      const section = outlet.querySelector(`#${credit.id}`);
      const hrefs = [...section.querySelectorAll("a")].map((link) => link.getAttribute("href"));
      expect(hrefs).toContain(credit.url);
      expect(hrefs).toContain(credit.licenseUrl);
    }
  });

  it("is reachable from Settings without signing in", () => {
    expect(settingsSource).toContain('href: "/credits"');
    expect(mainSource).toMatch(/route\("\/credits", creditsView, \{ open: true \}\)/);
  });
});
