#!/usr/bin/env bash
set -euo pipefail

# Check for lexical model and tfidf vectorizer in /app/models
MISSING=0
if [ -z "${LEXICAL_FASTTEXT_PATH:-}" ]; then
  LEX_PATH="fasttext_lexical_model.model"
else
  LEX_PATH="${LEXICAL_FASTTEXT_PATH}"
fi

if [ -z "${TFIDF_VECTORIZER_PATH:-}" ]; then
  TF_PATH="tfidf_vectorizer.joblib"
else
  TF_PATH="${TFIDF_VECTORIZER_PATH}"
fi

if [ ! -f "/app/${LEX_PATH}" ] && [ ! -f "/app/models/${LEX_PATH}" ]; then
  echo "⚠️  Lexical FastText model not found at /app/${LEX_PATH} or /app/models/${LEX_PATH}." >&2
  echo "    The server will start, but lexical features will be disabled." >&2
  export SKIP_LEXICAL=1
  MISSING=1
fi

if [ ! -f "/app/${TF_PATH}" ] && [ ! -f "/app/models/${TF_PATH}" ]; then
  echo "⚠️  TF-IDF vectorizer not found at /app/${TF_PATH} or /app/models/${TF_PATH}." >&2
  echo "    The server will start, but lexical features will be disabled." >&2
  export SKIP_LEXICAL=1
  MISSING=1
fi

# Check LLM model
if [ -z "${LLM_MODEL_PATH:-}" ]; then
  LLM_PATH="./models/your_model.gguf"
else
  LLM_PATH="${LLM_MODEL_PATH}"
fi

if [ ! -f "/app/${LLM_PATH}" ] && [ ! -f "/app/models/$(basename ${LLM_PATH})" ]; then
  echo "⚠️  LLM model not found at /app/${LLM_PATH} or /app/models/$(basename ${LLM_PATH})." >&2
  echo "    The server will start, but LLM features will be disabled (SKIP_LLM=1)." >&2
  export SKIP_LLM=1
  MISSING=1
fi

echo "Starting uvicorn (host 0.0.0.0:8000)..."
exec python -m uvicorn Text2SQL_Agent:app --host 0.0.0.0 --port 8000 --reload
