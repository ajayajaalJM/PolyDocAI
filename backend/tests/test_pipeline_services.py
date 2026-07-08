from app.models.document import DOM_SCHEMA_VERSION, Document, InlineRun, OCRBlockData, TextBlock, BoundingBox
from app.services.document_model.service import DocumentModelService
from app.services.vision.service import VisionService
from app.modules.layout.doclayout_service import LayoutElementType, LayoutPageResult, LayoutRegion


def test_document_schema_version_default():
    doc = Document(name="test.pdf")
    assert doc.schema_version == DOM_SCHEMA_VERSION


def test_document_model_service_enriches_inline_runs():
    block = TextBlock(
        page_number=1,
        bbox=BoundingBox(x=0, y=0, width=100, height=20),
        reading_order=0,
        original_text="Hello",
        inline_runs=[InlineRun(text="Hello")],
    )
    from app.models.document import Page

    doc = Document(name="t.pdf", pages=[Page(page_number=1, width=100, height=100, blocks=[block])])
    svc = DocumentModelService()
    result = svc.apply_pages(doc, doc.pages)
    assert result.success
    assert result.data is not None
    assert result.data.pages[0].blocks[0].inline_runs


def test_vision_service_builds_sections():
    layout = LayoutPageResult(
        page_number=1,
        width=600,
        height=800,
        regions=[
            LayoutRegion(LayoutElementType.HEADING, 0.9, (50, 50, 500, 40)),
            LayoutRegion(LayoutElementType.PARAGRAPH, 0.8, (50, 100, 500, 200)),
        ],
    )
    result = VisionService().analyze_page(layout, 600)
    assert result.success
    assert result.data is not None
    assert len(result.data.enrichments) == 2
    assert len(result.data.sections) >= 1
