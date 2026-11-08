"""Company and FinSight brand logos as inline SVG (no internet needed during the demo).

Apple, Google (Alphabet) and NVIDIA shapes come from Simple Icons (CC0 licence).
Microsoft and Amazon are simple hand-drawn marks. Logos identify the companies only;
FinSight AI is not affiliated with any of them.
"""

import base64


def _svg(path: str, color: str, size: int) -> str:
    return (f'<svg width="{size}" height="{size}" viewBox="0 0 24 24" xmlns="http://www.w3.org/2000/svg">'
            f'<path fill="{color}" d="{path}"/></svg>')


_APPLE = "M12.152 6.896c-.948 0-2.415-1.078-3.96-1.04-2.04.027-3.91 1.183-4.961 3.014-2.117 3.675-.546 9.103 1.519 12.09 1.013 1.454 2.208 3.09 3.792 3.039 1.52-.065 2.09-.987 3.935-.987 1.831 0 2.35.987 3.96.948 1.637-.026 2.676-1.48 3.676-2.948 1.156-1.688 1.636-3.325 1.662-3.415-.039-.013-3.182-1.221-3.22-4.857-.026-3.04 2.48-4.494 2.597-4.559-1.429-2.09-3.623-2.324-4.39-2.376-2-.156-3.675 1.09-4.61 1.09zM15.53 3.83c.843-1.012 1.4-2.427 1.245-3.83-1.207.052-2.662.805-3.532 1.818-.78.896-1.454 2.338-1.273 3.714 1.338.104 2.715-.688 3.559-1.701"
_GOOGLE = "M12.48 10.92v3.28h7.84c-.24 1.84-.853 3.187-1.787 4.133-1.147 1.147-2.933 2.4-6.053 2.4-4.827 0-8.6-3.893-8.6-8.72s3.773-8.72 8.6-8.72c2.6 0 4.507 1.027 5.907 2.347l2.307-2.307C18.747 1.44 16.133 0 12.48 0 5.867 0 .307 5.387.307 12s5.56 12 12.173 12c3.573 0 6.267-1.173 8.373-3.36 2.16-2.16 2.84-5.213 2.84-7.667 0-.76-.053-1.467-.173-2.053H12.48z"
_NVIDIA = "M8.948 8.798v-1.43a6.7 6.7 0 0 1 .424-.018c3.922-.124 6.493 3.374 6.493 3.374s-2.774 3.851-5.75 3.851c-.398 0-.787-.062-1.158-.185v-4.346c1.528.185 1.837.857 2.747 2.385l2.04-1.714s-1.492-1.952-4-1.952a6.016 6.016 0 0 0-.796.035m0-4.735v2.138l.424-.027c5.45-.185 9.01 4.47 9.01 4.47s-4.08 4.964-8.33 4.964c-.37 0-.733-.035-1.095-.097v1.325c.3.035.61.062.91.062 3.957 0 6.82-2.023 9.593-4.408.459.371 2.34 1.263 2.73 1.652-2.633 2.208-8.772 3.984-12.253 3.984-.335 0-.653-.018-.971-.053v1.864H24V4.063zm0 10.326v1.131c-3.657-.654-4.673-4.46-4.673-4.46s1.758-1.944 4.673-2.262v1.237H8.94c-1.528-.186-2.73 1.245-2.73 1.245s.68 2.412 2.739 3.11M2.456 10.9s2.164-3.197 6.5-3.533V6.201C4.153 6.59 0 10.653 0 10.653s2.35 6.802 8.948 7.42v-1.237c-4.84-.6-6.492-5.936-6.492-5.936z"


def company_logo(ticker: str, size: int = 32) -> str:
    """Inline SVG logo for a supported ticker."""
    if ticker == "AAPL":
        return _svg(_APPLE, "#E5E7EB", size)   # silver on the dark theme
    if ticker == "GOOGL":
        return _svg(_GOOGLE, "#4285F4", size)
    if ticker == "NVDA":
        return _svg(_NVIDIA, "#76B900", size)
    if ticker == "MSFT":
        return (f'<svg width="{size}" height="{size}" viewBox="0 0 24 24" xmlns="http://www.w3.org/2000/svg">'
                '<rect x="1" y="1" width="10.5" height="10.5" fill="#F25022"/>'
                '<rect x="12.5" y="1" width="10.5" height="10.5" fill="#7FBA00"/>'
                '<rect x="1" y="12.5" width="10.5" height="10.5" fill="#00A4EF"/>'
                '<rect x="12.5" y="12.5" width="10.5" height="10.5" fill="#FFB900"/></svg>')
    if ticker == "AMZN":
        return (f'<svg width="{size}" height="{size}" viewBox="0 0 24 24" xmlns="http://www.w3.org/2000/svg">'
                '<text x="12" y="15" text-anchor="middle" font-family="Arial, Helvetica, sans-serif" '
                'font-size="17" font-weight="700" fill="#E5E7EB">a</text>'
                '<path d="M4.5 17.2 Q12 21.6 19.5 17.2" stroke="#FF9900" stroke-width="2" fill="none" '
                'stroke-linecap="round"/><path d="M17.2 16.1 L19.8 17 L18.6 19.3" stroke="#FF9900" '
                'stroke-width="1.8" fill="none" stroke-linecap="round" stroke-linejoin="round"/></svg>')
    return ""


BRAND_COLORS = {"AAPL": "#CBD5E1", "MSFT": "#00A4EF", "AMZN": "#FF9900", "GOOGL": "#4285F4", "NVDA": "#76B900"}

# FinSight AI mark: rising bars + trend arrow on a blue gradient tile
FINSIGHT_MARK = """<svg width="{s}" height="{s}" viewBox="0 0 48 48" xmlns="http://www.w3.org/2000/svg">
<defs><linearGradient id="fsg" x1="0" y1="0" x2="1" y2="1">
<stop offset="0" stop-color="#2563EB"/><stop offset="1" stop-color="#06B6D4"/></linearGradient></defs>
<rect width="48" height="48" rx="12" fill="url(#fsg)"/>
<rect x="10" y="27" width="6" height="11" rx="1.5" fill="#fff" opacity=".75"/>
<rect x="19.5" y="21" width="6" height="17" rx="1.5" fill="#fff" opacity=".85"/>
<rect x="29" y="15" width="6" height="23" rx="1.5" fill="#fff"/>
<path d="M9 22 L19 14 L26 18 L38 9" stroke="#fff" stroke-width="2.6" fill="none" stroke-linecap="round" stroke-linejoin="round"/>
<path d="M32.5 8.5 L38.5 8.5 L38.5 14.5" stroke="#fff" stroke-width="2.6" fill="none" stroke-linecap="round" stroke-linejoin="round"/>
</svg>"""


def finsight_mark(size: int = 40) -> str:
    return FINSIGHT_MARK.replace("{s}", str(size))


# Wide logo (mark + wordmark) saved as a file for st.logo()
def finsight_wordmark_svg() -> str:
    mark = finsight_mark(36).replace("<svg ", '<svg x="4" y="4" ', 1)
    return ('<svg width="210" height="44" viewBox="0 0 210 44" xmlns="http://www.w3.org/2000/svg">'
            + mark +
            '<text x="50" y="29" font-family="Inter, Segoe UI, Arial, sans-serif" font-size="22" '
            'font-weight="800" fill="#F8FAFC">FinSight</text>'
            '<text x="146" y="29" font-family="Inter, Segoe UI, Arial, sans-serif" font-size="22" '
            'font-weight="800" fill="#60A5FA">AI</text></svg>')


def company_logo_img(ticker: str, size: int = 32) -> str:
    """The logo as an <img> (data URI). Dark-mode extensions such as Dark Reader recolour inline SVG
    shapes (Apple's turned black on black) but leave images alone, so this shows true colours everywhere."""
    svg = company_logo(ticker, size)
    if not svg:
        return ""
    data = base64.b64encode(svg.encode("utf-8")).decode("ascii")
    return (f'<img src="data:image/svg+xml;base64,{data}" width="{size}" height="{size}" '
            f'alt="{ticker} logo" style="display:inline-block">')
