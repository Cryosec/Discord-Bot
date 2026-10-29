// The bot stores and compares dates (jac.date, timers.endMute/endBan) as
// US/Central wall-clock strings in the format "%b-%d-%Y %H:%M:%S"
// (e.g. "Aug-12-2026 14:30:00") and parses them with datetime.strptime in its
// hourly checks. We MUST emit that exact format and timezone; anything else
// (e.g. an ISO/UTC string) raises ValueError in the bot. The API refuses it.
export const toBotDate = (date) => {
  // en-US "short" month matches Python's %b (Jan, Feb, ... Dec); h23
  // guarantees a 00-23 hour.
  const parts = new Intl.DateTimeFormat('en-US', {
    timeZone: 'America/Chicago',
    month: 'short',
    day: '2-digit',
    year: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
    hourCycle: 'h23',
  }).formatToParts(date).reduce((acc, part) => {
    acc[part.type] = part.value;
    return acc;
  }, {});

  return `${parts.month}-${parts.day}-${parts.year} ${parts.hour}:${parts.minute}:${parts.second}`;
};
