"""
ingest/models.py — Dataclasses dùng chung trong toàn bộ ingest pipeline.
Chỉ import stdlib + ingest.config — không import module nào khác trong ingest/.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List


@dataclass
class ParsedDocument:
    """Kết quả parse của một file bởi Docling."""
    file_path:  str                         # đường dẫn tuyệt đối tới file
    file_name:  str                         # tên file
    file_hash:  str                         # hash của file
    doc_type:   str                        # pdf | docx | pptx | html
    metadata:   Dict[str, Any]            # title, author, total_pages ...
    sections:   List[Dict[str, Any]]      # [{section_id, label, text, page, level}]
    tables:     List[Dict[str, Any]]      # [{table_id, markdown, page, caption}]
    images:     List[Dict[str, Any]]      # [{image_id, page, caption, analysis_markdown, path}]
    formulas:   List[Dict[str, Any]]      # [{formula_id, latex_string, page, is_decoded, self_ref}] 
    raw_blocks: List[Dict[str, Any]]      # [{text, page, section_id, block_type[text|table|formula], id}]


@dataclass
class Chunk:
    """Đơn vị vector hóa — metadata đầy đủ để query layer dùng."""
    text:          str              # nội dung chunk
    chunk_id:      str              # id của chunk
    source_file:   str              # tên file
    file_hash:     str              # hash của file
    page:          int              # số trang
    section_label: str              # nhãn section
    chunk_index:   int              # index của chunk
    total_chunks:  int              # tổng số chunk
    has_table:     bool             # có table không
    table_refs:    List[str]        # danh sách table id
    image_refs:    List[str]        # danh sách image id
    has_image:     bool             # có image không
    has_formula:   bool             # có formula không
    formula_refs:  List[str]        # danh sách formula id
    doc_type:      str              # loại tài liệu
    title:         str              # tiêu đề tài liệu
    language:      str    # vi | en | unknown
    workspace_id:  str = "default"  # namespace logic của workspace
    visual_assets: List[Dict[str, Any]] = field(default_factory=list)  # [{type,id,path,page}]
    visual_refs: List[Dict[str, Any]] = field(default_factory=list)     # [{type,id,self_ref,page,path}]
    table_markdowns: Dict[str, str] = field(default_factory=dict)       # table_id -> markdown gốc
    formula_latex: Dict[str, str] = field(default_factory=dict)         # formula_id -> LaTeX
