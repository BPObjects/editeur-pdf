# Composants tiers

L'Éditeur PDF BPO est distribué sous GNU AGPL v3 ou ultérieure (fichier `LICENSE`).
Il s'appuie sur les composants suivants, dont les licences sont compatibles :

| Composant | Rôle | Licence | Source |
|---|---|---|---|
| PyMuPDF | liaison Python vers MuPDF : rendu, texte, images, pages | GNU AGPL v3 (Artifex Software) | https://github.com/pymupdf/PyMuPDF |
| MuPDF | moteur PDF (embarqué dans PyMuPDF) | GNU AGPL v3 (Artifex Software) | https://mupdf.com |
| Polices URW Base 35 (Nimbus Sans, Nimbus Roman, Nimbus Mono…) | polices standard écrites dans les PDF, embarquées dans MuPDF | GNU AGPL v3 avec exception de police / LPPL (URW++) | https://github.com/ArtifexSoftware/urw-base35-fonts |
| Python 3 | bibliothèque standard (serveur HTTP, zip, json…) | PSF License | https://www.python.org |

Aucune autre dépendance : l'interface (`index.html`) n'utilise aucune
bibliothèque JavaScript, aucun service ni police distante.

Artifex propose aussi MuPDF / PyMuPDF sous licence commerciale, pour qui
souhaiterait redistribuer cet outil sans les obligations de l'AGPL.
