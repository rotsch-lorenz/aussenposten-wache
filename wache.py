#!/usr/bin/env python3
"""Außenposten-Wache für den Website-Check. Läuft in GitHub Actions, nicht auf dem Server.
Proben über HTTP/2: Seite 200, OPTIONS /check-anfrage 204 ohne Körper, Gesundheitsweg.
Ausfall = 2 Fehlschläge hintereinander (zweite Probe nach 60 s). Zustand in state/zustand.json.
Mail nur bei Wechsel ok->Ausfall und Ausfall->ok. Geheimnisse nur aus der Umgebung."""
import json, os, smtplib, ssl, sys, time
from email.message import EmailMessage
import httpx

BASIS = "https://augenweide-webdesign.de"
CHECK = "https://check.augenweide-webdesign.de"
ZUSTAND = "state/zustand.json"
H = {"Origin": BASIS, "Access-Control-Request-Method": "POST"}

def proben():
    f = []
    with httpx.Client(http2=True, timeout=15, follow_redirects=False) as c:
        def p(name, fn):
            try:
                r = fn()
                return name, r
            except Exception as e:
                f.append(f"{name}: {type(e).__name__}"); return name, None
        n, r = p("Seite", lambda: c.get(BASIS + "/website-check"))
        if r is not None and r.status_code != 200: f.append(f"Seite: HTTP {r.status_code}")
        for url in (BASIS + "/check-anfrage", CHECK + "/website-check/start"):
            n, r = p("OPTIONS " + url.split("//")[1], lambda: c.options(url, headers=H))
            if r is not None:
                if r.status_code != 204: f.append(f"{n}: HTTP {r.status_code}")
                elif r.content: f.append(f"{n}: 204 mit Körper ({len(r.content)} Byte)")
                elif r.http_version != "HTTP/2": f.append(f"{n}: nicht über HTTP/2 ({r.http_version})")
        n, r = p("Gesundheit", lambda: c.get(CHECK + "/website-check/status?id=wache"))
        if r is not None and r.status_code >= 500: f.append(f"Gesundheit: HTTP {r.status_code}")
    return f

def mail(betreff, text):
    msg = EmailMessage()
    msg["Subject"] = betreff; msg["From"] = os.environ["MAIL_VON"]; msg["To"] = os.environ["MAIL_AN"]
    msg["Date"] = time.strftime("%a, %d %b %Y %H:%M:%S +0000", time.gmtime())
    msg["X-Priority"] = "1"
    msg.set_content(text + "\n\nDiese Meldung kommt vom Außenposten (GitHub, außerhalb des Servers).")
    with smtplib.SMTP_SSL(os.environ.get("SMTP_HOST", "smtp.migadu.com"), 465, context=ssl.create_default_context(), timeout=30) as s:
        s.login(os.environ["SMTP_BENUTZER"], os.environ["SMTP_PASSWORT"]); s.send_message(msg)

def main():
    if len(sys.argv) > 1 and sys.argv[1] == "test-alarm":
        mail("Testalarm Außenposten Website-Check", "Testalarm vom Außenposten, Zeit UTC " + time.strftime("%H:%M:%S")); return
    z = json.load(open(ZUSTAND)) if os.path.exists(ZUSTAND) else {"ausfall": False}
    f = proben()
    if f and not os.environ.get("EINMAL"):
        time.sleep(60); f = proben()
    jetzt = time.strftime("%d.%m. %H:%M UTC", time.gmtime())
    print(jetzt, "FEHLER" if f else "ok", f)
    if os.environ.get("TROCKEN"): return
    if f and not z["ausfall"]:
        mail("⚠ AUSFALL Website-Check (Außenposten)", f"Ausfall des Website-Checks seit {jetzt} (zwei Proben hintereinander):\n- " + "\n- ".join(f))
        z = {"ausfall": True, "seit": jetzt}
    elif not f and z["ausfall"]:
        mail("Website-Check wieder online (Außenposten)", f"Wieder online um {jetzt}, Ausfall seit {z.get('seit')}.")
        z = {"ausfall": False}
    os.makedirs("state", exist_ok=True); json.dump(z, open(ZUSTAND, "w"))

main()
