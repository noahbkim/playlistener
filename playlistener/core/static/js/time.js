const DAYS = ['Sunday', 'Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday'];
const MONTHS = ['January', 'February', 'March', 'April', 'May', 'June', 'July', 'August', 'September', 'October', 'November', 'December'];

function pad(number) {
  const result = '0' + number;
  return result.slice(result.length - 2);
}

function yesterday() {
  const date = new Date();
  date.setDate(date.getDate() - 1);
  return date;
}

function isSameDate(left, right) {
  return left.getFullYear() === right.getFullYear() &&
    left.getMonth() === right.getMonth() &&
    left.getDate() === right.getDate();
}

function formatMonth(date) {
  return `${MONTHS[date.getMonth()]} ${date.getFullYear()}`;
}

function formatMonthRange(start, end) {
  if (start.getFullYear() === end.getFullYear()) {
    return `${MONTHS[start.getMonth()]} to ${MONTHS[end.getMonth()]} ${end.getFullYear()}`;
  } else {
    return `${formatMonth(start)} to ${formatMonth(end)}`;
  }
}

function formatDate(date, useEnglish = false) {
  if (useEnglish) {
    if (isSameDate(date, yesterday())) {
      return 'yesterday';
    } else if (isSameDate(date, new Date())) {
      return 'today';
    }
  }
  return `${DAYS[date.getDay()]}, ${MONTHS[date.getMonth()]} ${date.getDate()}`;
}

function formatTime(date, useEnglish = false) {
  if (useEnglish) {
    const difference = Math.floor((new Date().valueOf() - date.valueOf()) / 1000 / 60);
    if (difference < 60) {
      return `${difference} minutes ago`;
    }
  }
  let hours = date.getHours();
  const meridian = hours < 12 ? 'AM' : 'PM';
  if (hours > 12) {
    hours -= 12;
  } else if (hours === 0) {
    hours = 12;
  }
  return `${hours}:${pad(date.getMinutes())} ${meridian}`;
}

function formatDateTime(date, useEnglish = false, useOn = false) {
  if (useEnglish) {
    const difference = Math.floor((new Date().valueOf() - date.valueOf()) / 1000 / 60);
    if (difference < 60) {
      return `${difference} minutes ago`;
    }
  }
  return `${useOn ? "on " : ""}${formatDate(date, useEnglish)} at ${formatTime(date, false)}`;
}

function formatDuration(difference) {
  const seconds = difference / 1000;
  if (seconds < 60) {
    const s = Math.round(seconds);
    return `${s.toFixed(0)} second${s === 1 ? '' : 's'}`;
  }
  const minutes = seconds / 60;
  if (minutes < 60) {
    const m = Math.round(minutes);
    return `${m.toFixed(0)} minute${m === 1 ? '' : 's'}`;
  }
  const h = Math.floor(minutes / 60);
  const m = Math.round(minutes % 60);
  return `${h.toFixed(0)} hour${h === 1 ? '' : 's'} and ${m.toFixed(0)} minute${m === 1 ? '' : 's'}`;
}

window.addEventListener("load", () => {
  for (const element of document.getElementsByClassName("time")) {
    const date = new Date(element.dataset.time);
    element.innerText = formatDateTime(date, true, true);
  }
});
