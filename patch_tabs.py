"""Replace single-map block with tabs (Precipitations + Anomalie) version."""
import re, sys

fp      = r"c:\Users\laity\Desktop\Mémoire Master\Mémoire\Traitement01\scripts\pages\evenements.py"
blk_fp  = r"c:\Users\laity\Desktop\Mémoire Master\Mémoire\Traitement01\tabs_block.txt"

with open(fp, "rb") as fh:
    raw = fh.read()
text = raw.decode("utf-8")

with open(blk_fp, "r", encoding="utf-8") as fh:
    NEW_BLOCK = fh.read()
# Remove trailing newline from txt file so we don't add an extra blank line
NEW_BLOCK = NEW_BLOCK.rstrip("\n")

# ── Locate the block to replace ──────────────────────────────────────────────
# Start: the "Carte 1" comment line
m_start = re.search(r"        # ─+ Carte 1 : Precipitations \(mm\) ─+\r?\n", text)
if not m_start:
    print("ERROR: start anchor not found"); sys.exit(1)

# End: blank line(s) just before "Panneau d'information" comment
# We search from the start anchor onwards
m_end = re.search(r"\r?\n\r?\n        # ─+ Panneau d.information", text[m_start.start():])
if not m_end:
    print("ERROR: end anchor not found"); sys.exit(1)

start_idx = m_start.start()
end_idx   = m_start.start() + m_end.start()   # keep the trailing \n\n + comment

OLD_BLOCK = text[start_idx:end_idx]
n1 = text[:start_idx].count(chr(10)) + 1
n2 = text[:end_idx].count(chr(10)) + 1
print(f"Block found: {len(OLD_BLOCK)} chars, lines {n1}-{n2}")

new_text = text[:start_idx] + NEW_BLOCK + text[end_idx:]

# Sanity checks
for sym in ["st.tabs", "Densitymapbox", "_szs", "_tab_p", "_tab_a", "_anom_ext"]:
    if sym not in new_text:
        print(f"ERROR: '{sym}' missing from patched text"); sys.exit(1)
    else:
        print(f"  OK: '{sym}' present")

with open(fp, "wb") as fh:
    fh.write(new_text.encode("utf-8"))

print(f"\nDONE — file written ({len(new_text.splitlines())} lines total)")
