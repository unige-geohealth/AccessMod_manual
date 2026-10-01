# AccessMod 5 — manuel de l'utilisateur (Quarto)

Site bilingue (EN/FR) du manuel AccessMod 5, migré depuis les espaces Confluence
`EN` et `FRAN` (accessmod.atlassian.net) le 1er octobre 2026.

## Structure

| Élément | Rôle |
|---|---|
| `_quarto.yml` | Configuration du site : barre de navigation, barres latérales EN et FR (une par langue) |
| `index.qmd` | Page d'accueil avec le choix de la langue |
| `en/`, `fr/` | Une page `.qmd` par page Confluence ; `_metadata.yml` fixe la langue |
| `en/files/`, `fr/files/` | Images et pièces jointes (un sous-dossier par ID de page Confluence d'origine) |
| `styles.css` | Couleurs de texte reprises de Confluence, ajustements |
| `MIGRATION_REPORT.md` | Pages à relire après la conversion automatique |
| `tools/` | Script de conversion et modèles de `_quarto.yml` |

Chaque page renvoie vers sa traduction (lien « English version » / « Version française »
dans la marge de droite, champ `other-links` de l'en-tête YAML).

## Travailler sur le site

```bash
quarto preview      # aperçu local avec rechargement automatique
quarto render       # génère le site statique dans _site/
```

Pour ajouter une page : créer le `.qmd` dans `en/` (et son équivalent dans `fr/`),
puis l'ajouter à la barre latérale correspondante dans `_quarto.yml`.

## Publication

Chaque push sur `main` déclenche `.github/workflows/publish.yml`, qui génère le site et le publie
sur GitHub Pages : <https://unige-geohealth.github.io/AccessMod_manual/>.
Suivi des publications : onglet **Actions** du dépôt.

## Relancer la conversion depuis Confluence (optionnel)

⚠️ Cela écrase `en/`, `fr/` et `_quarto.yml`. À ne faire que tant que le contenu n'a pas
été modifié dans Quarto.

```bash
python3 tools/confluence2quarto.py <export_EN>/EN <export_FR>/FRAN .
```

Prérequis : Python 3 avec `beautifulsoup4`, et Quarto (sa version de pandoc est utilisée).
Pour modifier la navbar ou le thème, éditez `tools/_quarto.head.yml` / `tools/_quarto.tail.yml`.
