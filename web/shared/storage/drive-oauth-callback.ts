// Standalone callback storage bridge: deliberately no app layout or third-party code.
export const driveOAuthCallbackScript = `(() => {
  const params = new URLSearchParams(location.search);
  history.replaceState(null, '', '/drive-oauth-callback');
  let target = '/learning/drive';
  try {
    const pending = JSON.parse(sessionStorage.getItem('drive.oauth.pending') || 'null');
    if (pending && pending.state === params.get('state') && Date.now() < pending.expires) {
      sessionStorage.setItem('drive.oauth.callback', JSON.stringify({
        state: params.get('state'), code: (params.get('code') || '').slice(0, 8192),
        error: (params.get('error') || '').slice(0, 200)
      }));
      target += '?dt_workspace=' + encodeURIComponent(pending.workspace);
    } else { sessionStorage.setItem('drive.oauth.failure', 'invalid_callback'); }
  } catch { /* Do not reflect URL contents or exceptions. */ }
  location.replace(target);
})();`
