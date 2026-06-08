# Python & FastAPI Standards for DocuBot

## Function structure
def function_name(param: type, param2: type) -> return_type:
    """
    What this function does.
    Args: param - description. param2 - description.
    Returns: what it returns.
    Raises: ExceptionType - when it raises.
    """
    # implementation

## Error handling
try:
    result = risky_operation()
except SpecificError as e:
    raise HTTPException(status_code=400, detail=f"Descriptive message: {e}")
except Exception as e:
    logger.error(f"Unexpected error in function_name: {e}")
    raise HTTPException(status_code=500, detail="Internal server error")

## FastAPI endpoint structure
@router.post("/endpoint", response_model=ResponseSchema, status_code=201)
async def endpoint_name(request: RequestSchema, db = Depends(get_db)):
    """Endpoint docstring."""
    # validate → process → return

## File size validation
MAX_FILE_SIZE = int(os.getenv("MAX_FILE_SIZE_MB", 20)) * 1024 * 1024
if file.size > MAX_FILE_SIZE:
    raise HTTPException(status_code=413, detail="File too large")

## Allowed file types
ALLOWED_TYPES = {"application/pdf", "text/plain"}
if file.content_type not in ALLOWED_TYPES:
    raise HTTPException(status_code=415, detail="Unsupported file type")