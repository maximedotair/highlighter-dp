import json
import re
import difflib
import rapidfuzz
import unicodedata
import string
from typing import List, Tuple, Dict, Set, Optional, Sequence, Any, Union, Match

print("Lancement du script...")

# --- Configuration des fichiers et style HTML ---
JSON_FILE: str = 'quotes_exercice.json'
MARKDOWN_FILE: str = 'input_text_exercice.md'
FINAL_JSON_FILE: str = 'final.json'
FINAL_MD_FILE: str = 'final.md'
FINAL_HTML_FILE: str = 'final.html'
HTML_HEADER: str = """<!DOCTYPE html>
<html lang=\"fr\">
<head>
    <meta charset=\"UTF-8\">
    <title>Document</title>
    <style>
        body { font-family: Arial, sans-serif; line-height: 1.6; padding: 20px; }
        h1, h2, h3, h4, h5, h6 { color: #333; }
        .quote-highlight { font-weight: bold; color: blue; display: inline; }
    </style>
</head>"""

# --- Constantes de traitement ---
WINDOW_WORDS: int = 40
STEP_WORDS: int = 13
MIN_SEGMENT_MATCH_RATIO: float = 0.75
RAW_SEARCH_WINDOW_BACKWARD: int = 10
RAW_SEARCH_MIN_WINDOW_FORWARD: int = 50
RAW_SEARCH_WINDOW_MULTIPLIER: float = 1.5
FUZZY_ALIGNMENT_SCORE_CUTOFF: float = 85

# --- Fonctions utilitaires ---
WORD_SEPARATORS: Set[str] = set(string.whitespace + string.punctuation)

def preprocess_text(text: str) -> str:
    text = text.lower()
    return re.sub(r'[\t ]+', ' ', text).strip()

def remove_hyphenation(text: str) -> str:
    text = re.sub(r'(\w+)-\s*\n\s*(\w+)', r'\1\2', text)
    return re.sub(r'\s+',' ', text.replace('\n',' ')).strip()

def normalize_for_search(text: str) -> str:
    text = text.lower()
    text = "".join(c for c in unicodedata.normalize('NFKD', text) if not unicodedata.combining(c))
    text = re.sub(r'[^a-z0-9\s]', '', re.sub(r'\s+', ' ', text)).strip()
    return text

def map_fully_normalized_to_processed(idx: int, blocks: Sequence[difflib.Match]) -> int:
    for b in blocks:
        if b.b <= idx < b.b + b.size:
            return b.a + (idx - b.b)
    best: int = -1
    dist: float = float('inf')
    for b in blocks:
        if b.size == 0: continue
        d: float = abs(b.b - idx)
        if d < dist:
            dist, best = d, b.a
    return best

def map_normalized_to_raw(idx: int, blocks: Sequence[difflib.Match]) -> int:
    for b in blocks:
        if b.b <= idx < b.b + b.size:
            return b.a + (idx - b.b)
    best: int = -1
    dist: float = float('inf')
    for b in blocks:
        if b.size == 0: continue
        d: float = abs(b.b - idx)
        if d < dist:
            dist, best = d, b.a
    return best

def adjust_indices_to_word_boundaries(start: int, end: int, text: str) -> Tuple[int, int]:
    L: int = len(text)
    while start > 0 and text[start-1] not in WORD_SEPARATORS: start -= 1
    while end < L and text[end-1] not in WORD_SEPARATORS and text[end] not in WORD_SEPARATORS: end += 1
    return start, end

def get_line_number(idx: int, text: str) -> int:
    return text.count('\n', 0, idx) + 1

# --- Étape 1: Chargement des données ---
try:
    with open(JSON_FILE, 'r', encoding='utf-8') as f:
        json_quotes: List[str] = json.load(f)
except Exception as e:
    print(f"ERREUR chargement {JSON_FILE}: {e}")
    exit(1)

try:
    with open(MARKDOWN_FILE, 'r', encoding='utf-8') as f:
        raw_md: str = f.read()
except Exception as e:
    print(f"ERREUR chargement {MARKDOWN_FILE}: {e}")
    exit(1)

# --- Étape 2: Prétraitement du Markdown ---
processed_md: str = preprocess_text(remove_hyphenation(raw_md))
fully_norm_md: str = normalize_for_search(processed_md)
proc_norm_blocks: Sequence[difflib.Match] = difflib.SequenceMatcher(None, processed_md, fully_norm_md, autojunk=False).get_matching_blocks()

# --- Étape 3: Prétraitement des citations ---
processed_quotes: List[str] = [preprocess_text(q) for q in json_quotes]

# --- Étape 4: Segments glissants ---
words: List[str] = processed_md.split(' ')
segments: List[str] = [" ".join(words[i:i+WINDOW_WORDS]) for i in range(0, len(words)-WINDOW_WORDS+1, STEP_WORDS)]

# --- Étape 5: Recherche des correspondances ---
results: List[Dict[str, Optional[str]]] = []
best_matches: Dict[int, str] = {}
for i, orig in enumerate(json_quotes):
    pq: str = processed_quotes[i]
    found: Optional[str] = None
    # 5a. Recherche exacte sur version normalisée
    nq: str = normalize_for_search(pq)
    pos: int = fully_norm_md.find(nq) if nq else -1
    if pos >= 0:
        s: int = map_fully_normalized_to_processed(pos, proc_norm_blocks)
        e: int = map_fully_normalized_to_processed(pos + len(nq), proc_norm_blocks)
        found = processed_md[s:e]
        best_matches[i] = found
    else:
        # 5b. Analyse par fenêtres
        best_ratio: float = 0.0
        best_det: Optional[Tuple[str, List[difflib.Match]]] = None
        for idx, seg in enumerate(segments):
            mb: List[difflib.Match] = [b for b in difflib.SequenceMatcher(None, pq, seg, autojunk=False).get_matching_blocks() if b.size>0]
            ratio: float = sum(b.size for b in mb) / len(pq) if pq else 0.0
            if ratio >= MIN_SEGMENT_MATCH_RATIO:
                orat: float = difflib.SequenceMatcher(None, pq, seg, autojunk=False).ratio()
                if orat > best_ratio:
                    best_ratio, best_det = orat, (seg, mb)
        if best_det:
            seg, mb = best_det
            s = min(b.b for b in mb)
            e = max(b.b + b.size for b in mb)
            found = seg[s:e]
            best_matches[i] = found
    results.append({'source': orig, 'found_in_processed_text': found})

# --- Étape 6: Écriture de final.json ---
print(f"\nÉcriture des résultats dans {FINAL_JSON_FILE}...", flush=True)
try:
    with open(FINAL_JSON_FILE, 'w', encoding='utf-8') as f:
        json.dump(results, f, ensure_ascii=False, indent=4)
    print(f" -> {len(results)} résultats écrits dans {FINAL_JSON_FILE}.", flush=True)
except Exception as e:
    print(f"ERREUR lors de l'écriture de {FINAL_JSON_FILE}: {e}", flush=True)

# --- Étape 7: Recherche des positions brutes ---
norm_raw: str = normalize_for_search(raw_md)
raw_blocks: Sequence[difflib.Match] = difflib.SequenceMatcher(None, raw_md, norm_raw, autojunk=False).get_matching_blocks()
potential: List[Tuple[int, int]] = []
for i, r in enumerate(results):
    ft: Optional[str] = r['found_in_processed_text']
    if ft:
        nq = normalize_for_search(ft)
        match: Match[str]
        for match in re.finditer(re.escape(nq), norm_raw):
            rs: int = map_normalized_to_raw(match.start(), raw_blocks)
            if rs >= 0:
                potential.append((i, rs))

# --- Étape 8: Affinage local et collecte des intervalles ---
ranges: List[Tuple[int, int]] = []
for i, rs in sorted(potential, key=lambda x: x[1]):
    ft = results[i]['found_in_processed_text']
    # Vérifier que ft n'est pas None avant de continuer
    if ft is None:
        continue # Passer à l'itération suivante si ft est None
    sw: int = max(0, rs - RAW_SEARCH_WINDOW_BACKWARD)
    aw: int = max(RAW_SEARCH_MIN_WINDOW_FORWARD, int(len(ft) * RAW_SEARCH_WINDOW_MULTIPLIER))
    window: str = raw_md[sw:rs+aw]
    # Le type de retour de partial_ratio_alignment est Optionnel, il faut vérifier
    align: Optional[Tuple[int, int, int, int, int]] = rapidfuzz.fuzz.partial_ratio_alignment(ft, window, score_cutoff=FUZZY_ALIGNMENT_SCORE_CUTOFF)
    if align:
        # Utiliser directement les indices alignés par rapidfuzz
        _, qs, qe, ws, we = align
        fs: int = sw + ws  # Indice de début dans raw_md
        fe: int = sw + we  # Indice de fin dans raw_md
        s, e = adjust_indices_to_word_boundaries(fs, fe, raw_md)
        if e > s:
            ranges.append((s, e))

# --- Étape 9: Fusion des intervalles ---
merged: List[Tuple[int, int]] = []
if ranges:
    ranges.sort()
    cs: int
    ce: int
    cs, ce = ranges[0]
    for ns, ne in ranges[1:]:
        if ns <= ce and get_line_number(ce-1, raw_md) == get_line_number(ns, raw_md):
            ce = max(ce, ne)
        else:
            merged.append((cs, ce))
            cs, ce = ns, ne
    merged.append((cs, ce))

# --- Étape 10: Génération de final.md avec surlignage ---
parts: List[str] = []
last: int = 0
for s, e in merged:
    parts.append(raw_md[last:s])
    parts += ['<u>', raw_md[s:e], '</u>']
    last = e
parts.append(raw_md[last:])
with open(FINAL_MD_FILE, 'w', encoding='utf-8') as f:
    f.write(''.join(parts))

# --- Étape 11: Conversion HTML ligne par ligne avec état du span ---
print(f"\nConversion HTML de {FINAL_MD_FILE} en {FINAL_HTML_FILE} (gestion état span par ligne)...", flush=True)

try:
    with open(FINAL_MD_FILE, 'r', encoding='utf-8') as f:
        md_content: str = f.read()

    html_body_parts: List[str] = []
    is_span_open_globally: bool = False # État du span entre les blocs/lignes

    # Diviser en blocs basés sur une ou plusieurs lignes vides
    blocks: List[str] = re.split(r'\n\s*\n', md_content)

    for block_raw in blocks:
        block_trimmed: str = block_raw.strip()
        if not block_trimmed:
            continue

        # Détecter si c'est un titre Markdown
        heading_match: Optional[Match[str]] = re.match(r'^(#{1,6})\s+(.*)', block_trimmed, re.DOTALL)
        if heading_match:
            # --- Traitement Titre ---
            level: int = len(heading_match.group(1))
            tag_name: str = f'h{level}'
            # Pour les titres, prendre le contenu après les #
            content_to_process: str = heading_match.group(2).strip()
            # Remplacer les sauts de ligne internes par des espaces pour les titres
            content_to_process = re.sub(r'\s*\n\s*', ' ', content_to_process)

            processed_html_content: str = ""
            local_span_state: bool = is_span_open_globally # État au début du titre

            # Gérer l'ouverture initiale du span si nécessaire
            if local_span_state and not content_to_process.startswith('<u>'):
                 processed_html_content += '<span class="quote-highlight">'

            # Traiter le contenu inline (<u>, </u>)
            parts_title: List[str] = re.split(r'(<u>|</u>)', content_to_process)
            for part in parts_title:
                if not part: continue
                if part == '<u>':
                    if not local_span_state:
                        processed_html_content += '<span class="quote-highlight">'
                        local_span_state = True
                elif part == '</u>':
                    if local_span_state:
                        processed_html_content += '</span>'
                        local_span_state = False
                else:
                    processed_html_content += part

            # Gérer la fermeture finale du span si nécessaire
            if local_span_state and not processed_html_content.rstrip().endswith('</span>'):
                 processed_html_content += '</span>'
                 # L'état pour le prochain élément reste True si on ferme ici

            # Ajouter le titre formaté
            html_body_parts.append(f'<{tag_name}>{processed_html_content}</{tag_name}>')
            # Mettre à jour l'état global
            is_span_open_globally = local_span_state

        else:
            # --- Traitement Paragraphe (ligne par ligne) ---
            lines: List[str] = block_raw.split('\n') # Diviser le bloc original en lignes
            for line in lines:
                line_trimmed: str = line.strip()
                if not line_trimmed: # Ignorer les lignes vides
                    continue

                tag_name_p: str = 'p'
                content_to_process_p: str = line_trimmed # Traiter la ligne individuelle

                processed_html_content_p: str = ""
                local_span_state_p: bool = is_span_open_globally # État au début de la ligne

                # Gérer l'ouverture initiale du span si nécessaire
                if local_span_state_p and not content_to_process_p.startswith('<u>'):
                    processed_html_content_p += '<span class="quote-highlight">'

                # Traiter le contenu inline (<u>, </u>) de la ligne
                parts_p: List[str] = re.split(r'(<u>|</u>)', content_to_process_p)
                for part in parts_p:
                    if not part: continue
                    if part == '<u>':
                        if not local_span_state_p:
                            processed_html_content_p += '<span class="quote-highlight">'
                            local_span_state_p = True
                    elif part == '</u>':
                        if local_span_state_p:
                            processed_html_content_p += '</span>'
                            local_span_state_p = False
                    else:
                        processed_html_content_p += part

                # Gérer la fermeture finale du span si nécessaire pour cette balise <p>
                if local_span_state_p and not processed_html_content_p.rstrip().endswith('</span>'):
                     processed_html_content_p += '</span>'
                     # Important : local_span_state reste True pour la prochaine ligne

                # Ajouter le paragraphe formaté pour cette ligne
                html_body_parts.append(f'<{tag_name_p}>{processed_html_content_p}</{tag_name_p}>')
                # Mettre à jour l'état global pour la PROCHAINE LIGNE ou le prochain bloc
                is_span_open_globally = local_span_state_p

    # --- Assemblage final ---
    print("  Assemblage du HTML final...", flush=True)
    final_html_body: str = "\n".join(html_body_parts)

    # Post-traitement pour supprimer les paragraphes contenant uniquement un span vide
    final_html_body = final_html_body.replace('<p><span class="quote-highlight"></span></p>', '')
    # Nettoyer les lignes vides consécutives pouvant résulter du remplacement
    final_html_body = re.sub(r'\n{2,}', '\n', final_html_body).strip()

    final_html: str = (
        HTML_HEADER + "\n"
        "<body>\n" +
        final_html_body + "\n"
        "</body>\n"
        "</html>"
    )

    with open(FINAL_HTML_FILE, 'w', encoding='utf-8') as f:
        f.write(final_html)

    print(f" -> Fichier '{FINAL_HTML_FILE}' créé avec succès.", flush=True)

except FileNotFoundError:
    print(f"ERREUR: Fichier Markdown '{FINAL_MD_FILE}' non trouvé pour la conversion HTML.", flush=True)
except IOError as e:
    print(f"ERREUR: Impossible d'écrire dans le fichier HTML '{FINAL_HTML_FILE}': {e}", flush=True)
except Exception as e:
    print(f"ERREUR: Une erreur inattendue est survenue lors de la génération HTML : {e}", flush=True)

print("Terminé.", flush=True)
