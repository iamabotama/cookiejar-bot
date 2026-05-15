<!-- CookieChain Social Widget -->
<div id="cookiechain-widget"></div>
<script>
(function(){
  var TWITTER_URL  = 'https://x.com/TheCookieChain';
  var TELEGRAM_URL = 'https://t.me/+YulIZhqjDrw3NDcx';
  var TOKEN_URL    = 'https://cookiechain.io'; /* update me */
  var CA           = 'PASTE_CONTRACT_ADDRESS_HERE';

  var css = [
    '.ck-w{font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif;display:inline-block;width:100%;max-width:420px;box-sizing:border-box;}',
    '.ck-row{display:flex;gap:10px;margin-bottom:10px;}',
    '.ck-b{flex:1;display:flex;align-items:center;gap:10px;padding:12px 16px;border-radius:12px;text-decoration:none;border:none;cursor:pointer;transition:opacity .15s,transform .1s;}',
    '.ck-b:hover{opacity:.88;transform:translateY(-1px);}',
    '.ck-tw{background:#000;color:#fff;}',
    '.ck-tg{background:#229ED9;color:#fff;}',
    '.ck-ic{width:22px;height:22px;flex-shrink:0;}',
    '.ck-bt{display:flex;flex-direction:column;text-align:left;}',
    '.ck-bl{font-size:10px;opacity:.7;line-height:1;}',
    '.ck-bn{font-size:13px;font-weight:600;line-height:1.3;}',
    '.ck-tk{background:linear-gradient(135deg,#7c3c00,#c46a00);border-radius:12px;padding:16px 20px;display:flex;align-items:center;gap:16px;color:#fff;margin-bottom:10px;text-decoration:none;}',
    '.ck-tki{width:44px;height:44px;border-radius:50%;background:rgba(255,255,255,.15);display:flex;align-items:center;justify-content:center;font-size:22px;flex-shrink:0;}',
    '.ck-tkb{flex:1;}',
    '.ck-tkt{font-size:20px;font-weight:700;line-height:1;}',
    '.ck-tkn{font-size:12px;opacity:.75;margin-top:2px;}',
    '.ck-tkbg{background:rgba(255,255,255,.18);border-radius:20px;padding:4px 12px;font-size:11px;font-weight:600;white-space:nowrap;color:#fff;}',
    '.ck-ca{background:#1a0e00;border-radius:12px;padding:12px 16px;display:flex;align-items:center;gap:10px;border:1px solid rgba(196,106,0,.35);}',
    '.ck-cal{font-size:10px;font-weight:700;color:#c46a00;letter-spacing:.06em;white-space:nowrap;}',
    '.ck-caa{font-size:11px;color:#e8c080;font-family:monospace;flex:1;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;}',
    '.ck-cab{background:rgba(196,106,0,.25);border:1px solid rgba(196,106,0,.4);border-radius:7px;padding:5px 10px;font-size:11px;font-weight:600;color:#f0b060;cursor:pointer;white-space:nowrap;transition:background .15s;}',
    '.ck-cab:hover{background:rgba(196,106,0,.45);}'
  ].join('');

  var xIcon = '<svg class="ck-ic" viewBox="0 0 24 24" fill="currentColor"><path d="M18.244 2.25h3.308l-7.227 8.26 8.502 11.24H16.17l-4.714-6.231-5.401 6.231H2.744l7.736-8.849L1.254 2.25H8.08l4.253 5.622 5.912-5.622zm-1.161 17.52h1.833L7.084 4.126H5.117z"/></svg>';
  var tgIcon = '<svg class="ck-ic" viewBox="0 0 24 24" fill="currentColor"><path d="M11.944 0A12 12 0 0 0 0 12a12 12 0 0 0 12 12 12 12 0 0 0 12-12A12 12 0 0 0 12 0a12 12 0 0 0-.056 0zm4.962 7.224c.1-.002.321.023.465.14a.506.506 0 0 1 .171.325c.016.093.036.306.02.472-.18 1.898-.962 6.502-1.36 8.627-.168.9-.499 1.201-.82 1.23-.696.065-1.225-.46-1.9-.902-1.056-.693-1.653-1.124-2.678-1.8-1.185-.78-.417-1.21.258-1.91.177-.184 3.247-2.977 3.307-3.23.007-.032.014-.15-.056-.212s-.174-.041-.249-.024c-.106.024-1.793 1.14-5.061 3.345-.48.33-.913.49-1.302.48-.428-.008-1.252-.241-1.865-.44-.752-.245-1.349-.374-1.297-.789.027-.216.325-.437.893-.663 3.498-1.524 5.83-2.529 6.998-3.014 3.332-1.386 4.025-1.627 4.476-1.635z"/></svg>';

  var style = document.createElement('style');
  style.textContent = css;
  document.head.appendChild(style);

  var caId = 'ck-ca-' + Math.random().toString(36).slice(2);

  var html = '<div class="ck-w">'
    + '<div class="ck-row">'
    + '<a class="ck-b ck-tw" href="'+TWITTER_URL+'" target="_blank" rel="noopener">'
    + xIcon + '<span class="ck-bt"><span class="ck-bl">Follow us on</span><span class="ck-bn">@TheCookieChain</span></span></a>'
    + '<a class="ck-b ck-tg" href="'+TELEGRAM_URL+'" target="_blank" rel="noopener">'
    + tgIcon + '<span class="ck-bt"><span class="ck-bl">Join us on</span><span class="ck-bn">Telegram</span></span></a>'
    + '</div>'
    + '<a class="ck-tk" href="'+TOKEN_URL+'" target="_blank" rel="noopener">'
    + '<div class="ck-tki">🍪</div>'
    + '<div class="ck-tkb"><div class="ck-tkt">$COOK</div><div class="ck-tkn">The CookieChain Token</div></div>'
    + '<div class="ck-tkbg">Learn more →</div></a>'
    + '<div class="ck-ca">'
    + '<span class="ck-cal">CA:</span>'
    + '<span class="ck-caa" id="'+caId+'">'+CA+'</span>'
    + '<button class="ck-cab" onclick="(function(b){navigator.clipboard.writeText(''+CA+'').then(function(){b.textContent='Copied!';setTimeout(function(){b.textContent='Copy';},2000)})})(this)">Copy</button>'
    + '</div>'
    + '</div>';

  var target = document.getElementById('cookiechain-widget');
  if(target) target.innerHTML = html;
})();
</script>
