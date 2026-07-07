import pytest
from datetime import UTC, datetime

from app.models.document import (
    BoundingBox,
    Document,
    DocumentStatus,
    Page,
    TextBlock,
    TextStyle,
)


def test_document_round_trip_json():
    doc = Document(
        id="test-id",
        name="sample.pdf",
        status=DocumentStatus.UPLOADED,
        file_path="uploads/test/sample.pdf",
        mime_type="application/pdf",
        file_size=1024,
        pages=[
            Page(
                page_number=1,
                width=612,
                height=792,
                blocks=[
                    TextBlock(
                        page_number=1,
                        bbox=BoundingBox(x=10, y=20, width=100, height=30),
                        reading_order=0,
                        original_text="Hello world",
                        style=TextStyle(font_size=12),
                    )
                ],
            )
        ],
        created_at=datetime(2026, 1, 1, tzinfo=UTC),
        updated_at=datetime(2026, 1, 1, tzinfo=UTC),
    )
    json_str = doc.model_dump_json()
    restored = Document.model_validate_json(json_str)
    assert restored.id == doc.id
    assert restored.pages[0].blocks[0].original_text == "Hello world"


def test_text_block_discriminator():
    block = TextBlock(
        page_number=1,
        bbox=BoundingBox(x=0, y=0, width=10, height=10),
        reading_order=0,
        original_text="Test",
    )
    assert block.type == "text"
