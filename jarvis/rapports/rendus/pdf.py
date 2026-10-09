"""PDF: le HTML du rapport imprime par Chromium headless (Playwright).

WeasyPrint aurait evite un navigateur, mais il exige GTK, penible sous
Windows; Chromium imprime exactement le HTML que l'utilisateur voit. Sur le
serveur: `py -3 -m playwright install --with-deps chromium` (deploy/).

Un navigateur par export, sous verrou: deux impressions simultanees
doubleraient la memoire (~150 Mo chacune) pour un gain nul.
"""
import html as html_module
import threading

_verrou = threading.Lock()


class ExportIndisponible(RuntimeError):
    """Chromium ou Playwright absent: le PDF n'est pas produit, HTML et Word si."""


PIED = ('<div style="width:100%;font-size:7px;color:#4a5863;padding:0 14mm;'
        'font-family:Segoe UI,DejaVu Sans,Arial,sans-serif;display:flex;'
        'justify-content:space-between;">'
        '<span>ClimatSen · {ref} · généré le {date} · données {version}</span>'
        '<span>page <span class="pageNumber"></span> / <span class="totalPages"></span></span>'
        '</div>')


def en_pdf(html: str, meta) -> bytes:
    try:
        from playwright.sync_api import Error as ErreurPlaywright
        from playwright.sync_api import sync_playwright
    except ImportError as exc:
        raise ExportIndisponible("Playwright n'est pas installe.") from exc
    pied = PIED.format(ref=html_module.escape(meta.id), date=html_module.escape(meta.genere_le),
                       version=html_module.escape(meta.version_donnees))
    with _verrou:
        try:
            with sync_playwright() as p:
                navigateur = p.chromium.launch()
                try:
                    page = navigateur.new_page()
                    page.set_content(html, wait_until="load")
                    return page.pdf(format="A4", print_background=True,
                                    display_header_footer=True,
                                    header_template="<span></span>", footer_template=pied,
                                    margin={"top": "16mm", "bottom": "18mm",
                                            "left": "14mm", "right": "14mm"})
                finally:
                    navigateur.close()
        except ErreurPlaywright as exc:
            raise ExportIndisponible("Chromium indisponible: %s" % exc) from exc
