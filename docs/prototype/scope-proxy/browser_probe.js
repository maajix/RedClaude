// PROTOTYPE: does a browser survive a proxy that owns the cookies?
//
// This is the question the map's fog was hiding. Everything in Phase A used an
// HTTP client, which cooperates by construction. A browser does not: it has its
// own cookie jar, its own JS that reads that jar, and its own trust store.
//
// Run through run_browser.sh, which starts the fixture and the proxy first.

const { chromium } = require('playwright');

const PROXY = 'http://127.0.0.1:18080';
const FIX = 'http://127.0.0.1:18099';
const REAL = 'https://yekta-it.de/';

const results = [];
function check(ok, name, detail = '') {
  results.push({ ok, name });
  console.log(`  ${ok ? 'PASS' : 'FAIL'}  ${name}${detail ? `  [${detail}]` : ''}`);
}
function note(name, detail) { console.log(`  ....  ${name}: ${detail}`); }

async function xhrResult(page) {
  await page.goto(`${FIX}/xhr`, { waitUntil: 'load' });
  await page.waitForFunction(() => window.__rk !== undefined, null, { timeout: 15000 });
  return page.evaluate(() => window.__rk);
}

(async () => {
  // --- control: a browser talking straight to the target, no proxy ---------
  console.log('\n=== 1. control: browser talks to the target directly ===');
  const plain = await chromium.launch({ headless: true });
  const direct = await plain.newContext();
  const directPage = await direct.newPage();
  // Log in the ordinary way so the control is a real session.
  await directPage.goto(`${FIX}/login`);
  await directPage.fill('input[name="user"]', 'alice');
  await directPage.fill('input[name="password"]', 'alice-pw-9f3c');
  await directPage.click('button');
  const directXhr = await xhrResult(directPage);
  note('document.cookie', JSON.stringify(directXhr.cookie));
  check(directXhr.status === 200, 'double-submit XHR works without a proxy',
        `HTTP ${directXhr.status}`);
  check(directXhr.cookie.includes('XSRF='),
        'page JS can read the double-submit cookie');
  check(!directXhr.cookie.includes('FIXTSESS'),
        'the session cookie is HttpOnly even here');
  await plain.close();

  // --- everything below is behind the proxy -------------------------------
  const browser = await chromium.launch({
    headless: true,
    proxy: { server: PROXY },
  });

  console.log('\n=== 2. two identities, one browser, no login ===');
  const ctxA = await browser.newContext({
    extraHTTPHeaders: { 'X-RedKraken-Identity': 'userA' },
  });
  const ctxB = await browser.newContext({
    extraHTTPHeaders: { 'X-RedKraken-Identity': 'userB' },
  });
  const pageA = await ctxA.newPage();
  const pageB = await ctxB.newPage();

  await pageA.goto(`${FIX}/whoami`);
  await pageB.goto(`${FIX}/whoami`);
  const whoA = JSON.parse(await pageA.locator('pre').textContent().catch(
    async () => await pageA.content()) || '{}');
  const whoB = JSON.parse(await pageB.locator('pre').textContent().catch(
    async () => await pageB.content()) || '{}');
  note('userA', JSON.stringify(whoA));
  note('userB', JSON.stringify(whoB));
  check(whoA.user === 'alice' && whoB.user === 'bob',
        'the browser is logged in as two people at once, having logged in as neither',
        `${whoA.user} / ${whoB.user}`);

  console.log('\n=== 3. what the browser holds ===');
  const jarA = await ctxA.cookies();
  note('context cookies', JSON.stringify(jarA));
  check(jarA.length === 0, 'the browser profile holds no cookies at all',
        `${jarA.length} cookies`);
  const domCookie = await pageA.evaluate(() => document.cookie);
  check(domCookie === '', 'document.cookie is empty', JSON.stringify(domCookie));

  console.log('\n=== 4. double-submit CSRF: the thing that actually breaks ===');
  // The agent opts out of proxy CSRF repair, which is exactly what a browser
  // behind a naive credential-stripping proxy looks like.
  const ctxRaw = await browser.newContext({
    extraHTTPHeaders: {
      'X-RedKraken-Identity': 'userA',
      'X-RedKraken-Csrf-Raw': '1',
    },
  });
  const rawXhr = await xhrResult(await ctxRaw.newPage());
  note('js saw cookie', JSON.stringify(rawXhr.cookie));
  note('js sent token', JSON.stringify(rawXhr.token_seen_by_js));
  check(rawXhr.status === 403,
        'without proxy repair the double-submit XHR fails',
        `HTTP ${rawXhr.status} ${String(rawXhr.body).slice(0, 60)}`);

  const repaired = await xhrResult(await ctxA.newPage());
  note('js sent token', JSON.stringify(repaired.token_seen_by_js));
  check(repaired.status === 200,
        'the proxy echoes the cookie the page JS could not see',
        `HTTP ${repaired.status}`);
  check(repaired.token_seen_by_js === '',
        'and the page JS still never learned the token');

  console.log('\n=== 5. TLS: the browser is the hard case ===');
  const ctxTls = await browser.newContext({
    extraHTTPHeaders: { 'X-RedKraken-Identity': 'anonYekta' },
  });
  const tlsPage = await ctxTls.newPage();
  let strictErr = '';
  try {
    await tlsPage.goto(REAL, { timeout: 20000 });
  } catch (e) { strictErr = String(e).split('\n')[0]; }
  check(strictErr !== '', 'chromium rejects the run CA it was never told about',
        strictErr.slice(0, 70));

  const ctxLax = await browser.newContext({
    ignoreHTTPSErrors: true,
    extraHTTPHeaders: { 'X-RedKraken-Identity': 'anonYekta' },
  });
  const laxPage = await ctxLax.newPage();
  const resp = await laxPage.goto(REAL, { timeout: 25000 });
  check(resp && resp.status() === 200,
        'ignoreHTTPSErrors makes it work -- and blinds the agent to TLS entirely',
        `HTTP ${resp && resp.status()}`);
  note('consequence', 'ignoreHTTPSErrors is a global override: a real certificate '
       + 'problem on the target becomes unobservable. The CA belongs in the '
       + "browser's own trust store (NSS db in the agent image), not in a flag.");

  console.log('\n=== 6. per-identity isolation: profile or context? ===');
  await pageA.evaluate(() => localStorage.setItem('token', 'alice-only'));
  const leaked = await pageB.evaluate(() => localStorage.getItem('token'));
  check(leaked === null,
        'localStorage does NOT cross browser contexts',
        `userB saw ${JSON.stringify(leaked)}`);
  note('conclusion', 'one browser CONTEXT per identity is enough; a separate '
       + 'browser profile or container per identity is not. Credentials never '
       + 'enter the browser, and everything that does (localStorage, '
       + 'sessionStorage, IndexedDB) is already context-scoped.');

  await browser.close();

  const failed = results.filter((r) => !r.ok);
  console.log(`\n  ${results.length - failed.length}/${results.length} passed`);
  failed.forEach((r) => console.log(`  FAILED: ${r.name}`));
  process.exit(failed.length ? 1 : 0);
})().catch((e) => { console.error(e); process.exit(2); });
