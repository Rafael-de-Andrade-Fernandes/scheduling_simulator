"""Imagem vetorial autocontida e independente do tamanho da janela."""
from xml.sax.saxutils import escape


def save_svg(shapes, width, height, file_path):
    """Exporta as mesmas primitivas do Canvas, sem capturar nem recortar a janela."""
    lines = []
    lines.append(f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">')
    lines.append(f'<rect x="0" y="0" width="{width}" height="{height}" fill="#ffffff"/>')
    # O padrão pertence ao próprio SVG, sem imagens externas ou dependências.
    lines.append('<defs><pattern id="suspended-dots" width="4" height="4" patternUnits="userSpaceOnUse">'
                 '<rect width="4" height="4" fill="#ffffff"/>'
                 '<circle cx="1" cy="1" r="0.8" fill="#000000"/>'
                 '</pattern></defs>')

    for shape in shapes:
        if shape.kind == "rect":
            fill = "url(#suspended-dots)" if shape.pattern == "dots" else shape.fill
            lines.append(f'<rect x="{shape.x1}" y="{shape.y1}" width="{shape.x2 - shape.x1}" height="{shape.y2 - shape.y1}" '
                         f'fill="{fill}" stroke="{shape.outline}"/>')

        elif shape.kind == "line":
            lines.append(f'<line x1="{shape.x1}" y1="{shape.y1}" x2="{shape.x2}" y2="{shape.y2}" '
                         f'stroke="{shape.outline}" stroke-width="{shape.width}"/>')

        elif shape.kind == "polygon":
            points = " ".join(f"{x},{y}" for x, y in shape.points)
            lines.append(f'<polygon points="{points}" fill="{shape.fill}" stroke="{shape.outline}"/>')

        elif shape.kind == "text":
            lines.append(f'<text x="{shape.x1}" y="{shape.y1}" font-family="sans-serif" font-size="{shape.size}" '
                         f'text-anchor="{shape.anchor}" dominant-baseline="central" fill="{shape.fill}">'
                         f'{escape(shape.text)}</text>')

    lines.append('</svg>')

    with open(file_path, 'w', encoding='utf-8') as file:
        file.write("\n".join(lines))
