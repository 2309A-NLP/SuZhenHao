import sys
import os
sys.path.insert(0, '.')

print("=" * 60)
print("Local Module Tests (No Network Required)")
print("=" * 60)

print("\n[1] Testing config import...")
from config import DEEPSEEK_API_KEY, PDF_FILES, CHUNK_SIZE
print(f"  - config: OK")
print(f"  - API_KEY configured: {bool(DEEPSEEK_API_KEY)}")
print(f"  - PDF_FILES: {PDF_FILES}")

print("\n[2] Testing query_processor import...")
from query_processor import QueryProcessor
print("  - query_processor: OK")

print("\n[3] Testing document_loader import...")
from document_loader import DocumentLoader, TextChunker, prepare_documents
print("  - document_loader: OK")

print("\n[4] Testing QueryProcessor functionality...")
processor = QueryProcessor()
test_query = "公司2023年的财务状况如何？"
result = processor.process_query(test_query)
print(f"  - Query: {test_query}")
print(f"  - Intent: {result['intent']}")
print(f"  - Sub-queries: {result['sub_queries']}")
print(f"  - Entities: {result['entities']}")

print("\n[5] Testing TextChunker functionality...")
chunker = TextChunker(chunk_size=100, overlap=20)
test_text = "这是测试文本。" * 20
chunks = chunker.chunk_text(test_text, page_num=1)
print(f"  - Input: {len(test_text)} characters")
print(f"  - Output: {len(chunks)} chunks")
if chunks:
    print(f"  - Sample chunk: {chunks[0]['content'][:30]}...")

print("\n[6] Testing DocumentLoader initialization...")
loader = DocumentLoader(os.path.join("data", PDF_FILES[0]))
print(f"  - Loader created for: {loader.pdf_path}")
print(f"  - File exists check: {__import__('os').path.exists(loader.pdf_path)}")

print("\n" + "=" * 60)
print("All Local Tests Passed!")
print("=" * 60)