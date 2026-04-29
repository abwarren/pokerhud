// Test script to verify n4p.js selectors in browser console
// Run this in the poker table page after buy-in modal is visible

console.log('=== N4P SELECTOR VERIFICATION ===');

const SELECTORS = {
  FOLD: '.control-b-view-p.fold-c',
  CHECK: '.control-b-view-p.check-c',
  CALL: '.control-b-view-p.call-c',
  CASHOUT: '.control-b-view-p.cashout-c',
  BUYIN_BUTTON: 'body > sg-app > div > sg-lobby > div > div > sg-poker-table > sg-modal > div > div > div > div > sg-buy-in-modal > div > div > div.modal-button-container > ul > li:nth-child(1) > button',
  BUYIN_MAX: 'body > sg-app > div > sg-lobby > div > div > sg-poker-table > sg-modal > div > div > div > div > sg-buy-in-modal > div > div > div.modal-balance-v > ul > li:nth-child(2) > div.mini-button-view-m.last-v-p > button',
  BUYIN_MIN: 'body > sg-app > div > sg-lobby > div > div > sg-poker-table > sg-modal > div > div > div > div > sg-buy-in-modal > div > div > div.modal-balance-v > ul > li:nth-child(2) > div.mini-button-view-m.first-v-p > button',
  AUTO_BUYIN_CHECKBOX: 'body > sg-app > div > sg-lobby > div > div > sg-poker-table > sg-modal > div > div > div > div > sg-buy-in-modal > div > div > div.accept-info-m > label:nth-child(2) > span',
  ADD_CHIPS: 'body > sg-app > div > sg-lobby > div > div > sg-poker-table > div > div.table-header-v-right > div > div:nth-child(2) > span'
};

// Test each selector
for (const [name, selector] of Object.entries(SELECTORS)) {
  const element = document.querySelector(selector);
  if (element) {
    console.log(`✅ ${name}: FOUND`);
    console.log(`   Text: ${element.innerText || element.textContent || '(no text)'}`);
  } else {
    console.log(`❌ ${name}: NOT FOUND (may not be visible yet)`);
  }
}

console.log('\n=== ACTION BUTTON TEST ===');
console.log('To test buy-in MIN:');
console.log('  document.querySelector(SELECTORS.BUYIN_MIN).click()');
console.log('Then after 500ms:');
console.log('  document.querySelector(SELECTORS.BUYIN_BUTTON).click()');

console.log('\n=== N4P COMMAND TEST ===');
console.log('If n4p.js is loaded, try:');
console.log('1. Queue command: POST /api/commands/queue {token, type: "buyin_min"}');
console.log('2. Bot will auto-execute on next poll');
