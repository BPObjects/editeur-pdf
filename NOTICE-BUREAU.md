# Éditeur PDF BPO — à lire avant de l'installer

Un outil interne pour compresser, modifier, signer et assembler des PDF, sans
abonnement. Tout se passe sur votre ordinateur : **aucun fichier n'est envoyé
sur Internet**, même quand l'outil s'ouvre dans un navigateur.

---

## Sur un PC (Windows)

**1. Copiez `Editeur PDF BPO.exe` où vous voulez.** Il n'y a rien à installer :
un seul fichier, il fonctionne depuis le Bureau, un dossier ou une clé USB.
Pour un raccourci : clic droit sur le fichier → *Envoyer vers* → *Bureau*.

**2. Au premier lancement, Windows va vous faire peur.** Un écran bleu
apparaît :

> **Windows a protégé votre ordinateur**
> Microsoft Defender SmartScreen a empêché le démarrage d'une application non reconnue.

**Ce n'est pas un virus.** C'est le message que Windows affiche pour tout
programme qui n'a pas été signé auprès de Microsoft — une signature qui se loue
plusieurs centaines d'euros par an, ce qui n'a pas de sens pour un outil qu'on
se passe entre nous. Pour continuer :

> Cliquez sur **Informations complémentaires**, puis sur **Exécuter quand même**.

Windows ne le redemandera plus sur ce poste.

**3. Si vous préférez éviter cet écran**, faites un clic droit sur le fichier →
*Propriétés* → cochez **Débloquer** en bas → *OK*. Puis lancez-le normalement.

**4. Si la fenêtre ne s'ouvre pas** et qu'un message parle de « WebView2 » :
l'outil s'ouvrira tout seul dans votre navigateur, et il fonctionne aussi bien.
Laissez la petite fenêtre de message ouverte pendant que vous travaillez —
la fermer arrête l'outil.

---

## Sur un Mac

**1. Ouvrez `Editeur PDF BPO.dmg`**, puis glissez l'application sur le dossier
*Applications*.

**2. Au premier lancement, ne double-cliquez pas.** macOS refuserait avec :

> **« Éditeur PDF BPO » ne peut pas être ouvert, car Apple ne peut pas
> vérifier qu'il ne contient pas de logiciel malveillant.**

À la place : **clic droit sur l'application → Ouvrir**, puis **Ouvrir** dans la
boîte qui s'affiche. C'est le geste qui autorise l'application une fois pour
toutes. Là encore, il ne s'agit pas d'un problème de sécurité mais d'une
signature Apple payante, inutile pour un outil interne.

**3. Si vous avez oublié et double-cliqué**, allez dans *Réglages Système* →
*Confidentialité et sécurité*, descendez jusqu'au message qui mentionne
l'application, et cliquez sur **Ouvrir quand même**.

---

## Ce que fait l'outil

| | |
|---|---|
| **Compresser** | Quatre niveaux. Un catalogue de 121 pages passe de 19 à 6,5 Mo sans défaut visible à l'impression. |
| **Texte** | Cliquez sur une ligne du document et retapez-la. |
| **Ajouter texte** | Cliquez à l'endroit voulu et tapez. |
| **Signer** | Dessinez votre signature, importez-en une photo, ou tapez votre nom. Elle est conservée pour la prochaine fois. |
| **Pages** | Colonne de gauche : supprimer, tourner, réordonner en glissant, extraire dans un nouveau PDF. |
| **Fusionner** | Ajoutez d'autres PDF ou des images au document. |
| **Zoom** | Molette avec Ctrl (⌘ sur Mac), ou le menu du pourcentage : ajuster à la page, à la largeur, taille réelle. |
| **Annuler** | Ctrl+Z (⌘Z), trente fois de suite s'il le faut. |

---

## Imprimer vers l'éditeur

L'installation ajoute une imprimante nommée **PDF BPO** à votre liste
d'imprimantes. Depuis Archicad, Word ou n'importe quel logiciel, choisissez-la
au moment d'imprimer : le PDF s'ouvre tout seul dans l'éditeur, prêt à être
compressé, signé ou assemblé. Il est aussi rangé, daté, dans
*Documents / Impressions BPO*.

Tous les formats sont là, du A4 au **A0**. Dans la liste des formats, A1 et A0
peuvent s'appeler `ISOA1` et `ISOA0` — ce sont bien les bons : 594 × 841 mm et
841 × 1189 mm.

Si rien ne s'ouvre après une impression, le PDF est quand même dans
*Documents / Impressions BPO* : rien n'est perdu. Ouvrez-le à la main, et
signalez-le.

---

## Deux choses à savoir absolument

**Compresser n'enregistre pas.** Ce sont deux gestes : le bouton *Compresser*
allège le document et vous montre le gain, mais le fichier allégé n'existe sur
votre disque qu'après un clic sur **Enregistrer**.

**Votre fichier d'origine n'est jamais modifié.** L'outil produit toujours un
nouveau fichier, nommé `<votre fichier>-modifie.pdf`. Si vous fermez la fenêtre
sans enregistrer, votre travail est perdu et l'original est intact.

---

## Ce que l'outil ne fait pas

- La signature est une **image apposée**, pas une signature électronique
  certifiée. Pour un acte qui l'exige, il faut un prestataire agréé.
- Le texte se modifie **ligne par ligne**, sans remise en page : une ligne
  rallongée déborde.
- Pas de formulaires interactifs, pas de reconnaissance de texte sur un scan,
  pas de PDF protégés par mot de passe.

---

## Un souci ?

Prévenez Antoine. L'outil est développé en interne, donc tout se corrige —
dites simplement ce que vous faisiez et ce que vous avez vu à l'écran.

*Logiciel libre sous licence GNU AGPL v3. Le bouton « Source » de l'application
livre l'intégralité de son code.*
