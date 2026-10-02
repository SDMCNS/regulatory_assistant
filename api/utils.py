import time
import json
import sqlite3
import requests
import numpy as np
from typing import List, Dict, Any, Optional
from fastapi import HTTPException

from ingestion.core.config import settings

def log_debug_info(event: str, data: Any):
    log_file = settings.LOGS_DIR / "llm_debug.log"
    try:
        with open(log_file, "a", encoding="utf-8") as f:
            f.write(f"--- {time.strftime('%Y-%m-%d %H:%M:%S')} | {event} ---\n")
            if isinstance(data, (dict, list)):
                f.write(json.dumps(data, indent=2))
            else:
                f.write(str(data))
            f.write("\n\n")
    except Exception as e:
        print(f"Failed to write to debug log: {e}")

def call_lm_studio_chat(
    messages: List[dict],
    schema: Optional[dict] = None,
    max_tokens: int = 4096,
    temperature: float = 0.3
) -> str:
    messages_payload = [dict(m) for m in messages]
    if schema:
        schema_prompt = f"\n\nYou MUST return ONLY a JSON object that adheres to the following JSON schema:\n{json.dumps(schema, indent=2)}"
        if messages_payload and messages_payload[0]["role"] == "system":
            messages_payload[0]["content"] += schema_prompt
        else:
            messages_payload.insert(0, {"role": "system", "content": schema_prompt})

    payload = {
        "model": settings.LLM_MODEL_NAME,
        "messages": messages_payload,
        "temperature": temperature,
        "max_tokens": max_tokens,
        "stream": False
    }
    
    if schema:
        payload["response_format"] = {
            "type": "json_schema",
            "json_schema": {
                "name": "response_schema",
                "schema": schema
            }
        }
        
    try:
        log_debug_info("RAW LLM PAYLOAD", payload)
        response = requests.post(f"{settings.LM_STUDIO_BASE_URL}/chat/completions", json=payload, timeout=120)
        
        # If response_format was rejected by LM Studio model, retry cleanly with prompt-only JSON
        if response.status_code == 400 and schema and "response_format" in payload:
            log_debug_info("LLM RETRY WITHOUT RESPONSE_FORMAT", response.text)
            del payload["response_format"]
            response = requests.post(f"{settings.LM_STUDIO_BASE_URL}/chat/completions", json=payload, timeout=120)

        response.raise_for_status()
        data = response.json()
        log_debug_info("RAW LLM RESPONSE", data)
        msg = data.get("choices", [{}])[0].get("message", {})
        content = (msg.get("content") or "").strip()
        if not content and msg.get("reasoning_content"):
            content = (msg.get("reasoning_content") or "").strip()
        return content
    except requests.exceptions.HTTPError as e:
        log_debug_info("LLM HTTP ERROR", getattr(e.response, "text", str(e)))
        print(f"HTTPError from LM Studio: {getattr(e.response, 'text', str(e))}")
        raise HTTPException(status_code=500, detail=f"LLM API Error: {getattr(e.response, 'text', str(e))}")
    except Exception as e:
        log_debug_info("LLM EXCEPTION", str(e))
        raise HTTPException(status_code=500, detail=f"LLM call failed: {str(e)}")

def call_gemini_api(
    messages: List[dict],
    api_key: str,
    model: str = "gemini-3.5-flash",
    schema: Optional[dict] = None,
    max_tokens: int = 4096,
    temperature: float = 0.2
) -> str:
    """
    Direct REST API invocation of Google Gemini with automated retries on transient
    503/429 spikes and intelligent fallback to high-availability Flash models.
    """
    clean_key = (api_key or "").strip()
    clean_model = (model or "gemini-3.5-flash").strip()

    contents = []
    system_instruction_text = None
    for msg in messages:
        role = msg.get("role", "user")
        content = msg.get("content", "")
        if role == "system":
            if system_instruction_text:
                system_instruction_text += "\n\n" + content
            else:
                system_instruction_text = content
        elif role == "user":
            contents.append({"role": "user", "parts": [{"text": content}]})
        elif role in ("assistant", "model"):
            contents.append({"role": "model", "parts": [{"text": content}]})

    generation_config: Dict[str, Any] = {
        "temperature": temperature,
        "maxOutputTokens": max_tokens
    }

    if schema:
        generation_config["responseMimeType"] = "application/json"
        schema_text = f"\n\nYou MUST return valid JSON conforming to this schema:\n{json.dumps(schema, indent=2)}"
        if system_instruction_text:
            system_instruction_text += schema_text
        else:
            system_instruction_text = schema_text

    payload: Dict[str, Any] = {
        "contents": contents,
        "generationConfig": generation_config
    }

    if system_instruction_text:
        payload["systemInstruction"] = {
            "parts": [{"text": system_instruction_text}]
        }

    headers = {"Content-Type": "application/json"}

    # Ordered list of models to try if the primary encounters high demand (503) or rate limits (429)
    candidate_models = [clean_model]
    for alt in ["gemini-3.5-flash", "gemini-3.5-flash-lite", "gemini-3.6-flash"]:
        if alt not in candidate_models:
            candidate_models.append(alt)

    last_error_msg = None
    for cur_model in candidate_models:
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{cur_model}:generateContent?key={clean_key}"
        
        # Retry with exponential backoff on transient spikes
        for attempt in range(3):
            try:
                log_debug_info("GEMINI_REQUEST", {
                    "model": cur_model,
                    "attempt": attempt + 1,
                    "num_messages": len(messages)
                })
                response = requests.post(url, headers=headers, json=payload, timeout=60)
                
                if response.status_code == 200:
                    data = response.json()
                    log_debug_info("GEMINI_RESPONSE", {"model": cur_model, "status": "ok"})
                    candidates = data.get("candidates", [])
                    if not candidates:
                        raise HTTPException(status_code=500, detail=f"Gemini API returned no candidates from {cur_model}.")
                    
                    parts = candidates[0].get("content", {}).get("parts", [])
                    text_parts = [p.get("text", "") for p in parts if p.get("text")]
                    if not text_parts:
                        raise HTTPException(status_code=500, detail=f"Gemini ({cur_model}) candidate response contained no text parts.")
                    
                    return "".join(text_parts)
                
                # Check for transient demand spike (503) or rate limit (429)
                if response.status_code in (503, 429):
                    log_debug_info("GEMINI_TRANSIENT_SPIKE", {
                        "model": cur_model,
                        "status": response.status_code,
                        "attempt": attempt + 1
                    })
                    time.sleep(1.0 * (attempt + 1))
                    continue
                
                # Non-transient HTTP error (e.g. 404 deprecated model) -> break to try next candidate model
                err_text = response.text
                log_debug_info("GEMINI_HTTP_ERROR", {
                    "model": cur_model,
                    "status": response.status_code,
                    "error": err_text[:300]
                })
                last_error_msg = f"Gemini API error ({response.status_code}) on {cur_model}: {err_text}"
                break

            except requests.exceptions.RequestException as req_err:
                log_debug_info("GEMINI_REQUEST_EXCEPTION", {
                    "model": cur_model,
                    "error": str(req_err)
                })
                time.sleep(1.0 * (attempt + 1))
                last_error_msg = str(req_err)

    # If all candidate models failed
    final_err = last_error_msg or "All candidate Gemini models failed to respond."
    log_debug_info("GEMINI_ALL_CANDIDATES_FAILED", {"error": final_err})
    raise HTTPException(status_code=500, detail=final_err)

def test_gemini_connection(api_key: str, model: str = "gemini-3.5-flash") -> Dict[str, Any]:
    """Tests connectivity to Google Gemini API with a probe."""
    import os
    clean_key = (api_key or os.environ.get("GEMINI_API_KEY") or "").strip()
    if not clean_key:
        return {"status": "error", "success": False, "message": "Gemini API key is empty."}
    
    clean_model = (model or "gemini-3.5-flash").strip()
    candidate_models = [clean_model]
    for alt in ["gemini-3.5-flash", "gemini-3.5-flash-lite", "gemini-3.8-flash"]:
        if alt not in candidate_models:
            candidate_models.append(alt)

    payload = {
        "contents": [{"role": "user", "parts": [{"text": "Respond with OK."}]}],
        "generationConfig": {"maxOutputTokens": 2048}
    }

    last_msg = ""
    last_status = 500
    for cur_m in candidate_models:
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{cur_m}:generateContent?key={clean_key}"
        for attempt in range(2):
            try:
                r = requests.post(url, json=payload, timeout=20)
                if r.status_code == 200:
                    model_note = f"Successfully connected to Google Gemini Cloud ({cur_m})."
                    if cur_m != clean_model:
                        model_note += f" (Note: {clean_model} had transient traffic, verified via {cur_m})."
                    return {
                        "status": "connected",
                        "success": True,
                        "model": cur_m,
                        "message": model_note
                    }
                last_status = r.status_code
                try:
                    last_msg = r.json().get("error", {}).get("message", r.text)
                except Exception:
                    last_msg = r.text
                if r.status_code in (503, 429):
                    time.sleep(1.0)
                    continue
                break
            except Exception as e:
                last_msg = str(e)
                time.sleep(1.0)

    return {
        "status": "error",
        "success": False,
        "message": f"Gemini connection failed ({last_status}): {last_msg}"
    }

def call_unified_chat(
    messages: List[dict],
    schema: Optional[dict] = None,
    max_tokens: int = 4096,
    temperature: float = 0.2,
    provider: str = "local",
    gemini_api_key: Optional[str] = None,
    gemini_model: Optional[str] = None
) -> str:
    """
    Unified LLM router that directs calls to either Google Gemini Cloud or Local LM Studio.
    """
    import os
    active_key = (gemini_api_key or os.environ.get("GEMINI_API_KEY") or "").strip()
    if provider == "gemini" and active_key:
        try:
            return call_gemini_api(
                messages=messages,
                api_key=active_key,
                model=gemini_model or "gemini-3.5-flash",
                schema=schema,
                max_tokens=max_tokens,
                temperature=temperature
            )
        except Exception as e:
            print(f"Warning: Gemini API call failed: {e}. Falling back to LM Studio...")
            log_debug_info("GEMINI_FALLBACK_TRIGGERED", {"error": str(e)})
            return call_lm_studio_chat(messages, schema, max_tokens, temperature)
    return call_lm_studio_chat(messages, schema, max_tokens, temperature)

def cosine_similarity(v1, v2):
    if not v1 or not v2:
        return 0.0
    a, b = np.array(v1), np.array(v2)
    norm_a, norm_b = np.linalg.norm(a), np.linalg.norm(b)
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return float(np.dot(a, b) / (norm_a * norm_b))

def get_document_metadata(doc_id: str) -> dict:
    db_path = settings.DATA_DIR / "regulations" / "sqlite" / "chunks.db"
    if not db_path.exists():
        return {}
    with sqlite3.connect(db_path) as conn:
        c = conn.cursor()
        c.execute("SELECT metadata_json, title FROM documents WHERE document_id = ?", (doc_id,))
        row = c.fetchone()
        if not row:
            return {}
        meta_json, doc_title = row
        meta_dict = json.loads(meta_json) if meta_json else {}
        
        if not doc_title or str(doc_title).upper().startswith("ANNEX") or str(doc_title).upper().startswith("APPENDIX"):
            prefix = doc_id.split(".")[0] + "%"
            c.execute('''
                SELECT title FROM documents 
                WHERE document_id <= ? AND document_id LIKE ? 
                  AND title NOT LIKE 'ANNEX%' 
                  AND title NOT LIKE 'APPENDIX%'
                ORDER BY document_id DESC LIMIT 1
            ''', (doc_id, prefix))
            p_row = c.fetchone()
            if p_row and p_row[0]:
                doc_title = p_row[0]
                
        if doc_title:
            meta_dict["document_title"] = doc_title
            
        return meta_dict
