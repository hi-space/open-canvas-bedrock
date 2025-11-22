# Open Canvas Agents - FastAPI with AWS Bedrock

This is the Python FastAPI implementation of the Open Canvas agents, using AWS Bedrock for LLM integration.

## Setup

1. Install dependencies:
```bash
pip install -r requirements.txt
```

2. Set environment variables:
```bash
export AWS_REGION=us-east-1
export AWS_ACCESS_KEY_ID=your_access_key
export AWS_SECRET_ACCESS_KEY=your_secret_key
```

3. Run the FastAPI server:
```bash
python main.py
```

Or using uvicorn:
```bash
uvicorn main:app --host 0.0.0.0 --port 8000
```

## API Endpoints

- `GET /health` - Health check
- `POST /api/agent/run` - Run Open Canvas agent
- `POST /api/reflection/reflect` - Run reflection agent
- `POST /api/thread-title/generate` - Generate thread title
- `POST /api/summarizer/summarize` - Summarize conversation
- `POST /api/web-search/search` - Perform web search

## Model Configuration

Only AWS Bedrock models are supported. Model names must be prefixed with `bedrock/`, for example:
- `bedrock/claude-3-5-sonnet-20240620`
- `bedrock/claude-3-5-haiku-20241022`
- `bedrock/claude-3-opus-20240229`

See `agents/models.py` for the full list of supported models.

## Differences from TypeScript Version

- All LLM providers except AWS Bedrock have been removed
- TypeScript agents have been converted to Python using LangGraph
- FastAPI is used instead of LangGraph TypeScript server
- Supabase integration has been removed (simplified store implementation)

