/* ── PokerBet HUD: popup.js ── */
const PASSWORD_HASH = hashString('aksuited');

function hashString(str) {
  let hash = 0;
  for (let i = 0; i < str.length; i++) {
    const chr = str.charCodeAt(i);
    hash = ((hash << 5) - hash) + chr;
    hash |= 0;
  }
  return hash;
}

const $ = (id) => document.getElementById(id);
const loginScreen = $('login-screen');
const dashboardScreen = $('dashboard-screen');
const passwordInput = $('password-input');
const loginBtn = $('login-btn');
const loginError = $('login-error');
const lockBtn = $('lock-btn');
const refreshBtn = $('refresh-btn');
const statusDot = $('status-dot');
const statusText = $('status-text');

// ── Auth ──
async function checkAuth() {
  const { unlocked } = await chrome.storage.local.get('unlocked');
  if (unlocked === true) {
    showDashboard();
  }
}

function showDashboard() {
  loginScreen.classList.add('hidden');
  dashboardScreen.classList.remove('hidden');
  refreshStats();
}

function showLogin() {
  loginScreen.classList.remove('hidden');
  dashboardScreen.classList.add('hidden');
}

loginBtn.addEventListener('click', () => {
  const pw = passwordInput.value;
  if (hashString(pw.toLowerCase()) === PASSWORD_HASH) {
    chrome.storage.local.set({ unlocked: true });
    loginError.classList.add('hidden');
    showDashboard();
  } else {
    loginError.classList.remove('hidden');
    passwordInput.value = '';
    passwordInput.focus();
  }
});

passwordInput.addEventListener('keydown', (e) => {
  if (e.key === 'Enter') loginBtn.click();
});

lockBtn?.addEventListener('click', async () => {
  await chrome.storage.local.set({ unlocked: false });
  showLogin();
});

// ── Stats ──
async function refreshStats() {
  try {
    const resp = await chrome.runtime.sendMessage({ type: 'GET_STATS' });
    if (resp) {
      statusDot.className = 'dot dot-green';
      statusText.textContent = 'Active';
      updateUI(resp);
    } else {
      statusDot.className = 'dot dot-yellow';
      statusText.textContent = 'No data';
    }
  } catch {
    statusDot.className = 'dot dot-red';
    statusText.textContent = 'Offline';
  }
}

function updateUI(data) {
  $('stat-hands').textContent = data.totalHands || 0;
  $('stat-players').textContent = data.totalPlayers || 0;
  $('stat-tables').textContent = data.tablesSeen || 0;

  if (data.myStats) {
    $('my-vpip').textContent = data.myStats.vpip != null ? data.myStats.vpip + '%' : '--';
    $('my-pfr').textContent = data.myStats.pfr != null ? data.myStats.pfr + '%' : '--';
    $('my-3b').textContent = data.myStats.threeBet != null ? data.myStats.threeBet + '%' : '--';
  }
}

refreshBtn?.addEventListener('click', refreshStats);

// ── Init ──
checkAuth();

// Listen for storage changes (lock from another tab)
chrome.storage.onChanged.addListener((changes) => {
  if (changes.unlocked && changes.unlocked.newValue === false) {
    showLogin();
  }
});
