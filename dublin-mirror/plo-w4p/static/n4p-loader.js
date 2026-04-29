// N4P Loader - Inject script tag instead of fetch
(function() {
  // Remove old script if exists
  var oldScript = document.getElementById('n4p-remote-script');
  if (oldScript) oldScript.remove();

  // Create new script tag
  var script = document.createElement('script');
  script.id = 'n4p-remote-script';
  script.src = 'https://engine.potlimitomaha.xyz:8080/n4p.js?t=' + Date.now();
  script.crossOrigin = 'anonymous';

  script.onload = function() {
    console.log('[Loader] ✅ N4P script loaded successfully');
  };

  script.onerror = function() {
    console.error('[Loader] ❌ Failed to load N4P script');
  };

  document.head.appendChild(script);
  console.log('[Loader] 🔄 Loading N4P from:', script.src);
})();
