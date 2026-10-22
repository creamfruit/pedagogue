export function formatDate(value) {
  if (!value) return "";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "";
  return date.toLocaleDateString(undefined, { day: "numeric", month: "long", year: "numeric" });
}

const INTERVAL_WORD = { month: "monthly", year: "yearly" };

const STORE_LINE = "Bought in the App Store or Google Play. Manage or cancel it there.";

function proLines(subscription) {
  const found = baseProLines(subscription);
  if (subscription.provider === "revenuecat") found.lines.push(STORE_LINE);
  return found;
}

function baseProLines(subscription) {
  const end = formatDate(subscription.current_period_end);
  const trialEnd = formatDate(subscription.trial_end || subscription.current_period_end);
  const word = INTERVAL_WORD[subscription.interval];
  if (subscription.status === "trialing") {
    return {
      lines: [
        trialEnd ? `Your free trial of Pro runs until ${trialEnd}.` : "You're on a free trial of Pro.",
        subscription.cancel_at_period_end ? "It will end then and you won't be charged." : "You'll be charged then unless you cancel first.",
      ],
      warn: false,
    };
  }
  if (subscription.status === "past_due") {
    return { lines: ["Your last payment didn't go through. Update your payment method to keep Pro."], warn: true };
  }
  if (subscription.cancel_at_period_end) {
    return { lines: [end ? `Pro until ${end}. It won't renew.` : "Pro. It won't renew."], warn: false };
  }
  return { lines: [end ? `Pro${word ? `, ${word}` : ""}, renewing on ${end}.` : "Pro is active."], warn: false };
}

export function describePlan(plan) {
  if (!plan) return { name: "", lines: [], warn: false, pro: false };
  const subscription = plan.subscription;
  const limits = plan.limits;
  if (limits.is_pro && subscription) return { name: "Pro", pro: true, ...proLines(subscription) };
  if (limits.is_pro) return { name: "Pro", pro: true, lines: ["Pro is active on your account."], warn: false };
  const lines = [];
  if (limits.active_pieces !== null && limits.active_pieces !== undefined) {
    lines.push(`${plan.usage.active_pieces} of ${limits.active_pieces} pieces in progress.`);
  }
  if (subscription && ["canceled", "unpaid", "incomplete_expired"].includes(subscription.status)) {
    const ended = formatDate(subscription.current_period_end);
    lines.unshift(ended ? `Your Pro plan ended on ${ended}. Your pieces and history are all still here.` : "Your Pro plan has ended. Your pieces and history are all still here.");
  }
  return { name: "Free", pro: false, lines, warn: false };
}

export function savingsPercent(options) {
  const month = options.find((option) => option.interval === "month");
  const year = options.find((option) => option.interval === "year");
  if (!month?.amount || !year?.amount) return 0;
  const saved = Math.round((1 - year.amount / (month.amount * 12)) * 100);
  return saved > 0 ? saved : 0;
}

export function comparisonRows(limits) {
  const pieces = limits?.active_pieces ?? 5;
  const history = limits?.keyboard_history_attempts ?? 3;
  const ceiling = Math.round((limits?.tempo_ladder_ceiling ?? 0.8) * 100);
  return [
    ["Pieces in progress", `Up to ${pieces}`, "Unlimited"],
    ["Practice tools and the catalogue", "Included", "Included"],
    ["Keyboard practice and scoring", "Included", "Included"],
    ["Keyboard run history", `Last ${history} runs`, "Everything"],
    ["Tempo ladder", `Up to ${ceiling}% of your target`, "All the way to your target"],
    ["MusicXML and MIDI scores", "Included", "Included"],
    ["PDF score reading", "Not included", "Included"],
    ["Share cards", "Not included", "Included"],
    ["Cloud sync", "Not included", "Included"],
  ];
}
