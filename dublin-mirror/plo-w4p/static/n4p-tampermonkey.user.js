// ==UserScript==
// @name         PLO N4P Remote Control Auto-Inject
// @namespace    http://potlimitomaha.xyz/
// @version      1.0
// @description  Auto-inject n4p.js into PokerBet poker game for remote control
// @author       N4P System
// @match        https://www.pokerbet.co.za/*
// @match        https://poker-web.pokerbet.co.za/*
// @icon         https://www.google.com/s2/favicons?sz=64&domain=pokerbet.co.za
// @grant        none
// @run-at       document-start
// ==/UserScript==

(function() {
    'use strict';

    console.log('[N4P Tampermonkey] Auto-injection script loaded');

    // Configuration
    const N4P_URL = 'http://172.31.41.21:5000/n4p.js';
    const INJECT_DELAY_MS = 3000;  // Wait 3s after page load
    const RECHECK_INTERVAL_MS = 10000;  // Recheck every 10s

    // State
    let injectionAttempted = false;
    let recheckTimer = null;

    function isInIframe() {
        try {
            return window.self !== window.top;
        } catch (e) {
            return true;
        }
    }

    function isPokerGame() {
        // Check if we're in the poker game iframe or page
        const url = window.location.href;
        return url.includes('18751019') || url.includes('poker-web');
    }

    function injectN4P() {
        // Don't inject if already loaded
        if (window._n4p_injected) {
            console.log('[N4P Tampermonkey] Already injected, skipping');
            return;
        }

        console.log('[N4P Tampermonkey] Injecting n4p.js from', N4P_URL);

        fetch(N4P_URL)
            .then(response => {
                if (!response.ok) {
                    throw new Error(`HTTP ${response.status}: ${response.statusText}`);
                }
                return response.text();
            })
            .then(code => {
                // Execute the n4p.js code
                eval(code);
                console.log('[N4P Tampermonkey] ✅ Successfully injected n4p.js');
                injectionAttempted = true;

                // Verify injection
                setTimeout(() => {
                    if (window._n4p_injected) {
                        console.log('[N4P Tampermonkey] ✅ N4P confirmed active');
                    } else {
                        console.warn('[N4P Tampermonkey] ⚠️ N4P injection may have failed');
                    }
                }, 1000);
            })
            .catch(error => {
                console.error('[N4P Tampermonkey] ❌ Injection failed:', error);
                injectionAttempted = true;
            });
    }

    function setupRecheck() {
        // Periodically recheck if n4p.js is still loaded
        if (recheckTimer) {
            clearInterval(recheckTimer);
        }

        recheckTimer = setInterval(() => {
            if (!window._n4p_injected) {
                console.log('[N4P Tampermonkey] N4P lost, re-injecting...');
                injectionAttempted = false;
                injectN4P();
            }
        }, RECHECK_INTERVAL_MS);
    }

    function attemptInjection() {
        // Only inject in poker game context
        if (!isPokerGame()) {
            console.log('[N4P Tampermonkey] Not in poker game, waiting...');
            return;
        }

        if (injectionAttempted) {
            return;
        }

        injectN4P();
        setupRecheck();
    }

    // Initial injection after delay
    console.log('[N4P Tampermonkey] Waiting', INJECT_DELAY_MS, 'ms before injection...');
    setTimeout(attemptInjection, INJECT_DELAY_MS);

    // Also try on DOMContentLoaded
    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', () => {
            setTimeout(attemptInjection, 1000);
        });
    }

    // Monitor for iframe loads
    const observer = new MutationObserver((mutations) => {
        mutations.forEach((mutation) => {
            mutation.addedNodes.forEach((node) => {
                if (node.tagName === 'IFRAME') {
                    console.log('[N4P Tampermonkey] Iframe detected, will inject on load');
                    setTimeout(attemptInjection, INJECT_DELAY_MS);
                }
            });
        });
    });

    // Start observing
    if (document.body) {
        observer.observe(document.body, { childList: true, subtree: true });
    } else {
        document.addEventListener('DOMContentLoaded', () => {
            observer.observe(document.body, { childList: true, subtree: true });
        });
    }

    console.log('[N4P Tampermonkey] Monitoring active');
})();
