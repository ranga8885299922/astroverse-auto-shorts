// reply-comments v19 — auto-reply ONCE to new comments on BOTH Instagram
// accounts (astroloz_com Telugu + astroloz.hindi Hindi) and YouTube Shorts.
// Invoked every 10 min by pg_cron.
//
// DEDUP (v19): CLAIM-BEFORE-REPLY. Each candidate comment is first atomically
// inserted into replied_comments (ON CONFLICT DO NOTHING). We reply ONLY if
// this call actually inserted the row — so a comment is replied at most once,
// even across overlapping runs. If the DB write ever fails, claim() returns
// false, so we simply DON'T reply (and log the error once) instead of
// re-replying every run. This replaces the old read-all-then-fire-and-forget
// dedup, whose silent write failures caused duplicate-reply spam.

import "jsr:@supabase/functions-js/edge-runtime.d.ts";

const IG_API = "https://graph.instagram.com/v21.0";
const YT_API = "https://www.googleapis.com/youtube/v3";

const REPLY_TEXT_TE =
  "మీ విద్య, ఆరోగ్య, వివాహ మరియు ఉద్యోగ సంబంధిత ప్రశ్నలకు ఉచిత సమాధానాల కొరకు astroloz.com లో రిజిస్టర్ అయ్యి అడగండి. లింక్: www.astroloz.com";
const REPLY_TEXT_HI =
  "अपनी शिक्षा, स्वास्थ्य, विवाह और नौकरी से जुड़े सवालों के मुफ़्त जवाब के लिए astroloz.com पर रजिस्टर करके पूछें। लिंक: www.astroloz.com";
const YT_REPLY_TEXT = REPLY_TEXT_TE;

// ANY comment containing one of these is ours (or echoes ours) — never reply
const SELF_SIGNATURES = [
  "astroloz.com",
  "utm_campaign=reply",
  "utm_campaign=comment",
  "रीजिस्टर अय्यि अडगंडि",
  "रजिस्टर करके पूछें",
];
const OWN_IG_USERNAMES = new Set(["astroloz_com", "astroloz.hindi"]);

const MEDIA_LOOKBACK_DAYS = 14;
const COMMENT_LOOKBACK_DAYS = 7;
const MAX_REPLIES_PER_RUN = 20;

const SB_URL = Deno.env.get("SUPABASE_URL")!;
const SB_KEY = Deno.env.get("SUPABASE_SERVICE_ROLE_KEY")!;
const sbHeaders = {
  apikey: SB_KEY, Authorization: `Bearer ${SB_KEY}`, "Content-Type": "application/json",
};

function isSelf(text: string | undefined | null, username?: string | null): boolean {
  if (username && OWN_IG_USERNAMES.has(username)) return true;
  const t = text ?? "";
  return SELF_SIGNATURES.some((s) => t.includes(s));
}

async function getSecrets(): Promise<Record<string, string>> {
  const r = await fetch(`${SB_URL}/rest/v1/app_secrets?select=key,value`, { headers: sbHeaders });
  const rows = await r.json();
  const out: Record<string, string> = {};
  for (const row of rows) out[row.key] = row.value;
  return out;
}

// Atomically claim a comment. Returns true ONLY if this call inserted the row
// (i.e. it had never been replied). Empty result = already claimed → skip.
// Non-OK response = DB write is failing → return false (do NOT reply) and log
// once, so a broken DB pauses replies instead of spamming duplicates.
let claimErrLogged = false;
async function claim(commentId: string, mediaId: string, username: string | null, text: string): Promise<boolean> {
  let r: Response;
  try {
    r = await fetch(`${SB_URL}/rest/v1/replied_comments?on_conflict=comment_id`, {
      method: "POST",
      headers: { ...sbHeaders, Prefer: "return=representation,resolution=ignore-duplicates" },
      body: JSON.stringify({ comment_id: commentId, media_id: mediaId, username, comment_text: (text ?? "").slice(0, 500) }),
    });
  } catch (e) {
    if (!claimErrLogged) { claimErrLogged = true; console.error("claim network error:", e); }
    return false;
  }
  if (!r.ok) {
    if (!claimErrLogged) { claimErrLogged = true; console.error(`claim write FAILED ${r.status}: ${(await r.text()).slice(0, 300)}`); }
    return false;
  }
  const rows = await r.json().catch(() => []);
  return Array.isArray(rows) && rows.length > 0;
}

// Release a claim if the reply itself failed, so a transient reply error can
// retry next run (a persistent DB write failure just leaves it — no retry, but
// also no spam).
async function unclaim(commentId: string): Promise<void> {
  try {
    await fetch(`${SB_URL}/rest/v1/replied_comments?comment_id=eq.${encodeURIComponent(commentId)}`,
      { method: "DELETE", headers: sbHeaders });
  } catch (_e) { /* best effort */ }
}

// ── Instagram (parametrised by token + reply text — works for both accounts) ─
async function igReplyOnce(commentId: string, msg: string, token: string): Promise<boolean> {
  const r = await fetch(
    `${IG_API}/${commentId}/replies?message=${encodeURIComponent(msg)}&access_token=${token}`,
    { method: "POST" },
  );
  return r.ok;
}

async function replyInstagram(token: string, replyText: string): Promise<number> {
  const now = Date.now();
  const mediaSince = new Date(now - MEDIA_LOOKBACK_DAYS * 864e5).toISOString();
  const commentSince = new Date(now - COMMENT_LOOKBACK_DAYS * 864e5).toISOString();

  const mediaResp = await fetch(`${IG_API}/me/media?fields=id,timestamp&limit=50&access_token=${token}`);
  const media = (await mediaResp.json())?.data ?? [];

  let sent = 0;
  for (const m of media) {
    if ((m.timestamp ?? "") < mediaSince) continue;
    const cResp = await fetch(
      `${IG_API}/${m.id}/comments?fields=id,text,username,timestamp,replies{id,text,username,timestamp}&limit=50&access_token=${token}`,
    );
    const comments = (await cResp.json())?.data ?? [];
    for (const c of comments) {
      if (sent >= MAX_REPLIES_PER_RUN) return sent;
      if (!isSelf(c.text, c.username) && (c.timestamp ?? "") >= commentSince) {
        if (await claim(c.id, m.id, c.username ?? null, c.text ?? "")) {
          if (await igReplyOnce(c.id, replyText, token)) sent++;
          else await unclaim(c.id);
        }
      }
      for (const rep of c.replies?.data ?? []) {
        if (sent >= MAX_REPLIES_PER_RUN) return sent;
        if (isSelf(rep.text, rep.username) || (rep.timestamp ?? "") < commentSince) continue;
        if (await claim(rep.id, m.id, rep.username ?? null, rep.text ?? "")) {
          const mention = rep.username ? `@${rep.username} ` : "";
          if (await igReplyOnce(c.id, mention + replyText, token)) sent++;
          else await unclaim(rep.id);
        }
      }
    }
  }
  return sent;
}

// ── YouTube (Telugu channel) ───────────────────────────────────────────
async function ytAccessToken(s: Record<string, string>): Promise<string | null> {
  const r = await fetch("https://oauth2.googleapis.com/token", {
    method: "POST", headers: { "Content-Type": "application/x-www-form-urlencoded" },
    body: new URLSearchParams({
      client_id: s.yt_client_id, client_secret: s.yt_client_secret,
      refresh_token: s.yt_refresh_token, grant_type: "refresh_token",
    }),
  });
  return (await r.json())?.access_token ?? null;
}

async function replyYouTube(s: Record<string, string>): Promise<number> {
  if (!(s.yt_client_id && s.yt_client_secret && s.yt_refresh_token)) return 0;
  const token = await ytAccessToken(s);
  if (!token) return 0;
  const auth = { Authorization: `Bearer ${token}` };
  const chResp = await fetch(`${YT_API}/channels?part=id&mine=true`, { headers: auth });
  const channelId = (await chResp.json())?.items?.[0]?.id;
  if (!channelId) return 0;
  const tResp = await fetch(
    `${YT_API}/commentThreads?part=snippet,replies&allThreadsRelatedToChannelId=${channelId}&order=time&maxResults=50&textFormat=plainText`,
    { headers: auth },
  );
  const threads = (await tResp.json())?.items ?? [];
  const commentSince = new Date(Date.now() - COMMENT_LOOKBACK_DAYS * 864e5).toISOString();
  let sent = 0;
  const sendReply = async (parentId: string, text: string): Promise<boolean> => {
    const r = await fetch(`${YT_API}/comments?part=snippet`, {
      method: "POST", headers: { ...auth, "Content-Type": "application/json" },
      body: JSON.stringify({ snippet: { parentId, textOriginal: text } }),
    });
    return r.ok;
  };
  for (const t of threads) {
    if (sent >= MAX_REPLIES_PER_RUN) return sent;
    const top = t?.snippet?.topLevelComment; const topId = top?.id; const sn = top?.snippet;
    if (!topId || !sn) continue;
    const vid = sn.videoId ?? t?.snippet?.videoId ?? "";
    const isOwnTop = (sn.authorChannelId?.value ?? "") === channelId || isSelf(sn.textDisplay);
    if (!isOwnTop && (sn.publishedAt ?? "") >= commentSince) {
      if (await claim(topId, vid, sn.authorDisplayName ?? null, sn.textDisplay ?? "")) {
        if (await sendReply(topId, YT_REPLY_TEXT)) sent++;
        else await unclaim(topId);
      }
    }
    for (const rep of t?.replies?.comments ?? []) {
      if (sent >= MAX_REPLIES_PER_RUN) return sent;
      const rid = rep?.id; const rs = rep?.snippet;
      if (!rid || !rs) continue;
      const isOwnRep = (rs.authorChannelId?.value ?? "") === channelId || isSelf(rs.textDisplay);
      if (isOwnRep || (rs.publishedAt ?? "") < commentSince) continue;
      if (await claim(rid, vid, rs.authorDisplayName ?? null, rs.textDisplay ?? "")) {
        const mention = rs.authorDisplayName ? `${rs.authorDisplayName} ` : "";
        if (await sendReply(topId, mention + YT_REPLY_TEXT)) sent++;
        else await unclaim(rid);
      }
    }
  }
  return sent;
}

async function doWork(): Promise<void> {
  try {
    const s = await getSecrets();
    let igTe = 0, igHi = 0, yt = 0;
    try { if (s.ig_access_token) igTe = await replyInstagram(s.ig_access_token, REPLY_TEXT_TE); }
    catch (e) { console.error("IG-te error:", e); }
    try { if (s.ig_hindi_access_token) igHi = await replyInstagram(s.ig_hindi_access_token, REPLY_TEXT_HI); }
    catch (e) { console.error("IG-hi error:", e); }
    try { yt = await replyYouTube(s); } catch (e) { console.error("YT error:", e); }
    console.log(`reply-comments done: igTe=${igTe} igHi=${igHi} yt=${yt}`);
  } catch (e) { console.error("fatal:", e); }
}

Deno.serve((_req: Request) => {
  EdgeRuntime.waitUntil(doWork());
  return new Response(JSON.stringify({ status: "processing" }), { headers: { "Content-Type": "application/json" } });
});
