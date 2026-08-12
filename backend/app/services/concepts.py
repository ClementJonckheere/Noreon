"""Semantic Layer — traduit le langage physique du moteur en concepts métier.

La couche Decision ne doit jamais exposer le schéma physique : un dirigeant lit
« Le chiffre d'affaires recule de 8 % », pas « total de amount_ttc en baisse ».
Le physique (orders.amount_ttc, SUM, jointures) reste, lui, dans la Preuve.

Ce module s'applique en PRÉSENTATION, à la frontière de l'API : il enrichit le
dict d'investigation (concepts + lignage) et reformule les chaînes destinées à
l'utilisateur, sans toucher à l'état interne du moteur (le benchmark, qui lit
l'objet Investigation, reste inchangé).

Le vocabulaire vient d'un lexique métier (c'est le rôle d'une Semantic Layer) —
et non d'un `if column == "amount_ttc"` codé dans le frontend.

--------------------------------------------------------------------------------
NOTE D'ARCHITECTURE (à ne pas perdre)

Ce module est aujourd'hui la couche de projection sémantique de PRÉSENTATION :

    Investigation physique  →  projection sémantique  →  UI métier

Il n'altère pas l'objet Investigation (benchmark intact), mais cela signifie que
le moteur RAISONNE encore sur « amount_ttc » puis remplace le libellé à la sortie.
Ce n'est pas encore une Semantic Layer complète.

Cible (hors de ce commit) — les ConceptReference doivent entrer dans le
planning/reasoning, pas seulement dans le rendu :

    Schéma physique → Concepts métier → Reasoning/planning → Investigation → Evidence

Le moteur devra pouvoir raisonner sur `concept_id = "revenue"`. On préservera le
benchmark en conservant DEUX représentations : `investigation.raw` (ce que le
moteur a exécuté) et `investigation.semantic` (les concepts rattachés). Objectif :
que Noreon ne soit pas « un moteur SQL avec un excellent traducteur de labels ».
"""
from __future__ import annotations

import re

# --- Lexique métier : jetons physiques → concept ---------------------------
_REGION = ("region", "région", "regions")
_CITY = ("city", "ville", "villes")
_STORE = ("store", "shop", "magasin", "boutique", "pos")
_PRODUCT = ("product", "produit", "article", "item", "sku", "famille", "categorie", "catégorie", "category")
_SUPPLIER = ("supplier", "fournisseur", "vendor")
_CHANNEL = ("channel", "canal", "source")
_SEGMENT = ("segment", "tier", "categorie_client")
_DEPARTMENT = ("department", "departement", "département", "service", "equipe", "équipe", "team")
_CUSTOMER = ("customer", "client", "clients", "customers")
_EMPLOYEE = ("employee", "salarie", "salarié", "agent", "collaborateur")
_LOYALTY = ("loyalty", "loyal", "fidelite", "fidélité", "fidelity")
_GENDER = ("gender", "sexe", "sex", "genre")
_AGE = ("age", "âge", "ages")

# Domaines (table racine → intitulé d'analyse).
_DOMAINS = [
    (("order", "commande", "sale", "vente"), "Ventes"),
    (("customer", "client"), "Clients"),
    (("employee", "salarie", "rh", "hr", "staff"), "Ressources humaines"),
    (("invoice", "facture", "finance", "compta"), "Finance"),
    (("stock", "inventory", "supply", "appro"), "Supply chain"),
    (("product", "produit", "article"), "Catalogue"),
]

_MONEY = ("amount", "montant", "revenue", "ca", "chiffre", "price", "prix", "cost", "cout", "coût", "total", "mrr", "arr")
_TTC = ("ttc", "gross", "incl", "brut")
_HT = ("ht", "net", "excl", "hors")


def _tokens(s: str) -> set[str]:
    return {t for t in re.split(r"[_\W]+", (s or "").lower()) if t}


def _any(toks: set[str], hints) -> bool:
    return any(h in toks or any(h in t for t in toks) for h in hints)


def measure_concept(metric_label: str) -> str:
    """« total de amount_ttc » → « Chiffre d'affaires » ; « nombre de … » → volume."""
    low = (metric_label or "").lower()
    toks = _tokens(metric_label)
    if low.startswith("nombre") or "count" in toks:
        return "Nombre d'enregistrements"
    if _any(toks, _MONEY):
        if _any(toks, _HT) and not _any(toks, _TTC):
            return "Chiffre d'affaires (HT)"
        return "Chiffre d'affaires"
    if any(w in low for w in ("moyenne", "moyen", "avg")):
        return "Valeur moyenne"
    # À défaut : humaniser la dernière portion (sans préfixe « total de »).
    core = re.sub(r"^(total de|somme de|moyenne de)\s+", "", low).strip()
    return core[:1].upper() + core[1:] if core else (metric_label or "Mesure")


def _concept_for_tokens(toks: set[str]) -> str | None:
    # Fidélité / genre / âge testés AVANT le générique : ce sont des axes
    # d'analyse fréquents dont le libellé physique fuit sinon (« loyalty_points »).
    if _any(toks, _LOYALTY):
        return "Niveau de fidélité"
    if _any(toks, _GENDER):
        return "Genre"
    if _any(toks, _AGE):
        return "Tranche d'âge"
    if _any(toks, _REGION):
        return "Région"
    if _any(toks, _SEGMENT):
        return "Segment client"
    if _any(toks, _CITY):
        return "Ville"
    if _any(toks, _STORE):
        return "Magasin"
    if _any(toks, _SUPPLIER):
        return "Fournisseur"
    if _any(toks, _CHANNEL):
        return "Canal"
    if _any(toks, _DEPARTMENT):
        return "Département"
    if _any(toks, _PRODUCT):
        return "Produit"
    if _any(toks, _EMPLOYEE):
        return "Collaborateur"
    if _any(toks, _CUSTOMER):
        return "Client"
    return None


def dimension_concept(dim_label: str) -> tuple[str, str | None]:
    """« region (stores) » → (« Région », « stores.region »)."""
    physical = None
    inner = dim_label
    m = re.match(r"^(.*?)\s*\((.+)\)\s*$", dim_label or "")
    if m:
        inner, table = m.group(1).strip(), m.group(2).strip()
        col = inner.split()[-1] if inner else inner
        physical = f"{table}.{col}"
    label = _concept_for_tokens(_tokens(inner)) or (inner[:1].upper() + inner[1:] if inner else dim_label)
    return label, physical


def subject_domain(table: str) -> str:
    toks = _tokens(table)
    for hints, label in _DOMAINS:
        if _any(toks, hints):
            return label
    return (table[:1].upper() + table[1:]) if table else "Analyse"


# Identifiants de concept (cible : ConceptReference{id, label, definitionVersion,
# scope}). Le libellé est l'affichage ; l'id est stable pour l'univers.
_CONCEPT_IDS = {
    "Chiffre d'affaires": "revenue", "Chiffre d'affaires (HT)": "revenue_ht",
    "Région": "region", "Segment client": "customer_segment", "Ville": "city",
    "Magasin": "store", "Fournisseur": "supplier", "Canal": "channel",
    "Département": "department", "Produit": "product", "Collaborateur": "employee",
    "Client": "customer", "Nombre d'enregistrements": "record_count", "Valeur moyenne": "average",
    "Niveau de fidélité": "loyalty_tier", "Genre": "gender", "Tranche d'âge": "age_band",
}


def _concept_id(label: str) -> str:
    if label in _CONCEPT_IDS:
        return _CONCEPT_IDS[label]
    return re.sub(r"[^a-z0-9]+", "_", (label or "").lower()).strip("_") or "concept"


def _measure_physical(metric_label: str) -> str | None:
    core = re.sub(r"^(total de|somme de|moyenne de|nombre de)\s+", "", (metric_label or "").lower()).strip()
    return core or None


# Fuite du schéma : tout « libellé (table) » résiduel dans une chaîne destinée à
# l'utilisateur devient un concept lisible — JAMAIS un nom de table/colonne.
_LEAK_RE = re.compile(r"[A-Za-zÀ-ÿ'’]+(?:\s[A-Za-zÀ-ÿ'’]+)*\s*\([a-z][a-z0-9_]*\)")


def _humanize_leaks(text):
    if not isinstance(text, str):
        return text
    return _LEAK_RE.sub(lambda m: dimension_concept(m.group(0))[0], text)


# Jetons physiques NUS (sans « (table) ») restant dans « … par « X » » ou
# « tranche de X » : une dimension explorée mais non retenue comme facteur n'entre
# pas dans les remplacements connus et arrive telle quelle (« Gender »,
# « loyalty_Points »). On ne touche qu'aux jetons qui RESSEMBLENT à du physique —
# jamais aux VALEURS de segment (« F », « Particulier », « Paris »).
# Mots de colonne génériques sans concept propre (le reste — fidélité, genre, âge,
# canal — est désormais un vrai concept du lexique).
_ENGLISH_COL = {
    "name": "Nom", "email": "E-mail", "phone": "Téléphone", "status": "Statut",
    "type": "Type", "method": "Moyen de paiement", "payment": "Paiement",
}


def _looks_physical(tok: str) -> bool:
    """Vrai si le jeton est vraisemblablement un identifiant de colonne (et non une
    valeur de segment) : présence d'un underscore, ou mot de colonne anglais connu,
    ou reconnu comme axe d'analyse par le lexique."""
    if "_" in tok:
        return True
    low = tok.lower()
    return low in _ENGLISH_COL or _concept_for_tokens({low}) is not None


def _humanize_phys_token(tok: str) -> str:
    concept = _concept_for_tokens(_tokens(tok))
    if concept:
        return concept
    words = [w for w in re.split(r"[_\s]+", tok.strip()) if w]
    out = " ".join(_ENGLISH_COL.get(w.lower(), w) for w in words).strip()
    return out[:1].upper() + out[1:] if out else tok


_TRANCHE_RE = re.compile(r"\btranche de ([A-Za-z][A-Za-z0-9_]*)")
_QUOTED_RE = re.compile(r"«\s*([A-Za-z][A-Za-z0-9_]*)\s*»")


def _tranche_repl(m) -> str:
    tok = m.group(1)
    if not _looks_physical(tok):
        return m.group(0)
    # « tranche de age » / « tranche de loyalty_points » : le concept porte déjà la
    # notion de tranche (« Tranche d'âge », « Niveau de fidélité ») → on absorbe.
    concept = _concept_for_tokens(_tokens(tok))
    if concept:
        return concept
    return f"tranche de {_humanize_phys_token(tok)}"


def _detechnify(text):
    """Traduit les identifiants physiques nus résiduels en libellés lisibles,
    sans jamais altérer les valeurs de segment (« F », « Paris »…)."""
    if not isinstance(text, str):
        return text
    text = _TRANCHE_RE.sub(_tranche_repl, text)
    text = _QUOTED_RE.sub(
        lambda m: f"« {_humanize_phys_token(m.group(1))} »" if _looks_physical(m.group(1)) else m.group(0),
        text,
    )
    return text


# Valeurs de segment CODÉES → libellé métier, appliquées seulement dans le CONTEXTE
# d'un axe connu (le genre : « F » n'a de sens que sous « Genre »). Jamais en
# aveugle — « F » pourrait être une note, une taille, une région.
_VALUE_MAPS = {
    "gender": {"f": "Femmes", "m": "Hommes", "h": "Hommes",
               "female": "Femmes", "male": "Hommes", "femme": "Femmes", "homme": "Hommes"},
}


def humanize_segment_values(text: str, concept_id: str) -> str:
    """Dans une chaîne rattachée à un axe donné, remplace ses valeurs codées entre
    guillemets (« F » → « Femmes ») — uniquement pour les axes dont on connaît le
    codage."""
    vm = _VALUE_MAPS.get(concept_id)
    if not vm or not isinstance(text, str):
        return text
    return re.sub(r"«\s*([A-Za-zÀ-ÿ]+)\s*»",
                  lambda m: f"« {vm[m.group(1).lower()]} »" if m.group(1).lower() in vm else m.group(0),
                  text)


def _rephrase_conclusion(text: str) -> str:
    """« X est orienté à la baisse ; la baisse est portée à N% par » →
    « X recule ; N % du recul se concentre sur » (descriptif, non causal)."""
    text = re.sub(r"est orienté[e]? à la baisse\s*;\s*la baisse est portée à (\d+)\s*% par",
                  r"recule ; \1 % du recul se concentre sur", text)
    text = re.sub(r"est orienté[e]? à la hausse\s*;\s*la hausse est portée à (\d+)\s*% par",
                  r"progresse ; \1 % de la hausse se concentre sur", text)
    # Retirer la mention de dimension redondante après la valeur (« … » (Région)).
    text = re.sub(r"(«[^»]+»)\s*\([A-Za-zÀ-ÿ' ]+\)", r"\1", text)
    return text


_MONTHS_FR = ["", "janvier", "février", "mars", "avril", "mai", "juin", "juillet",
              "août", "septembre", "octobre", "novembre", "décembre"]


def humanize_presentation(text):
    """Couche Decision/Understand : pluriels et dates HUMANISÉS. (La Preuve, elle,
    garde les valeurs techniques exactes — « 2024-11 », « période(s) ».)"""
    if not isinstance(text, str):
        return text
    # « 2024-11 » → « novembre 2024 »
    text = re.sub(r"\b(\d{4})-(0[1-9]|1[0-2])\b",
                  lambda m: f"{_MONTHS_FR[int(m.group(2))]} {m.group(1)}", text)
    # « 4 période(s) consécutive(s) » → « 4 périodes consécutives »
    text = re.sub(r"\b(\d+)\s+([A-Za-zÀ-ÿ]+)\(s\)",
                  lambda m: f"{m.group(1)} {m.group(2)}s" if int(m.group(1)) != 1 else f"{m.group(1)} {m.group(2)}",
                  text)
    text = re.sub(r"\b([A-Za-zÀ-ÿ]+)\(s\)", r"\1s", text)  # « consécutive(s) » résiduel
    return text


def _walk_str(node, fn):
    if isinstance(node, str):
        return fn(node)
    if isinstance(node, list):
        return [_walk_str(x, fn) for x in node]
    if isinstance(node, dict):
        return {k: _walk_str(v, fn) for k, v in node.items()}
    return node


def humanize_presentation_deep(obj):
    """Humanise toutes les chaînes d'un objet (Decision/Understand)."""
    return _walk_str(obj, humanize_presentation)


def _walk_replace(node, repls: list[tuple[str, str]]):
    if isinstance(node, str):
        out = node
        for a, b in repls:
            if a and a in out:
                out = out.replace(a, b)
        return out
    if isinstance(node, list):
        return [_walk_replace(x, repls) for x in node]
    if isinstance(node, dict):
        return {k: _walk_replace(v, repls) for k, v in node.items()}
    return node


def translate(obj, repls: list[tuple[str, str]]):
    """Applique une liste de remplacements (physique → concept) à un objet."""
    return _walk_replace(obj, repls)


# Contraction grammaticale des mesures dans la couche Decision : « une baisse de
# Chiffre d'affaires » se lit « une baisse du chiffre d'affaires ».
_MEASURE_CONTRACT = {
    "Chiffre d'affaires (HT)": "du chiffre d'affaires (HT)",
    "Chiffre d'affaires": "du chiffre d'affaires",
    "Nombre d'enregistrements": "du nombre d'enregistrements",
    "Valeur moyenne": "de la valeur moyenne",
}


def humanize_decision_text(obj):
    """Fluidifie le langage de la couche Decision (« de Chiffre d'affaires » →
    « du chiffre d'affaires ») une fois les concepts substitués."""
    def fix(t):
        if not isinstance(t, str):
            return t
        for concept, contracted in _MEASURE_CONTRACT.items():
            t = re.sub(r"\bde " + re.escape(concept), contracted, t)
        return t
    return _walk_str(obj, fix)


def apply_semantic_layer(inv: dict) -> list[tuple[str, str]]:
    """Enrichit et reformule un dict d'investigation en langage métier.

    Ajoute `subject_label`, `lineage` (physique, pour la Preuve) et `concepts`,
    puis remplace les libellés physiques par les concepts dans les chaînes
    destinées à l'utilisateur. Renvoie la liste des remplacements pour que
    l'appelant traduise aussi le message, les décisions, etc. Défensif.
    """
    if not isinstance(inv, dict):
        return []

    metric_label = inv.get("metric_label") or ""
    measure_lbl = measure_concept(metric_label)

    # Collecte des libellés de dimension présents dans l'investigation.
    dim_labels: set[str] = set()
    attr = inv.get("attribution") or {}
    for key in ("candidates", "drivers"):
        for c in attr.get(key) or []:
            if c.get("dimension"):
                dim_labels.add(c["dimension"])
    for c in inv.get("drivers_struct") or []:
        if c.get("dimension"):
            dim_labels.add(c["dimension"])
    if isinstance(inv.get("broad_based"), dict) and inv["broad_based"].get("dimension"):
        dim_labels.add(inv["broad_based"]["dimension"])

    lineage_dims = []
    repls: list[tuple[str, str]] = []
    for dl in dim_labels:
        concept, physical = dimension_concept(dl)
        repls.append((dl, concept))
        lineage_dims.append({"concept": concept, "physical": physical, "physical_label": dl})
    measure_col = _measure_physical(metric_label)
    if metric_label:
        repls.append((metric_label, measure_lbl))
    # La colonne de mesure NUE (« amount_ttc », sans « total de ») fuit dans
    # l'objectif reformulé et les décisions : on la mappe aussi vers le concept —
    # mais seulement si c'est bien un identifiant physique (pas un mot générique
    # comme « commandes », qu'on ne veut pas remplacer partout).
    if measure_col and " " not in measure_col and _looks_physical(measure_col):
        repls.append((measure_col, measure_lbl))
    # Remplacer les chaînes les plus longues d'abord (évite les recouvrements).
    repls.sort(key=lambda p: len(p[0]), reverse=True)

    # Présentation = remplacements connus, PUIS humanisation des fuites « col
    # (table) », PUIS de-technification des identifiants physiques nus résiduels.
    def _present(text):
        return _detechnify(_humanize_leaks(_walk_replace(text, repls)))

    if inv.get("conclusion"):
        inv["conclusion"] = _rephrase_conclusion(humanize_presentation(_present(inv["conclusion"])))

    # Étapes : présentation générique, PUIS humanisation des VALEURS codées selon
    # l'axe de chaque étape (« F » ne devient « Femmes » que sous « Genre »).
    if isinstance(inv.get("steps"), list):
        for st in inv["steps"]:
            if not isinstance(st, dict):
                continue
            for k, v in list(st.items()):
                st[k] = _walk_str(v, _present)
            # Le titre d'étape est souvent le libellé d'axe NU (« Gender ») : s'il
            # correspond à un concept, on l'affiche en concept (« Genre »).
            title_concept = _concept_for_tokens(_tokens(st.get("title") or ""))
            if title_concept:
                st["title"] = title_concept
            cid = _concept_id(title_concept or "")
            if cid in _VALUE_MAPS:
                for f in ("finding", "question", "title"):
                    if isinstance(st.get(f), str):
                        st[f] = humanize_segment_values(st[f], cid)
                for fig in st.get("figures") or []:
                    lbl = (fig or {}).get("label")
                    if isinstance(lbl, str) and lbl.lower() in _VALUE_MAPS[cid]:
                        fig["label"] = _VALUE_MAPS[cid][lbl.lower()]

    for field in ("key_drivers", "recommendations", "revisions", "verification"):
        if inv.get(field) is not None:
            inv[field] = _walk_str(inv[field], _present)

    # Vérification automatique : humaniser les VALEURS de segment selon leur axe
    # (« Genre · M » → « Genre · Hommes »), une fois l'axe traduit en concept.
    verif = inv.get("verification")
    if isinstance(verif, dict):
        def _humval(dim: str, seg):
            if not isinstance(seg, str):
                return seg
            vm = _VALUE_MAPS.get(_concept_id(_concept_for_tokens(_tokens(dim)) or ""))
            return vm.get(seg.lower(), seg) if vm else seg
        def _norm_dim(d):
            return _concept_for_tokens(_tokens(d or "")) or d

        w = verif.get("winner")
        if isinstance(w, dict):
            if w.get("segment"):
                w["segment"] = _humval(w.get("dimension", ""), w["segment"])
            w["dimension"] = _norm_dim(w.get("dimension"))
        # Deux colonnes physiques distinctes peuvent se projeter sur le MÊME concept
        # (« city » et « billing_city » → « Ville ») : on normalise l'axe en concept
        # PUIS on dédoublonne par (axe, segment) — pas deux lignes identiques.
        deduped, seen_keys = [], set()
        for t in verif.get("tested") or []:
            if not isinstance(t, dict):
                continue
            if t.get("segment"):
                t["segment"] = _humval(t.get("dimension", ""), t["segment"])
            t["dimension"] = _norm_dim(t.get("dimension"))
            key = (t.get("dimension"), t.get("segment"))
            if key in seen_keys:
                continue
            seen_keys.add(key)
            deduped.append(t)
        if "tested" in verif:
            verif["tested"] = deduped

    subject = inv.get("subject") or ""
    aggregation = "COUNT(*)" if measure_lbl.startswith("Nombre") else (f"SUM({measure_col})" if measure_col else None)

    inv["subject_label"] = subject_domain(subject)
    inv["measure_label_concept"] = measure_lbl
    # Lignage physique (pour la Preuve) — table, colonne, agrégation.
    inv["lineage"] = {
        "measure": {
            "concept": measure_lbl, "concept_id": _concept_id(measure_lbl),
            "table": subject or None, "column": measure_col,
            "aggregation": aggregation, "physical_label": metric_label,
            "definition_version": None, "scope": "proposed",
        },
        "dimensions": [
            {
                "concept": d["concept"], "concept_id": _concept_id(d["concept"]),
                "physical": d["physical"], "physical_label": d["physical_label"],
                "definition_version": None, "scope": "proposed",
            }
            for d in lineage_dims
        ],
    }
    # ConceptReference (cible d'architecture) : id + libellé + version + portée.
    # definition_version reste None tant qu'aucun concept n'est validé (le lexique
    # n'est qu'un pont de migration, pas la couche sémantique définitive).
    inv["concepts"] = (
        [{"kind": "measure", "id": _concept_id(measure_lbl), "label": measure_lbl,
          "definition_version": None, "scope": "proposed", "physical_label": metric_label}]
        + [{"kind": "dimension", "id": _concept_id(d["concept"]), "label": d["concept"],
            "definition_version": None, "scope": "proposed", "physical": d["physical"]}
           for d in lineage_dims]
    )
    return repls
