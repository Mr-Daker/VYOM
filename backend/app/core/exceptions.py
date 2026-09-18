from fastapi import Request
from fastapi.responses import JSONResponse

class AppException(Exception):
    def __init__(self, code: str, message: str, status_code: int = 400, details: dict = None):
        self.code = code
        self.message = message
        self.status_code = status_code
        self.details = details or {}

def app_exception_handler(request: Request, exc: AppException):
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "error": {
                "code": exc.code,
                "message": exc.message,
                "details": exc.details
            }
        }
    )

class CurriculumDocumentNotFoundError(AppException):
    def __init__(self, doc_id: str):
        super().__init__("CURRICULUM_DOCUMENT_NOT_FOUND", f"Curriculum document not found: {doc_id}", 404)

class CurriculumDocumentDuplicateError(AppException):
    def __init__(self, existing_id: str):
        super().__init__("CURRICULUM_DOCUMENT_DUPLICATE", "Duplicate curriculum document exists.", 409, details={"existing_document_id": existing_id})

class CurriculumDocumentNotReadyError(AppException):
    def __init__(self, doc_id: str):
        super().__init__("CURRICULUM_DOCUMENT_NOT_READY", f"Document not ready: {doc_id}", 409)

class CurriculumContentEmptyError(AppException):
    def __init__(self):
        super().__init__("CURRICULUM_CONTENT_EMPTY", "Content is empty.", 400)

class CurriculumContentTooLargeError(AppException):
    def __init__(self):
        super().__init__("CURRICULUM_CONTENT_TOO_LARGE", "Content exceeds max size.", 413)

class CurriculumUnsupportedFormatError(AppException):
    def __init__(self):
        super().__init__("CURRICULUM_UNSUPPORTED_FORMAT", "Unsupported document format.", 415)

class CurriculumIngestionFailedError(AppException):
    def __init__(self):
        super().__init__("CURRICULUM_INGESTION_FAILED", "Ingestion failed.", 500)

class CurriculumEmbeddingFailedError(AppException):
    def __init__(self, message: str = "Embedding generation failed.", details: dict | None = None):
        super().__init__("CURRICULUM_EMBEDDING_FAILED", message, 503, details=details)

class CurriculumChunkNotFoundError(AppException):
    def __init__(self):
        super().__init__("CURRICULUM_CHUNK_NOT_FOUND", "Chunk not found.", 404)

class CurriculumMappingInvalidError(AppException):
    def __init__(self):
        super().__init__("CURRICULUM_MAPPING_INVALID", "Mapping request invalid.", 400)

class RetrievalFailedError(AppException):
    def __init__(self):
        super().__init__("RETRIEVAL_FAILED", "Retrieval failed.", 500)

class EmbeddingDimensionMismatchError(AppException):
    def __init__(self, details: dict | None = None):
        super().__init__("EMBEDDING_DIMENSION_MISMATCH", "Dimension mismatch.", 400, details=details)
