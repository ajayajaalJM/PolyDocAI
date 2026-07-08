from app.models.document import BoundingBox, Document, Page, TextBlock, TextStyle
from app.providers.rendering.base import RenderOptions
from app.services.rendering.semantic_html import SemanticHTMLRenderer


def test_semantic_html_positions_blocks(tmp_path):
    block = TextBlock(
        page_number=1,
        bbox=BoundingBox(x=50, y=100, width=200, height=30),
        reading_order=0,
        original_text="Hello world",
        translated_text="Hola mundo",
        style=TextStyle(font_size=14, alignment="left"),
        layout_type="paragraph",
    )
    doc = Document(
        name="sample.pdf",
        pages=[Page(page_number=1, width=600, height=800, blocks=[block])],
    )
    renderer = SemanticHTMLRenderer(tmp_path)
    result = renderer.render(doc, RenderOptions(use_translated=True, storage_root=tmp_path))
    html = result.content.decode("utf-8")
    assert "Hola mundo" in html
    assert "left:50" in html
    assert "top:100" in html
    assert "data-block-id" in html
