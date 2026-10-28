from copy import deepcopy
from io import BytesIO
from pathlib import Path
import sys

from docx import Document
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.text.paragraph import Paragraph


def paragraph_text(element, parent):
    return Paragraph(element, parent).text.strip()


def add_field_refresh(document):
    settings = document.settings.element
    update = settings.find(qn("w:updateFields"))
    if update is None:
        update = OxmlElement("w:updateFields")
        settings.append(update)
    update.set(qn("w:val"), "true")


def main():
    if len(sys.argv) != 2:
        raise SystemExit("Usage: insert_chapter3_into_report.py <path-to-baocaodoan.docx>")

    original_path = Path(sys.argv[1])
    output_path = original_path.with_name("baocaodoan_co_chuong3.docx")
    chapter_path = Path(__file__).resolve().parents[1] / "docs" / "Chuong_3_UniXcoder.docx"
    original = Document(original_path)
    chapter = Document(chapter_path)

    conclusion_anchor = None
    appendix_anchor = None
    for paragraph in original.paragraphs:
        text = paragraph.text.strip()
        if text == "Kết luận" and conclusion_anchor is None:
            conclusion_anchor = paragraph._p
        if text == "Phụ lục":
            appendix_anchor = paragraph._p
    if conclusion_anchor is None:
        raise RuntimeError("Cannot find the main Kết luận heading in the report.")
    if appendix_anchor is None:
        raise RuntimeError("Cannot find the Phụ lục heading in the report.")

    chapter_body = chapter._element.body
    source_nodes = list(chapter_body.iterchildren())
    reference_section = False
    caption_labels = iter([
        "B?ng 3.1. C?u h?nh ph?n c?ng th?c nghi?m",
        "B?ng 3.2. Ph?n m?m v? th? vi?n s? d?ng",
        "B?ng 3.3. Ph?n b? d? li?u Devign",
        "B?ng 3.4. Tham s? fine-tuning UniXcoder",
        "B?ng 3.5. K?t qu? so s?nh tr?n t?p test",
        "B?ng 3.6. Ma tr?n nh?m l?n c?a UniXcoder",
    ])
    inserted_tables = 0

    for source_node in source_nodes:
        if source_node.tag == qn("w:p"):
            text = paragraph_text(source_node, chapter)
            if text == "Tài liệu tham khảo của chương":
                reference_section = True
            if reference_section:
                continue

            cloned = deepcopy(source_node)
            cloned_paragraph = Paragraph(cloned, original)
            if text.startswith("CHƯƠNG 3."):
                cloned_paragraph.style = original.styles["Heading 1"]
                cloned_paragraph.paragraph_format.page_break_before = True
                cloned_paragraph.alignment = 1
            elif text.startswith("Hình 3."):
                try:
                    cloned_paragraph.style = original.styles["Caption"]
                except KeyError:
                    pass
            elif text == "Tài liệu tham khảo":
                continue

            # Align citations in Chapter 3 with the bibliography already in the report.
            if "checkpoint demo hiện có" in text or "checkpoint hiện có được mô tả" in text:
                for run in cloned_paragraph.runs:
                    run.text = run.text.replace("[4]", "[9]")
            if "Devign trong benchmark CodeXGLUE cho nhiệm vụ" in text:
                for run in cloned_paragraph.runs:
                    run.text = run.text.replace("[2], [3]", "[3], [4]")

            # Keep the report's existing body typography and spacing.
            if cloned_paragraph.style.name == "Normal":
                cloned_paragraph.paragraph_format.line_spacing = 1.3

            # Rebind embedded images to the destination document package.
            for blip in cloned.iter(qn("a:blip")):
                old_rid = blip.get(qn("r:embed"))
                if not old_rid:
                    continue
                image_part = chapter.part.related_parts[old_rid]
                new_rid, _ = original.part.get_or_add_image(BytesIO(image_part.blob))
                blip.set(qn("r:embed"), new_rid)

            conclusion_anchor.addprevious(cloned)
        elif source_node.tag == qn("w:tbl") and not reference_section:
            cloned = deepcopy(source_node)
            table = original.add_table(rows=0, cols=1) if False else None
            # Copy the table XML after adding a caption; the source table's style
            # and cell formatting are preserved by the cloned WordprocessingML.
            label = next(caption_labels, None)
            if label:
                caption = original.add_paragraph(label, style="Caption")
                caption.alignment = 1
                conclusion_anchor.addprevious(caption._p)
            for blip in cloned.iter(qn("a:blip")):
                old_rid = blip.get(qn("r:embed"))
                if old_rid:
                    image_part = chapter.part.related_parts[old_rid]
                    new_rid, _ = original.part.get_or_add_image(BytesIO(image_part.blob))
                    blip.set(qn("r:embed"), new_rid)
            conclusion_anchor.addprevious(cloned)
            inserted_tables += 1

    # Add the checkpoint model card to the report's existing bibliography.
    reference = original.add_paragraph(
        "[9] VulnScope, “UniXcoder Devign Checkpoint Model Card,” cấu hình demo và phạm vi sử dụng checkpoint. "
        "Available: https://huggingface.co/vinh204/vulnscope-unixcoder-devign.",
        style="Normal",
    )
    appendix_anchor.addprevious(reference._p)

    add_field_refresh(original)
    original.save(output_path)
    print(f"Saved report with Chapter 3: {output_path.name}")
    print(f"Chapter 3 tables inserted: {inserted_tables}")
    print(f"Chapter 3 images inserted: {sum(1 for rel in original.part.rels.values() if 'image' in rel.reltype)}")


if __name__ == "__main__":
    main()
