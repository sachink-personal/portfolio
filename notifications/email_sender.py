"""
Email notifications via Gmail SMTP with App Password (port 465, SSL).

Setup (one-time):
  1. Enable 2-Step Verification on your Google account.
  2. Go to myaccount.google.com → Security → App Passwords.
  3. Generate an app password for "Mail" → copy the 16-character code.
  4. Set EMAIL_SENDER and EMAIL_PASSWORD in your .env file.
"""
from __future__ import annotations

import logging
import smtplib
import ssl
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import Optional

import config

log = logging.getLogger(__name__)


class EmailSender:
    """
    Sends HTML-formatted portfolio notification emails via Gmail SMTP.
    """

    def __init__(
        self,
        sender: Optional[str] = None,
        password: Optional[str] = None,
        recipient: Optional[str] = None,
    ) -> None:
        self.sender = sender or config.EMAIL_SENDER
        self.password = password or config.EMAIL_PASSWORD
        self.recipient = recipient or config.EMAIL_RECIPIENT

    # ── Core send ─────────────────────────────────────────────────────────────

    def _send(self, subject: str, html_body: str, plain_body: str = "") -> bool:
        """Low-level SMTP send. Returns True on success."""
        if not self.sender or not self.password:
            log.error(
                "Email not configured — set EMAIL_SENDER and EMAIL_PASSWORD in .env"
            )
            return False
        try:
            msg = MIMEMultipart("alternative")
            msg["Subject"] = subject
            msg["From"] = self.sender
            msg["To"] = self.recipient
            if plain_body:
                msg.attach(MIMEText(plain_body, "plain", "utf-8"))
            msg.attach(MIMEText(html_body, "html", "utf-8"))
            ctx = ssl.create_default_context()
            with smtplib.SMTP_SSL("smtp.gmail.com", 465, context=ctx) as server:
                server.login(self.sender, self.password)
                server.sendmail(self.sender, self.recipient, msg.as_string())
            log.info("Email sent: %s", subject)
            return True
        except smtplib.SMTPAuthenticationError:
            log.error("Gmail authentication failed. Check your App Password.")
            return False
        except Exception as exc:
            log.error("Email send failed: %s", exc)
            return False

    # ── Daily digest ──────────────────────────────────────────────────────────

    def send_daily_digest(
        self,
        portfolio_value: float,
        regime: dict,
        sell_alerts: list[dict],
        date_str: str = "",
    ) -> bool:
        """
        Daily 8 AM email: portfolio value, regime status, and any exit alerts.
        """
        trend = regime.get("trend", {})
        val = regime.get("valuation", {})
        breadth = regime.get("breadth", {})

        t_label = trend.get("trend", "UNKNOWN")
        t_color = "green" if t_label == "BULLISH" else ("#dc3545" if t_label == "BEARISH" else "gray")
        v_label = val.get("valuation", "UNKNOWN")
        v_color = {"OVERVALUED": "#dc3545", "UNDERVALUED": "#28a745", "FAIR": "#f0a500"}.get(v_label, "gray")
        b_pct = breadth.get("breadth_pct")
        b_status = breadth.get("status", "UNKNOWN")
        b_color = "#dc3545" if breadth.get("warning") else "#28a745"
        pe_val = val.get("pe")
        pe_str = f"{pe_val:.1f}" if pe_val else "N/A"

        if sell_alerts:
            rows_html = "".join(
                f"<tr><td style='padding:6px'><strong>{a['Ticker']}</strong></td>"
                f"<td style='padding:6px;color:#dc3545'>{a['ExitReason']}</td></tr>"
                for a in sell_alerts
            )
            alerts_section = f"""
            <h3 style="color:#dc3545">🚨 Exit Signals ({len(sell_alerts)})</h3>
            <table border="1" cellpadding="0" cellspacing="0"
                   style="border-collapse:collapse;width:100%;font-size:14px">
              <tr style="background:#f8d7da;font-weight:bold">
                <th style="padding:8px">Ticker</th>
                <th style="padding:8px">Reason</th>
              </tr>
              {rows_html}
            </table>
            <p style="color:#dc3545"><strong>Action required:</strong>
            Review these positions and consider exiting per the strategy rules.</p>"""
        else:
            alerts_section = (
                '<p style="color:#28a745">✅ No exit signals triggered today. '
                "All holdings are within healthy parameters.</p>"
            )

        breadth_str = f"{b_pct:.1f}%" if b_pct is not None else "Not set (update via sidebar)"

        html = f"""<!DOCTYPE html>
<html>
<body style="font-family:Arial,sans-serif;max-width:620px;margin:auto;color:#333">
  <h2 style="color:#1a1a2e;border-bottom:2px solid #4a90e2;padding-bottom:8px">
    🌅 Morning Portfolio Digest — {date_str}
  </h2>
  <div style="background:#f8f9fa;border-radius:8px;padding:20px;text-align:center;margin:15px 0">
    <div style="font-size:13px;color:#666">Total Portfolio Value</div>
    <div style="font-size:32px;font-weight:bold;color:#1a1a2e">₹{portfolio_value:,.0f}</div>
  </div>

  <h3>📡 Market Regime</h3>
  <table border="1" cellpadding="0" cellspacing="0"
         style="border-collapse:collapse;width:100%;font-size:14px">
    <tr>
      <td style="padding:10px;width:35%"><strong>Trend (200-DMA)</strong></td>
      <td style="padding:10px;color:{t_color};font-weight:bold">{t_label}</td>
      <td style="padding:10px;color:#666">
        Nifty 500: {trend.get('close', 0):,.0f} &nbsp;|&nbsp;
        200-DMA: {trend.get('dma_200', 0):,.0f}
        ({trend.get('distance_pct', 0):+.1f}%)
      </td>
    </tr>
    <tr style="background:#f8f9fa">
      <td style="padding:10px"><strong>Valuation (PE)</strong></td>
      <td style="padding:10px;color:{v_color};font-weight:bold">{v_label}</td>
      <td style="padding:10px;color:#666">Nifty 50 PE: {pe_str}</td>
    </tr>
    <tr>
      <td style="padding:10px"><strong>Market Breadth</strong></td>
      <td style="padding:10px;color:{b_color};font-weight:bold">{b_status}</td>
      <td style="padding:10px;color:#666">{breadth_str} stocks above 200-DMA</td>
    </tr>
  </table>

  {alerts_section}

  <hr style="margin-top:30px">
  <p style="color:#999;font-size:11px">
    Quantitative Portfolio Manager | Not financial advice
  </p>
</body>
</html>"""
        subject = (
            f"🌅 Morning Digest {date_str} | "
            f"₹{portfolio_value:,.0f} | {t_label}"
            + (" | ⚠️ EXIT ALERTS" if sell_alerts else "")
        )
        return self._send(subject, html)

    # ── Weekly analysis ───────────────────────────────────────────────────────

    def send_weekly_analysis(
        self,
        regime: dict,
        approved_candidates: list[dict],
        holdings_performance: list[dict],
        date_str: str = "",
    ) -> bool:
        """Saturday 9 AM email: filtered candidates + holdings P&L."""
        if approved_candidates:
            cand_rows = "".join(
                f"<tr>"
                f"<td style='padding:6px'><strong>{c.get('Ticker','')}</strong></td>"
                f"<td style='padding:6px'>{c.get('Sector','')}</td>"
                f"<td style='padding:6px'>{float(c.get('ROC_6M',0)):.1f}%</td>"
                f"<td style='padding:6px'>{float(c.get('RSI_Weekly',0)):.1f}</td>"
                f"<td style='padding:6px'>{float(c.get('ROE',0)):.1f}%</td>"
                f"</tr>"
                for c in approved_candidates
            )
            cand_section = f"""
            <table border="1" cellpadding="0" cellspacing="0"
                   style="border-collapse:collapse;width:100%;font-size:14px">
              <tr style="background:#d4edda;font-weight:bold">
                <th style="padding:8px">Ticker</th>
                <th style="padding:8px">Sector</th>
                <th style="padding:8px">ROC 6M</th>
                <th style="padding:8px">RSI</th>
                <th style="padding:8px">ROE</th>
              </tr>
              {cand_rows}
            </table>"""
        else:
            cand_section = "<p><em>No candidates passed all filters this week. Paste fresh data into the Signals sheet.</em></p>"

        if holdings_performance:
            hold_rows = "".join(
                f"<tr>"
                f"<td style='padding:6px'>{h.get('Ticker','')}</td>"
                f"<td style='padding:6px;"
                f"color:{'#28a745' if float(h.get('pnl_pct',0)) >= 0 else '#dc3545'}'>"
                f"{float(h.get('pnl_pct',0)):+.1f}%</td>"
                f"<td style='padding:6px'>{float(h.get('CurrentWeight',0)):.1f}%</td>"
                f"</tr>"
                for h in holdings_performance
            )
            hold_section = f"""
            <table border="1" cellpadding="0" cellspacing="0"
                   style="border-collapse:collapse;width:100%;font-size:14px">
              <tr style="background:#f8f9fa;font-weight:bold">
                <th style="padding:8px">Ticker</th>
                <th style="padding:8px">P&amp;L %</th>
                <th style="padding:8px">Weight</th>
              </tr>
              {hold_rows}
            </table>"""
        else:
            hold_section = "<p><em>No holdings data.</em></p>"

        trend_label = regime.get("trend", {}).get("trend", "?")
        html = f"""<!DOCTYPE html>
<html>
<body style="font-family:Arial,sans-serif;max-width:700px;margin:auto;color:#333">
  <h2 style="color:#1a1a2e;border-bottom:2px solid #4a90e2;padding-bottom:8px">
    📅 Weekly Portfolio Analysis — {date_str}
  </h2>
  <p>
    <strong>Regime:</strong> {regime.get('regime_label','—')} &nbsp;|&nbsp;
    <strong>Equity Cap:</strong> {regime.get('equity_cap',0)*100:.0f}%
  </p>

  <h3>🔍 Approved Candidates This Week ({len(approved_candidates)})</h3>
  {cand_section}

  <h3>📦 Holdings Performance</h3>
  {hold_section}

  <hr style="margin-top:30px">
  <p style="color:#999;font-size:11px">
    Next action: If it is the 1st Saturday of the month, the full rebalance plan
    will arrive in a separate email. Not financial advice.
  </p>
</body>
</html>"""
        subject = f"📅 Weekly Analysis {date_str} | {trend_label} Market | {len(approved_candidates)} candidates"
        return self._send(subject, html)

    # ── Monthly rebalance ─────────────────────────────────────────────────────

    def send_monthly_rebalance(self, html_plan: str, date_str: str = "") -> bool:
        """1st Saturday email: full rebalance plan HTML."""
        subject = f"🔄 Monthly Rebalance Plan — {date_str}"
        return self._send(subject, html_plan)

    # ── Test ──────────────────────────────────────────────────────────────────

    def send_test(self) -> bool:
        """Fire a test email to verify SMTP credentials are working."""
        html = """<!DOCTYPE html>
<html>
<body style="font-family:Arial,sans-serif;max-width:500px;margin:auto">
  <h2 style="color:#28a745">✅ Email Configuration Test Passed</h2>
  <p>Your Quantitative Portfolio Manager email notifications are configured correctly.</p>
  <p>You will receive:</p>
  <ul>
    <li>🌅 <strong>Daily digest</strong> at 8:00 AM IST (Mon–Fri)</li>
    <li>📅 <strong>Weekly analysis</strong> every Saturday at 9:00 AM IST</li>
    <li>🔄 <strong>Monthly rebalance plan</strong> on the 1st Saturday of each month</li>
  </ul>
</body>
</html>"""
        return self._send("✅ Portfolio Manager — Email Test", html)
