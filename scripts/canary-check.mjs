/**
 * Asserts that a canary run actually pulled a complete Flashscore team and player.
 *
 * The unit tests run against captured pages and feeds, so they stay green
 * through a Flashscore change -- the failure that matters most, because every
 * field depends on server-rendered HTML class names, an inline JSON object, an
 * undocumented `¬`/`÷` text format and the `x-fsign` header staying put. This
 * script reads a real run's dataset and fails when coverage collapses.
 *
 * The canary input is Arsenal (team page, `pr_` paging past the embedded
 * results, `tetr_` transfers) plus "Bukayo Saka" through the search API (the
 * player header and `playerProfilePageEnvironment`).
 *
 * Usage:  apify datasets get-items <id> --format json | node scripts/canary-check.mjs
 */

const num = (v) => typeof v === 'number';
const kind = (type) => (i) => i.recordType === type;
const team = kind('team');
const squad = kind('squadPlayer');
const match = kind('match');
const result = (i) => match(i) && i.status === 'finished';
const transfer = (i) => kind('transfer')(i) && i.source === 'team';
const player = kind('player');
const career = kind('careerSeason');
const playerMatch = kind('playerMatch');
const injury = kind('injury');
const id8 = (v) => /^[A-Za-z0-9]{8}$/.test(v ?? '');

const CHECKS = [
    { name: 'team stadium / capacity', scope: team, min: 1, test: (i) => i.stadium === 'Emirates Stadium' && i.capacity > 50000 },
    { name: 'team history size', scope: team, min: 1, test: (i) => i.totalResults > 5000 },    { name: 'squad player id / url', scope: squad, min: 1, test: (i) => id8(i.playerId) && (i.playerUrl ?? '').includes('/player/') },
    { name: 'squad position group', scope: squad, min: 1, test: (i) => Boolean(i.positionGroup) },
    { name: 'squad age', scope: squad, min: 0.95, test: (i) => num(i.age) },
    { name: 'squad matches played', scope: (i) => squad(i) && i.role === 'player', min: 1, test: (i) => num(i.matchesPlayed) },
    { name: 'match ids / teams', scope: match, min: 1, test: (i) => id8(i.eventId) && Boolean(i.homeTeam && i.awayTeam) },
    { name: 'match competition (ZA header)', scope: match, min: 1, test: (i) => Boolean(i.competition) },
    { name: 'match venue / opponent', scope: match, min: 1, test: (i) => ['home', 'away'].includes(i.venue) && Boolean(i.opponent) },
    { name: 'result score / W-D-L', scope: result, min: 0.99, test: (i) => num(i.homeScore) && num(i.awayScore) && ['W', 'D', 'L'].includes(i.result) },
    { name: 'result half-time score', scope: result, min: 0.95, test: (i) => /^\d+-\d+$/.test(i.halfTimeScore ?? '') },
    { name: 'transfer date / direction', scope: transfer, min: 1, test: (i) => /^\d{4}-\d{2}-\d{2}$/.test(i.date ?? '') && ['in', 'out'].includes(i.direction) },
    // A released player has no destination club, so only one side is required.
    { name: 'transfer player / club', scope: transfer, min: 1, test: (i) => id8(i.playerId) && Boolean(i.fromTeam || i.toTeam) },
    { name: 'player market value / contract', scope: player, min: 1, test: (i) => num(i.marketValueAmount) && /^\d{4}-/.test(i.contractExpires ?? '') },
    { name: 'career season rows', scope: career, min: 1, test: (i) => Boolean(i.season && i.competition && i.team) && num(i.matchesPlayed) },
    { name: 'player match ids', scope: playerMatch, min: 1, test: (i) => id8(i.eventId) && /^\d{4}-\d{2}-\d{2}$/.test(i.date ?? '') },
    { name: 'injury dates', scope: injury, min: 0.9, test: (i) => Boolean(i.injury) && /^\d{4}-/.test(i.from ?? '') },
    { name: 'no error rows', min: 1, test: (i) => !i.error },
];

const RUN_CHECKS = [
    {
        name: '120+ distinct matches',
        test: (all) => {
            const ms = all.filter(match);
            return all.filter(result).length >= 110 && new Set(ms.map((r) => r.eventId)).size === ms.length;
        },
        why: 'pr_ paging stopped short of the 120 results asked for, or pushed (and billed) a match twice',
    },
    {
        name: 'results newest first',
        test: (all) => {
            const times = all.filter(result).map((r) => r.startTime);
            return times.every((t, n) => n === 0 || times[n - 1] >= t);
        },
        why: 'results are out of order',
    },
    {
        name: 'squad of 20+ with a coach',
        test: (all) => all.filter(squad).length >= 20 && all.some((r) => squad(r) && r.role === 'coach'),
        why: 'the squad tables (lineupTable__row) changed',
    },
    {
        name: '40 team transfers',
        test: (all) => all.filter(transfer).length === 40,
        why: 'tetr_ paging or its tree format changed',
    },
    {
        name: 'Saka found by search',
        test: (all) => all.some((r) => player(r) && r.playerId === '08NLEo06' && r.dateOfBirth === '2001-09-05'),
        why: 'the search API or the player header changed',
    },
    {
        name: '10 last matches',
        test: (all) => all.filter(playerMatch).length === 10,
        why: 'playerProfilePageEnvironment.lastMatchesData moved',
    },
];

function readStdin() {
    return new Promise((resolve, reject) => {
        let raw = '';
        process.stdin.setEncoding('utf8');
        process.stdin.on('data', (chunk) => { raw += chunk; });
        process.stdin.on('end', () => resolve(raw));
        process.stdin.on('error', reject);
    });
}

const raw = await readStdin();

// `apify datasets get-items` prints its content type on stderr today, but a
// future version putting it on stdout would otherwise turn every canary red
// for the wrong reason.
const firstBracket = raw.indexOf('[');
const payload = firstBracket > 0 ? raw.slice(firstBracket) : raw;

let items;
try {
    items = JSON.parse(payload);
} catch (error) {
    console.error(`Could not parse the dataset as JSON: ${error.message}`);
    console.error(`First 200 characters received: ${raw.slice(0, 200)}`);
    process.exit(1);
}

if (!Array.isArray(items)) {
    console.error('Expected a JSON array of dataset items.');
    process.exit(1);
}

const failures = [];
const rows = [];

if (items.length === 0) {
    failures.push('Scraped 0 items.');
}

for (const check of items.length === 0 ? [] : CHECKS) {
    const scoped = check.scope ? items.filter(check.scope) : items;
    if (scoped.length === 0) {
        rows.push({ name: check.name, hits: 0, total: 0, min: check.min, ok: false });
        failures.push(`${check.name}: no rows of that kind were scraped at all.`);
        continue;
    }
    const hits = scoped.filter((item) => {
        try {
            return check.test(item);
        } catch {
            return false;
        }
    }).length;
    const ratio = hits / scoped.length;
    const ok = ratio >= check.min;
    rows.push({ name: check.name, hits, total: scoped.length, min: check.min, ok });
    if (!ok) {
        failures.push(
            `${check.name}: ${hits}/${scoped.length} items populated `
            + `(${Math.round(ratio * 100)}%), below the ${Math.round(check.min * 100)}% floor.`,
        );
    }
}

for (const check of items.length === 0 ? [] : RUN_CHECKS) {
    let ok = false;
    try {
        ok = check.test(items);
    } catch {
        ok = false;
    }
    rows.push({ name: check.name, hits: ok ? 1 : 0, total: 1, min: 1, ok });
    if (!ok) failures.push(`${check.name}: ${check.why}.`);
}

const table = rows
    .map((r) => `  ${r.ok ? 'ok  ' : 'FAIL'} ${r.name.padEnd(38)} ${r.hits}/${r.total}`
        + ` (floor ${Math.round(r.min * 100)}%)`)
    .join('\n');

console.log(`Canary dataset: ${items.length} item(s)\n${table}`);

if (process.env.GITHUB_STEP_SUMMARY) {
    const { appendFileSync } = await import('node:fs');
    const md = [
        `### Canary — ${items.length} item(s), ${failures.length ? '❌ failed' : '✅ healthy'}`,
        '',
        '| Check | Passed | Floor |',
        '|---|---|---|',
        ...rows.map((r) => `| ${r.ok ? '✅' : '❌'} \`${r.name}\` | ${r.hits}/${r.total} |`
            + ` ${Math.round(r.min * 100)}% |`),
        '',
    ].join('\n');
    appendFileSync(process.env.GITHUB_STEP_SUMMARY, md);
}

if (failures.length) {
    console.error('\nCanary failed — Flashscore has probably changed a page template, a feed key, '
        + 'the feed sign or the search API:\n'
        + failures.map((f) => `  - ${f}`).join('\n'));
    process.exit(1);
}

console.log('\nCanary passed: the deployed build still pulls a complete Flashscore team and player.');
