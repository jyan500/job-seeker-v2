"""Get the user's attention: Windows toast notification + terminal bell + console line.

  python tools/notify.py "Captcha needed" "Acme - Greenhouse application"

Uses the built-in Windows toast API through PowerShell, so no extra packages
are needed. Falls back to a msg.exe popup if toasts fail.
"""
from __future__ import annotations

import subprocess
import sys
from xml.sax.saxutils import escape

PS_TOAST = r"""
[Windows.UI.Notifications.ToastNotificationManager, Windows.UI.Notifications, ContentType = WindowsRuntime] | Out-Null
[Windows.Data.Xml.Dom.XmlDocument, Windows.Data.Xml.Dom.XmlDocument, ContentType = WindowsRuntime] | Out-Null
$xml = New-Object Windows.Data.Xml.Dom.XmlDocument
$xml.LoadXml(@'
<toast scenario="reminder"><visual><binding template="ToastGeneric"><text>{title}</text><text>{message}</text></binding></visual><audio src="ms-winsoundevent:Notification.Reminder"/></toast>
'@)
$appId = '{{1AC14E77-02E7-4E5D-B744-2EB1AE5198B7}}\WindowsPowerShell\v1.0\powershell.exe'
[Windows.UI.Notifications.ToastNotificationManager]::CreateToastNotifier($appId).Show([Windows.UI.Notifications.ToastNotification]::new($xml))
"""


def notify(title: str, message: str) -> bool:
    print(f"\a\n>>> ACTION NEEDED: {title} - {message}\n", flush=True)
    script = PS_TOAST.format(title=escape(title), message=escape(message))
    try:
        r = subprocess.run(
            ["powershell", "-NoProfile", "-NonInteractive", "-Command", script],
            capture_output=True, text=True, timeout=20,
        )
        if r.returncode == 0 and not r.stderr.strip():
            return True
    except Exception:
        pass
    try:
        subprocess.run(["msg", "*", "/TIME:60", f"{title}: {message}"], timeout=10)
        return True
    except Exception:
        return False


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(2)
    ok = notify(sys.argv[1], " ".join(sys.argv[2:]) or sys.argv[1])
    sys.exit(0 if ok else 1)
