const KEY = "pp.guestPrompt";

export function shouldPromptGuest(user) {
  if (!user?.is_guest) return false;
  try {
    return localStorage.getItem(KEY) !== "1";
  } catch {
    return true;
  }
}

export function markGuestPrompted() {
  try {
    localStorage.setItem(KEY, "1");
  } catch {
    return;
  }
}
