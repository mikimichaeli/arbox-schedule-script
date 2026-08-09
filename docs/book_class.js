/**
 * Arbox Auto-Booking — Browser version
 *
 * Query string parameters:
 *   email            – Arbox account email
 *   password         – Arbox account password
 *   location         – Location name (e.g. "CrossFit Binyamina")
 *   prefix           – Default class name prefix (default: "WOD")
 *   timezone         – Timezone (default: "Asia/Jerusalem")
 *   dryRun           – "true" to preview without booking (default: "false")
 *   classes          – JSON array of {day, time, prefix?} objects
 *                      day: 1=Sunday...7=Saturday
 *
 * Example URL:
 *   arbox_book.html?email=...&password=...&location=CrossFit%20Binyamina&classes=[{"day":1,"time":"18:00"},{"day":3,"time":"18:00"},{"day":5,"time":"08:00"}]
 */

const BASE_URL = 'https://apiappv2.arboxapp.com/api/v2';
const DAY_NAMES = ['', 'Sunday', 'Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday'];

const logEl = document.getElementById('log');

function log(msg, cls = 'info') {
  const span = document.createElement('span');
  span.className = cls;
  span.textContent = msg + '\n';
  logEl.appendChild(span);
  window.scrollTo(0, document.body.scrollHeight);
}

function getConfig() {
  const params = new URLSearchParams(window.location.search);

  const email = params.get('email');
  const password = params.get('password');
  if (!email || !password) {
    throw new Error('email and password query params are required');
  }

  const classesRaw = params.get('classes');
  if (!classesRaw) {
    throw new Error('classes query param is required (JSON array)');
  }

  return {
    email,
    password,
    locationName: params.get('location') || '',
    classNamePrefix: params.get('prefix') || 'WOD',
    timezone: params.get('timezone') || 'Asia/Jerusalem',
    dryRun: params.get('dryRun') === 'true',
    classes: JSON.parse(classesRaw),
  };
}

async function apiPost(url, body, token, refreshToken) {
  const headers = {
    'Content-Type': 'application/json',
    'Accept': 'application/json',
  };
  if (token) {
    headers['accesstoken'] = token;
    headers['refreshtoken'] = refreshToken;
  }
  const resp = await fetch(url, {
    method: 'POST',
    headers,
    body: JSON.stringify(body),
  });
  return resp.json();
}

async function apiGet(url, token, refreshToken) {
  const resp = await fetch(url, {
    method: 'GET',
    headers: {
      'Accept': 'application/json',
      'accesstoken': token,
      'refreshtoken': refreshToken,
    },
  });
  return resp.json();
}

function getTomorrow(timezone) {
  const now = new Date();
  // Build tomorrow in the target timezone
  const formatter = new Intl.DateTimeFormat('en-CA', { timeZone: timezone, year: 'numeric', month: '2-digit', day: '2-digit' });
  const todayStr = formatter.format(now);
  const today = new Date(todayStr + 'T12:00:00');
  today.setDate(today.getDate() + 1);

  const tomorrowStr = formatter.format(today);
  // getDay() from the formatted date
  const tomorrowDate = new Date(tomorrowStr + 'T12:00:00');
  const tomorrowDay = tomorrowDate.getDay() + 1; // 1=Sunday...7=Saturday

  return { tomorrowStr, tomorrowDay, tomorrowDayName: DAY_NAMES[tomorrowDay] };
}

async function book() {
  try {
    const config = getConfig();

    if (config.dryRun) {
      log('[DRY RUN MODE]', 'warn');
    }

    // Check tomorrow
    const { tomorrowStr, tomorrowDay, tomorrowDayName } = getTomorrow(config.timezone);
    const matchingEntries = config.classes.filter(c => c.day === tomorrowDay);

    if (matchingEntries.length === 0) {
      log(`No configured classes for ${tomorrowDayName} (${tomorrowStr}). Nothing to book.`, 'warn');
      return;
    }

    log(`Tomorrow is ${tomorrowDayName} (${tomorrowStr}) — ${matchingEntries.length} class(es) to book.`, 'step');

    // Login
    log('Logging in...', 'step');
    const loginResp = await apiPost(`${BASE_URL}/user/login`, {
      email: config.email,
      password: config.password,
    });
    const token = loginResp.data.token;
    const refreshToken = loginResp.data.refreshToken;
    log(`Login successful (user id: ${loginResp.data.id})`);

    // Get locations
    log('Fetching locations...', 'step');
    const locResp = await apiGet(`${BASE_URL}/boxes/locations`, token, refreshToken);
    const locations = locResp.data;

    let location;
    if (config.locationName) {
      location = locations.find(l => (l.name || '').trim() === config.locationName);
      if (!location) {
        const available = locations.map(l => l.name).join(', ');
        throw new Error(`Location '${config.locationName}' not found. Available: ${available}`);
      }
    } else {
      location = locations[0];
    }

    const boxId = location.id;
    const locationsBoxId = location.locations_box[0].id;
    log(`Using location: ${location.name} (locations_box_id: ${locationsBoxId})`);

    // Get membership
    log('Fetching membership...', 'step');
    const memResp = await apiGet(`${BASE_URL}/boxes/${boxId}/memberships/1`, token, refreshToken);
    if (!memResp.data || memResp.data.length === 0) {
      throw new Error('No active membership found.');
    }
    const membershipId = memResp.data[0].id;
    log(`Membership id: ${membershipId}`);

    // Get schedule
    log(`Fetching schedule for ${tomorrowStr}...`, 'step');
    const schedResp = await apiPost(`${BASE_URL}/schedule/betweenDates`, {
      from: `${tomorrowStr}T00:00:00.000Z`,
      to: `${tomorrowStr}T00:00:00.000Z`,
      locations_box_id: locationsBoxId,
    }, token, refreshToken);
    const classes = schedResp.data;
    log(`Found ${classes.length} classes on ${tomorrowStr}`);

    // Book each matching entry
    let booked = 0;
    for (const entry of matchingEntries) {
      const classTime = entry.time;
      const prefix = entry.prefix || config.classNamePrefix;

      const target = classes.find(c =>
        c.time === classTime &&
        ((c.box_categories || {}).name || '').trim().startsWith(prefix)
      );

      if (!target) {
        log(`No class matching '${prefix}*' at ${classTime} on ${tomorrowStr}`, 'warn');
        continue;
      }

      const className = target.box_categories.name.trim();
      log(`Target class: ${className} at ${target.time} (schedule_id: ${target.id})`);

      if (config.dryRun) {
        log(`[DRY RUN] Would register for schedule_id=${target.id}`, 'warn');
        booked++;
        continue;
      }

      // Register
      log('Registering...', 'step');
      const regResp = await apiPost(`${BASE_URL}/scheduleUser/insert`, {
        extras: null,
        membership_user_id: membershipId,
        schedule_id: target.id,
      }, token, refreshToken);

      if (regResp.error) {
        const msg = regResp.error.messageToUser || JSON.stringify(regResp.error);
        log(`Registration failed: ${msg}`, 'error');
        continue;
      }

      log(`Enrolled successfully for ${className} at ${classTime}!`);
      booked++;
    }

    log(`\nBooked ${booked} / ${matchingEntries.length} class(es).`, booked > 0 ? 'info' : 'warn');

  } catch (err) {
    log(`ERROR: ${err.message}`, 'error');
  }
}

book();