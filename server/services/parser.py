from pypdf import PdfReader
from pathlib import Path
from typing import Any, Dict, List, Optional,Tuple
import re

def decode_text_with_fallback(raw: bytes) -> str:
    for enc in ['utf-8', 'gbk']:
        try:
            return raw.decode(enc)
        except UnicodeDecodeError:
            continue
    return raw.decode('utf8', errors='ignore')

def normalize_text(text: str) -> str:
    text=text.replace('\r\n', '\n').replace('\r', '\n')
    return text.strip()

def split_paragraphs(text: str) -> List[str]:
    parts=re.split(r"\n\s*\n+", text)
    return [p.strip() for p in parts if p.strip()]

def chunk_text(text: str, chunk_size: int = 600, overlap: int = 80,
               page_no:Optional[int]=None,start_index:int=0,
               min_chuk_chars:int=20) -> List[Dict[str, Any]]:
    if chunk_size <=0:
        raise ValueError("chunk_size must > 0")
    if overlap<0 or overlap>=chunk_size:
        raise ValueError("overlap must >=0 and < chunk_size")
    
    text=normalize_text(text)
    if not text:
        return []
    
    paragraphs=split_paragraphs(text)
    if not paragraphs:
        paragraphs=[text]
    
    chunks:List[Dict[str, Any]]=[]
    idx=start_index
    step=chunk_size-overlap

    for para in paragraphs:
        para=para.strip()
        if not para:
            continue

        if len(para)<=chunk_size:
            if len(para)>=min_chuk_chars:
                chunks.append(
                    {
                        "chunk_index":idx,
                        "content":para,
                        "token_count": len(para), 
                        "page_no": page_no,
                        "tags": None,
                    }
                )
                idx+=1
            continue
        
        start=0
        while start<len(para):
            piece=para[start:start+chunk_size].strip()
            if len(piece)>=min_chuk_chars:
                chunks.append(
                    {
                        "chunk_index":idx,
                        "content":piece,
                        "token_count": len(piece), 
                        "page_no": page_no,
                        "tags": None,
                    }
                )
                idx+=1  
            start+=step
    return chunks
    

def parse_txt(file_path: str, chunk_size: int = 600, 
              overlap: int = 80) -> List[Dict[str, Any]]:
    p = Path(file_path)
    raw = p.read_bytes()
    text = decode_text_with_fallback(raw)
    chunks = chunk_text(text, chunk_size=chunk_size, overlap=overlap, page_no=None, start_index=0)
    if not chunks:
        raise ValueError("txt 文件为空或无可解析文本")
    return chunks

def parse_pdf(file_path: str, chunk_size: int = 600, overlap: int = 80) -> List[Dict[str, Any]]:
    p = Path(file_path)
    reader = PdfReader(str(p))

    chunks: List[Dict[str, Any]] = []
    next_index = 0

    for i, page in enumerate(reader.pages, start=1):
        page_text = page.extract_text() or ""
        page_text = normalize_text(page_text)
        if not page_text:
            continue

        page_chunks = chunk_text(
            page_text,
            chunk_size=chunk_size,
            overlap=overlap,
            page_no=i,
            start_index=next_index,
        )
        chunks.extend(page_chunks)
        next_index += len(page_chunks)

    if not chunks:
        raise ValueError("pdf 文件为空或无法提取文本")
    return chunks

def parse_document(file_path: str, chunk_size: int = 600, overlap: int = 80) -> Tuple[str, List[Dict[str, Any]]]:
    suffix = Path(file_path).suffix.lower()

    if suffix == ".txt":
        return "txt", parse_txt(file_path, chunk_size=chunk_size, overlap=overlap)

    if suffix == ".pdf":
        return "pdf", parse_pdf(file_path, chunk_size=chunk_size, overlap=overlap)

    raise ValueError(f"暂不支持的文件类型: {suffix}")
