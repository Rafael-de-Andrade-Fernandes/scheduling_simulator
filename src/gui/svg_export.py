"""Imagem vetorial autocontida e independente do tamanho da janela."""
from xml.sax.saxutils import escape


# Escreve a lista de formas (vinda de gantt.build_gantt) em um arquivo SVG.
# SVG é um arquivo de texto simples, então não precisa de nenhuma biblioteca extra.
def save_svg(shapes, width, height, file_path):
    """Exporta primitivas e padrões autocontidos, sem capturar a janela."""
    lines = []
    lines.append(f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">')
    lines.append(f'<rect x="0" y="0" width="{width}" height="{height}" fill="#ffffff"/>')
    # O padrão pertence ao próprio SVG, sem imagens externas ou dependências.
    lines.append('<defs><pattern id="suspended-dots" width="4" height="4" patternUnits="userSpaceOnUse">'
                 '<rect width="4" height="4" fill="#ffffff"/>'
                 '<circle cx="1" cy="1" r="0.8" fill="#000000"/>'
                 '</pattern></defs>')

    for s in shapes:
        if s.kind == "rect":
            fill = "url(#suspended-dots)" if s.pattern == "dots" else s.fill
            lines.append(f'<rect x="{s.x1}" y="{s.y1}" width="{s.x2 - s.x1}" height="{s.y2 - s.y1}" '
                         f'fill="{fill}" stroke="{s.outline}"/>')

        elif s.kind == "line":
            lines.append(f'<line x1="{s.x1}" y1="{s.y1}" x2="{s.x2}" y2="{s.y2}" '
                         f'stroke="{s.outline}" stroke-width="{s.width}"/>')

        elif s.kind == "polygon":
            points = ""
            for point in s.points:
                points += f"{point[0]},{point[1]} "
            lines.append(f'<polygon points="{points.strip()}" fill="{s.fill}" stroke="{s.outline}"/>')

        elif s.kind == "text":
            lines.append(f'<text x="{s.x1}" y="{s.y1}" font-family="sans-serif" font-size="{s.size}" '
                         f'text-anchor="{s.anchor}" dominant-baseline="central" fill="{s.fill}">'
                         f'{escape(s.text)}</text>')

    lines.append('</svg>')

    with open(file_path, 'w', encoding='utf-8') as file:
        file.write("\n".join(lines))
