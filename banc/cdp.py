# SPDX-License-Identifier: AGPL-3.0-or-later
"""Pilote Chrome par le protocole CDP, sans aucune dépendance.

POURQUOI CE FICHIER EXISTE ET POURQUOI IL EST DANS LE DÉPÔT. Les bancs de cette
application ont besoin d'un VRAI navigateur : un volet d'aperçu non peint ne
livre ni requestAnimationFrame, ni ResizeObserver, ni le chargement différé des
images, et il ne sait pas émettre un bouton du milieu. CDP sait tout cela, et
ses événements sont TRUSTED — ce qui est la première chose à vérifier avant
d'éprouver une interface.

Le WebSocket est écrit à la main : une dépendance de plus serait une dépendance
à installer sur chaque poste qui veut rejouer le banc.

Ce fichier a d'abord vécu dans un dossier temporaire, et il a été PERDU avec lui.
Un banc qui ne survit pas à la session ne protège rien.
"""
from __future__ import annotations

import base64
import json
import os
import socket
import struct
import subprocess
import tempfile
import time
import urllib.request

CHROME = r"C:\Program Files\Google\Chrome\Application\chrome.exe"


# --------------------------------------------------------------- WebSocket
class WS:
    def __init__(self, url: str):
        assert url.startswith("ws://"), url
        hote, chemin = url[5:].split("/", 1)
        h, p = hote.split(":")
        self.s = socket.create_connection((h, int(p)), timeout=20)
        cle = base64.b64encode(os.urandom(16)).decode()
        self.s.sendall((
            "GET /%s HTTP/1.1\r\nHost: %s\r\nUpgrade: websocket\r\n"
            "Connection: Upgrade\r\nSec-WebSocket-Key: %s\r\n"
            "Sec-WebSocket-Version: 13\r\n\r\n" % (chemin, hote, cle)).encode())
        tampon = b""
        while b"\r\n\r\n" not in tampon:
            tampon += self.s.recv(4096)
        assert b"101" in tampon.split(b"\r\n")[0], tampon[:200]
        self.reste = tampon.split(b"\r\n\r\n", 1)[1]
        self.n = 0

    def _envoyer(self, data: str):
        charge = data.encode()
        n = len(charge)
        tete = b"\x81"
        if n < 126:
            tete += struct.pack("!B", 0x80 | n)
        elif n < 65536:
            tete += struct.pack("!BH", 0x80 | 126, n)
        else:
            tete += struct.pack("!BQ", 0x80 | 127, n)
        cle = os.urandom(4)
        self.s.sendall(tete + cle + bytes(c ^ cle[i % 4] for i, c in enumerate(charge)))

    def _lire(self, n: int) -> bytes:
        while len(self.reste) < n:
            bout = self.s.recv(65536)
            if not bout:
                raise IOError("connexion fermée")
            self.reste += bout
        out, self.reste = self.reste[:n], self.reste[n:]
        return out

    def _recevoir(self) -> str:
        while True:
            t = self._lire(2)
            opcode, n = t[0] & 0x0F, t[1] & 0x7F
            if n == 126:
                n = struct.unpack("!H", self._lire(2))[0]
            elif n == 127:
                n = struct.unpack("!Q", self._lire(8))[0]
            charge = self._lire(n)
            if opcode == 0x8:
                raise IOError("le pair a fermé")
            if opcode == 0x9:                       # ping → pong
                self.s.sendall(b"\x8a\x80" + os.urandom(4))
                continue
            if opcode in (0x1, 0x2):
                return charge.decode("utf-8", "replace")

    def appel(self, methode: str, **params):
        self.n += 1
        self._envoyer(json.dumps({"id": self.n, "method": methode, "params": params}))
        t0 = time.time()
        while time.time() - t0 < 60:
            m = json.loads(self._recevoir())
            if m.get("id") == self.n:
                if "error" in m:
                    raise RuntimeError("%s : %s" % (methode, m["error"]))
                return m.get("result", {})
        raise TimeoutError(methode)


# ------------------------------------------------------------------ Chrome
class Navigateur:
    def __init__(self, url: str, largeur=1400, hauteur=900, port=0):
        # Port LIBRE et non fixe : un Chrome de débogage laissé en vie par un
        # essai précédent tenait le port, et le suivant échouait sur un
        # « Chrome n'a pas ouvert de page » qui n'apprenait rien.
        if not port:
            s = socket.socket()
            s.bind(("127.0.0.1", 0))
            port = s.getsockname()[1]
            s.close()
        self.profil = tempfile.mkdtemp(prefix="banc-pdf-")
        self.p = subprocess.Popen([
            CHROME, "--headless=new", "--remote-debugging-port=%d" % port,
            "--user-data-dir=" + self.profil, "--no-first-run",
            "--no-default-browser-check", "--disable-gpu",
            "--force-device-scale-factor=1",
            "--window-size=%d,%d" % (largeur, hauteur), url],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        cible = None
        for _ in range(120):
            time.sleep(0.25)
            try:
                d = json.load(urllib.request.urlopen(
                    "http://127.0.0.1:%d/json" % port, timeout=3))
            except Exception:
                continue
            pages = [x for x in d if x.get("type") == "page" and x.get("webSocketDebuggerUrl")]
            if pages:
                cible = pages[0]
                break
        assert cible, "Chrome n'a pas ouvert de page"
        self.ws = WS(cible["webSocketDebuggerUrl"])
        for dom in ("Page", "Runtime", "Network"):
            self.ws.appel(dom + ".enable")

    def js(self, expr: str, attendre=True):
        """Évalue `expr` dans la page. Le corps est enveloppé dans une fonction
        async : `await` y marche, et il faut un `return` explicite."""
        r = self.ws.appel("Runtime.evaluate", expression="(async()=>{%s})()" % expr,
                          returnByValue=True, awaitPromise=attendre)
        if r.get("exceptionDetails"):
            d = r["exceptionDetails"]
            raise RuntimeError("JS : " + (d.get("exception", {}).get("description")
                                          or json.dumps(d))[:400])
        return r["result"].get("value")

    def souris(self, type_, x, y, bouton="middle", boutons=4, clics=1):
        self.ws.appel("Input.dispatchMouseEvent", type=type_, x=x, y=y, button=bouton,
                      buttons=boutons, clickCount=clics, pointerType="mouse")

    def touche(self, cle, code=None, vk=0):
        for t in ("keyDown", "keyUp"):
            self.ws.appel("Input.dispatchKeyEvent", type=t, key=cle,
                          code=code or cle, windowsVirtualKeyCode=vk)

    def fenetre(self, largeur, hauteur):
        self.ws.appel("Emulation.setDeviceMetricsOverride", width=largeur,
                      height=hauteur, deviceScaleFactor=1, mobile=False)

    def image(self, chemin: str):
        d = self.ws.appel("Page.captureScreenshot", format="png")
        with open(chemin, "wb") as f:
            f.write(base64.b64decode(d["data"]))
        return chemin

    def fermer(self):
        try:
            self.p.terminate()
        except Exception:
            pass
