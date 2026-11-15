# ADR-0010 — Édition de fichiers : suivi des lectures, appariement tolérant, réindentation

Statut : proposé · Spec : 002 §4.1 à §4.3, §4.9, §9 q.2, CA-26 à CA-39, CA-52

## Contexte

L'outil `edit_file` remplace du texte exact, dans un fichier lu au préalable. Il doit refuser sans effet ce qui est ambigu ou périmé, tolérer les petites différences de forme sans produire un fichier abîmé, et ne pas bloquer l'agent quand c'est son propre shell qui a modifié le fichier.

## Décision

### Contrat de l'outil

1. `edit_file(path, edits: [{old_text, new_text}])` ; une édition seule est acceptée sans liste (ADR-0009 §6). Chaque `old_text` est cherché dans le fichier **tel qu'il était avant l'action** ; tout ou rien ; les zones qui se chevauchent sont refusées ; l'application se fait de la fin vers le début du fichier. Les messages d'erreur disent quoi a échoué, le rang de l'édition fautive et comment se corriger, avec des marqueurs stables en anglais comme l'ADR-0002.
2. **Préservation** : fichier lu en octets, décodé en UTF-8 **sans traduction de fins de ligne**, réécrit tel quel hors des zones modifiées (CA-26). Fichier vide ou sans fin de ligne finale : conservé.

### Suivi des fichiers lus (`FileTracker`, par session)

3. Pour chaque fichier lu, écrit en entier ou modifié par l'agent, on enregistre, sous le chemin résolu absolu : l'empreinte SHA-256 du contenu et `(mtime_ns, taille)`. Toute lecture compte, y compris tronquée ou par plage (CA-33).
4. **À la modification** : l'outil lit déjà le fichier ; il compare l'empreinte du contenu actuel à celle enregistrée. Jamais lu → refus « lis d'abord » (CA-32). Empreinte différente → refus « changé depuis la lecture, relis » (CA-35). Le `mtime` n'est jamais décisif : un `touch` ne provoque pas de refus.
5. **Tolérance au shell** : autour de chaque appel `shell`, avant la commande on note les fichiers suivis « propres » (leur `stat` correspond à l'enregistrement) ; après la commande, ceux dont le `stat` a changé sont ré-enregistrés (nouvelle empreinte). Un fichier déjà modifié de l'extérieur *avant* la commande reste signalé comme tel (CA-36 sans affaiblir CA-35). Un changement extérieur survenu *pendant* la commande est absorbé : risque jugé négligeable.
6. Un fichier supprimé par une commande donne l'erreur « fichier absent » (la même qu'à la lecture), jamais une création.

### Appariement

7. **Exact d'abord.** Une correspondance unique l'emporte toujours. Plusieurs → refus d'ambiguïté avec le nombre d'occurrences (CA-29). Aucune → appariement tolérant.
8. **Tolérant, en une seule passe** : le fichier et l'`old_text` sont normalisés (CRLF→LF ; espaces et tabulations de fin de ligne retirés ; guillemets, apostrophes et tirets typographiques → ASCII ; indentation retirée au début de chaque ligne). La recherche se fait dans le texte normalisé ; les bornes sont reportées sur le texte original par une table de correspondance de positions. Un `old_text` multi-ligne désigne des lignes entières : une correspondance qui commence ou finit en milieu de ligne est écartée (sinon le remplacement recollerait les lignes voisines) ; un `old_text` d'une seule ligne peut s'apparier en milieu de ligne. Plusieurs correspondances → refus d'ambiguïté ; aucune → refus « introuvable » (CA-37, CA-39). Silencieux : le résultat est identique à celui d'un appariement exact.
9. **Fins de ligne** : les `\n` du `new_text` sont convertis à la convention du fichier (CRLF si le fichier utilise CRLF), après un appariement exact comme tolérant, pour qu'un fichier CRLF reste entièrement CRLF (CA-38).

### Réindentation du nouveau texte (spec §9 q.2)

10. **Seulement après un appariement tolérant dont l'indentation diffère** ; un appariement exact insère le `new_text` tel quel. On déduit une table « indentation dans `old_text` → indentation réelle dans le fichier » à partir des lignes appariées deux à deux, puis on l'applique aux lignes du `new_text` : correspondance exacte si l'indentation est connue, sinon remplacement du plus long préfixe connu, le reste de la ligne restant inchangé.
11. **Limite assumée** : un niveau d'indentation entièrement nouveau, dans un fichier qui mélange tabulations et espaces, garde l'unité du modèle. Les fichiers à indentation homogène (cas courant) sont corrects.

### Affichage (§4.9)

12. Le résultat renvoyé au modèle confirme le nombre de remplacements. L'événement transporte le chemin et un diff simple des lignes modifiées ; la ligne-titre (par défaut) ne montre que le fichier et le nombre de remplacements, le diff n'apparaît qu'en mode détaillé.

## Options considérées

| Sujet | Option | Pour | Contre |
|---|---|---|---|
| Changement extérieur | **A. Empreinte du contenu + ré-enregistrement avant/après shell** (retenue) | exact, ne cache pas un changement antérieur au shell, pas de faux positifs du `mtime` | quelques `stat` autour de chaque shell |
| | B. Ne rien détecter, comparer seulement le texte | rien à suivre | contredit CA-35 |
| | C. Ré-enregistrer tout après chaque shell | simple | cache un changement extérieur antérieur à la commande |
| | D. `mtime` seul | pas de hachage | faux refus (`touch`), changements manqués à granularité grossière |
| Appariement | **A. Normalisation unique avec table de positions** (retenue) | une règle de comptage des occurrences, couvre les cas de la spec, y compris partiels | table de positions à écrire |
| | B. Cascade de stratégies (exact, sans espaces de fin, indentation…) | courante (Pi, opencode) | règles d'ambiguïté qui se superposent, difficile à relire |
| | C. Appariement flou (`difflib`) | tolérance maximale | peut viser le mauvais endroit, contraire à « refuser dans le doute » |
| Réindentation | **A. Table de correspondance déduite des lignes appariées** (retenue) | fidèle au fichier, gère tabulations/espaces | limite sur un nouveau niveau en fichier mixte |
| | B. Aucune réindentation | trivial | fichier mal indenté (Python) sans que le modèle le sache |
| | C. Un seul décalage de base | simple | faux quand les unités diffèrent |

## Conséquences

- **Un seul algorithme de comptage** pour exact et tolérant : plus facile à tester par comportement (CA-26 à CA-39) sans tester les fonctions internes.
- Le suivi est un état de session, hors historique : il ne survit pas à la session (reprise : It. 3).
- Les cas limites de la spec §6 (fichier vide, sans fin de ligne, lecture par plage puis modification de la zone omise, chevauchements) relèvent de ce contrat.
- Lire un fichier volumineux pour l'empreinte coûte une lecture complète à chaque modification : acceptable, l'outil lit déjà le fichier.
- Assertion à tester : un refus ne laisse aucune trace sur le fichier (spec §7).
