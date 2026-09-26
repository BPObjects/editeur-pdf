# Éditeur PDF BPO

Remplaçant local d'Acrobat Pro pour les besoins courants : compresser, modifier
le texte, signer, supprimer / tourner / réordonner des pages, fusionner.

Tout tourne sur la machine (serveur Python local + interface dans le navigateur).
Aucun fichier ne quitte l'ordinateur.

## Lancer

**Application bureau** (recommandé) : double-cliquer sur `Editeur PDF.bat`.
Fenêtre native, boîtes Ouvrir / Enregistrer du système, aucun onglet de
navigateur. Le premier lancement crée `.venv` et installe PyMuPDF + pywebview
(~40 s). En ligne de commande : `python app.py [fichier.pdf ...]`.

Un PDF peut aussi être glissé sur l'icône de l'application, ou ouvert par
« Ouvrir avec ».

**Variante navigateur** : `Editeur PDF (navigateur).bat`, ou
`python serveur.py [--port 8790] [--sans-navigateur]` — le même éditeur servi
sur http://localhost:8790/. Utile sur une machine sans WebView2, ou pour
travailler depuis un autre poste du réseau local.

## Installer sur son poste

`python installer.py` pose l'application dans `%LOCALAPPDATA%\Programs\Editeur PDF BPO`,
crée les raccourcis Bureau et menu Démarrer, et l'enregistre pour qu'elle
apparaisse dans « Ouvrir avec » et dans les Paramètres de Windows.
`--etat` dit ce qui est posé sans rien écrire, `--desinstaller` retire tout,
`--diffuser` recopie en plus le build dans le dossier de diffusion de l'agence.
Ce dossier dépend du poste, il n'est donc pas écrit dans le source : donnez-le une
fois par `--diffuser "<dossier>"`, il est retenu dans `diffusion.txt` à côté du
script. La variable d'environnement `EDITEUR_PDF_DIFFUSION` l'emporte sur lui.

**Pourquoi un emplacement fixe.** L'exécutable était lancé depuis là où il avait
été déposé — Dropbox, la sortie de build, la copie d'un collègue — et Windows
enregistrait ce chemin-là. On se retrouvait avec quatre exemplaires de dates
différentes et un double-clic qui ouvrait le plus ancien. Règle à tenir :
**on lance l'application par son raccourci, jamais par un exe trouvé dans
Dropbox** — Windows n'a qu'une entrée de registre pour tous les exemplaires qui
portent le même nom de fichier.

**Ce que l'installateur ne fait pas.** Il ne se désigne pas « application par
défaut » pour le .pdf. Windows protège ce choix par un hachage lié au compte :
le forger est ce que fait un logiciel indésirable, et Windows le défait. Pour
désigner l'éditeur par défaut : clic droit sur un PDF → *Ouvrir avec* →
*Choisir une autre application* → **Éditeur PDF BPO** → *Toujours*. Si le bouton
reste sans effet, passer par *Paramètres* → *Applications* → *Applications par
défaut*, y taper `.pdf`, et choisir l'éditeur.

## Imprimer vers l'éditeur depuis n'importe quel logiciel

`installer.py` pose aussi une imprimante **« PDF BPO »**. Imprimer dessus depuis
Archicad, Word ou tout autre logiciel produit un PDF qui **s'ouvre tout seul
dans l'éditeur**, prêt à être compressé, signé ou assemblé.

Les cinq formats sont disponibles et mesurés à la sortie : A4 210×297, A3
297×420, A2 420×594, A1 594×841, A0 841×1189 mm. Dans la liste des formats du
logiciel, A1 et A0 s'appellent `ISOA1` et `ISOA0`.

**Comment ça marche, et pourquoi ce détour.** Windows ne sait pas fabriquer une
imprimante qui APPELLE une application : un port d'impression écrit dans un
fichier, un point c'est tout. L'imprimante écrit donc toujours dans
`Documents\Impressions BPO\impression.pdf`, et `veilleur.py` — le même
exécutable lancé avec `--veilleur`, démarré à chaque ouverture de session —
attend que le fichier soit complet, lui donne un nom daté, et l'ouvre.

Un vrai pilote d'imprimante virtuelle ferait cela seul, mais il faut le signer
et l'installer en administrateur. Ce détour ne demande ni l'un ni l'autre :
l'imprimante s'appuie sur le pilote **Microsoft Print To PDF** déjà présent dans
Windows. `installer.py --sans-imprimante` l'omet, `--desinstaller` la retire.

## Exécutable Windows

`python build.py` produit `dist/Editeur PDF BPO.exe` : un seul fichier d'environ
57 Mo, sans Python ni installation à prévoir sur la machine de destination
(WebView2 est fourni avec Windows 11). L'icône est générée par `make_icon.py`.
Les sources sont embarquées dans l'exécutable pour que le bouton **Source**
continue de les livrer, comme l'exige l'AGPL.

## Ce que ça fait

| Fonction | Comment |
|---|---|
| Compresser | Bouton **Compresser** : 4 niveaux. Les images sont rééchantillonnées (150 / 110 / 72 dpi) et réencodées en JPEG, les masques de transparence sont conservés, les polices réduites au sous-ensemble utilisé. Texte et vecteurs intacts. |
| Modifier le texte | Mode **Texte** : survoler une ligne, cliquer, retaper, Entrée. Une barre s'ouvre au-dessus de la ligne : **corps, police, gras, italique, couleur**, avec l'aperçu en direct dans le champ. La ligne d'origine est effacée (redaction sans fond) et réécrite avec la police d'origine si elle est embarquée avec les glyphes nécessaires, sinon Helvetica / Times / Courier (gras, italique respectés). Vider la ligne la supprime. |
| Ajouter du texte | Mode **Ajouter texte** : cliquer, taper, Entrée. Taille, couleur, police dans le panneau. |
| Signer | Mode **Signer** : dessiner (souris, stylet, doigt), importer une image (fond blanc rendu transparent), ou taper son nom en écriture cursive. Poser, déplacer, redimensionner, valider. Les signatures sont mémorisées dans le navigateur. |
| Défilement | Toutes les pages sont empilées : on fait défiler verticalement d'une page à l'autre, sans clic. Le numéro de page et la vignette suivent le défilement ; cliquer une vignette ou taper un numéro amène la page sous les yeux. Seules les pages proches de la vue portent une image — un dossier de 61 planches ne charge pas 61 rendus. |
| Défiler vite | **Bouton du milieu enfoncé**, puis on s'éloigne de l'ancre : la vitesse croît plus vite que la distance — quelques pages près de l'ancre, la traversée du document loin d'elle (exposant 1,6, plafond 14 000 px/s). Relâcher ou Échap arrête. Au-delà de 2 500 px/s les images ne sont plus demandées : les pages montrent leur numéro, ce qu'on cherche justement en traversant. |
| Colonne des vignettes | Elle **suit la page affichée**, et se tait une seconde et demie si l'on vient d'y défiler soi-même. On l'élargit en tirant la poignée à sa droite, par le bouton ‹→‹ ou par F4 ; au-delà de deux vignettes de front elle s'étale en grille, et les images sont redemandées à la définition réellement affichée. La largeur est retenue d'une fois sur l'autre. |
| Zoom | Barre sous la fenêtre : `−`, le niveau courant (menu déroulant), `+`. Le menu offre **Ajuster à la page**, **Ajuster à la largeur**, **Taille réelle** et sept niveaux de 25 à 400 %. Ctrl+molette ou pincement sur pavé tactile zoome à l'endroit du curseur ; en mode Sélection, on déplace la page en la tirant à la souris. L'ajustement est un **mode** : tant qu'il est actif, redimensionner la fenêtre recalcule l'échelle. |
| Pages | Colonne de gauche : clic / Ctrl / Maj pour sélectionner, **Supprimer**, tourner, **Extraire** (nouveau PDF), glisser pour réordonner. |
| Fusionner | Bouton **Fusionner** ou déposer des fichiers sur la fenêtre. PDF et images (PNG, JPG…). Inséré après la page sélectionnée s'il y en a une, sinon à la fin. |
| Annuler | Ctrl+Z, 30 niveaux, toutes opérations comprises (compression incluse). |
| Imprimer | Bouton **Imprimer** ou Ctrl+P : le PDF modifié (pas la page web) part dans la boîte d'impression du navigateur. |
| Enregistrer | Boîte « Enregistrer sous » du système (application bureau) ou téléchargement de `<nom>-modifie.pdf` (navigateur). Le fichier d'origine n'est jamais touché. |

Raccourcis : V / T / A / S changent de mode, Suppr efface les pages
sélectionnées, flèches pour changer de page, Ctrl+S enregistre, Ctrl+P imprime,
Ctrl+O ouvre.

Zoom : Ctrl + et Ctrl − parcourent les niveaux, Ctrl 0 ajuste à la page,
Ctrl 1 revient à la taille réelle, Ctrl 2 ajuste à la largeur ; `+` et `−` seuls
font la même chose hors champ de saisie.

## Limites connues

- La signature est une **image apposée**, pas une signature électronique
  certifiée (certificat X.509). Pour du eIDAS qualifié il faut un prestataire.
- La modification de texte travaille **ligne par ligne** : une ligne aux styles
  mixtes (un mot en gras) prend le style de son premier mot. Le texte n'est pas
  reflué (pas de renvoi à la ligne automatique) : une ligne rallongée déborde.
- Pas de formulaires interactifs (champs AcroForm), pas d'OCR des scans, pas de
  mot de passe (les PDF chiffrés sont refusés à l'ouverture).
- Fichiers testés jusqu'à 190 pages / 52 Mo : compression forte en ~20 s.
- L'application bureau a besoin du moteur WebView2, fourni d'origine avec
  Windows 11 et installable gratuitement sur Windows 10. À défaut, la variante
  navigateur fonctionne partout.
- Le rendu envoyé par le serveur est plafonné à 3 600 pixels de côté : au-delà
  de 400 % sur une page déjà grande, l'image s'adoucit légèrement plutôt que de
  faire attendre plusieurs secondes.

## Fichiers

- `app.py` — application bureau : fenêtre native (pywebview) + dialogues système.
- `serveur.py` — API HTTP + toute la logique PDF (classe `Document`).
  Le texte ajouté ou réécrit avec une police standard passe par les polices
  URW embarquées dans MuPDF (Nimbus Sans / Roman / Mono, équivalents métriques
  d'Helvetica, Times, Courier) enregistrées en police CID : tout l'Unicode
  couvert (—, €, œ, →…) s'écrit, et l'export ne garde que les glyphes utilisés.
- `index.html` — interface, un seul fichier, sans dépendance.
- `make_icon.py`, `build.py` — icône et construction de l'exécutable.
- `installer.py` — installation pour l'utilisateur courant, raccourcis, registre, imprimante.
- `veilleur.py` — ramasse ce que l'imprimante « PDF BPO » dépose et l'ouvre.
- `requirements.txt` / `requirements-app.txt` / `requirements-build.txt` —
  moteur seul / application bureau / outils de construction.
- `LICENSE`, `THIRD-PARTY.md` — licence et composants tiers.

## Licence

Logiciel libre sous **GNU Affero General Public License v3 ou ultérieure**
(décision du 03/09/2026). Il peut être utilisé, modifié, redistribué et vendu,
à condition que le code source correspondant reste disponible sous la même
licence pour toute personne qui l'utilise, y compris à travers un réseau.
L'application remplit cette obligation elle-même : le lien **Source** de
l'interface (route `/source.zip`) livre l'intégralité du code, et la licence
est servie sur `/LICENSE`.

Le moteur PDF (PyMuPDF / MuPDF, Artifex) est lui-même sous AGPL v3, ce qui a
dicté ce choix ; voir `THIRD-PARTY.md`.
