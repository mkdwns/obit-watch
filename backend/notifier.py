"""
notifier.py — sends email alerts when new obit matches are found.

SMTP settings are read from the database at send time (not at import),
so changes made via the settings UI take effect immediately without restart.
"""
import os
import smtplib
import ssl
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from datetime import datetime


def _cfg(key: str, fallback: str = "") -> str:
    """Read a setting from DB (preferred) or environment."""
    try:
        import database as db
        val = db.get_setting(key)
        return val if val is not None else fallback
    except Exception:
        return os.getenv(key.upper(), fallback)


def _build_html(matches: list[dict]) -> tuple[str, str, str]:
    count   = len(matches)
    subject = f"Obit Watch — {count} new match{'es' if count > 1 else ''} found"
    date_str = datetime.now().strftime("%B %d, %Y at %I:%M %p")

    plain = f"Obit Watch found {count} new match(es) on {date_str}.\n\n"
    for m in matches:
        plain += f"{m['first_name']} {m['last_name']}"
        if m.get("birth_year") or m.get("death_year"):
            plain += f" ({m.get('birth_year','?')} – {m.get('death_year','?')})"
        if m.get("location"):
            plain += f" — {m['location']}"
        plain += "\n"
        if m.get("watch_note"):
            plain += f"  Note: {m['watch_note']}\n"
        if m.get("obit_snippet"):
            plain += f"  \"{m['obit_snippet'][:200]}\"\n"
        if m.get("obit_url"):
            plain += f"  {m['obit_url']}\n"
        plain += "\n"

    cards_html = ""
    for m in matches:
        years = f"<span style='color:#8B3A2A;font-size:13px'>{m.get('birth_year','?')} – {m.get('death_year','?')}</span><br>" if (m.get("birth_year") or m.get("death_year")) else ""
        loc   = f"<span style='color:#666;font-size:13px'>📍 {m['location']}</span><br>" if m.get("location") else ""
        note  = f"<span style='color:#B8966A;font-size:12px'>Watching for: {m['watch_note']}</span><br>" if m.get("watch_note") else ""
        snip  = f"<p style='color:#4A4540;font-size:13px;font-style:italic;margin:8px 0'>\"{m['obit_snippet'][:200]}...\"</p>" if m.get("obit_snippet") else ""
        btn   = f"<a href='{m['obit_url']}' style='display:inline-block;background:#1A1714;color:#F5F0E8;padding:8px 18px;text-decoration:none;font-size:12px;letter-spacing:0.08em;text-transform:uppercase;margin-top:10px'>View Full Obituary &rarr;</a>" if m.get("obit_url") else ""
        cards_html += f"""
        <div style='background:#FDF5F3;border-left:4px solid #8B3A2A;padding:16px 20px;margin-bottom:16px'>
          <h2 style='margin:0 0 6px;font-size:20px;font-weight:500;font-family:Georgia,serif'>{m['first_name']} {m['last_name']}</h2>
          {years}{loc}{note}{snip}{btn}
        </div>"""

    html = f"""<!DOCTYPE html><html><body style='margin:0;padding:0;background:#F5F0E8;font-family:sans-serif'>
    <div style='max-width:580px;margin:0 auto;background:#FAF7F2;border-top:3px solid #B8966A'>
      <div style='background:#1A1714;padding:20px 28px'>
        <h1 style='color:#FAF7F2;margin:0;font-size:22px;font-weight:400;font-family:Georgia,serif'>Obit Watch</h1>
        <p style='color:#B8966A;margin:4px 0 0;font-size:11px;letter-spacing:0.15em;text-transform:uppercase'>Obituary Monitor</p>
      </div>
      <div style='padding:24px 28px'>
        <p style='color:#4A4540;margin:0 0 20px'>{count} new match{'es were' if count > 1 else ' was'} found on {date_str}.</p>
        {cards_html}
        <hr style='border:none;border-top:1px solid #D8D0C4;margin:24px 0'>
        <p style='color:#8A8580;font-size:12px'>Sent by Obit Watch on your local server. Visit your dashboard to review or dismiss matches.</p>
      </div>
    </div></body></html>"""

    return subject, plain, html


def send_alert(matches: list[dict]) -> bool:
    if not matches:
        return True

    smtp_host  = _cfg("smtp_host",  "smtp.gmail.com")
    smtp_port  = int(_cfg("smtp_port", "587"))
    smtp_user  = _cfg("smtp_user",  "")
    smtp_pass  = _cfg("smtp_pass",  "")
    alert_from = _cfg("alert_from", smtp_user)
    alert_to   = _cfg("alert_to",   "")
    enabled    = _cfg("notifications_enabled", "true").lower()

    if enabled == "false":
        print("[notifier] notifications disabled — skipping")
        return False
    if not alert_to:
        print("[notifier] ERROR: no alert_to address — set ALERT_TO in env or save an email in the UI")
        return False
    if not smtp_user:
        print("[notifier] ERROR: no smtp_user — set SMTP_USER in env")
        return False
    if not smtp_pass:
        print("[notifier] ERROR: no smtp_pass — set SMTP_PASS in env")
        return False

    subject, plain, html = _build_html(matches)
    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"]    = alert_from
    msg["To"]      = alert_to
    msg.attach(MIMEText(plain, "plain"))
    msg.attach(MIMEText(html,  "html"))

    try:
        ctx = ssl.create_default_context()
        with smtplib.SMTP(smtp_host, smtp_port) as s:
            s.ehlo()
            s.starttls(context=ctx)
            s.login(smtp_user, smtp_pass)
            s.sendmail(alert_from, [a.strip() for a in alert_to.split(",")], msg.as_string())
        print(f"[notifier] sent alert to {alert_to} — {len(matches)} match(es)")
        return True
    except Exception as e:
        import traceback
        print(f"[notifier] ERROR: {e}")
        print(traceback.format_exc())
        return False
